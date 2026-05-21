"""
rotation — Engine xoay vòng API key cho LLM & Embedding (multi-provider qua litellm).

Public API:
    from app.ai_gateway import (
        AIGateway, ModelProfile, AICapability, KeyConfig,
        LLMRotator, EmbeddingRotator, RotationResult,
    )

Luồng điển hình:
    profile = ModelProfile(
        id="llm-default",
        capability=AICapability.LLM,
        keys=[KeyConfig(id="1", provider="gemini", model_name="gemini/...", api_key=decrypt(...))],
    )
    gateway = AIGateway([profile])
    result = await gateway.complete(messages=[{"role": "user", "content": "Xin chào"}])
    if result.success:
        print(result.data, "via", result.used_model)
    else:
        print("Thất bại:", result.final_reason)
"""

from app.ai_gateway.base_rotator import AdminAlert, BaseRotator, ProviderCallResult, RotationResult
from app.ai_gateway.embedding_rotator import EmbeddingDimensionMismatch, EmbeddingRotator
from app.ai_gateway.errors import ErrorAction, Verdict, classify_error
from app.ai_gateway.gateway import AIGateway
from app.ai_gateway.key_pool import KeyConfig, KeyPool, KeyState, KeyStatus, PoolExhausted
from app.ai_gateway.llm_rotator import LLMRotator
from app.ai_gateway.types import AICapability, GatewayRequestContext, ModelProfile, UsageRecord

__all__ = [
    "LLMRotator",
    "EmbeddingRotator",
    "EmbeddingDimensionMismatch",
    "BaseRotator",
    "ProviderCallResult",
    "RotationResult",
    "AdminAlert",
    "AIGateway",
    "AICapability",
    "GatewayRequestContext",
    "ModelProfile",
    "UsageRecord",
    "KeyConfig",
    "KeyPool",
    "KeyState",
    "KeyStatus",
    "PoolExhausted",
    "ErrorAction",
    "Verdict",
    "classify_error",
]
