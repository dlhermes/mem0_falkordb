from unittest import mock

import pytest

from mem0.graphs.falkordb import graph_memory as gm


class FakeResult:
    def __init__(self, result_set, header=None):
        self.result_set = result_set
        if header is None:
            header = (
                []
                if not result_set
                else [["SCALAR", f"c{i}"] for i in range(len(result_set[0]))]
            )
        self.header = header


@pytest.fixture
def store():
    with mock.patch.object(gm, "FalkorDB") as falkor_cls:
        client = falkor_cls.return_value
        client.select_graph.side_effect = lambda name: mock.MagicMock()
        wrapper = gm._FalkorDBGraphWrapper(
            host="localhost", port=6379, database="mem0"
        )
        yield wrapper, client


def _make_graph(store, uid):
    wrapper, _ = store
    graph = wrapper._get_graph(uid)
    graph.query.return_value = FakeResult([], [])
    return graph


def _make_memory_graph(store):
    wrapper, _ = store
    gmem = gm.MemoryGraph.__new__(gm.MemoryGraph)
    gmem.graph = wrapper
    gmem.node_label = ": `__Entity__`"
    gmem.use_base_label = True
    gmem.embedding_model = mock.MagicMock()
    gmem._indexed_user_graphs = set()
    gmem.llm = mock.MagicMock()
    return gmem


def test_invalidate_entities_marks_relationship(store):
    graph = _make_graph(store, "alice")
    gmem = _make_memory_graph(store)
    gmem._invalidate_entities(
        [{"source": "alice", "destination": "bob", "relationship": "works_with"}],
        {"user_id": "alice"},
    )
    cypher = graph.query.call_args.args[0]
    assert "MATCH" in cypher
    assert "SET r.invalidated_at = timestamp()" in cypher


def test_add_revives_invalidated_relationship(store):
    graph = _make_graph(store, "alice")
    gmem = _make_memory_graph(store)
    gmem.embedding_model.embed_batch.return_value = [[0.1] * 8, [0.2] * 8]
    gmem._add_entities(
        [{"source": "alice", "destination": "bob", "relationship": "works_with"}],
        {"user_id": "alice"},
        {"alice": "person", "bob": "person"},
    )
    cyphers = [call.args[0] for call in graph.query.call_args_list]
    revival = [c for c in cyphers if "invalidated_at = null" in c]
    assert revival
    assert "coalesce(rel.mentions, 0) + 1" in revival[0]


def test_search_excludes_invalidated(store):
    graph = _make_graph(store, "alice")
    graph.query.side_effect = lambda cypher, params=None: (
        FakeResult(
            [[1, "alice", 0.05]],
            [["SCALAR", "node_id"], ["SCALAR", "node_name"], ["SCALAR", "score"]],
        )
        if "vector.queryNodes" in cypher
        else FakeResult([], [])
    )
    gmem = _make_memory_graph(store)
    gmem.embedding_model.embed_batch.return_value = [[0.1] * 8] * 4
    gmem.search("alice works with bob", {"user_id": "alice"})
    cyphers = [call.args[0] for call in graph.query.call_args_list]
    assert any("invalidated_at IS NULL" in c for c in cyphers)


def test_per_user_graph_isolation(store):
    wrapper, client = store
    g1 = wrapper._get_graph("alice")
    g2 = wrapper._get_graph("bob")
    g3 = wrapper._get_graph("alice")
    names = [call.args[0] for call in client.select_graph.call_args_list]
    assert names == ["mem0_alice", "mem0_bob"]
    assert g1 is g3
    assert g1 is not g2
