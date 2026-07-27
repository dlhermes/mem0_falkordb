import logging

logger = logging.getLogger(__name__)


class MemoryGraph:
    def __init__(self, config):
        self.config = config

    def add(self, data, filters):
        return {}

    def search(self, query, filters, limit=100):
        return []

    def delete_all(self, filters):
        pass

    def get_all(self, filters, limit=100):
        return []

    def reset(self):
        pass
