"""
rotation — Engine xoay vòng API key cho LLM & Embedding (multi-provider qua litellm).

Public API:
    from rotation import (
        LLMRotator, EmbeddingRotator, KeyConfig,
        RotationResult, AdminAlert, ErrorAction,
    )

Luồng điển hình:
    keys = [
        KeyConfig(id="1", provider="gemini", model_name="gemini/gemini-2.0-flash",
                  api_key=decrypt(cfg.api_key)),
        KeyConfig(id="2", provider="groq", model_name="groq/llama-3.3-70b-versatile",
                  api_key=decrypt(cfg2.api_key)),
    ]
    llm = LLMRotator(keys)
    result = await llm.run(messages=[{"role": "user", "content": "Xin chào"}])
    if result.success:
        print(result.data, "via", result.used_model)
    else:
        print("Thất bại:", result.final_reason)
"""

from app.ai_gateway.base_rotator import AdminAlert, BaseRotator, RotationResult
from app.core.rotation_mechanism import EmbeddingDimensionMismatch, EmbeddingRotator
from app.core.rotation_mechanism import ErrorAction, Verdict, classify_error
from app.core.rotation_mechanism import KeyConfig, KeyPool, KeyState, KeyStatus, PoolExhausted
from app.core.rotation_mechanism import LLMRotator

__all__ = [
    "LLMRotator",
    "EmbeddingRotator",
    "EmbeddingDimensionMismatch",
    "BaseRotator",
    "RotationResult",
    "AdminAlert",
    "KeyConfig",
    "KeyPool",
    "KeyState",
    "KeyStatus",
    "PoolExhausted",
    "ErrorAction",
    "Verdict",
    "classify_error",
]
