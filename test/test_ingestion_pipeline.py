from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.services.ingestion import DocumentIngestionPipeline
from app.services.ingestion.models import ChunkStrategy, ChunkingConfig, DocumentScope
from app.services.ingestion.parsers import validate_document_file


class IngestionPipelineTests(unittest.TestCase):
    def test_accepts_direct_png_uploads(self) -> None:
        self.assertEqual(validate_document_file("photo.png", "image/png"), ".png")

    def test_text_pipeline_chunks_and_scopes_vector_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "guide.txt"
            path.write_text(
                "Install\n\nUse tenant scoped APIs.\n\nKeep retrieval scoped by app and collection.\n",
                encoding="utf-8",
            )

            bundle = DocumentIngestionPipeline().ingest_file(
                path=path,
                scope=DocumentScope(tenant_id="tenant-a", app_id="app-a"),
                filename="guide.txt",
                content_type="text/plain",
                chunking=ChunkingConfig(strategy=ChunkStrategy.SEMANTIC, max_tokens=100, overlap_tokens=0),
            )

        self.assertEqual(bundle.parsed_document.title, "guide")
        self.assertGreaterEqual(bundle.stats["elements"], 3)
        self.assertEqual(bundle.stats["vector_records"], 1)
        self.assertEqual(bundle.vector_records[0].metadata["tenant_id"], "tenant-a")

    def test_image_pipeline_creates_placeholder_element(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "photo.png"
            path.write_bytes(b"\x89PNG\r\n\x1a\n")

            bundle = DocumentIngestionPipeline().ingest_file(
                path=path,
                scope=DocumentScope(tenant_id="tenant-a", app_id="app-a"),
                filename="photo.png",
                content_type="image/png",
            )

        element_types = [element.element_type.value for element in bundle.parsed_document.elements]
        self.assertIn("image", element_types)
        self.assertEqual(bundle.parsed_document.title, "photo")
        self.assertEqual(bundle.stats["vector_records"], 1)
        self.assertEqual(bundle.vector_records[0].metadata["media"][0]["stored_path"], str(path))
        self.assertTrue(bundle.warnings)


if __name__ == "__main__":
    unittest.main()
