"""
embedding_rotator.py — Xoay vòng cho MODEL EMBEDDING.

Khác LLM ở mấy điểm cốt yếu:
  - Output là VECTOR (list[float]), không phải text.
  - Thường gọi theo BATCH (nhiều đoạn text một lần) -> tiết kiệm request.
  - CHIỀU vector phải NHẤT QUÁN: nếu giữa chừng xoay sang model embedding KHÁC
    chiều thì index sẽ hỏng. -> Cảnh báo/khoá chiều bên dưới.

Khung xoay vòng + bắt lỗi kế thừa BaseRotator. Chỗ làm tiếp đánh dấu # TODO.
"""

from __future__ import annotations

from typing import Any

from litellm import aembedding

from .base_rotator import BaseRotator, ProviderCallResult, usage_to_dict
from .key_pool import KeyState


class EmbeddingDimensionMismatch(Exception):
    """Một key trả vector khác chiều so với chiều đã chốt -> không được trộn vào index."""


class EmbeddingRotator(BaseRotator):
    """
    Dùng:
        rotator = EmbeddingRotator(keys, expected_dim=768)
        result = await rotator.run(inputs=["đoạn 1", "đoạn 2", ...])
        if result.success:
            vectors = result.data        # list[list[float]], cùng thứ tự inputs

    expected_dim:
      - Đặt = chiều vector của index hiện có (vd LanceDB table đang dùng 768).
      - Nếu key trả về vector khác chiều -> ném EmbeddingDimensionMismatch
        (được phân loại như lỗi lạ -> SKIP_REQUEST + báo admin). Tránh làm bẩn index.
      - Để None nếu chấp nhận mọi chiều (KHÔNG khuyến nghị cho production).
    """

    def __init__(
        self,
        keys,
        *,
        expected_dim: int | None = None,
        default_params: dict | None = None,
        max_batch_size: int | None = None,
        **base_kwargs,
    ):
        super().__init__(keys, **base_kwargs)
        self.expected_dim = expected_dim
        self.default_params = {
            "timeout": 60,
            **(default_params or {}),
        }
        self.max_batch_size = max_batch_size

    async def _call(self, key: KeyState, **kwargs) -> Any:
        inputs = kwargs.pop("inputs")
        if isinstance(inputs, (str, dict)):
            inputs = [inputs]
        inputs = list(inputs or [])
        if not inputs:
            raise ValueError("EmbeddingRotator.run() cần tham số `inputs`.")

        default_batch_size = key.config.extra.get("embedding_batch_size", self.max_batch_size)
        batch_size = int(kwargs.pop("batch_size", default_batch_size or len(inputs)))
        if batch_size <= 0:
            raise ValueError("batch_size phải lớn hơn 0.")

        call_kwargs = {
            **self.default_params,
            **key.config.extra,
            **kwargs,
            "model": key.config.model_name,
            "api_key": key.config.api_key,
        }
        call_kwargs.pop("embedding_batch_size", None)
        if key.config.api_base:
            call_kwargs["api_base"] = key.config.api_base

        vectors: list[list[float]] = []
        usage: dict[str, Any] = {}
        for start in range(0, len(inputs), batch_size):
            batch = inputs[start:start + batch_size]
            response = await aembedding(**{**call_kwargs, "input": batch})
            vectors.extend(self._extract(response, expected_n=len(batch)))
            usage = self._merge_usage(usage, usage_to_dict(getattr(response, "usage", None)))

        return ProviderCallResult(data=vectors, usage=usage)

    # -----------------------------------------------------------------------
    def _extract(self, response: Any, expected_n: int) -> list[list[float]]:
        """
        litellm EmbeddingResponse.data = [{"embedding": [...], "index": i}, ...]
        TODO(claude-cli):
          - Một số provider giới hạn batch size -> nếu inputs quá lớn, tự chia nhỏ
            TRƯỚC khi gọi (đừng để dính BadRequest rồi mới xử lý).
          - Cân nhắc giữ map index -> để chắc thứ tự vector khớp thứ tự inputs.
        """
        items = sorted(response.data, key=self._item_index)
        vectors = [self._item_embedding(item) for item in items]

        if len(vectors) != expected_n:
            raise ValueError(
                f"Số vector ({len(vectors)}) != số input ({expected_n})."
            )

        if self.expected_dim is not None and vectors:
            dim = len(vectors[0])
            if dim != self.expected_dim:
                raise EmbeddingDimensionMismatch(
                    f"Model trả vector {dim} chiều, index cần {self.expected_dim}. "
                    f"KHÔNG trộn để tránh hỏng vector store."
                )
        return vectors

    def _item_index(self, item: Any) -> int:
        if isinstance(item, dict):
            return item.get("index", 0)
        return getattr(item, "index", 0)

    def _item_embedding(self, item: Any) -> list[float]:
        if isinstance(item, dict):
            return item["embedding"]
        return item.embedding

    def _merge_usage(self, current: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
        if not incoming:
            return current
        merged = dict(current)
        for key, value in incoming.items():
            if isinstance(value, (int, float)) and isinstance(merged.get(key), (int, float)):
                merged[key] += value
            else:
                merged[key] = value
        return merged
