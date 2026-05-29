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
    EmbeddingRotationPool,
)


class AIGatewayRuntimeError(RuntimeError):
    pass


def build_embedding_gateway(
    db: Session,
    *,
    tenant_id: str | None = None,
    app_id: str | None = None,
    profile_id: UUID | None = None,
    rotator_options: dict | None = None,
) -> AIGateway:
    rows = _embedding_pool_rows(db, tenant_id=tenant_id, app_id=app_id, profile_id=profile_id)
    keys: list[KeyConfig] = []
    expected_dim: int | None = None
    max_batch_size: int | None = None
    default_params: dict = {}

    for pool in rows:
        profile = pool.profile
        provider = db.get(AIProvider, profile.provider_id)
        api_key = db.get(AIAPIKey, profile.api_key_id)
        if provider is None or api_key is None:
            continue
        if api_key.provider_id != profile.provider_id:
            continue
        if not _is_runtime_row_usable(pool, provider, api_key):
            continue

        if expected_dim is None:
            expected_dim = profile.embedding_dimensions
        elif profile.embedding_dimensions is not None and profile.embedding_dimensions != expected_dim:
            continue

        if max_batch_size is None:
            max_batch_size = profile.batch_size
        if not default_params:
            default_params = {
                "timeout": profile.timeout_seconds,
                **(profile.extra_parameters or {}),
            }

        keys.append(
            KeyConfig(
                id=str(api_key.id),
                provider=provider.code,
                model_name=_litellm_model_name(provider, profile.model_name),
                api_key=decrypt_secret(api_key.encrypted_api_key),
                capability=AICapability.EMBEDDING.value,
                api_base=profile.api_base or api_key.api_base or provider.base_url,
                endpoint_id=profile.endpoint_id or api_key.endpoint_id,
                enabled=True,
                locked=False,
                tenant_allowlist={str(pool.tenant_id)} if pool.tenant_id else set(),
                app_allowlist={str(pool.app_id)} if pool.app_id else set(),
                extra={
                    **(profile.extra_parameters or {}),
                    **({"embedding_batch_size": profile.batch_size} if profile.batch_size else {}),
                    **_provider_override(provider),
                },
            )
        )

    if not keys:
        raise AIGatewayRuntimeError("No usable embedding model profile is available for this scope.")

    runtime_profile_id = str(profile_id) if profile_id else "runtime-embedding-pool"
    gateway = AIGateway(
        [
            ModelProfile(
                id=runtime_profile_id,
                capability=AICapability.EMBEDDING,
                keys=keys,
                default_params=default_params,
                expected_dim=expected_dim,
                max_batch_size=max_batch_size,
            )
        ],
        default_embedding_profile_id=runtime_profile_id,
        usage_recorder=lambda record: _record_usage(db, record),
        rotator_options=rotator_options,
    )
    return gateway


def _embedding_pool_rows(
    db: Session,
    *,
    tenant_id: str | None,
    app_id: str | None,
    profile_id: UUID | None,
) -> list[EmbeddingRotationPool]:
    statement = (
        select(EmbeddingRotationPool)
        .options(joinedload(EmbeddingRotationPool.profile))
        .join(EmbeddingRotationPool.profile)
        .order_by(
            EmbeddingRotationPool.current_position.desc(),
            EmbeddingRotationPool.rotation_order,
            EmbeddingRotationPool.created_at,
        )
    )
    if profile_id is not None:
        statement = statement.where(EmbeddingRotationPool.profile_id == profile_id)

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


def _is_runtime_row_usable(pool: EmbeddingRotationPool, provider: AIProvider, api_key: AIAPIKey) -> bool:
    if not pool.is_enabled or pool.is_locked or pool.today_quota_exhausted:
        return False
    if not provider.is_enabled or provider.is_locked:
        return False
    if not api_key.is_enabled or api_key.is_locked:
        return False
    if api_key.status in {"disabled", "locked"}:
        return False
    allowed_capabilities = [str(capability).lower() for capability in api_key.allowed_capabilities or []]
    return not allowed_capabilities or AICapability.EMBEDDING.value in allowed_capabilities


def _provider_override(provider: AIProvider) -> dict:
    provider_config = provider.provider_config or {}
    litellm_provider = provider_config.get("litellm_provider") or provider_config.get("custom_llm_provider")
    return {"custom_llm_provider": str(litellm_provider)} if litellm_provider else {}


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
