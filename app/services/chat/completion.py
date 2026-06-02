from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.graphrag.ai_client import GraphRAGAIClient
from app.graphrag.graph_database import (
    GraphChunkContext,
    GraphEntityContext,
    KuzuGraphStore,
    get_kuzu_graph_store,
)
from app.ai_gateway import GatewayRequestContext
from app.graphrag.llama_index import GatewayLLM
from app.graphrag.vector_database import VectorDatabaseScope
from app.graphrag.vector_database.factory import get_lancedb_vector_store
from app.models.ai_gateway import EmbeddingModelProfile
from app.models.documents import Document
from app.schemas.chat import (
    ChatCitationResponse,
    ChatCompletionRequest,
    ChatCompletionResponse,
)
from app.services.ai_gateway_runtime import build_embedding_gateway, build_llm_gateway
from app.services.chat.behavior import ChatAssistantBehavior, DEFAULT_CHAT_BEHAVIOR, refusal_response
from app.services.chat.policy import (
    chat_response_messages,
    has_restricted_topic,
    parse_chat_response,
)
from app.services.retrieval import GraphRAGRetrievalService


class ChatCompletionError(RuntimeError):
    pass


@dataclass(frozen=True)
class _ContextBlock:
    source: str
    document_id: str
    chunk_id: str
    text: str
    filename: str | None = None
    similarity: float | None = None


class ChatCompletionService:
    """Runs the initial scoped GraphRAG retrieval and answer synthesis flow."""

    def __init__(
        self,
        db: Session,
        *,
        vector_store=None,
        graph_store: KuzuGraphStore | None = None,
        behavior: ChatAssistantBehavior = DEFAULT_CHAT_BEHAVIOR,
    ) -> None:
        self.db = db
        self.vector_store = vector_store or get_lancedb_vector_store()
        self.graph_store = graph_store or get_kuzu_graph_store()
        self.behavior = behavior

    async def complete(self, payload: ChatCompletionRequest) -> ChatCompletionResponse:
        if has_restricted_topic(payload.message, behavior=self.behavior):
            return ChatCompletionResponse(
                tenant_id=payload.tenant_id,
                app_id=payload.app_id,
                collection_id=payload.collection_id,
                session_id=payload.session_id,
                answer=refusal_response(self.behavior),
                strategy="policy_refusal",
                response_type="refusal",
            )

        # Dựng LLM gateway một lần: vừa cho router/text2cypher (qua GatewayLLM) khi
        # retrieval, vừa tái dùng cho bước sinh câu trả lời cuối.
        llm_gateway = build_llm_gateway(
            self.db,
            tenant_id=payload.tenant_id,
            app_id=payload.app_id,
        )
        router_llm = GatewayLLM(
            self._router_acomplete(llm_gateway, payload),
            max_tokens=self.behavior.answer_max_tokens,
        )
        retrieval_service = GraphRAGRetrievalService(
            self.db,
            vector_store=self.vector_store,
            graph_store=self.graph_store,
            embedding_ai_client=GraphRAGAIClient(build_embedding_gateway(self.db)),
            router_llm=router_llm,
        )
        retrieval = await retrieval_service.retrieve(
            scope=VectorDatabaseScope(
                tenant_id=payload.tenant_id,
                app_id=payload.app_id,
                collection_id=payload.collection_id,
            ),
            query=_retrieval_query(payload),
            top_k=self._retrieval_top_k(),
            min_similarity=self.behavior.grounded_min_similarity,
        )
        grounded_matches = retrieval.vector_matches
        graph_chunks = retrieval.graph_chunks
        graph_entities = retrieval.graph_entities
        parent_graph_chunks = [
            chunk
            for chunk in graph_chunks
            if chunk.metadata.get("chunk_role") == "parent"
        ]
        other_graph_chunks = [
            chunk
            for chunk in graph_chunks
            if chunk.metadata.get("chunk_role") != "parent"
        ]
        context_blocks = _compact_context_blocks(
            [
                *[
                    _ContextBlock(
                        source="graph",
                        document_id=chunk.document_id,
                        chunk_id=chunk.chunk_id,
                        text=chunk.text,
                        filename=self._document_filename(chunk.document_id),
                    )
                    for chunk in parent_graph_chunks
                ],
                *[
                    _ContextBlock(
                        source="vector",
                        document_id=match.document_id,
                        chunk_id=match.chunk_id,
                        text=match.text,
                        filename=self._document_filename(match.document_id, match.metadata),
                        similarity=match.similarity,
                    )
                    for match in grounded_matches
                ],
                *[
                    _ContextBlock(
                        source="graph",
                        document_id=chunk.document_id,
                        chunk_id=chunk.chunk_id,
                        text=chunk.text,
                        filename=self._document_filename(chunk.document_id),
                    )
                    for chunk in other_graph_chunks
                ],
                *[
                    _ContextBlock(
                        source="graph_query",
                        document_id="knowledge-graph",
                        chunk_id=f"graph-query-{index}",
                        text=block.text,
                        filename=None,
                    )
                    for index, block in enumerate(retrieval.graph_query_blocks)
                ],
            ]
        )
        citations = _citations(context_blocks)
        messages = _answer_messages(
            question=payload.message,
            history=[message.model_dump() for message in payload.history],
            context_blocks=context_blocks,
            graph_entities=graph_entities,
            has_document_context=bool(context_blocks),
            behavior=self.behavior,
        )
        llm_client = GraphRAGAIClient(llm_gateway)
        llm_result = await llm_client.synthesize_answer(
            messages,
            tenant_id=payload.tenant_id,
            app_id=payload.app_id,
            session_id=payload.session_id,
            temperature=self.behavior.answer_temperature,
            max_tokens=self.behavior.answer_max_tokens,
        )
        if not llm_result.success:
            raise ChatCompletionError(llm_result.final_reason or "LLM answer synthesis failed.")

        decision = parse_chat_response(
            llm_result.data,
            valid_references={citation.reference for citation in citations},
            allow_grounded_answer=bool(context_blocks),
            behavior=self.behavior,
        )
        used_references = set(decision.references)
        return ChatCompletionResponse(
            tenant_id=payload.tenant_id,
            app_id=payload.app_id,
            collection_id=payload.collection_id,
            session_id=payload.session_id,
            answer=decision.answer,
            strategy=_response_strategy(decision.response_type, graph_chunks, graph_entities, context_blocks),
            response_type=decision.response_type,
            citations=[citation for citation in citations if citation.reference in used_references],
            usage=_combined_usage(retrieval.usage, llm_result.usage),
        )

    def _router_acomplete(self, llm_gateway, payload: ChatCompletionRequest):
        """Closure để GatewayLLM gọi LLM gateway cho router + text2cypher (temperature 0)."""
        behavior = self.behavior

        async def _acomplete(prompt: str) -> str:
            result = await llm_gateway.complete(
                [{"role": "user", "content": prompt}],
                context=GatewayRequestContext(
                    tenant_id=payload.tenant_id,
                    app_id=payload.app_id,
                    session_id=payload.session_id,
                    endpoint="graphrag.retrieval.router",
                ),
                temperature=0.0,
                max_tokens=behavior.answer_max_tokens,
            )
            if not result.success:
                raise RuntimeError(result.final_reason or "Router LLM call failed.")
            return result.data if isinstance(result.data, str) else str(result.data or "")

        return _acomplete

    def _document_filename(self, document_id: str, metadata: dict | None = None) -> str | None:
        raw_filename = (metadata or {}).get("filename")
        if raw_filename:
            return str(raw_filename)
        try:
            document = self.db.get(Document, UUID(document_id))
        except (AttributeError, ValueError):
            return None
        return document.filename if document is not None else None

    def _retrieval_top_k(self) -> int:
        try:
            profiles = self.db.scalars(
                select(EmbeddingModelProfile).order_by(EmbeddingModelProfile.created_at.desc())
            ).all()
        except AttributeError:
            return self.behavior.default_retrieval_top_k
        if profiles:
            retrieval_top_k = profiles[0].retrieval_top_k
            if retrieval_top_k and retrieval_top_k > 0:
                return int(retrieval_top_k)
        return self.behavior.default_retrieval_top_k


def _compact_context_blocks(
    blocks: list[_ContextBlock],
    *,
    total_char_limit: int = settings.CHAT_CONTEXT_TOTAL_CHAR_LIMIT,
    per_chunk_char_limit: int = settings.CHAT_CONTEXT_PER_CHUNK_CHAR_LIMIT,
    max_blocks: int = settings.CHAT_CONTEXT_MAX_BLOCKS,
) -> list[_ContextBlock]:
    compacted: list[_ContextBlock] = []
    seen_chunk_ids: set[str] = set()
    used_chars = 0
    for block in blocks:
        if block.chunk_id in seen_chunk_ids or len(compacted) >= max_blocks:
            continue
        text = _truncate_text(block.text, per_chunk_char_limit)
        if not text:
            continue
        remaining = total_char_limit - used_chars
        if remaining <= 0:
            break
        text = _truncate_text(text, remaining)
        if not text:
            break
        compacted.append(
            _ContextBlock(
                source=block.source,
                document_id=block.document_id,
                chunk_id=block.chunk_id,
                text=text,
                filename=block.filename,
                similarity=block.similarity,
            )
        )
        seen_chunk_ids.add(block.chunk_id)
        used_chars += len(text)
    return compacted


def _answer_messages(
    *,
    question: str,
    history: list[dict[str, str]],
    context_blocks: list[_ContextBlock],
    graph_entities: list[GraphEntityContext],
    has_document_context: bool,
    behavior: ChatAssistantBehavior = DEFAULT_CHAT_BEHAVIOR,
) -> list[dict[str, str]]:
    rendered_context = "\n\n".join(
        f"[{index}] source={block.filename or block.document_id}; chunk={block.chunk_id}\n{block.text}"
        for index, block in enumerate(context_blocks, start=1)
    )
    rendered_entities = ", ".join(
        f"{entity.name} ({entity.entity_type})"
        for entity in graph_entities[:24]
    )
    return chat_response_messages(
        question=question,
        history=history,
        rendered_context=rendered_context,
        rendered_entities=rendered_entities,
        has_document_context=has_document_context,
        behavior=behavior,
    )


def _retrieval_query(payload: ChatCompletionRequest) -> str:
    previous_questions = [
        message.content
        for message in payload.history[-4:]
        if message.role == "user"
    ]
    if not previous_questions or len(payload.message.split()) >= 8:
        return payload.message
    return f"{previous_questions[-1]}\nFollow-up: {payload.message}"


def _citations(blocks: list[_ContextBlock]) -> list[ChatCitationResponse]:
    return [
        ChatCitationResponse(
            reference=index,
            source=block.source,
            document_id=block.document_id,
            chunk_id=block.chunk_id,
            filename=block.filename,
            similarity=block.similarity,
            excerpt=_truncate_text(block.text, 320),
        )
        for index, block in enumerate(blocks, start=1)
    ]


def _truncate_text(value: str, limit: int) -> str:
    clean_value = " ".join(str(value or "").split())
    if len(clean_value) <= limit:
        return clean_value
    if limit <= 3:
        return clean_value[:limit]
    return f"{clean_value[: limit - 3].rstrip()}..."


def _combined_usage(embedding_usage: dict, answer_usage: dict) -> dict:
    return {
        "retrieval_embedding": dict(embedding_usage or {}),
        "llm_response": dict(answer_usage or {}),
        "total_tokens": int((embedding_usage or {}).get("total_tokens") or 0)
        + int((answer_usage or {}).get("total_tokens") or 0),
    }


def _response_strategy(
    response_type: str,
    graph_chunks: list[GraphChunkContext],
    graph_entities: list[GraphEntityContext],
    context_blocks: list[_ContextBlock],
) -> str:
    if response_type == "social":
        return "embedding_first_social"
    if response_type == "refusal" and not context_blocks:
        return "embedding_first_no_context"
    if graph_entities:
        return "vector_semantic_graph"
    if graph_chunks:
        return "vector_graph"
    return "vector_only"
