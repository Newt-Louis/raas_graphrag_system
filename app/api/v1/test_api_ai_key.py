from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from litellm import acompletion
from sqlalchemy.orm import Session

from app.ai_gateway.base_rotator import usage_to_dict
from app.core.security import decrypt_secret
from app.db.session import get_db
from app.models.ai_gateway import AIAPIKey, AIProvider, LLMModelProfile
from app.schemas.test_api_ai_key import (
    TestAPIAIKeyRequest,
    TestAPIAIKeyResponse,
    TestLLMModelProfileRequest,
    TestLLMModelProfileResponse,
)


router = APIRouter(prefix="/test-api-ai-key", tags=["test-api-ai-key"])


@router.post("/llm/model-profiles/{profile_id}", response_model=TestLLMModelProfileResponse)
async def test_llm_model_profile(
    profile_id: UUID,
    payload: TestLLMModelProfileRequest,
    db: Session = Depends(get_db),
) -> TestLLMModelProfileResponse:
    profile = db.get(LLMModelProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="LLM model profile not found.")

    provider = db.get(AIProvider, profile.provider_id)
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found.")
    if not provider.is_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provider is disabled.")
    if provider.is_locked:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provider is locked.")

    api_key = db.get(AIAPIKey, profile.api_key_id)
    if api_key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found.")
    if api_key.provider_id != profile.provider_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="API key does not belong to profile provider.")
    if not api_key.is_enabled or api_key.status == "disabled":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="API key is disabled.")
    if api_key.is_locked or api_key.status == "locked":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="API key is locked.")
    allowed_capabilities = [str(capability).lower() for capability in api_key.allowed_capabilities or []]
    if allowed_capabilities and "llm" not in allowed_capabilities:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="API key is not allowed for LLM calls.")

    pool = profile.pool_state
    if pool is not None:
        if not pool.is_enabled:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="LLM model profile is disabled.")
        if pool.is_locked:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="LLM model profile is locked.")

    call_kwargs = _llm_profile_call_kwargs(
        profile=profile,
        provider=provider,
        api_key=api_key,
        message=payload.message,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
    )

    try:
        response = await acompletion(**call_kwargs)
    except Exception as exc:  # noqa: BLE001 - test endpoint returns provider error to admin UI
        return _llm_profile_response(profile, provider, api_key, success=False, error=str(exc))

    choice = response.choices[0]
    message = getattr(choice, "message", None)
    content = getattr(message, "content", "") if message is not None else ""
    return _llm_profile_response(
        profile,
        provider,
        api_key,
        success=True,
        response_text=content or "",
        usage=usage_to_dict(getattr(response, "usage", None)),
    )


@router.post("/{api_key_id}", response_model=TestAPIAIKeyResponse)
async def test_api_ai_key(
    api_key_id: UUID,
    payload: TestAPIAIKeyRequest,
    db: Session = Depends(get_db),
) -> TestAPIAIKeyResponse:
    api_key = db.get(AIAPIKey, api_key_id)
    if api_key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found.")
    if not api_key.is_enabled or api_key.status == "disabled":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="API key is disabled.")
    if api_key.is_locked or api_key.status == "locked":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="API key is locked.")

    call_kwargs = {
        "model": payload.model_name,
        "messages": [{"role": "user", "content": payload.message}],
        "api_key": decrypt_secret(api_key.encrypted_api_key),
        "temperature": payload.temperature,
        "max_tokens": payload.max_tokens,
        "timeout": 60,
    }
    if api_key.api_base:
        call_kwargs["api_base"] = api_key.api_base

    try:
        response = await acompletion(**call_kwargs)
    except Exception as exc:  # noqa: BLE001 - test endpoint returns provider error to admin UI
        return TestAPIAIKeyResponse(
            success=False,
            model_name=payload.model_name,
            error=str(exc),
        )

    choice = response.choices[0]
    message = getattr(choice, "message", None)
    content = getattr(message, "content", "") if message is not None else ""
    return TestAPIAIKeyResponse(
        success=True,
        model_name=payload.model_name,
        response_text=content or "",
        usage=usage_to_dict(getattr(response, "usage", None)),
    )


def _llm_profile_call_kwargs(
    *,
    profile: LLMModelProfile,
    provider: AIProvider,
    api_key: AIAPIKey,
    message: str,
    temperature: float | None,
    max_tokens: int | None,
) -> dict:
    call_kwargs = {
        **(profile.extra_parameters or {}),
        "model": _litellm_model_name(provider, profile.model_name),
        "messages": [{"role": "user", "content": message}],
        "api_key": decrypt_secret(api_key.encrypted_api_key),
        "timeout": profile.timeout_seconds or 60,
    }

    effective_temperature = temperature if temperature is not None else profile.temperature
    if effective_temperature is not None:
        call_kwargs["temperature"] = effective_temperature

    effective_max_tokens = max_tokens if max_tokens is not None else profile.max_output_tokens
    if effective_max_tokens is not None:
        call_kwargs["max_tokens"] = effective_max_tokens

    if profile.top_p is not None:
        call_kwargs["top_p"] = profile.top_p
    if profile.top_k is not None:
        call_kwargs["top_k"] = profile.top_k

    api_base = profile.api_base or api_key.api_base or provider.base_url
    if api_base:
        call_kwargs["api_base"] = api_base

    litellm_provider = _litellm_provider(provider)
    if litellm_provider:
        call_kwargs["custom_llm_provider"] = litellm_provider

    return call_kwargs


def _litellm_model_name(provider: AIProvider, model_name: str) -> str:
    provider_code = str(provider.code or "").strip().strip("/")
    clean_model_name = str(model_name or "").strip().lstrip("/")
    if not provider_code or not clean_model_name:
        return clean_model_name
    provider_prefix = f"{provider_code}/"
    if clean_model_name.startswith(provider_prefix):
        return clean_model_name
    return f"{provider_prefix}{clean_model_name}"


def _litellm_provider(provider: AIProvider) -> str | None:
    provider_config = provider.provider_config or {}
    value = provider_config.get("litellm_provider") or provider_config.get("custom_llm_provider")
    return str(value).strip() if value else None


def _llm_profile_response(
    profile: LLMModelProfile,
    provider: AIProvider,
    api_key: AIAPIKey,
    *,
    success: bool,
    response_text: str = "",
    usage: dict | None = None,
    error: str = "",
) -> TestLLMModelProfileResponse:
    return TestLLMModelProfileResponse(
        success=success,
        profile_id=str(profile.id),
        profile_name=profile.profile_name,
        provider_id=str(provider.id),
        provider_code=provider.code,
        api_key_id=str(api_key.id),
        model_name=profile.model_name,
        response_text=response_text,
        usage=usage or {},
        error=error,
    )
