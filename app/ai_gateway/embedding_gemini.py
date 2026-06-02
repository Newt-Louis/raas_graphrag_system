"""Gemini embedding adapter.

Embedding vectors in one LanceDB index must come from the same model,
dimension and retrieval task family. Unlike LLM calls, embedding calls do not
rotate across providers or API keys. This adapter deliberately binds one
Gemini profile to one Gemini API key and uses the official google-genai SDK.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any

from google import genai
from google.genai import types

from .base_rotator import RotationResult
from .key_pool import KeyConfig

logger = logging.getLogger("ai_gateway.embedding")

# Khi profile không khai báo batch_size, gom tối đa ngần này chunk vào một request
# embed_content để tránh vừa nổ token-limit (1 request khổng lồ) vừa spam API
# (mỗi chunk một request). Có thể giảm/đặt batch_size trên profile nếu model giới
# hạn số input mỗi request.
DEFAULT_EMBEDDING_BATCH_SIZE = 100

# Retry/backoff khi provider trả rate-limit/quá tải tạm thời (429/RESOURCE_EXHAUSTED,
# 503/UNAVAILABLE, deadline). Đây là cơ chế "ngủ rồi thử lại" thay vì văng lỗi đỏ.
_MAX_EMBEDDING_RETRIES = 5
_RETRY_BASE_DELAY_SECONDS = 2.0
_RETRY_MAX_DELAY_SECONDS = 30.0
_TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}
_TRANSIENT_MARKERS = (
    "resource_exhausted",
    "rate limit",
    "rate-limit",
    "ratelimit",
    "quota",
    "too many requests",
    "unavailable",
    "overloaded",
    "deadline",
    "timeout",
    "try again",
)


class EmbeddingDimensionMismatch(Exception):
    """Gemini returned vectors with a dimension that does not match the index."""


class EmbeddingRotator:
    """Compatibility facade for the previous embedding rotator public API.

    The class name and ``run(inputs=...)`` method remain stable for callers,
    but this implementation intentionally does not inherit ``BaseRotator`` and
    does not own a ``KeyPool``.
    """

    _CONFIG_KEYS = {
        "task_type",
        "title",
        "output_dimensionality",
        "mime_type",
        "auto_truncate",
        "document_ocr",
        "audio_track_extraction",
    }

    def __init__(
        self,
        keys: list[KeyConfig],
        *,
        expected_dim: int | None = None,
        default_params: dict[str, Any] | None = None,
        max_batch_size: int | None = None,
        profile_id: str | None = None,
        capability: str | None = None,
        **_ignored_rotator_options: Any,
    ) -> None:
        if len(keys) != 1:
            raise ValueError("Gemini embedding requires exactly one API key.")
        key = keys[0]
        if key.provider.strip().lower() != "gemini":
            raise ValueError("Gemini embedding only accepts provider='gemini'.")

        self.key = key
        self.expected_dim = expected_dim
        self.default_params = dict(default_params or {})
        self.max_batch_size = max_batch_size
        self.profile_id = profile_id
        self.capability = capability

    async def run(self, **kwargs: Any) -> RotationResult:
        started = time.perf_counter()
        result = RotationResult(
            success=False,
            profile_id=self.key.model_profile_id or self.profile_id,
            capability=self.capability,
            used_key_id=self.key.id,
            used_provider=self.key.provider,
            used_model=self.key.model_name,
            used_endpoint_id=self.key.endpoint_id,
            attempts=1,
        )
        try:
            result.data = await self._call(**kwargs)
            result.success = True
            return result
        except Exception as exc:
            result.final_reason = _embedding_error_reason(exc)
            return result
        finally:
            result.elapsed_ms = round((time.perf_counter() - started) * 1000, 3)

    async def _call(self, **kwargs: Any) -> list[list[float]]:
        inputs = kwargs.pop("inputs")
        if isinstance(inputs, (str, dict)):
            inputs = [inputs]
        inputs = list(inputs or [])
        if not inputs:
            raise ValueError("EmbeddingRotator.run() cần tham số `inputs`.")
        normalized_inputs = [_text_for_gemini_embedding(value) for value in inputs]

        default_batch_size = self.key.extra.get("embedding_batch_size", self.max_batch_size)
        batch_size = int(kwargs.pop("batch_size", default_batch_size or DEFAULT_EMBEDDING_BATCH_SIZE))
        if batch_size <= 0:
            raise ValueError("batch_size phải lớn hơn 0.")

        config = self._embed_config(kwargs)
        model_name = _gemini_model_name(self.key.model_name)
        vectors: list[list[float]] = []
        client = genai.Client(api_key=self.key.api_key)
        async with client.aio as async_client:
            for start in range(0, len(normalized_inputs), batch_size):
                batch = normalized_inputs[start:start + batch_size]
                response = await self._embed_batch_with_retry(
                    async_client,
                    model_name=model_name,
                    batch=batch,
                    config=config,
                )
                vectors.extend(self._extract(response, expected_n=len(batch)))
        return vectors

    async def _embed_batch_with_retry(
        self,
        async_client: Any,
        *,
        model_name: str,
        batch: list[str],
        config: types.EmbedContentConfig | None,
    ) -> Any:
        contents = [_content_for_gemini_embedding(text) for text in batch]
        last_exc: Exception | None = None
        for attempt in range(1, _MAX_EMBEDDING_RETRIES + 1):
            try:
                return await async_client.models.embed_content(
                    model=model_name,
                    contents=contents,
                    config=config,
                )
            except Exception as exc:  # noqa: BLE001 - phân loại lại ngay bên dưới
                if not _is_transient_error(exc) or attempt == _MAX_EMBEDDING_RETRIES:
                    raise
                last_exc = exc
                delay = min(_RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1)), _RETRY_MAX_DELAY_SECONDS)
                logger.warning(
                    "Gemini embedding rate-limited (lần %d/%d), chờ %.1fs rồi thử lại: %s",
                    attempt,
                    _MAX_EMBEDDING_RETRIES,
                    delay,
                    _redact_sensitive_text(str(exc))[:200],
                )
                await asyncio.sleep(delay)
        if last_exc is not None:  # pragma: no cover - vòng lặp luôn return/raise trước
            raise last_exc
        raise RuntimeError("Embedding retry loop kết thúc bất thường.")

    def _embed_config(self, overrides: dict[str, Any]) -> types.EmbedContentConfig | None:
        raw = {
            **self.default_params,
            **self.key.extra,
            **overrides,
        }
        raw.pop("embedding_batch_size", None)
        values = {
            key: value
            for key, value in raw.items()
            if key in self._CONFIG_KEYS and value is not None
        }
        if "output_dimensionality" not in values and self.expected_dim is not None:
            values["output_dimensionality"] = self.expected_dim
        return types.EmbedContentConfig(**values) if values else None

    def _extract(self, response: Any, *, expected_n: int) -> list[list[float]]:
        embeddings = list(getattr(response, "embeddings", None) or [])
        vectors = [list(getattr(embedding, "values", None) or []) for embedding in embeddings]
        if len(vectors) != expected_n:
            raise ValueError(f"Số vector ({len(vectors)}) != số input ({expected_n}).")
        if any(not vector for vector in vectors):
            raise ValueError("Gemini trả về vector rỗng.")
        if self.expected_dim is not None:
            for vector in vectors:
                if len(vector) != self.expected_dim:
                    raise EmbeddingDimensionMismatch(
                        f"Model trả vector {len(vector)} chiều, index cần {self.expected_dim}."
                    )
        return vectors

    def snapshot(self) -> list[dict[str, Any]]:
        return [
            {
                "id": self.key.id,
                "provider": self.key.provider,
                "model": self.key.model_name,
                "capability": self.key.capability,
                "endpoint_id": self.key.endpoint_id,
                "status": "active",
                "enabled": self.key.enabled,
                "locked": self.key.locked,
                "lock_reason": self.key.lock_reason,
            }
        ]


def _gemini_model_name(model_name: str) -> str:
    clean_name = model_name.strip().lstrip("/")
    if clean_name.startswith("models/"):
        clean_name = clean_name.removeprefix("models/")
    if clean_name.startswith("gemini/"):
        clean_name = clean_name.removeprefix("gemini/")
    return clean_name


def _text_for_gemini_embedding(value: Any) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        text = value.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
    if isinstance(value, list):
        text_parts = [
            str(part["text"]).strip()
            for part in value
            if isinstance(part, dict)
            and part.get("type") == "text"
            and isinstance(part.get("text"), str)
            and str(part["text"]).strip()
        ]
        if text_parts:
            return "\n".join(text_parts)
    raise ValueError("Gemini embedding hiện chỉ hỗ trợ input có nội dung text không rỗng.")


def _content_for_gemini_embedding(text: str) -> types.Content:
    # google-genai normalizes list[str] as parts of one Content for
    # gemini-embedding-2. Keep chunks as separate Content objects so each one
    # receives its own vector.
    return types.Content(parts=[types.Part(text=text)])


def _is_transient_error(exc: Exception) -> bool:
    """Lỗi tạm thời (rate-limit/quá tải) thì nên backoff + retry, không phải lỗi cấu hình."""
    if isinstance(exc, EmbeddingDimensionMismatch):
        return False
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if isinstance(code, int) and code in _TRANSIENT_STATUS_CODES:
        return True
    message = str(exc).lower()
    if any(str(status_code) in message for status_code in _TRANSIENT_STATUS_CODES):
        return True
    return any(marker in message for marker in _TRANSIENT_MARKERS)


def _embedding_error_reason(exc: Exception) -> str:
    detail = _redact_sensitive_text(str(exc))
    if isinstance(exc, EmbeddingDimensionMismatch):
        return f"Embedding Gemini khác chiều với LanceDB index: {detail}"
    return f"Gemini embedding failed: {detail or type(exc).__name__}"


def _redact_sensitive_text(text: str) -> str:
    if not text:
        return ""
    redacted = re.sub(
        r"(?i)(api[_-]?key|authorization|bearer|x-goog-api-key)(\s*[=:]\s*)\S+",
        r"\1\2[redacted]",
        text,
    )
    return re.sub(r"(?i)(AIza)[a-z0-9_-]{12,}", r"\1[redacted]", redacted)
