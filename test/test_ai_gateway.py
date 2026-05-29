from __future__ import annotations

import unittest

import litellm

from app.ai_gateway.base_rotator import BaseRotator
from app.ai_gateway import (
    AICapability,
    AIGateway,
    GatewayRequestContext,
    KeyConfig,
    KeyPool,
    ModelProfile,
)


class AlwaysApiErrorRotator(BaseRotator):
    async def _call(self, key, **kwargs):
        raise litellm.APIError(
            status_code=503,
            message="provider temporarily unavailable",
            llm_provider="test",
            model="embedding-model",
        )


class InvalidRequestApiErrorRotator(BaseRotator):
    async def _call(self, key, **kwargs):
        raise litellm.APIError(
            status_code=400,
            message="invalid request payload",
            llm_provider="test",
            model="embedding-model",
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

    async def test_max_attempts_reports_last_provider_error_instead_of_counter_only(self) -> None:
        rotator = AlwaysApiErrorRotator(
            [
                KeyConfig(
                    id="key-1",
                    provider="test",
                    model_name="embedding-model",
                    api_key="secret",
                )
            ],
            max_attempts=2,
            wait_for_cooldown=False,
        )

        result = await rotator.run()

        self.assertFalse(result.success)
        self.assertIn("Không gọi được provider sau 2 lần thử", result.final_reason)
        self.assertIn("Lỗi API không xác định rõ", result.final_reason)
        self.assertNotIn("Vượt quá max_attempts", result.final_reason)

    async def test_bad_request_wrapped_as_api_error_stops_without_exhausting_attempts(self) -> None:
        rotator = InvalidRequestApiErrorRotator(
            [
                KeyConfig(
                    id="key-1",
                    provider="test",
                    model_name="embedding-model",
                    api_key="secret",
                )
            ],
            max_attempts=3,
            wait_for_cooldown=False,
        )

        result = await rotator.run()

        self.assertFalse(result.success)
        self.assertEqual(result.attempts, 1)
        self.assertIn("Cần admin xử lý", result.final_reason)


if __name__ == "__main__":
    unittest.main()
