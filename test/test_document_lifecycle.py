from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.models.documents import Document
from app.services.documents.lifecycle import DocumentLifecycleService


class DocumentLifecycleServiceTests(unittest.TestCase):
    def test_semantic_graph_enrichment_status_is_tracked_separately_from_document_ready(self) -> None:
        db = MagicMock()
        service = DocumentLifecycleService(db)
        document = Document(
            id=uuid4(),
            filename="guide.txt",
            extension=".txt",
            byte_size=10,
            sha256="a" * 64,
            metadata_json={},
        )
        service.repository = MagicMock()
        service.repository.get_document.return_value = document

        service.mark_document_ready(
            document,
            vector_result=SimpleNamespace(stored_count=2, embedding_model="embedding-model"),
            graph_result=_graph_result(),
            semantic_graph_requested=True,
        )

        self.assertEqual(document.status, "ready")
        self.assertEqual(document.metadata_json["semantic_graph_status"], "queued")

        service.mark_semantic_graph_completed(document.id, graph_result=_graph_result(entity_count=1))

        self.assertEqual(document.metadata_json["semantic_graph_status"], "ready")
        self.assertEqual(document.metadata_json["semantic_entity_count"], 1)

        service.mark_semantic_graph_failed(document.id, reason="AIGatewayRuntimeError")

        self.assertEqual(document.status, "ready")
        self.assertEqual(document.metadata_json["semantic_graph_status"], "failed")
        self.assertEqual(document.metadata_json["semantic_graph_error"], "AIGatewayRuntimeError")


def _graph_result(*, entity_count: int = 0):
    return SimpleNamespace(
        stored_count=3,
        semantic_entity_count=entity_count,
        semantic_relation_count=0,
        semantic_mention_count=0,
        semantic_warnings=[],
    )


if __name__ == "__main__":
    unittest.main()
