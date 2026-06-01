from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.ai_gateway import AICapability, AIGateway, KeyConfig, ModelProfile
from app.core.security import decrypt_secret
from app.models.ai_gateway import (
    AIAPIKey,
    AIProvider,
    AIUsageEvent,
    EmbeddingModelProfile,
    LLMRotationPool,
)


class AIGatewayRuntimeError(RuntimeError):
    pass


def build_embedding_gateway(
    db: Session,
    *,
    rotator_options: dict | None = None,
) -> AIGateway:
    profiles = db.scalars(
        select(EmbeddingModelProfile).order_by(EmbeddingModelProfile.created_at.desc())
    ).all()
    for profile in profiles:
        provider = db.get(AIProvider, profile.provider_id)
        api_key = db.get(AIAPIKey, profile.api_key_id)
        if provider is None or api_key is None:
            continue
        if api_key.provider_id != profile.provider_id:
            continue
        if not _is_runtime_key_usable(provider, api_key, capability=AICapability.EMBEDDING):
            continue
        if not _is_gemini_embedding_provider(provider):
            continue

        runtime_profile_id = str(profile.id)
        return AIGateway(
            [
                ModelProfile(
                    id=runtime_profile_id,
                    capability=AICapability.EMBEDDING,
                    keys=[
                        KeyConfig(
                            id=str(api_key.id),
                            provider=provider.code,
                            model_name=_gemini_embedding_model_name(profile.model_name),
                            api_key=decrypt_secret(api_key.encrypted_api_key),
                            capability=AICapability.EMBEDDING.value,
                            model_profile_id=runtime_profile_id,
                            api_base=profile.api_base or api_key.api_base or provider.base_url,
                            endpoint_id=profile.endpoint_id or api_key.endpoint_id,
                            enabled=True,
                            locked=False,
                            extra={
                                **(profile.extra_parameters or {}),
                                **({"embedding_batch_size": profile.batch_size} if profile.batch_size else {}),
                            },
                        )
                    ],
                    default_params=dict(profile.extra_parameters or {}),
                    expected_dim=profile.embedding_dimensions,
                    max_batch_size=profile.batch_size,
                )
            ],
            default_embedding_profile_id=runtime_profile_id,
            usage_recorder=lambda record: _record_usage(db, record),
            rotator_options=rotator_options,
        )

    raise AIGatewayRuntimeError("No usable Gemini embedding model profile is available.")


def build_llm_gateway(
    db: Session,
    *,
    tenant_id: str | None = None,
    app_id: str | None = None,
    profile_id: UUID | None = None,
    rotator_options: dict | None = None,
) -> AIGateway:
    rows = _llm_pool_rows(db, tenant_id=tenant_id, app_id=app_id, profile_id=profile_id)
    keys: list[KeyConfig] = []
    default_params: dict = {}

    for pool in rows:
        profile = pool.profile
        provider = db.get(AIProvider, profile.provider_id)
        api_key = db.get(AIAPIKey, profile.api_key_id)
        if provider is None or api_key is None:
            continue
        if api_key.provider_id != profile.provider_id:
            continue
        if not _is_runtime_row_usable(pool, provider, api_key, capability=AICapability.LLM):
            continue

        if not default_params:
            default_params = {
                "timeout": profile.timeout_seconds,
                **({"temperature": profile.temperature} if profile.temperature is not None else {}),
                **({"top_p": profile.top_p} if profile.top_p is not None else {}),
                **({"top_k": profile.top_k} if profile.top_k else {}),
                **({"max_tokens": profile.max_output_tokens} if profile.max_output_tokens is not None else {}),
                **(profile.extra_parameters or {}),
            }
        keys.append(
            KeyConfig(
                id=str(api_key.id),
                provider=provider.code,
                model_name=_litellm_model_name(provider, profile.model_name),
                api_key=decrypt_secret(api_key.encrypted_api_key),
                capability=AICapability.LLM.value,
                model_profile_id=str(profile.id),
                api_base=profile.api_base or api_key.api_base or provider.base_url,
                endpoint_id=profile.endpoint_id or api_key.endpoint_id,
                enabled=True,
                locked=False,
                tenant_allowlist={str(pool.tenant_id)} if pool.tenant_id else set(),
                app_allowlist={str(pool.app_id)} if pool.app_id else set(),
                extra={
                    **(profile.extra_parameters or {}),
                    **_provider_override(provider),
                },
            )
        )

    if not keys:
        raise AIGatewayRuntimeError("No usable LLM model profile is available for this scope.")

    runtime_profile_id = str(profile_id) if profile_id else "runtime-llm-pool"
    return AIGateway(
        [
            ModelProfile(
                id=runtime_profile_id,
                capability=AICapability.LLM,
                keys=keys,
                default_params=default_params,
            )
        ],
        default_llm_profile_id=runtime_profile_id,
        usage_recorder=lambda record: _record_usage(db, record),
        rotator_options=rotator_options,
    )


def _llm_pool_rows(
    db: Session,
    *,
    tenant_id: str | None,
    app_id: str | None,
    profile_id: UUID | None,
) -> list[LLMRotationPool]:
    statement = (
        select(LLMRotationPool)
        .options(joinedload(LLMRotationPool.profile))
        .join(LLMRotationPool.profile)
        .order_by(
            LLMRotationPool.current_position.desc(),
            LLMRotationPool.rotation_order,
            LLMRotationPool.created_at,
        )
    )
    if profile_id is not None:
        statement = statement.where(LLMRotationPool.profile_id == profile_id)

    rows = list(db.scalars(statement).all())
    return [
        row
        for row in rows
        if _scope_matches(row.tenant_id, tenant_id) and _scope_matches(row.app_id, app_id)
    ]


def _scope_matches(row_scope: object, request_scope: str | None) -> bool:
    if row_scope is None:
        return True
    if request_scope is None:
        return False
    return str(row_scope) == request_scope


def _is_runtime_row_usable(
    pool: LLMRotationPool,
    provider: AIProvider,
    api_key: AIAPIKey,
    *,
    capability: AICapability,
) -> bool:
    if not pool.is_enabled or pool.is_locked or pool.today_quota_exhausted:
        return False
    return _is_runtime_key_usable(provider, api_key, capability=capability)


def _is_runtime_key_usable(
    provider: AIProvider,
    api_key: AIAPIKey,
    *,
    capability: AICapability,
) -> bool:
    if not provider.is_enabled or provider.is_locked:
        return False
    if not api_key.is_enabled or api_key.is_locked:
        return False
    if api_key.status in {"disabled", "locked"}:
        return False
    allowed_capabilities = [str(value).lower() for value in api_key.allowed_capabilities or []]
    return not allowed_capabilities or capability.value in allowed_capabilities


def _provider_override(provider: AIProvider) -> dict:
    provider_config = provider.provider_config or {}
    litellm_provider = provider_config.get("litellm_provider") or provider_config.get("custom_llm_provider")
    return {"custom_llm_provider": str(litellm_provider)} if litellm_provider else {}


def _is_gemini_embedding_provider(provider: AIProvider) -> bool:
    return str(provider.code or "").strip().lower() == "gemini"


def _gemini_embedding_model_name(model_name: str) -> str:
    clean_model_name = str(model_name or "").strip().lstrip("/")
    if clean_model_name.startswith("models/"):
        clean_model_name = clean_model_name.removeprefix("models/")
    if clean_model_name.startswith("gemini/"):
        clean_model_name = clean_model_name.removeprefix("gemini/")
    return clean_model_name


def _litellm_model_name(provider: AIProvider, model_name: str) -> str:
    provider_code = str(provider.code or "").strip().strip("/")
    clean_model_name = str(model_name or "").strip().lstrip("/")
    if not provider_code or not clean_model_name:
        return clean_model_name
    provider_prefix = f"{provider_code}/"
    if clean_model_name.startswith(provider_prefix):
        return clean_model_name
    return f"{provider_prefix}{clean_model_name}"


def _record_usage(db: Session, record) -> None:
    usage = dict(record.usage or {})
    event = AIUsageEvent(
        tenant_id=_uuid_or_none(record.tenant_id),
        app_id=_uuid_or_none(record.app_id),
        profile_id=_uuid_or_none(record.profile_id),
        provider_id=None,
        api_key_id=_uuid_or_none(record.key_id),
        capability=record.capability,
        model_name=record.model,
        endpoint=record.endpoint,
        success=record.success,
        attempts=record.attempts,
        latency_ms=record.latency_ms,
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
        total_tokens=usage.get("total_tokens"),
        input_count=record.input_count,
        verdict_action=record.last_verdict_action,
        error_reason=record.error_reason,
        metadata_json={
            "collection_id": record.collection_id,
            "endpoint_id": record.endpoint_id,
            "usage": usage,
        },
    )
    db.add(event)
    db.commit()


def _uuid_or_none(value: str | None) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(str(value))
    except ValueError:
        return None
