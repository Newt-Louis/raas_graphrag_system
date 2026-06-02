from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from google.genai import types

from app.ai_gateway import AICapability, AIGateway, GatewayRequestContext, KeyConfig, ModelProfile
from app.ai_gateway.embedding_gemini import EmbeddingRotator
from app.graphrag.ai_client import GraphRAGAIClient


class FakeAsyncModels:
    def __init__(self, vectors: list[list[float]]) -> None:
        self.vectors = vectors
        self.calls: list[dict] = []

    async def embed_content(self, **kwargs):
        self.calls.append(kwargs)
        count = len(kwargs["contents"])
        return SimpleNamespace(
            embeddings=[
                SimpleNamespace(values=vector)
                for vector in self.vectors[:count]
            ]
        )


class FakeAsyncClient:
    def __init__(self, models: FakeAsyncModels) -> None:
        self.models = models

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None


class FakeClient:
    def __init__(self, models: FakeAsyncModels) -> None:
        self.aio = FakeAsyncClient(models)


class RecordingGateway:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def embed(self, inputs, **kwargs):
        self.calls.append({"inputs": inputs, **kwargs})
        return SimpleNamespace(success=True)


def _content_texts(contents: list[types.Content]) -> list[str]:
    return [content.parts[0].text for content in contents]


class GeminiEmbeddingTests(unittest.IsolatedAsyncioTestCase):
    async def test_uses_google_genai_with_retrieval_task_and_expected_dimension(self) -> None:
        models = FakeAsyncModels([[1.0, 0.0, 0.0]])
        rotator = EmbeddingRotator(
            [
                KeyConfig(
                    id="gemini-key",
                    provider="gemini",
                    model_name="gemini/gemini-embedding-001",
                    api_key="secret",
                )
            ],
            expected_dim=3,
            capability="embedding",
        )

        with patch("app.ai_gateway.embedding_gemini.genai.Client", return_value=FakeClient(models)):
            result = await rotator.run(inputs=["refund policy"], task_type="RETRIEVAL_DOCUMENT")

        self.assertTrue(result.success)
        self.assertEqual(result.data, [[1.0, 0.0, 0.0]])
        self.assertEqual(models.calls[0]["model"], "gemini-embedding-001")
        config = models.calls[0]["config"].model_dump(exclude_none=True, by_alias=True)
        self.assertEqual(config["taskType"], "RETRIEVAL_DOCUMENT")
        self.assertEqual(config["outputDimensionality"], 3)

    async def test_dimension_mismatch_returns_failed_gateway_result(self) -> None:
        models = FakeAsyncModels([[1.0, 0.0]])
        rotator = EmbeddingRotator(
            [
                KeyConfig(
                    id="gemini-key",
                    provider="gemini",
                    model_name="gemini-embedding-001",
                    api_key="secret",
                )
            ],
            expected_dim=3,
            capability="embedding",
        )

        with patch("app.ai_gateway.embedding_gemini.genai.Client", return_value=FakeClient(models)):
            result = await rotator.run(inputs=["refund policy"])

        self.assertFalse(result.success)
        self.assertIn("khác chiều", result.final_reason)

    async def test_structured_image_payload_embeds_its_text_description(self) -> None:
        models = FakeAsyncModels([[1.0, 0.0, 0.0]])
        rotator = EmbeddingRotator(
            [
                KeyConfig(
                    id="gemini-key",
                    provider="gemini",
                    model_name="gemini-embedding-001",
                    api_key="secret",
                )
            ],
            expected_dim=3,
        )

        with patch("app.ai_gateway.embedding_gemini.genai.Client", return_value=FakeClient(models)):
            result = await rotator.run(
                inputs=[
                    [
                        {"type": "text", "text": "Represent invoice image."},
                        {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
                    ]
                ]
            )

        self.assertTrue(result.success)
        self.assertEqual(_content_texts(models.calls[0]["contents"]), ["Represent invoice image."])

    async def test_keeps_gemini_embedding_2_batch_items_as_separate_contents(self) -> None:
        models = FakeAsyncModels(
            [
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [0.0, 0.0, 1.0],
                [1.0, 1.0, 0.0],
            ]
        )
        rotator = EmbeddingRotator(
            [
                KeyConfig(
                    id="gemini-key",
                    provider="gemini",
                    model_name="gemini-embedding-2",
                    api_key="secret",
                )
            ],
            expected_dim=3,
            max_batch_size=32,
        )

        with patch("app.ai_gateway.embedding_gemini.genai.Client", return_value=FakeClient(models)):
            result = await rotator.run(inputs=["one", "two", "three", "four"])

        self.assertTrue(result.success)
        self.assertEqual(len(result.data), 4)
        contents = models.calls[0]["contents"]
        self.assertTrue(all(isinstance(content, types.Content) for content in contents))
        self.assertEqual(_content_texts(contents), ["one", "two", "three", "four"])

    def test_rejects_multiple_embedding_keys(self) -> None:
        keys = [
            KeyConfig(id=f"gemini-key-{index}", provider="gemini", model_name="model", api_key="secret")
            for index in range(2)
        ]

        with self.assertRaisesRegex(ValueError, "exactly one API key"):
            EmbeddingRotator(keys)

    async def test_graphrag_client_marks_document_and_query_tasks(self) -> None:
        gateway = RecordingGateway()
        client = GraphRAGAIClient(gateway)  # type: ignore[arg-type]

        await client.embed_documents(["policy"], tenant_id="tenant-a", app_id="app-a")
        await client.embed_query("refund", tenant_id="tenant-a", app_id="app-a")
        await client.embed_semantic_units(["sentence"], tenant_id="tenant-a", app_id="app-a")

        self.assertEqual(gateway.calls[0]["task_type"], "RETRIEVAL_DOCUMENT")
        self.assertEqual(gateway.calls[1]["task_type"], "RETRIEVAL_QUERY")
        self.assertEqual(gateway.calls[2]["task_type"], "RETRIEVAL_DOCUMENT")
        self.assertEqual(gateway.calls[2]["context"].endpoint, "graphrag.documents.semantic_chunking")

    async def test_gateway_uses_only_first_gemini_embedding_key(self) -> None:
        models = FakeAsyncModels([[1.0, 0.0, 0.0]])
        profile = ModelProfile(
            id="gemini-embedding",
            capability=AICapability.EMBEDDING,
            keys=[
                KeyConfig(id="first", provider="gemini", model_name="gemini-embedding-001", api_key="one"),
                KeyConfig(id="second", provider="gemini", model_name="gemini-embedding-001", api_key="two"),
            ],
            expected_dim=3,
        )
        gateway = AIGateway([profile])

        with patch("app.ai_gateway.embedding_gemini.genai.Client", return_value=FakeClient(models)):
            result = await gateway.embed(
                ["refund"],
                context=GatewayRequestContext(tenant_id="tenant-a", app_id="app-a"),
            )

        self.assertTrue(result.success)
        self.assertEqual(result.used_key_id, "first")


if __name__ == "__main__":
    unittest.main()
