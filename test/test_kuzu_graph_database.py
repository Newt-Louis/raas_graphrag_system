from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.graphrag.graph_database import GraphDatabaseScope, KuzuGraphStore
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
        chunking=ChunkingConfig(strategy=ChunkStrategy.SEMANTIC, max_tokens=100, overlap_tokens=0),
    )


if __name__ == "__main__":
    unittest.main()
