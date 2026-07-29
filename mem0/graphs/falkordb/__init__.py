"""FalkorDB graph store provider for Mem0.

FalkorDB is natively compiled into GraphStoreFactory and GraphStoreConfig.
No register() call needed --- configure ``graph_store.provider="falkordb"`` and
its config dict directly when creating a Mem0 Memory instance.
"""

from mem0.graphs.falkordb.patch import register

__all__ = ["register"]
