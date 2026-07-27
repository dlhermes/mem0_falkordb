import logging

logger = logging.getLogger(__name__)


class MemoryGraph:
    def __init__(self, config=None):
        self.config = config
        self.edges = set()

    def add(self, source, destination, relationship, source_type=None, destination_type=None):
        edge = (source, destination, relationship)
        self.edges.add(edge)

    def get_all(self, filters=None):
        return [
            {"source": s, "destination": d, "relationship": r}
            for s, d, r in self.edges
        ]

    def search(self, query, filters=None):
        results = []
        for s, d, r in self.edges:
            if query.lower() in s.lower() or query.lower() in d.lower() or query.lower() in r.lower():
                results.append({"source": s, "destination": d, "relationship": r})
        return results

    def get(self, source, destination, relationship):
        for s, d, r in self.edges:
            if s == source and d == destination and r == relationship:
                return {"source": s, "destination": d, "relationship": r}
        return None

    def update(self, source, destination, old_relationship, new_relationship):
        edge = (source, destination, old_relationship)
        if edge in self.edges:
            self.edges.discard(edge)
            self.edges.add((source, destination, new_relationship))

    def delete(self, source, destination, relationship):
        self.edges.discard((source, destination, relationship))

    def delete_all(self):
        self.edges.clear()

    def reset(self):
        self.edges.clear()
