from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from app.graphrag.ai_client import GraphRAGAIClient
from app.graphrag.graph_database import (
    GraphChunkContext,
    GraphDatabaseScope,
    GraphEntityContext,
    KuzuGraphStore,
    KuzuGraphStoreError,
    get_kuzu_graph_store,
)
from app.graphrag.vector_database import (
    GraphRAGVectorDatabasePipeline,
    VectorDatabaseScope,
    VectorMatch,
    VectorQueryRequest,
)
from app.graphrag.vector_database.factory import get_lancedb_vector_store
from app.models.documents import Document
from app.schemas.chat import (
    ChatCitationResponse,
    ChatCompletionRequest,
    ChatCompletionResponse,
)
from app.services.ai_gateway_runtime import build_embedding_gateway, build_llm_gateway


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
    ) -> None:
        self.db = db
        self.vector_store = vector_store or get_lancedb_vector_store()
        self.graph_store = graph_store or get_kuzu_graph_store()

    async def complete(self, payload: ChatCompletionRequest) -> ChatCompletionResponse:
        vector_pipeline = GraphRAGVectorDatabasePipeline(
            ai_client=GraphRAGAIClient(build_embedding_gateway(self.db)),
            vector_store=self.vector_store,
        )
        vector_result = await vector_pipeline.query(
            VectorQueryRequest(
                scope=VectorDatabaseScope(
                    tenant_id=payload.tenant_id,
                    app_id=payload.app_id,
                    collection_id=payload.collection_id,
                ),
                query=payload.message,
                top_k=payload.top_k,
                min_similarity=payload.min_similarity,
            )
        )
        if not vector_result.matches:
            return ChatCompletionResponse(
                tenant_id=payload.tenant_id,
                app_id=payload.app_id,
                collection_id=payload.collection_id,
                session_id=payload.session_id,
                answer="Không tìm thấy ngữ cảnh phù hợp trong tài liệu đã nạp.",
                strategy="no_context",
            )

        graph_chunks, graph_entities = self._expand_graph_context(payload, vector_result.matches)
        context_blocks = _compact_context_blocks(
            [
                *[
                    _ContextBlock(
                        source="vector",
                        document_id=match.document_id,
                        chunk_id=match.chunk_id,
                        text=match.text,
                        filename=self._document_filename(match.document_id, match.metadata),
                        similarity=match.similarity,
                    )
                    for match in vector_result.matches
                ],
                *[
                    _ContextBlock(
                        source="graph",
                        document_id=chunk.document_id,
                        chunk_id=chunk.chunk_id,
                        text=chunk.text,
                        filename=self._document_filename(chunk.document_id),
                    )
                    for chunk in graph_chunks
                ],
            ]
        )
        citations = _citations(context_blocks)
        messages = _answer_messages(
            question=payload.message,
            history=[message.model_dump() for message in payload.history],
            context_blocks=context_blocks,
            graph_entities=graph_entities,
        )
        llm_result = await GraphRAGAIClient(
            build_llm_gateway(
                self.db,
                tenant_id=payload.tenant_id,
                app_id=payload.app_id,
            )
        ).synthesize_answer(
            messages,
            tenant_id=payload.tenant_id,
            app_id=payload.app_id,
            session_id=payload.session_id,
            temperature=0.2,
        )
        if not llm_result.success or not isinstance(llm_result.data, str):
            raise ChatCompletionError(llm_result.final_reason or "LLM answer synthesis failed.")

        return ChatCompletionResponse(
            tenant_id=payload.tenant_id,
            app_id=payload.app_id,
            collection_id=payload.collection_id,
            session_id=payload.session_id,
            answer=llm_result.data.strip(),
            strategy=(
                "vector_semantic_graph"
                if graph_entities
                else "vector_graph"
                if graph_chunks
                else "vector_only"
            ),
            citations=citations,
            usage=llm_result.usage,
        )

    def _expand_graph_context(
        self,
        payload: ChatCompletionRequest,
        matches: list[VectorMatch],
    ) -> tuple[list[GraphChunkContext], list[GraphEntityContext]]:
        scope = GraphDatabaseScope(
            tenant_id=payload.tenant_id,
            app_id=payload.app_id,
            collection_id=payload.collection_id,
        )
        seed_chunk_ids = [match.chunk_id for match in matches]
        try:
            semantic_result = self.graph_store.semantic_context_for_chunks(
                scope=scope,
                chunk_ids=seed_chunk_ids,
                hops=1,
            )
            chunk_result = self.graph_store.chunk_context(
                scope=scope,
                chunk_ids=list(dict.fromkeys([*seed_chunk_ids, *semantic_result.chunk_ids])),
            )
        except KuzuGraphStoreError:
            return [], []
        return chunk_result.chunks, semantic_result.entities

    def _document_filename(self, document_id: str, metadata: dict | None = None) -> str | None:
        raw_filename = (metadata or {}).get("filename")
        if raw_filename:
            return str(raw_filename)
        try:
            document = self.db.get(Document, UUID(document_id))
        except (AttributeError, ValueError):
            return None
        return document.filename if document is not None else None


def _compact_context_blocks(
    blocks: list[_ContextBlock],
    *,
    total_char_limit: int = 12_000,
    per_chunk_char_limit: int = 1_800,
    max_blocks: int = 8,
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
) -> list[dict[str, str]]:
    rendered_context = "\n\n".join(
        f"[{index}] source={block.filename or block.document_id}; chunk={block.chunk_id}\n{block.text}"
        for index, block in enumerate(context_blocks, start=1)
    )
    rendered_entities = ", ".join(
        f"{entity.name} ({entity.entity_type})"
        for entity in graph_entities[:24]
    )
    graph_summary = f"\nRelated graph entities: {rendered_entities}" if rendered_entities else ""
    return [
        {
            "role": "system",
            "content": (
                "Answer the user only from the provided document context. "
                "Use the same language as the user. Cite supporting sources as [n]. "
                "If the context is insufficient, state that clearly. Do not invent facts."
            ),
        },
        *history[-8:],
        {
            "role": "user",
            "content": f"Document context:\n{rendered_context}{graph_summary}\n\nQuestion:\n{question}",
        },
    ]


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
