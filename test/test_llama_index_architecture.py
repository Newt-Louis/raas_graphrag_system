from __future__ import annotations

import unittest

from llama_index.core.graph_stores.types import PropertyGraphStore
from llama_index.core.vector_stores.simple import SimpleVectorStore

from app.graphrag.graph_database import KuzuGraphStore
from app.graphrag.vector_database import InMemoryPrecomputedVectorStore


class LlamaIndexArchitectureTests(unittest.TestCase):
    def test_kuzu_bridge_implements_llamaindex_property_graph_store(self) -> None:
        self.assertTrue(issubclass(KuzuGraphStore, PropertyGraphStore))

    def test_in_memory_vector_store_uses_llamaindex_simple_vector_store(self) -> None:
        store = InMemoryPrecomputedVectorStore()

        self.assertIsInstance(store.llama_vector_store, SimpleVectorStore)


if __name__ == "__main__":
    unittest.main()
