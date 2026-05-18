from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.services.ingestion import DocumentIngestionPipeline
from app.services.ingestion.models import ChunkStrategy, ChunkingConfig, DocumentScope
from app.services.ingestion.parsers import DocumentValidationError, validate_document_file


class IngestionPipelineTests(unittest.TestCase):
    def test_rejects_direct_image_uploads(self) -> None:
        with self.assertRaises(DocumentValidationError):
            validate_document_file("photo.png", "image/png")

    def test_markdown_pipeline_preserves_headings_and_dedupes_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "guide.md"
            path.write_text(
                "# Install\n\nUse tenant scoped APIs.\n\n# Install\n\nUse tenant scoped APIs.\n",
                encoding="utf-8",
            )

            bundle = DocumentIngestionPipeline().ingest_file(
                path=path,
                scope=DocumentScope(tenant_id="tenant-a", app_id="app-a"),
                filename="guide.md",
                content_type="text/markdown",
                chunking=ChunkingConfig(strategy=ChunkStrategy.SEMANTIC, max_tokens=100, overlap_tokens=0),
            )

        self.assertEqual(bundle.parsed_document.title, "Install")
        self.assertGreaterEqual(bundle.stats["elements"], 4)
        self.assertEqual(bundle.duplicate_chunk_count, 1)
        self.assertEqual(bundle.stats["vector_records"], 1)
        self.assertEqual(bundle.vector_records[0].metadata["tenant_id"], "tenant-a")

    def test_html_parser_keeps_table_and_embedded_image_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "page.html"
            path.write_text(
                "<h1>Policy</h1><p>Hello</p><table><tr><th>A</th></tr><tr><td>B</td></tr></table>"
                "<img src='media/chart.png' alt='Chart'>",
                encoding="utf-8",
            )

            bundle = DocumentIngestionPipeline().ingest_file(
                path=path,
                scope=DocumentScope(tenant_id="tenant-a", app_id="app-a"),
                filename="page.html",
                content_type="text/html",
            )

        element_types = [element.element_type.value for element in bundle.parsed_document.elements]
        self.assertIn("table", element_types)
        self.assertIn("image", element_types)
        self.assertEqual(bundle.parsed_document.title, "Policy")


if __name__ == "__main__":
    unittest.main()
