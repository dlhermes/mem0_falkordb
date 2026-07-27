# mem0 + FalkorDB = Graph-Enhanced Memory Layer

> **Fork of [mem0ai/mem0](https://github.com/mem0ai/mem0) v2.0.14** — backporting the `graphs/` module removed since v2.0.0, enabling external graph database integration via [mem0-falkordb](https://github.com/FalkorDB/mem0-falkordb).

## What This Fork Does

mem0 OSS v2.0.0+ removed external graph database support (Neo4j, Kuzu, Memgraph, Apache AGE, Neptune). The entire `mem0/graphs/` module — interface, factory, configs, tools — was deleted.

This fork restores the graph store interface layer while keeping everything else intact from v2.0.14:

- **`mem0/graphs/`** — configs, tools (LLM function schemas), utils (extraction prompts), memory stub
- **`GraphStoreFactory`** — factory with provider registry (`provider_to_class` dict)
- **`graph_store` field** — added to `MemoryConfig` (default provider: `"memory"`)
- **`Memory` integration** — `add()` fires non-blocking graph write, `search()` merges graph relations, `delete()`/`reset()` cleanup graph data. Sync + async both covered.

## Architecture

```
┌─────────────────────────────────────────────────┐
│                  AI Agent                        │
│         add() / search() / delete()              │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│              Mem0 SDK v2.0.14 + graphs           │
│  ┌──────────┐  ┌───────────┐  ┌──────────────┐  │
│  │ vector   │  │ entity    │  │ graph_store  │  │
│  │ store    │  │ store     │  │ (restored)   │  │
│  └──────────┘  └───────────┘  └──────┬───────┘  │
│                                      │           │
│                           GraphStoreFactory     │
│                           provider_to_class     │
└──────────────────────────────────┬─────────────┘
                                   │ plugin registers
┌──────────────────────────────────▼─────────────┐
│           mem0-falkordb plugin                  │
│  ┌──────────────────────────────────────────┐  │
│  │  MemoryGraph (775 lines)                  │  │
│  │  - FalkorDB Cypher (vector index, merge)  │  │
│  │  - Per-user graph isolation               │  │
│  │  - Mention counting / entity linking       │  │
│  └──────────────────────────────────────────┘  │
└──────────────────────┬─────────────────────────┘
                       │
┌──────────────────────▼─────────────────────────┐
│              FalkorDB (graph DB)                │
│  Real Cypher graphs — traversable, queryable   │
└────────────────────────────────────────────────┘
```

## Quick Start

```bash
pip install mem0ai mem0-falkordb falkordb
```

```python
from mem0_falkordb import register
register()  # must be called before Memory.from_config()

from mem0 import Memory

config = {
    "graph_store": {
        "provider": "falkordb",
        "config": {
            "host": "localhost",
            "port": 6379,
            "database": "mem0",
        },
    },
    "vector_store": {
        "provider": "qdrant",
        "config": {"host": "localhost", "port": 6333},
    },
    "llm": {"provider": "openai", "config": {"model": "gpt-4o-mini"}},
    "embedder": {"provider": "openai", "config": {"model": "text-embedding-3-small", "embedding_dims": 1536}},
}

m = Memory.from_config(config)
m.add("I love pizza", user_id="alice")

# Graph relationships are created automatically via FalkorDB
results = m.search("what does alice like?", user_id="alice")
```

## Changes from Upstream

| File | Change |
|---|---|
| `mem0/graphs/__init__.py` | New (empty) |
| `mem0/graphs/configs.py` | Adapted — default provider `"memory"`, removed old backends |
| `mem0/graphs/tools.py` | Copied from pre-v2-era (LLM tool schemas) |
| `mem0/graphs/utils.py` | Copied (EXTRACT_RELATIONS_PROMPT) |
| `mem0/graphs/memory.py` | New — MemoryGraph stub (replaced by plugin at runtime) |
| `mem0/utils/factory.py` | +17 lines — GraphStoreFactory |
| `mem0/configs/base.py` | +4 lines — graph_store field |
| `mem0/memory/main.py` | ~80 lines — graph integration in add/search/delete (sync+async) |

## Requirements

- Python 3.10-3.12
- mem0-falkordb ≥ 0.4.1
- FalkorDB ≥ 1.6.0

## License

Apache 2.0 — same as upstream [mem0ai/mem0](https://github.com/mem0ai/mem0).
