from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.ai_gateway.base_rotator import RotationResult
from app.services.ingestion import DocumentIngestionPipeline
from app.services.ingestion.chunking import DocumentChunker, _token_count
from app.services.ingestion.models import (
    ChunkStrategy,
    ChunkingConfig,
    DocumentScope,
    ElementType,
    ParsedDocument,
    SourceFile,
    StructuralElement,
)
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
                chunking=ChunkingConfig(strategy=ChunkStrategy.SLIDING_WINDOW, max_tokens=100, overlap_tokens=0),
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

    def test_sliding_window_preserves_overlap_without_crossing_page_boundaries(self) -> None:
        chunks = DocumentChunker().chunk(
            _parsed_document(
                [
                    StructuralElement("page-1", ElementType.PARAGRAPH, "alpha beta gamma delta epsilon", page_number=1),
                    StructuralElement("page-2", ElementType.PARAGRAPH, "zeta eta theta iota kappa", page_number=2),
                ]
            ),
            ChunkingConfig(strategy=ChunkStrategy.SLIDING_WINDOW, max_tokens=4, overlap_tokens=1),
        )

        self.assertEqual({chunk.metadata["boundary_value"] for chunk in chunks}, {1, 2})
        self.assertFalse(any("epsilon zeta" in chunk.text for chunk in chunks))
        self.assertTrue(all(chunk.metadata["chunk_role"] == "window" for chunk in chunks))

    def test_parent_child_bounds_parents_and_links_embeddable_children(self) -> None:
        chunks = DocumentChunker().chunk(
            _parsed_document(
                [
                    StructuralElement(
                        "paragraph",
                        ElementType.PARAGRAPH,
                        "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu",
                    ),
                ]
            ),
            ChunkingConfig(
                strategy=ChunkStrategy.PARENT_CHILD,
                max_tokens=4,
                overlap_tokens=1,
                parent_max_tokens=7,
            ),
        )

        parents = [chunk for chunk in chunks if chunk.metadata["chunk_role"] == "parent"]
        children = [chunk for chunk in chunks if chunk.metadata["chunk_role"] == "child"]
        self.assertGreater(len(parents), 1)
        self.assertTrue(all(not parent.is_embeddable for parent in parents))
        self.assertTrue(all(_token_count(parent.text) <= 7 for parent in parents))
        self.assertTrue(all(child.is_embeddable and child.parent_chunk_id for child in children))
        self.assertTrue({child.parent_chunk_id for child in children}.issubset({parent.chunk_id for parent in parents}))


class SemanticIngestionPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_semantic_chunking_groups_adjacent_sentences_above_similarity_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "guide.txt"
            path.write_text(
                "Refunds are available. Returns are accepted. Warehouse robots move crates.",
                encoding="utf-8",
            )
            embedder = FakeSemanticEmbeddingClient()

            bundle = await DocumentIngestionPipeline().ingest_file_async(
                path=path,
                scope=DocumentScope(tenant_id="tenant-a", app_id="app-a"),
                filename="guide.txt",
                content_type="text/plain",
                chunking=ChunkingConfig(
                    strategy=ChunkStrategy.SEMANTIC,
                    max_tokens=100,
                    overlap_tokens=0,
                    semantic_similarity_threshold=0.8,
                ),
                semantic_embedding_client=embedder,
            )

        self.assertEqual(len(embedder.calls[0]), 3)
        self.assertEqual(bundle.stats["vector_records"], 2)
        self.assertIn("Refunds are available.", bundle.chunks[0].text)
        self.assertIn("Returns are accepted.", bundle.chunks[0].text)
        self.assertEqual(bundle.chunks[0].metadata["semantic_unit_count"], 2)
        self.assertEqual(bundle.chunks[1].text, "Warehouse robots move crates.")


class FakeSemanticEmbeddingClient:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def embed_semantic_units(self, texts, **kwargs):
        self.calls.append(list(texts))
        return RotationResult(
            success=True,
            data=[
                [1.0, 0.0],
                [0.99, 0.01],
                [0.0, 1.0],
            ],
        )


def _parsed_document(elements: list[StructuralElement]) -> ParsedDocument:
    return ParsedDocument(
        scope=DocumentScope(tenant_id="tenant-a", app_id="app-a"),
        source=SourceFile(
            document_id="doc-1",
            filename="guide.txt",
            extension=".txt",
            content_type="text/plain",
            byte_size=0,
            sha256="checksum",
        ),
        title="guide",
        elements=elements,
    )


if __name__ == "__main__":
    unittest.main()
