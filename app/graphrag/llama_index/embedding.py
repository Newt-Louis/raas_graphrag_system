from __future__ import annotations

import asyncio
import concurrent.futures
from collections.abc import Awaitable, Callable

from llama_index.core.base.embeddings.base import BaseEmbedding
from pydantic import PrivateAttr

EmbedTextsFn = Callable[[list[str]], Awaitable[list[list[float]]]]


class GatewayEmbedding(BaseEmbedding):
    """LlamaIndex ``BaseEmbedding`` bọc embedding gateway nội bộ của hệ thống.

    Mục đích: cho các node parser của LlamaIndex (ví dụ ``SemanticSplitterNodeParser``)
    có thể gọi embedding để cắt chunk, nhưng model thực thi vẫn đi qua embedding
    gateway của ta (google-genai SDK trực tiếp), KHÔNG dùng ``llama-index-embeddings-*``
    hay litellm. Việc batching/sub-batching/retry nằm trong embedding gateway/adapter.
    """

    _embed_texts: EmbedTextsFn = PrivateAttr()

    def __init__(
        self,
        embed_texts: EmbedTextsFn,
        *,
        embed_batch_size: int = 100,
        model_name: str = "gateway-embedding",
    ) -> None:
        super().__init__(embed_batch_size=embed_batch_size, model_name=model_name)
        self._embed_texts = embed_texts

    async def _aget_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return await self._embed_texts(list(texts))

    async def _aget_text_embedding(self, text: str) -> list[float]:
        vectors = await self._embed_texts([text])
        return vectors[0]

    async def _aget_query_embedding(self, query: str) -> list[float]:
        return await self._aget_text_embedding(query)

    def _get_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        return _run_coro(self._aget_text_embeddings(texts))

    def _get_text_embedding(self, text: str) -> list[float]:
        return _run_coro(self._aget_text_embedding(text))

    def _get_query_embedding(self, query: str) -> list[float]:
        return _run_coro(self._aget_query_embedding(query))


def _run_coro(coro: Awaitable):
    """Chạy coroutine từ ngữ cảnh sync.

    LlamaIndex node parser gọi embedding theo kiểu sync. Khi chunker chạy parser này
    bên trong ``asyncio.to_thread`` (không có event loop đang chạy ở thread đó) thì
    ``asyncio.run`` hoạt động trực tiếp. Nếu lỡ được gọi trong khi đã có event loop,
    fallback sang chạy coroutine trên một thread riêng để không vỡ loop hiện tại.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()
