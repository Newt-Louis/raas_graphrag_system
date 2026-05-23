from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from litellm import acompletion
from sqlalchemy.orm import Session

from app.ai_gateway.base_rotator import usage_to_dict
from app.core.security import decrypt_secret
from app.db.session import get_db
from app.models.ai_gateway import AIAPIKey
from app.schemas.test_api_ai_key import TestAPIAIKeyRequest, TestAPIAIKeyResponse


router = APIRouter(prefix="/test-api-ai-key", tags=["test-api-ai-key"])


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
