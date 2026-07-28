"""SiliconFlow native reranker using their /v1/rerank API directly via HTTP."""
import logging
import os
from typing import Any, Dict, List, Optional

import httpx

from mem0.reranker.base import BaseReranker

logger = logging.getLogger(__name__)


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
        self._client = httpx.Client(timeout=timeout)

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

        payload = {
            "model": self.model,
            "query": query,
            "documents": doc_texts,
            "top_n": top_k or self.config.top_k or len(documents),
            "return_documents": getattr(self.config, "return_documents", False),
            "max_chunks_per_doc": getattr(self.config, "max_chunks_per_doc", None),
        }
        payload = {k: v for k, v in payload.items() if v is not None}

        try:
            response = self._client.post(
                f"{self.base_url.rstrip('/')}/rerank",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            )
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            logger.warning("SiliconFlow reranking failed: %s", e)
            for doc in documents:
                doc["rerank_score"] = 0.0
            final_top_k = top_k or getattr(self.config, "top_k", None)
            return documents[:final_top_k] if final_top_k else documents

        reranked_docs = []
        for result in data.get("results", []):
            idx = result.get("index", 0)
            if idx < len(documents):
                original_doc = documents[idx].copy()
                original_doc["rerank_score"] = result.get("relevance_score", 0.0)
                reranked_docs.append(original_doc)

        reranked_docs.sort(key=lambda x: x["rerank_score"], reverse=True)
        if top_k:
            reranked_docs = reranked_docs[:top_k]
        elif self.config.top_k:
            reranked_docs = reranked_docs[:self.config.top_k]

        return reranked_docs
