from __future__ import annotations

from llama_index.core.base.base_query_engine import BaseQueryEngine
from llama_index.core.base.base_retriever import BaseRetriever
from llama_index.core.base.response.schema import Response
from llama_index.core.schema import NodeWithScore, QueryBundle


class RetrievalOnlyQueryEngine(BaseQueryEngine):
    """LlamaIndex query engine for retrieval while synthesis stays in AI Gateway."""

    def __init__(self, retriever: BaseRetriever) -> None:
        self.retriever = retriever
        super().__init__(callback_manager=retriever.callback_manager)

    def retrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
        return self.retriever.retrieve(query_bundle)

    async def aretrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
        return await self.retriever.aretrieve(query_bundle)

    def _query(self, query_bundle: QueryBundle) -> Response:
        return Response(response="", source_nodes=self.retrieve(query_bundle))

    async def _aquery(self, query_bundle: QueryBundle) -> Response:
        return Response(response="", source_nodes=await self.aretrieve(query_bundle))

    def _get_prompt_modules(self) -> dict:
        return {}

    # TODO(phase-2): expose a ChatEngine composition when persisted chat memory
    # and workflow routing are introduced. Model execution must still go through
    # GraphRAGAIClient/AIGateway instead of a LlamaIndex provider adapter.
