from __future__ import annotations

from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import encrypt_secret, hash_secret, mask_secret
from app.models.ai_gateway import AIAPIKey, EmbeddingModelProfile, LLMRotationPool
from app.models.platform import CustomerApp, Tenant
from app.repositories.ai_gateway import AIAdminRepository
from app.schemas.ai_gateway import (
    AIAPIKeyCreate,
    AIAPIKeyResponse,
    AIAPIKeyStatusUpdate,
    AIModelCatalogCreate,
    AIProviderCreate,
    AIProviderUpdate,
    EmbeddingModelProfileCreate,
    EmbeddingModelProfileResponse,
    EmbeddingModelProfileUpdate,
    LLMModelProfileCreate,
    LLMModelProfileResponse,
    LLMModelProfileUpdate,
    LLMRotationPoolCreate,
)


class AIAdminServiceError(Exception):
    pass


class AIAdminNotFoundError(AIAdminServiceError):
    pass


class AIAdminConflictError(AIAdminServiceError):
    pass


class AIAdminValidationError(AIAdminServiceError):
    pass


LLM_PROFILE_FIELDS = {
    "provider_id",
    "api_key_id",
    "model_id",
    "profile_name",
    "model_name",
    "api_base",
    "endpoint_id",
    "temperature",
    "top_p",
    "top_k",
    "max_output_tokens",
    "timeout_seconds",
    "cost_per_1k_input_tokens",
    "cost_per_1k_output_tokens",
    "extra_parameters",
}
POOL_FIELDS = {
    "pool_id",
    "rotation_order",
    "weight",
    "is_enabled",
    "is_locked",
    "lock_reason",
    "today_quota_exhausted",
    "daily_request_count",
    "minute_request_count",
}


class AIAdminService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = AIAdminRepository(db)

    def list_providers(self):
        return self.repository.list_providers()

    def create_provider(self, payload: AIProviderCreate):
        return self._commit_or_conflict(
            lambda: self.repository.create_provider(payload.model_dump()),
            "Provider code already exists.",
        )

    def update_provider(self, provider_id: UUID, payload: AIProviderUpdate):
        provider = self.repository.get_provider(provider_id)
        if provider is None:
            raise AIAdminNotFoundError("Provider not found.")

        values = payload.model_dump(exclude_unset=True)
        return self._commit_or_conflict(
            lambda: self.repository.update_provider(provider, values),
            "Provider code already exists.",
        )

    def delete_provider(self, provider_id: UUID) -> None:
        provider = self.repository.get_provider(provider_id)
        if provider is None:
            raise AIAdminNotFoundError("Provider not found.")

        self._commit_or_conflict(
            lambda: self.repository.delete_provider(provider),
            "Provider is still referenced by API keys, models, or profiles.",
        )

    def list_api_keys(self) -> list[AIAPIKeyResponse]:
        return [self._api_key_response(api_key) for api_key in self.repository.list_api_keys()]

    def create_api_key(self, payload: AIAPIKeyCreate) -> AIAPIKeyResponse:
        self._require_provider(payload.provider_id)
        raw_key = payload.api_key.strip()
        if not raw_key:
            raise AIAdminValidationError("API key cannot be blank.")
        values = payload.model_dump(exclude={"api_key"})
        key_hash = hash_secret(raw_key)
        existing_api_key = self.repository.get_api_key_by_provider_hash(payload.provider_id, key_hash)
        if existing_api_key is not None:
            existing_capabilities = {
                str(capability).strip().lower()
                for capability in existing_api_key.allowed_capabilities or []
                if str(capability).strip()
            }
            requested_capabilities = {
                str(capability).strip().lower()
                for capability in payload.allowed_capabilities or []
                if str(capability).strip()
            }
            updates = {}
            if existing_capabilities and requested_capabilities and not requested_capabilities.issubset(existing_capabilities):
                updates["allowed_capabilities"] = sorted(existing_capabilities | requested_capabilities)
            if not existing_api_key.api_base and payload.api_base:
                updates["api_base"] = payload.api_base
            if not existing_api_key.endpoint_id and payload.endpoint_id:
                updates["endpoint_id"] = payload.endpoint_id
            if updates:
                existing_api_key = self._commit_or_conflict(
                    lambda: self.repository.update_api_key(existing_api_key, updates),
                    "API key could not be updated.",
                )
            return self._api_key_response(existing_api_key)

        metadata_json = dict(values.get("metadata_json") or {})
        metadata_json["api_key_preview"] = mask_secret(raw_key)
        values["metadata_json"] = metadata_json
        values["key_hash"] = key_hash
        values["encrypted_api_key"] = encrypt_secret(raw_key)

        api_key = self._commit_or_conflict(
            lambda: self.repository.create_api_key(values),
            "API key could not be saved.",
        )
        return self._api_key_response(api_key)

    def update_api_key_status(self, api_key_id: UUID, payload: AIAPIKeyStatusUpdate) -> AIAPIKeyResponse:
        api_key = self.repository.get_api_key(api_key_id)
        if api_key is None:
            raise AIAdminNotFoundError("API key not found.")

        status_value = payload.status.lower()
        values = {
            "status": status_value,
            "is_enabled": status_value == "active",
            "is_locked": status_value == "locked",
        }
        if status_value == "cooldown":
            values["is_enabled"] = True

        updated = self._commit_or_conflict(
            lambda: self.repository.update_api_key(api_key, values),
            "API key status could not be updated.",
        )
        return self._api_key_response(updated)

    def delete_api_key(self, api_key_id: UUID) -> None:
        api_key = self.repository.get_api_key(api_key_id)
        if api_key is None:
            raise AIAdminNotFoundError("API key not found.")

        self._commit_or_conflict(
            lambda: self.repository.delete_api_key(api_key),
            "API key is still referenced by model profiles.",
        )

    def list_models(self):
        return self.repository.list_models()

    def create_model(self, payload: AIModelCatalogCreate):
        self._require_provider(payload.provider_id)
        values = payload.model_dump()
        values["capability"] = values["capability"].strip().lower()
        return self._commit_or_conflict(
            lambda: self.repository.create_model(values),
            "Model already exists for this provider and capability.",
        )

    def list_llm_pools(self):
        return self.repository.list_llm_pools()

    def create_llm_pool(self, payload: LLMRotationPoolCreate):
        self._validate_scope(payload.tenant_id, payload.app_id)
        if self.repository.get_llm_profile(payload.profile_id) is None:
            raise AIAdminNotFoundError("LLM model profile not found.")
        return self._commit_or_conflict(
            lambda: self.repository.create_llm_pool(payload.model_dump()),
            "LLM rotation pool already exists for this profile.",
        )

    def list_llm_profiles(self) -> list[LLMModelProfileResponse]:
        return [self._llm_profile_response(pool) for pool in self.repository.list_llm_profiles()]

    def create_llm_profile(self, payload: LLMModelProfileCreate) -> LLMModelProfileResponse:
        self._validate_llm_profile_refs(
            provider_id=payload.provider_id,
            api_key_id=payload.api_key_id,
            model_id=payload.model_id,
        )
        values = payload.model_dump()
        profile_values, pool_values = self._split_values(values, LLM_PROFILE_FIELDS, POOL_FIELDS)

        def create_profile_and_pool():
            profile = self.repository.create_llm_profile(profile_values)
            pool_values.pop("pool_id", None)
            pool_values["id"] = profile.id
            pool_values["profile_id"] = profile.id
            pool_values["name"] = profile.profile_name
            return self.repository.create_llm_pool(pool_values)

        pool = self._commit_or_conflict(
            create_profile_and_pool,
            "LLM model profile already exists in runtime pool.",
        )
        return self._llm_profile_response(pool)

    def update_llm_profile(self, profile_id: UUID, payload: LLMModelProfileUpdate) -> LLMModelProfileResponse:
        profile = self.repository.get_llm_profile(profile_id)
        if profile is None:
            raise AIAdminNotFoundError("LLM model profile not found.")

        values = payload.model_dump(exclude_unset=True)
        pool = self.repository.get_llm_pool(values["pool_id"]) if values.get("pool_id") else None
        if pool is None:
            pool = self.repository.get_llm_pool_by_profile(profile_id)
        if pool is None:
            raise AIAdminNotFoundError("LLM model profile runtime pool row not found.")

        self._validate_llm_profile_refs(
            provider_id=values.get("provider_id", profile.provider_id),
            api_key_id=values.get("api_key_id", profile.api_key_id),
            model_id=values.get("model_id", profile.model_id),
        )
        profile_values, pool_values = self._split_values(values, LLM_PROFILE_FIELDS, POOL_FIELDS)
        pool_values.pop("pool_id", None)

        def update_profile_and_pool():
            if profile_values:
                self.repository.update_llm_profile(profile, profile_values)
                if "profile_name" in profile_values and "name" not in pool_values:
                    pool_values["name"] = profile_values["profile_name"]
            if pool_values:
                return self.repository.update_llm_pool(pool, pool_values)
            return pool

        updated_pool = self._commit_or_conflict(
            update_profile_and_pool,
            "LLM model profile runtime pool row could not be updated.",
        )
        return self._llm_profile_response(updated_pool)

    def delete_llm_profile(self, profile_id: UUID) -> None:
        profile = self.repository.get_llm_profile(profile_id)
        if profile is None:
            raise AIAdminNotFoundError("LLM model profile not found.")

        self._commit_or_conflict(
            lambda: self.repository.delete_llm_profile(profile),
            "LLM model profile could not be deleted.",
        )

    def list_embedding_profiles(self) -> list[EmbeddingModelProfileResponse]:
        return [self._embedding_profile_response(profile) for profile in self.repository.list_embedding_profiles()]

    def create_embedding_profile(self, payload: EmbeddingModelProfileCreate) -> EmbeddingModelProfileResponse:
        self._validate_embedding_profile_refs(
            provider_id=payload.provider_id,
            api_key_id=payload.api_key_id,
            model_id=payload.model_id,
        )
        profile = self._commit_or_conflict(
            lambda: self.repository.create_embedding_profile(payload.model_dump()),
            "Embedding model profile could not be saved.",
        )
        return self._embedding_profile_response(profile)

    def update_embedding_profile(self, profile_id: UUID, payload: EmbeddingModelProfileUpdate) -> EmbeddingModelProfileResponse:
        profile = self.repository.get_embedding_profile(profile_id)
        if profile is None:
            raise AIAdminNotFoundError("Embedding model profile not found.")

        values = payload.model_dump(exclude_unset=True)
        self._validate_embedding_profile_refs(
            provider_id=values.get("provider_id", profile.provider_id),
            api_key_id=values.get("api_key_id", profile.api_key_id),
            model_id=values.get("model_id", profile.model_id),
        )

        updated_profile = self._commit_or_conflict(
            lambda: self.repository.update_embedding_profile(profile, values),
            "Embedding model profile could not be updated.",
        )
        return self._embedding_profile_response(updated_profile)

    def delete_embedding_profile(self, profile_id: UUID) -> None:
        profile = self.repository.get_embedding_profile(profile_id)
        if profile is None:
            raise AIAdminNotFoundError("Embedding model profile not found.")

        self._commit_or_conflict(
            lambda: self.repository.delete_embedding_profile(profile),
            "Embedding model profile could not be deleted.",
        )

    def _validate_llm_profile_refs(
        self,
        *,
        provider_id: UUID | None,
        api_key_id: UUID | None,
        model_id: UUID | None,
    ) -> None:
        if provider_id is None:
            raise AIAdminValidationError("provider_id is required.")
        if api_key_id is None:
            raise AIAdminValidationError("api_key_id is required.")
        self._require_provider(provider_id)
        api_key = self.db.get(AIAPIKey, api_key_id)
        if api_key is None:
            raise AIAdminNotFoundError("API key not found.")
        if api_key.provider_id != provider_id:
            raise AIAdminValidationError("api_key_id does not belong to provider_id.")
        if model_id is not None:
            model = self.repository.get_model(model_id)
            if model is None:
                raise AIAdminNotFoundError("Model catalog entry not found.")
            if model.provider_id != provider_id:
                raise AIAdminValidationError("model_id does not belong to provider_id.")
            if model.capability.lower() != "llm":
                raise AIAdminValidationError("model_id must reference an LLM model.")

    def _validate_embedding_profile_refs(
        self,
        *,
        provider_id: UUID | None,
        api_key_id: UUID | None,
        model_id: UUID | None,
    ) -> None:
        if provider_id is None:
            raise AIAdminValidationError("provider_id is required.")
        if api_key_id is None:
            raise AIAdminValidationError("api_key_id is required.")
        provider = self.repository.get_provider(provider_id)
        if provider is None:
            raise AIAdminNotFoundError("Provider not found.")
        if str(provider.code or "").strip().lower() != "gemini":
            raise AIAdminValidationError("Embedding model profiles currently require provider code 'gemini'.")
        api_key = self.db.get(AIAPIKey, api_key_id)
        if api_key is None:
            raise AIAdminNotFoundError("API key not found.")
        if api_key.provider_id != provider_id:
            raise AIAdminValidationError("api_key_id does not belong to provider_id.")
        if model_id is not None:
            model = self.repository.get_model(model_id)
            if model is None:
                raise AIAdminNotFoundError("Model catalog entry not found.")
            if model.provider_id != provider_id:
                raise AIAdminValidationError("model_id does not belong to provider_id.")
            if model.capability.lower() != "embedding":
                raise AIAdminValidationError("model_id must reference an embedding model.")

    def _require_provider(self, provider_id: UUID) -> None:
        if self.repository.get_provider(provider_id) is None:
            raise AIAdminNotFoundError("Provider not found.")

    def _require_llm_pool(self, pool_id: UUID) -> None:
        if self.repository.get_llm_pool(pool_id) is None:
            raise AIAdminNotFoundError("LLM rotation pool not found.")

    def _validate_scope(self, tenant_id: UUID | None, app_id: UUID | None) -> None:
        if tenant_id is not None and self.db.get(Tenant, tenant_id) is None:
            raise AIAdminNotFoundError("Tenant not found.")

        if app_id is None:
            return

        app = self.db.get(CustomerApp, app_id)
        if app is None:
            raise AIAdminNotFoundError("Customer app not found.")
        if tenant_id is not None and app.tenant_id != tenant_id:
            raise AIAdminValidationError("app_id does not belong to tenant_id.")

    def _split_values(self, values: dict, profile_fields: set[str], entry_fields: set[str]) -> tuple[dict, dict]:
        profile_values = {key: value for key, value in values.items() if key in profile_fields}
        entry_values = {key: value for key, value in values.items() if key in entry_fields}
        return profile_values, entry_values

    def _llm_profile_response(self, pool: LLMRotationPool) -> LLMModelProfileResponse:
        profile = pool.profile
        return LLMModelProfileResponse(
            id=profile.id,
            pool_id=pool.id,
            provider_id=profile.provider_id,
            api_key_id=profile.api_key_id,
            model_id=profile.model_id,
            profile_name=profile.profile_name,
            model_name=profile.model_name,
            api_base=profile.api_base,
            endpoint_id=profile.endpoint_id,
            rotation_order=pool.rotation_order,
            weight=pool.weight,
            is_enabled=pool.is_enabled,
            is_locked=pool.is_locked,
            lock_reason=pool.lock_reason,
            today_quota_exhausted=pool.today_quota_exhausted,
            daily_request_count=pool.daily_request_count,
            minute_request_count=pool.minute_request_count,
            temperature=profile.temperature,
            top_p=profile.top_p,
            top_k=profile.top_k,
            max_output_tokens=profile.max_output_tokens,
            timeout_seconds=profile.timeout_seconds,
            cost_per_1k_input_tokens=profile.cost_per_1k_input_tokens,
            cost_per_1k_output_tokens=profile.cost_per_1k_output_tokens,
            extra_parameters=profile.extra_parameters,
            created_at=profile.created_at,
            updated_at=profile.updated_at,
        )

    def _embedding_profile_response(self, profile: EmbeddingModelProfile) -> EmbeddingModelProfileResponse:
        return EmbeddingModelProfileResponse(
            id=profile.id,
            provider_id=profile.provider_id,
            api_key_id=profile.api_key_id,
            model_id=profile.model_id,
            profile_name=profile.profile_name,
            model_name=profile.model_name,
            api_base=profile.api_base,
            endpoint_id=profile.endpoint_id,
            embedding_dimensions=profile.embedding_dimensions,
            batch_size=profile.batch_size,
            retrieval_top_k=profile.retrieval_top_k,
            timeout_seconds=profile.timeout_seconds,
            cost_per_1k_tokens=profile.cost_per_1k_tokens,
            extra_parameters=profile.extra_parameters,
            created_at=profile.created_at,
            updated_at=profile.updated_at,
        )

    def _api_key_response(self, api_key: AIAPIKey) -> AIAPIKeyResponse:
        metadata_json = dict(api_key.metadata_json or {})
        return AIAPIKeyResponse(
            id=api_key.id,
            provider_id=api_key.provider_id,
            name=api_key.name,
            api_key_preview=str(metadata_json.get("api_key_preview") or ""),
            api_base=api_key.api_base,
            endpoint_id=api_key.endpoint_id,
            allowed_capabilities=list(api_key.allowed_capabilities or []),
            status=api_key.status,
            is_enabled=api_key.is_enabled,
            is_locked=api_key.is_locked,
            lock_reason=api_key.lock_reason,
            daily_quota_limit=api_key.daily_quota_limit,
            minute_quota_limit=api_key.minute_quota_limit,
            metadata_json=metadata_json,
            created_at=api_key.created_at,
            updated_at=api_key.updated_at,
        )

    def _commit_or_conflict(self, factory, conflict_message: str):
        try:
            result = factory()
            self.db.commit()
            return result
        except IntegrityError as exc:
            self.db.rollback()
            raise AIAdminConflictError(conflict_message) from exc
