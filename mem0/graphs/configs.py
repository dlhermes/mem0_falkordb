from typing import Optional

from pydantic import BaseModel, Field, field_validator

from mem0.llms.configs import LlmConfig


class MemoryGraphConfig(BaseModel):
    pass


class GraphStoreConfig(BaseModel):
    provider: str = Field(
        description="Provider of the graph store (e.g., 'memory')",
        default="memory",
    )
    config: Optional[MemoryGraphConfig] = Field(
        description="Configuration for the specific graph store", default=None
    )
    llm: Optional[LlmConfig] = Field(description="LLM configuration for querying the graph store", default=None)
    custom_prompt: Optional[str] = Field(
        description="Custom prompt to fetch entities from the given text", default=None
    )
    threshold: float = Field(
        description="Threshold for embedding similarity when matching nodes during graph ingestion. "
                    "Range: 0.0 to 1.0. Higher values require closer matches. "
                    "Use lower values (e.g., 0.5-0.7) for distinct entities with similar embeddings. "
                    "Use higher values (e.g., 0.9+) when you want stricter matching.",
        default=0.7,
        ge=0.0,
        le=1.0,
    )

    @field_validator("config")
    def validate_config(cls, v, values):
        provider = values.data.get("provider")
        if provider == "memory":
            return MemoryGraphConfig(**v.model_dump())
        else:
            raise ValueError(f"Unsupported graph store provider: {provider}")
