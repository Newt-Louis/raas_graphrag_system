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

from .base_rotator import BaseRotator
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

    def __init__(self, keys, *, expected_dim: int | None = None, **base_kwargs):
        super().__init__(keys, **base_kwargs)
        self.expected_dim = expected_dim

    async def _call(self, key: KeyState, **kwargs) -> Any:
        inputs = kwargs.pop("inputs")
        if not inputs:
            raise ValueError("EmbeddingRotator.run() cần tham số `inputs` (list[str]).")

        call_kwargs = {
            "model": key.config.model_name,
            "input": inputs,
            "api_key": key.config.api_key,
            "timeout": kwargs.pop("timeout", 60),
            **kwargs,
        }
        if key.config.api_base:
            call_kwargs["api_base"] = key.config.api_base

        response = await aembedding(**call_kwargs)
        return self._extract(response, expected_n=len(inputs))

    # -----------------------------------------------------------------------
    def _extract(self, response: Any, expected_n: int) -> list[list[float]]:
        """
        litellm EmbeddingResponse.data = [{"embedding": [...], "index": i}, ...]
        TODO(claude-cli):
          - Một số provider giới hạn batch size -> nếu inputs quá lớn, tự chia nhỏ
            TRƯỚC khi gọi (đừng để dính BadRequest rồi mới xử lý).
          - Cân nhắc giữ map index -> để chắc thứ tự vector khớp thứ tự inputs.
        """
        items = sorted(response.data, key=lambda d: d.get("index", 0))
        vectors = [d["embedding"] for d in items]

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
