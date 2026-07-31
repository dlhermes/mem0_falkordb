import json
"""SiliconFlow native reranker using their /v1/rerank API directly via HTTP."""
import logging
import os
import time
from typing import Any, Dict, List, Optional

import httpx

from mem0.reranker.base import BaseReranker

logger = logging.getLogger(__name__)

# SiliconFlow rerank API 的 query+documents 共享 8K token 上下文限制。
# query 临界点实测约 20000 chars（4000 words），留余量给 documents。
_RERANK_QUERY_MAX_CHARS = 4000
# documents 分批阈值：总字符数超此值时分批请求再合并 top_k。
_RERANK_DOCS_MAX_CHARS = 6000
# 可重试的 HTTP 状态码（429 限流 / 500-503 服务端临时错误）
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503}


class SiliconFlowReranker(BaseReranker):
    """SiliconFlow-native reranker — calls POST /v1/rerank directly."""

    def __init__(self, config):
        self.config = config
        self.api_key = config.api_key or os.getenv("SILICONFLOW_API_KEY")
        if not self.api_key:
            raise ValueError("SiliconFlow API key is required. Pass api_key in config or set SILICONFLOW_API_KEY env var.")
        self.model = config.model or "BAAI/bge-reranker-v2-m3"
        self.base_url = getattr(config, "siliconflow_base_url", None) or os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
        timeout = float(os.environ.get("MEM0_RERANK_TIMEOUT", "60"))
        self._max_retries = int(os.environ.get("MEM0_RERANK_MAX_RETRIES", "3"))
        self._client = httpx.Client(timeout=timeout)
        self._request_delay = float(os.environ.get("MEM0_RERANK_REQUEST_DELAY", "0"))

    def _truncate_query(self, query: str) -> str:
        """截断 query 以避免 SiliconFlow API 的 'Query is too long' 400 错误。"""
        if len(query) <= _RERANK_QUERY_MAX_CHARS:
            return query
        truncated = query[:_RERANK_QUERY_MAX_CHARS]
        logger.info(
            "Rerank query truncated: %d -> %d chars (limit=%d)",
            len(query), len(truncated), _RERANK_QUERY_MAX_CHARS,
        )
        return truncated

    def _chunk_documents(self, doc_texts: List[str]) -> List[List[str]]:
        """当 documents 总字符数超阈值时，分批以避免 query+docs 超 8K token 限制。"""
        total_chars = sum(len(d) for d in doc_texts)
        if total_chars <= _RERANK_DOCS_MAX_CHARS:
            return [doc_texts]
        chunks = []
        current = []
        current_chars = 0
        for doc in doc_texts:
            doc_chars = len(doc)
            if current and current_chars + doc_chars > _RERANK_DOCS_MAX_CHARS:
                chunks.append(current)
                current = []
                current_chars = 0
            current.append(doc)
            current_chars += doc_chars
        if current:
            chunks.append(current)
        logger.info(
            "Rerank documents split into %d batches (total %d chars, limit=%d)",
            len(chunks), total_chars, _RERANK_DOCS_MAX_CHARS,
        )
        return chunks

    def _post_rerank(self, payload: dict) -> dict:
        """发送 rerank 请求，对可重试错误做指数退避重试，400 不重试。"""
        url = f"{self.base_url.rstrip('/')}/rerank"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        last_exc = None
        for attempt in range(1, self._max_retries + 1):
            try:
                response = self._client.post(url, content=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers=headers)
                if response.status_code in _RETRYABLE_STATUS_CODES:
                    last_exc = httpx.HTTPStatusError(
                        f"HTTP {response.status_code}: {response.text[:200]}",
                        request=response.request, response=response,
                    )
                    if attempt < self._max_retries:
                        delay = min(2 ** (attempt - 1), 10)
                        logger.warning(
                            "SiliconFlow rerank got %d (attempt %d/%d), retrying in %ds",
                            response.status_code, attempt, self._max_retries, delay,
                        )
                        time.sleep(delay)
                        continue
                response.raise_for_status()
                return response.json()
            except httpx.TimeoutException as e:
                last_exc = e
                if attempt < self._max_retries:
                    delay = min(2 ** (attempt - 1), 10)
                    logger.warning(
                        "SiliconFlow rerank timeout (attempt %d/%d), retrying in %ds",
                        attempt, self._max_retries, delay,
                    )
                    time.sleep(delay)
                    continue
                raise
            except httpx.HTTPStatusError:
                raise
            except Exception as e:
                last_exc = e
                if attempt < self._max_retries:
                    delay = min(2 ** (attempt - 1), 10)
                    logger.warning(
                        "SiliconFlow rerank error: %s (attempt %d/%d), retrying in %ds",
                        e, attempt, self._max_retries, delay,
                    )
                    time.sleep(delay)
                    continue
                raise
        # 所有重试用尽
        raise last_exc if last_exc else RuntimeError("Rerank failed after all retries")

    def rerank(self, query: str, documents: List[Dict[str, Any]], top_k: int = None) -> List[Dict[str, Any]]:
        if not documents:
            return documents

        doc_texts = []
        for doc in documents:
            if "memory" in doc:
                doc_texts.append(doc["memory"])
            elif "text" in doc:
                doc_texts.append(doc["text"])
            elif "content" in doc:
                doc_texts.append(doc["content"])
            else:
                doc_texts.append(str(doc))

        # 截断 query 以避免 SiliconFlow API 400 "Query is too long"
        truncated_query = self._truncate_query(query)

        # documents 分批
        doc_chunks = self._chunk_documents(doc_texts)
        final_top_k = top_k or getattr(self.config, "top_k", None) or len(documents)

        all_reranked = []
        for chunk_idx, chunk in enumerate(doc_chunks):
            payload = {
                "model": self.model,
                "query": truncated_query,
                "documents": chunk,
                "top_n": len(chunk),  # 每批返回全部，最后全局取 top_k
                "return_documents": getattr(self.config, "return_documents", False),
                "max_chunks_per_doc": getattr(self.config, "max_chunks_per_doc", None),
            }
            payload = {k: v for k, v in payload.items() if v is not None}

            # 请求间隔（避免触发限流）
            if chunk_idx > 0 and self._request_delay > 0:
                time.sleep(self._request_delay)
            try:
                data = self._post_rerank(payload)
            except httpx.HTTPStatusError as e:
                resp = getattr(e, "response", None)
                body = resp.text[:300] if resp is not None else "no response body"
                logger.warning(
                    "SiliconFlow reranking failed (batch %d/%d): %s | response: %s",
                    chunk_idx + 1, len(doc_chunks), e, body,
                )
                # 失败的 batch 中所有 doc score=0，保留原始顺序
                for doc in documents[len(all_reranked):len(all_reranked) + len(chunk)]:
                    original_doc = doc.copy()
                    original_doc["rerank_score"] = 0.0
                    all_reranked.append(original_doc)
                continue
            except Exception as e:
                logger.warning(
                    "SiliconFlow reranking error (batch %d/%d): %s",
                    chunk_idx + 1, len(doc_chunks), e,
                )
                for doc in documents[len(all_reranked):len(all_reranked) + len(chunk)]:
                    original_doc = doc.copy()
                    original_doc["rerank_score"] = 0.0
                    all_reranked.append(original_doc)
                continue

            # 将 API 返回的 index 映射回原始 documents（按 chunk 偏移）
            chunk_offset = sum(len(c) for c in doc_chunks[:chunk_idx])
            for result in data.get("results", []):
                idx = result.get("index", 0)
                global_idx = chunk_offset + idx
                if global_idx < len(documents):
                    original_doc = documents[global_idx].copy()
                    original_doc["rerank_score"] = result.get("relevance_score", 0.0)
                    all_reranked.append(original_doc)

        # 全局排序并取 top_k
        all_reranked.sort(key=lambda x: x["rerank_score"], reverse=True)
        if top_k:
            all_reranked = all_reranked[:top_k]
        elif self.config.top_k:
            all_reranked = all_reranked[:self.config.top_k]

        return all_reranked
