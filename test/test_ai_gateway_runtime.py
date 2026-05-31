from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from app.models.ai_gateway import AIAPIKey, AIProvider
from app.services.ai_gateway_runtime import AIGatewayRuntimeError, build_embedding_gateway, build_llm_gateway


class FakeScalarResult:
    def __init__(self, rows) -> None:
        self.rows = rows

    def all(self):
        return self.rows


class FakeRuntimeSession:
    def __init__(self, *, rows, provider, api_key) -> None:
        self.rows = rows
        self.provider = provider
        self.api_key = api_key

    def scalars(self, statement):
        return FakeScalarResult(self.rows)

    def get(self, model, record_id):
        if model is AIProvider:
            return self.provider
        if model is AIAPIKey:
            return self.api_key
        return None


class AIGatewayRuntimeTests(unittest.TestCase):
    def test_embedding_runtime_key_keeps_master_profile_id(self) -> None:
        provider_id = uuid4()
        api_key_id = uuid4()
        profile_id = uuid4()
        profile = SimpleNamespace(
            id=profile_id,
            provider_id=provider_id,
            api_key_id=api_key_id,
            embedding_dimensions=3072,
            batch_size=None,
            extra_parameters={},
            timeout_seconds=60,
            api_base=None,
            endpoint_id=None,
            model_name="gemini/gemini-embedding-2",
        )
        pool = SimpleNamespace(
            profile=profile,
            tenant_id=None,
            app_id=None,
            is_enabled=True,
            is_locked=False,
            today_quota_exhausted=False,
        )
        provider = SimpleNamespace(
            code="gemini",
            base_url=None,
            provider_config={},
            is_enabled=True,
            is_locked=False,
        )
        api_key = SimpleNamespace(
            id=api_key_id,
            provider_id=provider_id,
            encrypted_api_key="encrypted",
            api_base=None,
            endpoint_id=None,
            allowed_capabilities=["embedding"],
            status="active",
            is_enabled=True,
            is_locked=False,
        )
        db = FakeRuntimeSession(rows=[pool], provider=provider, api_key=api_key)

        with patch("app.services.ai_gateway_runtime.decrypt_secret", return_value="secret"):
            gateway = build_embedding_gateway(db)

        snapshot = gateway.health_snapshot()
        self.assertEqual(snapshot["default_embedding_profile_id"], "runtime-embedding-pool")
        self.assertEqual(snapshot["profiles"][0]["keys"][0]["model_profile_id"], str(profile_id))
        self.assertEqual(snapshot["profiles"][0]["keys"][0]["model"], "gemini-embedding-2")

    def test_llm_runtime_key_keeps_master_profile_id(self) -> None:
        provider_id = uuid4()
        api_key_id = uuid4()
        profile_id = uuid4()
        profile = SimpleNamespace(
            id=profile_id,
            provider_id=provider_id,
            api_key_id=api_key_id,
            temperature=0.2,
            top_p=None,
            top_k=None,
            max_output_tokens=1024,
            extra_parameters={},
            timeout_seconds=120,
            api_base=None,
            endpoint_id=None,
            model_name="gemini-2.5-flash",
        )
        pool = SimpleNamespace(
            profile=profile,
            tenant_id=None,
            app_id=None,
            is_enabled=True,
            is_locked=False,
            today_quota_exhausted=False,
        )
        provider = SimpleNamespace(
            code="gemini",
            base_url=None,
            provider_config={},
            is_enabled=True,
            is_locked=False,
        )
        api_key = SimpleNamespace(
            id=api_key_id,
            provider_id=provider_id,
            encrypted_api_key="encrypted",
            api_base=None,
            endpoint_id=None,
            allowed_capabilities=["llm"],
            status="active",
            is_enabled=True,
            is_locked=False,
        )
        db = FakeRuntimeSession(rows=[pool], provider=provider, api_key=api_key)

        with patch("app.services.ai_gateway_runtime.decrypt_secret", return_value="secret"):
            gateway = build_llm_gateway(db)

        snapshot = gateway.health_snapshot()
        self.assertEqual(snapshot["default_llm_profile_id"], "runtime-llm-pool")
        self.assertEqual(snapshot["profiles"][0]["keys"][0]["model_profile_id"], str(profile_id))

    def test_embedding_runtime_rejects_non_gemini_provider(self) -> None:
        provider_id = uuid4()
        api_key_id = uuid4()
        profile = SimpleNamespace(
            id=uuid4(),
            provider_id=provider_id,
            api_key_id=api_key_id,
            embedding_dimensions=1536,
            batch_size=None,
            extra_parameters={},
            timeout_seconds=60,
            api_base=None,
            endpoint_id=None,
            model_name="text-embedding-3-small",
        )
        pool = SimpleNamespace(
            profile=profile,
            tenant_id=None,
            app_id=None,
            is_enabled=True,
            is_locked=False,
            today_quota_exhausted=False,
        )
        provider = SimpleNamespace(
            code="openai",
            base_url=None,
            provider_config={},
            is_enabled=True,
            is_locked=False,
        )
        api_key = SimpleNamespace(
            id=api_key_id,
            provider_id=provider_id,
            encrypted_api_key="encrypted",
            api_base=None,
            endpoint_id=None,
            allowed_capabilities=["embedding"],
            status="active",
            is_enabled=True,
            is_locked=False,
        )
        db = FakeRuntimeSession(rows=[pool], provider=provider, api_key=api_key)

        with self.assertRaisesRegex(AIGatewayRuntimeError, "No usable embedding model profile"):
            build_embedding_gateway(db)


if __name__ == "__main__":
    unittest.main()
