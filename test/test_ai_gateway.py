from __future__ import annotations

import unittest

from app.ai_gateway import (
    AICapability,
    AIGateway,
    GatewayRequestContext,
    KeyConfig,
    KeyPool,
    ModelProfile,
)


class AIGatewayTests(unittest.IsolatedAsyncioTestCase):
    def test_model_profile_sets_key_capability_and_snapshot_hides_secret(self) -> None:
        profile = ModelProfile(
            id="embedding-default",
            capability=AICapability.EMBEDDING,
            keys=[
                KeyConfig(
                    id="emb-key-1",
                    provider="openai",
                    model_name="text-embedding-model",
                    api_key="secret",
                )
            ],
            expected_dim=1536,
        )
        gateway = AIGateway([profile])

        snapshot = gateway.health_snapshot()

        self.assertEqual(profile.keys[0].capability, "embedding")
        self.assertEqual(snapshot["default_embedding_profile_id"], "embedding-default")
        self.assertNotIn("api_key", snapshot["profiles"][0]["keys"][0])

    def test_key_pool_skips_locked_keys_and_can_retry_same_key(self) -> None:
        pool = KeyPool(
            [
                KeyConfig(
                    id="locked",
                    provider="test",
                    model_name="model-a",
                    api_key="secret",
                    locked=True,
                ),
                KeyConfig(
                    id="active",
                    provider="test",
                    model_name="model-b",
                    api_key="secret",
                ),
            ]
        )

        first = pool.acquire()
        pool.retry_next(first)
        second = pool.acquire()

        self.assertEqual(first.config.id, "active")
        self.assertIs(first, second)

    async def test_usage_record_is_emitted_when_profile_has_no_usable_key(self) -> None:
        records = []
        profile = ModelProfile(
            id="llm-default",
            capability=AICapability.LLM,
            keys=[
                KeyConfig(
                    id="llm-key-1",
                    provider="test",
                    model_name="model",
                    api_key="secret",
                    locked=True,
                )
            ],
        )
        gateway = AIGateway([profile], usage_recorder=records.append)

        result = await gateway.complete(
            [{"role": "user", "content": "hello"}],
            context=GatewayRequestContext(tenant_id="tenant-a", app_id="app-a"),
        )

        self.assertFalse(result.success)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].tenant_id, "tenant-a")
        self.assertEqual(records[0].profile_id, "llm-default")
        self.assertEqual(records[0].capability, "llm")


if __name__ == "__main__":
    unittest.main()
