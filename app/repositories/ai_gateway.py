from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ai_gateway import (
    AIAPIKey,
    AIModelCatalog,
    AIProvider,
    EmbeddingModelProfile,
    EmbeddingRotationPool,
    LLMModelProfile,
    LLMRotationPool,
)


class AIAdminRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_providers(self) -> Sequence[AIProvider]:
        return self.db.scalars(select(AIProvider).order_by(AIProvider.code)).all()

    def get_provider(self, provider_id: UUID) -> AIProvider | None:
        return self.db.get(AIProvider, provider_id)

    def create_provider(self, values: dict) -> AIProvider:
        provider = AIProvider(**values)
        self.db.add(provider)
        self.db.flush()
        self.db.refresh(provider)
        return provider

    def list_api_keys(self) -> Sequence[AIAPIKey]:
        return self.db.scalars(select(AIAPIKey).order_by(AIAPIKey.created_at.desc())).all()

    def create_api_key(self, values: dict) -> AIAPIKey:
        api_key = AIAPIKey(**values)
        self.db.add(api_key)
        self.db.flush()
        self.db.refresh(api_key)
        return api_key

    def list_models(self) -> Sequence[AIModelCatalog]:
        return self.db.scalars(select(AIModelCatalog).order_by(AIModelCatalog.model_name)).all()

    def get_model(self, model_id: UUID) -> AIModelCatalog | None:
        return self.db.get(AIModelCatalog, model_id)

    def create_model(self, values: dict) -> AIModelCatalog:
        model = AIModelCatalog(**values)
        self.db.add(model)
        self.db.flush()
        self.db.refresh(model)
        return model

    def list_llm_pools(self) -> Sequence[LLMRotationPool]:
        return self.db.scalars(select(LLMRotationPool).order_by(LLMRotationPool.name)).all()

    def get_llm_pool(self, pool_id: UUID) -> LLMRotationPool | None:
        return self.db.get(LLMRotationPool, pool_id)

    def create_llm_pool(self, values: dict) -> LLMRotationPool:
        pool = LLMRotationPool(**values)
        self.db.add(pool)
        self.db.flush()
        self.db.refresh(pool)
        return pool

    def list_llm_profiles(self) -> Sequence[LLMModelProfile]:
        return self.db.scalars(
            select(LLMModelProfile).order_by(
                LLMModelProfile.pool_id,
                LLMModelProfile.rotation_order,
                LLMModelProfile.profile_name,
            )
        ).all()

    def get_llm_profile(self, profile_id: UUID) -> LLMModelProfile | None:
        return self.db.get(LLMModelProfile, profile_id)

    def create_llm_profile(self, values: dict) -> LLMModelProfile:
        profile = LLMModelProfile(**values)
        self.db.add(profile)
        self.db.flush()
        self.db.refresh(profile)
        return profile

    def update_llm_profile(self, profile: LLMModelProfile, values: dict) -> LLMModelProfile:
        for key, value in values.items():
            setattr(profile, key, value)
        self.db.flush()
        self.db.refresh(profile)
        return profile

    def list_embedding_pools(self) -> Sequence[EmbeddingRotationPool]:
        return self.db.scalars(select(EmbeddingRotationPool).order_by(EmbeddingRotationPool.name)).all()

    def get_embedding_pool(self, pool_id: UUID) -> EmbeddingRotationPool | None:
        return self.db.get(EmbeddingRotationPool, pool_id)

    def create_embedding_pool(self, values: dict) -> EmbeddingRotationPool:
        pool = EmbeddingRotationPool(**values)
        self.db.add(pool)
        self.db.flush()
        self.db.refresh(pool)
        return pool

    def list_embedding_profiles(self) -> Sequence[EmbeddingModelProfile]:
        return self.db.scalars(
            select(EmbeddingModelProfile).order_by(
                EmbeddingModelProfile.pool_id,
                EmbeddingModelProfile.rotation_order,
                EmbeddingModelProfile.profile_name,
            )
        ).all()

    def get_embedding_profile(self, profile_id: UUID) -> EmbeddingModelProfile | None:
        return self.db.get(EmbeddingModelProfile, profile_id)

    def create_embedding_profile(self, values: dict) -> EmbeddingModelProfile:
        profile = EmbeddingModelProfile(**values)
        self.db.add(profile)
        self.db.flush()
        self.db.refresh(profile)
        return profile

    def update_embedding_profile(
        self,
        profile: EmbeddingModelProfile,
        values: dict,
    ) -> EmbeddingModelProfile:
        for key, value in values.items():
            setattr(profile, key, value)
        self.db.flush()
        self.db.refresh(profile)
        return profile
