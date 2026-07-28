from typing import Optional

from pydantic import Field

from mem0.configs.rerankers.base import BaseRerankerConfig


class SiliconFlowRerankerConfig(BaseRerankerConfig):
    """
    Configuration for SiliconFlow native reranker.
    Uses SiliconFlow's /v1/rerank endpoint directly via HTTP.
    """

    model: Optional[str] = Field(default="BAAI/bge-reranker-v2-m3", description="The SiliconFlow rerank model to use")
    return_documents: bool = Field(default=False, description="Whether to return the document texts in the response")
    max_chunks_per_doc: Optional[int] = Field(default=None, description="Maximum number of chunks per document")
    siliconflow_base_url: Optional[str] = Field(default="https://api.siliconflow.cn/v1", description="SiliconFlow API base URL")
