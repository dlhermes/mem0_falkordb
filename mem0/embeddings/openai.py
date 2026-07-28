import base64
import os
import struct
import warnings
from typing import Literal, Optional

from openai import OpenAI

from mem0.configs.embeddings.base import BaseEmbedderConfig
from mem0.embeddings.base import EmbeddingBase


class OpenAIEmbedding(EmbeddingBase):
    def __init__(self, config: Optional[BaseEmbedderConfig] = None):
        super().__init__(config)

        self.config.model = self.config.model or "text-embedding-3-small"
        # Only pass `dimensions` to the API when the user set embedding_dims; non-matryoshka
        # OpenAI-compatible backends (vLLM, Voyage, etc.) reject the parameter
        self._pass_dimensions_to_api = self.config.embedding_dims is not None
        self.config.embedding_dims = self.config.embedding_dims or 1536

        api_key = self.config.api_key or os.getenv("OPENAI_API_KEY")
        base_url = (
            self.config.openai_base_url
            or os.getenv("OPENAI_API_BASE")
            or os.getenv("OPENAI_BASE_URL")
            or "https://api.openai.com/v1"
        )
        if os.environ.get("OPENAI_API_BASE"):
            warnings.warn(
                "The environment variable 'OPENAI_API_BASE' is deprecated and will be removed in the 0.1.80. "
                "Please use 'OPENAI_BASE_URL' instead.",
                DeprecationWarning,
            )

        embedder_kwargs = {}
        embedder_timeout = os.environ.get("MEM0_EMBEDDER_TIMEOUT")
        if embedder_timeout is not None:
            embedder_kwargs["timeout"] = float(embedder_timeout)
        embedder_max_retries = os.environ.get("MEM0_EMBEDDER_MAX_RETRIES")
        if embedder_max_retries is not None:
            embedder_kwargs["max_retries"] = int(embedder_max_retries)
        self.client = OpenAI(api_key=api_key, base_url=base_url, **embedder_kwargs)

    def _decode_embedding(self, data):
        """Decode embedding from API response — handles float[] and base64 string."""
        if isinstance(data, list):
            return data
        if isinstance(data, str):
            raw_bytes = base64.b64decode(data)
            return list(struct.unpack(f'{len(raw_bytes) // 4}f', raw_bytes))

    def embed(self, text, memory_action: Optional[Literal["add", "search", "update"]] = None):
        """
        Get the embedding for the given text using OpenAI.

        Args:
            text (str): The text to embed.
            memory_action (optional): The type of embedding to use. Must be one of "add", "search", or "update". Defaults to None.
        Returns:
            list: The embedding vector.
        """
        text = text.replace("\n", " ")
        kwargs = {
            "input": [text],
            "model": self.config.model,
        }
        # VoyageAI API rejects 'float' encoding_format and 'dimensions' parameter
        _is_voyage = "voyageai" in (self.config.openai_base_url or "")
        if not _is_voyage:
            kwargs["encoding_format"] = "float"
        else:
            kwargs["encoding_format"] = "base64"
        if self._pass_dimensions_to_api and not _is_voyage:
            kwargs["dimensions"] = self.config.embedding_dims
        raw = self.client.embeddings.create(**kwargs).data[0].embedding
        return self._decode_embedding(raw)

    def embed_batch(self, texts, memory_action="add"):
        """Embed multiple texts in a single OpenAI API call.

        Automatically chunks into batches of 100 to stay within API limits.
        """
        MAX_BATCH = int(os.environ.get("MEM0_EMBEDDING_BATCH_SIZE", "100"))
        texts = [text.replace("\n", " ") for text in texts]
        all_embeddings = []
        for i in range(0, len(texts), MAX_BATCH):
            chunk = texts[i : i + MAX_BATCH]
            kwargs = {
                "input": chunk,
                "model": self.config.model,
            }
            # VoyageAI API rejects 'float' encoding_format and 'dimensions' parameter
            _is_voyage = "voyageai" in (self.config.openai_base_url or "")
            if not _is_voyage:
                kwargs["encoding_format"] = "float"
            else:
                kwargs["encoding_format"] = "base64"
            if self._pass_dimensions_to_api and not _is_voyage:
                kwargs["dimensions"] = self.config.embedding_dims
            response = self.client.embeddings.create(**kwargs)
            all_embeddings.extend(
                self._decode_embedding(item.embedding)
                for item in sorted(response.data, key=lambda x: x.index)
            )
        if len(all_embeddings) != len(texts):
            raise ValueError(
                f"OpenAI embed_batch() returned {len(all_embeddings)} embeddings for {len(texts)} texts"
                f" using model '{self.config.model}'"
            )
        return all_embeddings
