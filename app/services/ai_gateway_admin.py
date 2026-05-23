from __future__ import annotations

from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import encrypt_secret, hash_secret, mask_secret
from app.models.ai_gateway import AIAPIKey
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
    EmbeddingModelProfileUpdate,
    EmbeddingRotationPoolCreate,
    LLMModelProfileCreate,
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
        metadata_json = dict(values.get("metadata_json") or {})
        metadata_json["api_key_preview"] = mask_secret(raw_key)
        values["metadata_json"] = metadata_json
        values["key_hash"] = hash_secret(raw_key)
        values["encrypted_api_key"] = encrypt_secret(raw_key)

        api_key = self._commit_or_conflict(
            lambda: self.repository.create_api_key(values),
            "API key already exists.",
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
        return self._commit_or_conflict(
            lambda: self.repository.create_llm_pool(payload.model_dump()),
            "LLM rotation pool already exists for this scope and name.",
        )

    def list_llm_profiles(self):
        return self.repository.list_llm_profiles()

    def create_llm_profile(self, payload: LLMModelProfileCreate):
        self._validate_llm_profile_refs(
            pool_id=payload.pool_id,
            provider_id=payload.provider_id,
            api_key_id=payload.api_key_id,
            model_id=payload.model_id,
        )
        return self._commit_or_conflict(
            lambda: self.repository.create_llm_profile(payload.model_dump()),
            "LLM model profile rotation_order already exists in this pool.",
        )

    def update_llm_profile(self, profile_id: UUID, payload: LLMModelProfileUpdate):
        profile = self.repository.get_llm_profile(profile_id)
        if profile is None:
            raise AIAdminNotFoundError("LLM model profile not found.")

        values = payload.model_dump(exclude_unset=True)
        self._validate_llm_profile_refs(
            pool_id=values.get("pool_id", profile.pool_id),
            provider_id=values.get("provider_id", profile.provider_id),
            api_key_id=values.get("api_key_id", profile.api_key_id),
            model_id=values.get("model_id", profile.model_id),
        )
        return self._commit_or_conflict(
            lambda: self.repository.update_llm_profile(profile, values),
            "LLM model profile rotation_order already exists in this pool.",
        )

    def delete_llm_profile(self, profile_id: UUID) -> None:
        profile = self.repository.get_llm_profile(profile_id)
        if profile is None:
            raise AIAdminNotFoundError("LLM model profile not found.")

        self._commit_or_conflict(
            lambda: self.repository.delete_llm_profile(profile),
            "LLM model profile could not be deleted.",
        )

    def list_embedding_pools(self):
        return self.repository.list_embedding_pools()

    def create_embedding_pool(self, payload: EmbeddingRotationPoolCreate):
        self._validate_scope(payload.tenant_id, payload.app_id)
        return self._commit_or_conflict(
            lambda: self.repository.create_embedding_pool(payload.model_dump()),
            "Embedding rotation pool already exists for this scope and name.",
        )

    def list_embedding_profiles(self):
        return self.repository.list_embedding_profiles()

    def create_embedding_profile(self, payload: EmbeddingModelProfileCreate):
        self._validate_embedding_profile_refs(
            pool_id=payload.pool_id,
            provider_id=payload.provider_id,
            api_key_id=payload.api_key_id,
            model_id=payload.model_id,
        )
        return self._commit_or_conflict(
            lambda: self.repository.create_embedding_profile(payload.model_dump()),
            "Embedding model profile rotation_order already exists in this pool.",
        )

    def update_embedding_profile(self, profile_id: UUID, payload: EmbeddingModelProfileUpdate):
        profile = self.repository.get_embedding_profile(profile_id)
        if profile is None:
            raise AIAdminNotFoundError("Embedding model profile not found.")

        values = payload.model_dump(exclude_unset=True)
        self._validate_embedding_profile_refs(
            pool_id=values.get("pool_id", profile.pool_id),
            provider_id=values.get("provider_id", profile.provider_id),
            api_key_id=values.get("api_key_id", profile.api_key_id),
            model_id=values.get("model_id", profile.model_id),
        )
        return self._commit_or_conflict(
            lambda: self.repository.update_embedding_profile(profile, values),
            "Embedding model profile rotation_order already exists in this pool.",
        )

    def _validate_llm_profile_refs(
        self,
        *,
        pool_id: UUID,
        provider_id: UUID,
        api_key_id: UUID,
        model_id: UUID | None,
    ) -> None:
        self._require_llm_pool(pool_id)
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
        pool_id: UUID,
        provider_id: UUID,
        api_key_id: UUID,
        model_id: UUID | None,
    ) -> None:
        self._require_embedding_pool(pool_id)
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
            if model.capability.lower() != "embedding":
                raise AIAdminValidationError("model_id must reference an embedding model.")

    def _require_provider(self, provider_id: UUID) -> None:
        if self.repository.get_provider(provider_id) is None:
            raise AIAdminNotFoundError("Provider not found.")

    def _require_llm_pool(self, pool_id: UUID) -> None:
        if self.repository.get_llm_pool(pool_id) is None:
            raise AIAdminNotFoundError("LLM rotation pool not found.")

    def _require_embedding_pool(self, pool_id: UUID) -> None:
        if self.repository.get_embedding_pool(pool_id) is None:
            raise AIAdminNotFoundError("Embedding rotation pool not found.")

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
