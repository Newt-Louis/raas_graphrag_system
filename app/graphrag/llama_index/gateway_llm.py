from __future__ import annotations

import asyncio
import concurrent.futures
from collections.abc import Awaitable, Callable
from typing import Any

from llama_index.core.base.llms.types import (
    CompletionResponse,
    CompletionResponseGen,
    LLMMetadata,
)
from llama_index.core.llms import CustomLLM
from llama_index.core.llms.callbacks import llm_completion_callback
from pydantic import PrivateAttr

ACompleteFn = Callable[[str], Awaitable[str]]

# Trần token đầu ra mặc định cho các tác vụ điều phối (routing/text2cypher) và để
# LLM có không gian trả lời chi tiết, không bị cụt.
DEFAULT_GATEWAY_LLM_MAX_TOKENS = 4_096
DEFAULT_GATEWAY_LLM_CONTEXT_WINDOW = 32_768


class GatewayLLM(CustomLLM):
    """LlamaIndex ``CustomLLM`` bọc cơ chế gọi LLM xoay vòng (LiteLLM) của AI Gateway.

    Mục đích DUY NHẤT: cho các thành phần điều phối/truy vấn của LlamaIndex
    (``RouterRetriever``/``LLMSingleSelector``, ``TextToCypherRetriever``) gọi được
    LLM, nhưng việc thực thi model vẫn đi qua AI Gateway nội bộ (rotation key/quota/
    usage/LiteLLM). KHÔNG dùng ``llama-index-llms-litellm`` như một lớp trung gian
    riêng. Phần sinh câu trả lời chat cuối cùng vẫn gọi gateway trực tiếp như cũ.
    """

    _acomplete_fn: ACompleteFn = PrivateAttr()
    _model_name: str = PrivateAttr()
    _max_tokens: int = PrivateAttr()
    _context_window: int = PrivateAttr()

    def __init__(
        self,
        acomplete_fn: ACompleteFn,
        *,
        model_name: str = "gateway-llm",
        max_tokens: int = DEFAULT_GATEWAY_LLM_MAX_TOKENS,
        context_window: int = DEFAULT_GATEWAY_LLM_CONTEXT_WINDOW,
    ) -> None:
        super().__init__()
        self._acomplete_fn = acomplete_fn
        self._model_name = model_name
        self._max_tokens = max_tokens
        self._context_window = context_window

    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(
            context_window=self._context_window,
            num_output=self._max_tokens,
            model_name=self._model_name,
            is_chat_model=True,
        )

    @llm_completion_callback()
    def complete(self, prompt: str, formatted: bool = False, **kwargs: Any) -> CompletionResponse:
        text = _run_coro(self._acomplete_fn(prompt))
        return CompletionResponse(text=text)

    @llm_completion_callback()
    async def acomplete(self, prompt: str, formatted: bool = False, **kwargs: Any) -> CompletionResponse:
        text = await self._acomplete_fn(prompt)
        return CompletionResponse(text=text)

    @llm_completion_callback()
    def stream_complete(self, prompt: str, formatted: bool = False, **kwargs: Any) -> CompletionResponseGen:
        text = _run_coro(self._acomplete_fn(prompt))

        def _gen() -> CompletionResponseGen:
            yield CompletionResponse(text=text, delta=text)

        return _gen()


def _run_coro(coro: Awaitable):
    """Chạy coroutine từ ngữ cảnh sync.

    LlamaIndex selector/retriever gọi ``complete`` kiểu sync. Khi chạy trong thread
    riêng (không có event loop) thì ``asyncio.run`` dùng trực tiếp; nếu đang trong
    event loop thì chạy coroutine trên thread phụ để không vỡ loop hiện tại.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()
