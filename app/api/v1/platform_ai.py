from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.ai_gateway import (
    AIAPIKeyCreate,
    AIAPIKeyResponse,
    AIAPIKeyStatusUpdate,
    AIModelCatalogCreate,
    AIModelCatalogResponse,
    AIProviderCreate,
    AIProviderResponse,
    EmbeddingModelProfileCreate,
    EmbeddingModelProfileResponse,
    EmbeddingModelProfileUpdate,
    EmbeddingRotationPoolCreate,
    EmbeddingRotationPoolResponse,
    LLMModelProfileCreate,
    LLMModelProfileResponse,
    LLMModelProfileUpdate,
    LLMRotationPoolCreate,
    LLMRotationPoolResponse,
)
from app.services.ai_gateway_admin import (
    AIAdminConflictError,
    AIAdminNotFoundError,
    AIAdminService,
    AIAdminServiceError,
    AIAdminValidationError,
)


router = APIRouter(prefix="/platform/ai", tags=["platform-ai"])
T = TypeVar("T")


def get_ai_admin_service(db: Session = Depends(get_db)) -> AIAdminService:
    return AIAdminService(db)


@router.get("/providers", response_model=list[AIProviderResponse])
def list_providers(service: AIAdminService = Depends(get_ai_admin_service)):
    return _run_service(service.list_providers)


@router.post("/providers", response_model=AIProviderResponse, status_code=status.HTTP_201_CREATED)
def create_provider(
    payload: AIProviderCreate,
    service: AIAdminService = Depends(get_ai_admin_service),
):
    return _run_service(lambda: service.create_provider(payload))


@router.get("/api-keys", response_model=list[AIAPIKeyResponse])
def list_api_keys(service: AIAdminService = Depends(get_ai_admin_service)):
    return _run_service(service.list_api_keys)


@router.post("/api-keys", response_model=AIAPIKeyResponse, status_code=status.HTTP_201_CREATED)
def create_api_key(
    payload: AIAPIKeyCreate,
    service: AIAdminService = Depends(get_ai_admin_service),
):
    return _run_service(lambda: service.create_api_key(payload))


@router.patch("/api-keys/{api_key_id}/status", response_model=AIAPIKeyResponse)
def update_api_key_status(
    api_key_id: UUID,
    payload: AIAPIKeyStatusUpdate,
    service: AIAdminService = Depends(get_ai_admin_service),
):
    return _run_service(lambda: service.update_api_key_status(api_key_id, payload))


@router.delete("/api-keys/{api_key_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_api_key(
    api_key_id: UUID,
    service: AIAdminService = Depends(get_ai_admin_service),
):
    _run_service(lambda: service.delete_api_key(api_key_id))
    return None


@router.get("/model-catalog", response_model=list[AIModelCatalogResponse])
def list_model_catalog(service: AIAdminService = Depends(get_ai_admin_service)):
    return _run_service(service.list_models)


@router.post("/model-catalog", response_model=AIModelCatalogResponse, status_code=status.HTTP_201_CREATED)
def create_model_catalog_entry(
    payload: AIModelCatalogCreate,
    service: AIAdminService = Depends(get_ai_admin_service),
):
    return _run_service(lambda: service.create_model(payload))


@router.get("/llm/rotation-pools", response_model=list[LLMRotationPoolResponse])
def list_llm_rotation_pools(service: AIAdminService = Depends(get_ai_admin_service)):
    return _run_service(service.list_llm_pools)


@router.post("/llm/rotation-pools", response_model=LLMRotationPoolResponse, status_code=status.HTTP_201_CREATED)
def create_llm_rotation_pool(
    payload: LLMRotationPoolCreate,
    service: AIAdminService = Depends(get_ai_admin_service),
):
    return _run_service(lambda: service.create_llm_pool(payload))


@router.get("/llm/model-profiles", response_model=list[LLMModelProfileResponse])
def list_llm_model_profiles(service: AIAdminService = Depends(get_ai_admin_service)):
    return _run_service(service.list_llm_profiles)


@router.post("/llm/model-profiles", response_model=LLMModelProfileResponse, status_code=status.HTTP_201_CREATED)
def create_llm_model_profile(
    payload: LLMModelProfileCreate,
    service: AIAdminService = Depends(get_ai_admin_service),
):
    return _run_service(lambda: service.create_llm_profile(payload))


@router.patch("/llm/model-profiles/{profile_id}", response_model=LLMModelProfileResponse)
def update_llm_model_profile(
    profile_id: UUID,
    payload: LLMModelProfileUpdate,
    service: AIAdminService = Depends(get_ai_admin_service),
):
    return _run_service(lambda: service.update_llm_profile(profile_id, payload))


@router.delete("/llm/model-profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_llm_model_profile(
    profile_id: UUID,
    service: AIAdminService = Depends(get_ai_admin_service),
):
    _run_service(lambda: service.delete_llm_profile(profile_id))
    return None


@router.get("/embedding/rotation-pools", response_model=list[EmbeddingRotationPoolResponse])
def list_embedding_rotation_pools(service: AIAdminService = Depends(get_ai_admin_service)):
    return _run_service(service.list_embedding_pools)


@router.post(
    "/embedding/rotation-pools",
    response_model=EmbeddingRotationPoolResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_embedding_rotation_pool(
    payload: EmbeddingRotationPoolCreate,
    service: AIAdminService = Depends(get_ai_admin_service),
):
    return _run_service(lambda: service.create_embedding_pool(payload))


@router.get("/embedding/model-profiles", response_model=list[EmbeddingModelProfileResponse])
def list_embedding_model_profiles(service: AIAdminService = Depends(get_ai_admin_service)):
    return _run_service(service.list_embedding_profiles)


@router.post(
    "/embedding/model-profiles",
    response_model=EmbeddingModelProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_embedding_model_profile(
    payload: EmbeddingModelProfileCreate,
    service: AIAdminService = Depends(get_ai_admin_service),
):
    return _run_service(lambda: service.create_embedding_profile(payload))


@router.patch("/embedding/model-profiles/{profile_id}", response_model=EmbeddingModelProfileResponse)
def update_embedding_model_profile(
    profile_id: UUID,
    payload: EmbeddingModelProfileUpdate,
    service: AIAdminService = Depends(get_ai_admin_service),
):
    return _run_service(lambda: service.update_embedding_profile(profile_id, payload))


def _run_service(factory: Callable[[], T]) -> T:
    try:
        return factory()
    except AIAdminNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AIAdminValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except AIAdminConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except AIAdminServiceError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
