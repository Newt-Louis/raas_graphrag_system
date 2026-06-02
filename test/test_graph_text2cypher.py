from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.graphrag.graph_database import GraphDatabaseScope
from app.graphrag.graph_database.kuzu_store import KuzuGraphStore
from app.graphrag.llama_index import GatewayLLM
from app.graphrag.llama_index.graph_text2cypher import (
    CypherGuardrailError,
    build_kuzu_text2cypher_retriever,
    read_only_cypher_validator,
)


class ReadOnlyGuardrailTests(unittest.TestCase):
    def test_accepts_read_query_and_strips_fences(self) -> None:
        cleaned = read_only_cypher_validator("```cypher\nMATCH (e:Entity) RETURN e.name LIMIT 5\n```")
        self.assertEqual(cleaned, "MATCH (e:Entity) RETURN e.name LIMIT 5")

    def test_blocks_write_operations(self) -> None:
        for bad in (
            "CREATE (n:Entity {id:'x'})",
            "MATCH (e:Entity) DETACH DELETE e",
            "MATCH (e:Entity) SET e.name='x'",
            "DROP TABLE Entity",
            "not a query",
        ):
            with self.assertRaises(CypherGuardrailError):
                read_only_cypher_validator(bad)


class FixedCypherLLM:
    """GatewayLLM acomplete trả về một câu Cypher cố định cho text2cypher."""

    def __init__(self, cypher: str) -> None:
        self.cypher = cypher
        self.prompts: list[str] = []

    async def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.cypher


class KuzuTextToCypherTests(unittest.TestCase):
    def test_schema_str_lists_node_and_relation_tables(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = KuzuGraphStore(Path(tmp) / "graph.db")
            store.ensure_schema()
            schema = store.get_schema_str()
        for token in ("Document", "Element", "Chunk", "Entity", "SEMANTIC_RELATION", "MENTIONED_IN"):
            self.assertIn(token, schema)

    def test_text2cypher_runs_generated_query_against_kuzu(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = KuzuGraphStore(Path(tmp) / "graph.db")
            store.ensure_schema()
            store.structured_query(
                """
                CREATE (e:Entity {
                    id: 'tenant-a:app-a::entity:lancedb',
                    tenant_id: 'tenant-a', app_id: 'app-a', collection_id: '',
                    entity_type: 'Technology', name: 'LanceDB',
                    normalized_name: 'lancedb', description: 'Vector database',
                    metadata_json: '{}'
                })
                """
            )

            llm_backend = FixedCypherLLM(
                "MATCH (e:Entity) WHERE e.tenant_id = 'tenant-a' AND e.app_id = 'app-a' "
                "RETURN e.name, e.description LIMIT 30"
            )
            retriever = build_kuzu_text2cypher_retriever(
                graph_store=store,
                llm=GatewayLLM(llm_backend, model_name="fake"),
                scope=GraphDatabaseScope(tenant_id="tenant-a", app_id="app-a"),
            )

            from llama_index.core.schema import QueryBundle

            nodes = retriever.retrieve(QueryBundle(query_str="What is LanceDB?"))

        self.assertTrue(nodes)
        combined = " ".join(node.node.get_content() for node in nodes)
        self.assertIn("LanceDB", combined)
        self.assertTrue(llm_backend.prompts)


if __name__ == "__main__":
    unittest.main()
