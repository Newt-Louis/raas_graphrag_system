"""
llm_rotator.py — Xoay vòng cho MODEL LLM (sinh câu trả lời cho khách).

Khác bộ thu thập dataset cũ: KHÔNG fix cứng prompt/seed/temperature/max_tokens.
Mọi tham số gọi vào lúc runtime qua `run(messages=..., **overrides)` để linh hoạt
theo từng câu hỏi của khách.

Khung này đã hoàn chỉnh phần xoay vòng + bắt lỗi (kế thừa BaseRotator).
Chỗ cần Claude CLI / bạn làm tiếp được đánh dấu  # TODO.
"""

from __future__ import annotations

from typing import Any

from litellm import acompletion

from .base_rotator import BaseRotator, ProviderCallResult, usage_to_dict
from .key_pool import KeyState


class LLMRotator(BaseRotator):
    """
    Dùng:
        rotator = LLMRotator(keys, default_params={"temperature": 0.3})
        result = await rotator.run(
            messages=[{"role": "user", "content": "..."}],
            max_tokens=1024,          # override per-request
        )
        if result.success:
            text = result.data        # chuỗi trả lời (hoặc dict nếu structured)
    """

    def __init__(self, keys, *, default_params: dict | None = None, **base_kwargs):
        super().__init__(keys, **base_kwargs)
        # Tham số mặc định, có thể bị override mỗi lần run()
        self.default_params: dict = {
            "timeout": 120,
            "temperature": 0.7,
            # KHÔNG set max_tokens cứng — để None / override theo nhu cầu
            **(default_params or {}),
        }

    async def _call(self, key: KeyState, **kwargs) -> Any:
        messages = kwargs.pop("messages")
        if not messages:
            raise ValueError("LLMRotator.run() cần tham số `messages`.")

        call_kwargs = {
            **self.default_params,
            **key.config.extra,
            **kwargs,                       # override per-request thắng
            "model": key.config.model_name,
            "messages": messages,
            "api_key": key.config.api_key,
        }
        if key.config.api_base:
            call_kwargs["api_base"] = key.config.api_base

        # Gọi litellm — lỗi sẽ được BaseRotator bắt và phân loại
        return_raw = bool(call_kwargs.pop("return_raw", False))
        response = await acompletion(**call_kwargs)
        if return_raw:
            data: Any = response
        else:
            data = self._extract(response)

        return ProviderCallResult(
            data=data,
            usage=usage_to_dict(getattr(response, "usage", None)),
        )

    # -----------------------------------------------------------------------
    def _extract(self, response: Any) -> Any:
        """
        Lấy nội dung từ litellm ModelResponse.
        TODO(claude-cli):
          - Xử lý streaming nếu bật stream=True (trả về async generator thay vì str).
          - Xử lý tool/function calling nếu dùng.
          - Nếu yêu cầu structured output: parse + validate JSON ở đây
            (giống parse_and_validate_dataset cũ nhưng cho schema câu trả lời).
        """
        choice = response.choices[0]
        content = choice.message.content
        if content is None:
            tool_calls = getattr(choice.message, "tool_calls", None)
            if tool_calls:
                return {"content": None, "tool_calls": tool_calls}
            raise ValueError("LLM trả về content rỗng.")
        return content

    # Tiện ích thường dùng cho RAG: ghép context vào messages
    @staticmethod
    def build_messages(
        question: str,
        context: str = "",
        history: list[dict] | None = None,
        system_prompt: str | None = None,
    ) -> list[dict]:
        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if history:
            messages.extend(history)
        user_content = f"{context}\n\n{question}" if context else question
        messages.append({"role": "user", "content": user_content})
        return messages
