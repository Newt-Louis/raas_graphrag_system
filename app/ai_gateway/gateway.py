from __future__ import annotations

import inspect
import logging
from collections.abc import Iterable
from typing import Any

from app.ai_gateway.base_rotator import RotationResult
from app.ai_gateway.embedding_rotator import EmbeddingRotator
from app.ai_gateway.llm_rotator import LLMRotator
from app.ai_gateway.types import (
    AICapability,
    AdminNotifier,
    GatewayRequestContext,
    ModelProfile,
    UsageRecord,
    UsageRecorder,
)

logger = logging.getLogger("ai_gateway")


class AIGateway:
    """
    Facade cho mọi lời gọi AI model.

    GraphRAG và Services dùng interface này thay vì tự gọi LitellM/rotator. Platform
    Admin sau này chỉ cần cập nhật profile/key ở lớp service/repository rồi nạp lại
    vào gateway.
    """

    def __init__(
        self,
        profiles: Iterable[ModelProfile] | None = None,
        *,
        default_llm_profile_id: str | None = None,
        default_embedding_profile_id: str | None = None,
        usage_recorder: UsageRecorder | None = None,
        admin_notifier: AdminNotifier | None = None,
        rotator_options: dict[str, Any] | None = None,
    ) -> None:
        self._profiles: dict[str, ModelProfile] = {}
        self._rotators: dict[tuple[Any, ...], LLMRotator | EmbeddingRotator] = {}
        self.default_llm_profile_id = default_llm_profile_id
        self.default_embedding_profile_id = default_embedding_profile_id
        self.usage_recorder = usage_recorder
        self.admin_notifier = admin_notifier
        self.rotator_options = {
            "max_attempts": 12,
            "max_retry_same": 2,
            "wait_for_cooldown": True,
            "max_cooldown_wait": 65.0,
            **(rotator_options or {}),
        }
        for profile in profiles or []:
            self.register_profile(profile)

    def register_profile(self, profile: ModelProfile) -> None:
        self._profiles[profile.id] = profile
        self._rotators = {
            cache_key: rotator
            for cache_key, rotator in self._rotators.items()
            if cache_key[0] != profile.id
        }
        if profile.capability == AICapability.LLM and self.default_llm_profile_id is None:
            self.default_llm_profile_id = profile.id
        if profile.capability == AICapability.EMBEDDING and self.default_embedding_profile_id is None:
            self.default_embedding_profile_id = profile.id

    def unregister_profile(self, profile_id: str) -> None:
        self._profiles.pop(profile_id, None)
        self._rotators = {
            cache_key: rotator
            for cache_key, rotator in self._rotators.items()
            if cache_key[0] != profile_id
        }
        if self.default_llm_profile_id == profile_id:
            self.default_llm_profile_id = None
        if self.default_embedding_profile_id == profile_id:
            self.default_embedding_profile_id = None

    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        profile_id: str | None = None,
        context: GatewayRequestContext | None = None,
        **overrides: Any,
    ) -> RotationResult:
        profile = self._resolve_profile(AICapability.LLM, profile_id)
        if profile is None:
            return self._failure(AICapability.LLM, profile_id, "Không có LLM profile khả dụng.")

        rotator = self._get_rotator(profile, context)
        if rotator is None:
            result = self._failure(AICapability.LLM, profile.id, "Không có LLM key khả dụng cho scope này.")
        else:
            result = await rotator.run(messages=messages, **overrides)
        await self._emit_usage(profile, result, context, input_count=len(messages))
        return result

    async def embed(
        self,
        inputs: Any | list[Any],
        *,
        profile_id: str | None = None,
        context: GatewayRequestContext | None = None,
        expected_dim: int | None = None,
        **overrides: Any,
    ) -> RotationResult:
        profile = self._resolve_profile(AICapability.EMBEDDING, profile_id)
        if profile is None:
            return self._failure(AICapability.EMBEDDING, profile_id, "Không có embedding profile khả dụng.")

        rotator = self._get_rotator(profile, context, expected_dim=expected_dim)
        input_count = 1 if isinstance(inputs, (str, dict)) else len(inputs)
        if rotator is None:
            result = self._failure(
                AICapability.EMBEDDING,
                profile.id,
                "Không có embedding key khả dụng cho scope này.",
            )
        else:
            result = await rotator.run(inputs=inputs, **overrides)
        await self._emit_usage(profile, result, context, input_count=input_count)
        return result

    async def test_llm(
        self,
        *,
        profile_id: str | None = None,
        prompt: str = "Return the word ok.",
        context: GatewayRequestContext | None = None,
        **overrides: Any,
    ) -> RotationResult:
        return await self.complete(
            [{"role": "user", "content": prompt}],
            profile_id=profile_id,
            context=context,
            **overrides,
        )

    async def test_embedding(
        self,
        *,
        profile_id: str | None = None,
        text: str = "health check",
        context: GatewayRequestContext | None = None,
        **overrides: Any,
    ) -> RotationResult:
        return await self.embed([text], profile_id=profile_id, context=context, **overrides)

    def health_snapshot(self) -> dict[str, Any]:
        profiles: list[dict[str, Any]] = []
        for profile in self._profiles.values():
            profile_key = {
                "id": profile.id,
                "capability": profile.capability.value,
                "enabled": profile.enabled,
                "locked": profile.locked,
                "lock_reason": profile.lock_reason,
                "expected_dim": profile.expected_dim,
                "max_batch_size": profile.max_batch_size,
                "keys": [
                    {
                        "id": key.id,
                        "model_profile_id": key.model_profile_id,
                        "provider": key.provider,
                        "model": key.model_name,
                        "capability": key.capability,
                        "endpoint_id": key.endpoint_id,
                        "enabled": key.enabled,
                        "locked": key.locked,
                        "lock_reason": key.lock_reason,
                    }
                    for key in profile.keys
                ],
                "runtime_pools": [],
            }
            for cache_key, rotator in self._rotators.items():
                if cache_key[0] == profile.id:
                    profile_key["runtime_pools"].append(
                        {
                            "cache_key": list(cache_key),
                            "pool": rotator.pool.snapshot(),
                        }
                    )
            profiles.append(profile_key)
        return {
            "default_llm_profile_id": self.default_llm_profile_id,
            "default_embedding_profile_id": self.default_embedding_profile_id,
            "profiles": profiles,
        }

    def _resolve_profile(
        self,
        capability: AICapability,
        profile_id: str | None,
    ) -> ModelProfile | None:
        resolved_id = profile_id
        if resolved_id is None and capability == AICapability.LLM:
            resolved_id = self.default_llm_profile_id
        if resolved_id is None and capability == AICapability.EMBEDDING:
            resolved_id = self.default_embedding_profile_id
        if resolved_id:
            profile = self._profiles.get(resolved_id)
            if profile and profile.capability == capability and profile.enabled and not profile.locked:
                return profile
            return None
        for profile in self._profiles.values():
            if profile.capability == capability and profile.enabled and not profile.locked:
                return profile
        return None

    def _get_rotator(
        self,
        profile: ModelProfile,
        context: GatewayRequestContext | None,
        *,
        expected_dim: int | None = None,
    ) -> LLMRotator | EmbeddingRotator | None:
        tenant_id = context.tenant_id if context else None
        app_id = context.app_id if context else None
        keys = profile.usable_keys(tenant_id=tenant_id, app_id=app_id)
        if not keys:
            return None

        resolved_dim = expected_dim if expected_dim is not None else profile.expected_dim
        cache_key = (
            profile.id,
            profile.capability.value,
            tenant_id,
            app_id,
            resolved_dim,
        )
        cached = self._rotators.get(cache_key)
        if cached is not None:
            return cached

        if profile.capability == AICapability.LLM:
            rotator = LLMRotator(
                keys,
                default_params=profile.default_params,
                profile_id=profile.id,
                capability=profile.capability.value,
                **self.rotator_options,
            )
        else:
            rotator = EmbeddingRotator(
                keys,
                default_params=profile.default_params,
                expected_dim=resolved_dim,
                max_batch_size=profile.max_batch_size,
                profile_id=profile.id,
                capability=profile.capability.value,
                **self.rotator_options,
            )
        self._rotators[cache_key] = rotator
        return rotator

    def _failure(
        self,
        capability: AICapability,
        profile_id: str | None,
        reason: str,
    ) -> RotationResult:
        return RotationResult(
            success=False,
            capability=capability.value,
            profile_id=profile_id,
            final_reason=reason,
        )

    async def _emit_usage(
        self,
        profile: ModelProfile,
        result: RotationResult,
        context: GatewayRequestContext | None,
        *,
        input_count: int | None,
    ) -> None:
        last_verdict = result.last_verdict
        record = UsageRecord(
            profile_id=result.profile_id or profile.id,
            capability=profile.capability.value,
            provider=result.used_provider,
            key_id=result.used_key_id,
            model=result.used_model,
            endpoint_id=result.used_endpoint_id,
            success=result.success,
            attempts=result.attempts,
            latency_ms=result.elapsed_ms,
            tenant_id=context.tenant_id if context else None,
            app_id=context.app_id if context else None,
            collection_id=context.collection_id if context else None,
            session_id=context.session_id if context else None,
            user_id=context.user_id if context else None,
            endpoint=context.endpoint if context else None,
            request_id=context.request_id if context else None,
            usage=result.usage,
            error_reason=result.final_reason,
            last_verdict_action=last_verdict.action.value if last_verdict else None,
            input_count=input_count,
        )
        await self._call_optional(self.usage_recorder, record)
        if last_verdict and last_verdict.notify_admin:
            await self._call_optional(self.admin_notifier, record)
        if not result.success and result.final_reason:
            logger.info("AI gateway call failed: %s", result.final_reason)

    async def _call_optional(self, callback: Any, record: UsageRecord) -> None:
        if callback is None:
            return
        value = callback(record)
        if inspect.isawaitable(value):
            await value
