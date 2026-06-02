from __future__ import annotations

import tempfile
import unittest
from asyncio import run
from pathlib import Path

from app.graphrag.graph_database import (
    GraphDatabaseScope,
    KuzuGraphStore,
    SemanticEntity,
    SemanticExtraction,
    SemanticExtractionError,
    SemanticRelation,
)
from app.graphrag.graph_database.semantic_extraction import parse_semantic_extraction
from app.graphrag.ingestion_pipeline import GraphRAGIngestionPipeline
from app.services.ingestion import DocumentIngestionPipeline
from app.services.ingestion.models import ChunkStrategy, ChunkingConfig, DocumentScope


class KuzuGraphDatabaseTests(unittest.TestCase):
    def test_ingests_document_graph_and_returns_chunk_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle = _bundle(temp_dir, tenant_id="tenant-a", app_id="app-a")
            store = KuzuGraphStore(Path(temp_dir) / "kuzu" / "graph.db")

            result = store.ingest_bundle(bundle)
            context = store.chunk_context(
                scope=GraphDatabaseScope("tenant-a", "app-a", "docs"),
                chunk_ids=[bundle.chunks[0].chunk_id],
            )

        self.assertEqual(result.document_id, bundle.parsed_document.source.document_id)
        self.assertGreaterEqual(result.stored_count, 2)
        self.assertEqual(len(context.chunks), 1)
        self.assertEqual(context.chunks[0].chunk_id, bundle.chunks[0].chunk_id)
        self.assertTrue(context.chunks[0].source_elements)

    def test_chunk_context_is_tenant_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle = _bundle(temp_dir, tenant_id="tenant-a", app_id="app-a")
            store = KuzuGraphStore(Path(temp_dir) / "kuzu" / "graph.db")

            store.ingest_bundle(bundle)
            context = store.chunk_context(
                scope=GraphDatabaseScope("tenant-b", "app-a", "docs"),
                chunk_ids=[bundle.chunks[0].chunk_id],
            )

        self.assertEqual(context.chunks, [])

    def test_ingest_is_idempotent_for_same_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle = _bundle(temp_dir, tenant_id="tenant-a", app_id="app-a")
            store = KuzuGraphStore(Path(temp_dir) / "kuzu" / "graph.db")

            first = store.ingest_bundle(bundle)
            second = store.ingest_bundle(bundle)
            context = store.chunk_context(
                scope=GraphDatabaseScope("tenant-a", "app-a", "docs"),
                chunk_ids=[bundle.chunks[0].chunk_id],
            )

        self.assertEqual(first.stored_count, second.stored_count)
        self.assertEqual(len(context.chunks), 1)

    def test_document_chunk_stats_are_scoped_by_document(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle = _bundle(temp_dir, tenant_id="tenant-a", app_id="app-a")
            store = KuzuGraphStore(Path(temp_dir) / "kuzu" / "graph.db")

            store.ingest_bundle(bundle)
            stats = store.document_chunk_stats(
                scope=GraphDatabaseScope("tenant-a", "app-a", "docs"),
                document_id=bundle.parsed_document.source.document_id,
            )

        item = stats[bundle.parsed_document.source.document_id]
        self.assertEqual(item.chunk_count, len(bundle.chunks))
        self.assertEqual(item.embeddable_chunk_count, len([chunk for chunk in bundle.chunks if chunk.is_embeddable]))

    def test_parent_child_graph_returns_parent_for_embeddable_child(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "policy.txt"
            path.write_text("Refunds are available within 30 days for eligible orders.", encoding="utf-8")
            bundle = DocumentIngestionPipeline().ingest_file(
                path=path,
                scope=DocumentScope(tenant_id="tenant-a", app_id="app-a", collection_id="docs"),
                filename=path.name,
                content_type="text/plain",
                chunking=ChunkingConfig(strategy=ChunkStrategy.PARENT_CHILD, max_tokens=100),
            )
            child = next(chunk for chunk in bundle.chunks if chunk.is_embeddable)
            parent = next(chunk for chunk in bundle.chunks if not chunk.is_embeddable)
            store = KuzuGraphStore(Path(temp_dir) / "kuzu" / "graph.db")

            store.ingest_bundle(bundle)
            context = store.chunk_context(
                scope=GraphDatabaseScope("tenant-a", "app-a", "docs"),
                chunk_ids=[child.chunk_id],
            )

        self.assertEqual(context.chunks[0].parent_chunk_id, parent.chunk_id)

    def test_persists_semantic_graph_traverses_entities_and_returns_visualization(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle = _bundle(temp_dir, tenant_id="tenant-a", app_id="app-a")
            store = KuzuGraphStore(Path(temp_dir) / "kuzu" / "graph.db")
            scope = GraphDatabaseScope("tenant-a", "app-a", "docs")
            chunk = bundle.chunks[0]

            store.ingest_bundle(bundle)
            stored = store.persist_semantic_extraction(
                scope=scope,
                document_id=chunk.document_id,
                chunk_id=chunk.chunk_id,
                extraction=SemanticExtraction(
                    entities=[
                        SemanticEntity("e1", "Technology", "LanceDB", "lancedb"),
                        SemanticEntity("e2", "Concept", "Vector search", "vector search"),
                    ],
                    relations=[SemanticRelation("e1", "e2", "IMPLEMENTS", confidence=0.9)],
                ),
            )
            traversal = store.entity_context(scope=scope, entity_names=["LanceDB"], hops=1)
            visualization = store.graph_visualization(scope=scope, document_id=chunk.document_id)
            store.delete_document(scope=scope, document_id=chunk.document_id)
            after_delete = store.graph_visualization(scope=scope)

        self.assertEqual(stored.entity_count, 2)
        self.assertEqual(stored.relation_count, 1)
        self.assertIn(chunk.chunk_id, traversal.chunk_ids)
        self.assertIn("Entity", {node.node_type for node in visualization.nodes})
        self.assertIn("IMPLEMENTS", {edge.relation_type for edge in visualization.edges})
        self.assertIn("MENTIONED_IN", {edge.relation_type for edge in visualization.edges})
        self.assertNotIn("Entity", {node.node_type for node in after_delete.nodes})

    def test_structure_visualization_labels_include_readable_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle = _bundle(temp_dir, tenant_id="tenant-a", app_id="app-a")
            store = KuzuGraphStore(Path(temp_dir) / "kuzu" / "graph.db")
            scope = GraphDatabaseScope("tenant-a", "app-a", "docs")

            store.ingest_bundle(bundle)
            visualization = store.graph_visualization(scope=scope)

        element_labels = [node.label for node in visualization.nodes if node.node_type == "Element"]
        chunk_labels = [node.label for node in visualization.nodes if node.node_type == "Chunk"]
        self.assertTrue(any("Use tenant scoped APIs" in label for label in element_labels))
        self.assertTrue(any(label.startswith("Chunk 1:") for label in chunk_labels))
        self.assertNotIn("paragraph", element_labels)

    def test_semantic_extraction_parser_enforces_ontology_allowlist(self) -> None:
        extraction = parse_semantic_extraction(
            """
            ```json
            {
              "entities": [
                {"id": "e1", "type": "Technology", "name": "LanceDB"},
                {"id": "e2", "type": "Unsupported", "name": "Skip me"}
              ],
              "relations": [
                {"from_id": "e1", "type": "RELATED_TO", "to_id": "e1"},
                {"from_id": "e1", "type": "INVENTED", "to_id": "e2"}
              ]
            }
            ```
            """
        )

        self.assertEqual([entity.name for entity in extraction.entities], ["LanceDB"])
        self.assertEqual([relation.relation_type for relation in extraction.relations], ["RELATED_TO"])

    def test_ingestion_pipeline_runs_injected_semantic_extractor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle = _bundle(temp_dir, tenant_id="tenant-a", app_id="app-a")
            store = KuzuGraphStore(Path(temp_dir) / "kuzu" / "graph.db")

            result = run(
                GraphRAGIngestionPipeline(store).ingest_graph(
                    bundle,
                    semantic_extractor=FakeSemanticExtractor(),
                )
            )

        self.assertGreater(result.semantic_entity_count, 0)
        self.assertGreater(result.semantic_mention_count, 0)

    def test_semantic_graph_enrichment_records_chunk_failures_as_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle = _bundle(temp_dir, tenant_id="tenant-a", app_id="app-a")
            store = KuzuGraphStore(Path(temp_dir) / "kuzu" / "graph.db")
            pipeline = GraphRAGIngestionPipeline(store)
            structure_result = run(pipeline.ingest_graph(bundle))

            result = run(
                pipeline.extract_semantic_graph(
                    bundle,
                    semantic_extractor=FailingSemanticExtractor(),
                    base_result=structure_result,
                )
            )

        self.assertEqual(result.stored_count, structure_result.stored_count)
        self.assertEqual(result.semantic_entity_count, 0)
        self.assertTrue(result.semantic_warnings)


class FakeSemanticExtractor:
    async def extract_chunk(self, text, **kwargs):
        return SemanticExtraction(
            entities=[SemanticEntity("e1", "Technology", "LanceDB", "lancedb")],
        )


class FailingSemanticExtractor:
    async def extract_chunk(self, text, **kwargs):
        raise SemanticExtractionError("Provider unavailable.")


def _bundle(temp_dir: str, *, tenant_id: str, app_id: str):
    path = Path(temp_dir) / f"{tenant_id}-{app_id}.txt"
    path.write_text(
        "Install\n\nUse tenant scoped APIs.\n\nKeep graph retrieval scoped by app.\n",
        encoding="utf-8",
    )
    return DocumentIngestionPipeline().ingest_file(
        path=path,
        scope=DocumentScope(tenant_id=tenant_id, app_id=app_id, collection_id="docs"),
        filename=path.name,
        content_type="text/plain",
        chunking=ChunkingConfig(strategy=ChunkStrategy.SLIDING_WINDOW, max_tokens=100, overlap_tokens=0),
    )


if __name__ == "__main__":
    unittest.main()
