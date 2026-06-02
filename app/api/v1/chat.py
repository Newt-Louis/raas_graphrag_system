from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.graphrag.vector_database import VectorDatabasePipelineError, VectorDatabaseScope
from app.schemas.chat import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatRetrieveRequest,
    ChatRetrieveResponse,
    RetrievedContextResponse,
)
from app.services.ai_gateway_runtime import AIGatewayRuntimeError
from app.services.chat import ChatCompletionError, ChatCompletionService
from app.services.retrieval import GraphRAGRetrieval, GraphRAGRetrievalService


router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/completions", response_model=ChatCompletionResponse)
async def complete_chat(
    payload: ChatCompletionRequest,
    db: Session = Depends(get_db),
) -> ChatCompletionResponse:
    return await _complete_chat(payload, db)


@router.post("/completions/stream")
async def stream_chat_completion(
    payload: ChatCompletionRequest,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    response = await _complete_chat(payload, db)
    return StreamingResponse(
        _chat_sse_events(response),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _complete_chat(
    payload: ChatCompletionRequest,
    db: Session,
) -> ChatCompletionResponse:
    try:
        return await ChatCompletionService(db).complete(payload)
    except AIGatewayRuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except VectorDatabasePipelineError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except ChatCompletionError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


async def _chat_sse_events(response: ChatCompletionResponse) -> AsyncIterator[str]:
    yield _sse_event(
        "metadata",
        response.model_dump(mode="json", exclude={"answer"}),
    )
    for character in response.answer:
        yield _sse_event("delta", {"text": character})
        await asyncio.sleep(0)
    yield _sse_event("done", {"finish_reason": "stop"})


def _sse_event(event: str, data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n"


@router.post("/retrieve", response_model=ChatRetrieveResponse)
async def retrieve_chat_context(
    request: ChatRetrieveRequest,
    db: Session = Depends(get_db),
) -> ChatRetrieveResponse:
    try:
        retrieval = await GraphRAGRetrievalService(db).retrieve(
            scope=VectorDatabaseScope(
                tenant_id=request.tenant_id,
                app_id=request.app_id,
                collection_id=request.collection_id,
            ),
            query=request.message,
            top_k=request.top_k,
            min_similarity=request.min_score,
        )
    except AIGatewayRuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except VectorDatabasePipelineError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return ChatRetrieveResponse(
        tenant_id=request.tenant_id,
        app_id=request.app_id,
        collection_id=request.collection_id,
        query=retrieval.query,
        strategy=retrieval.strategy,
        contexts=_retrieved_contexts(retrieval),
    )


def _retrieved_contexts(retrieval: GraphRAGRetrieval) -> list[RetrievedContextResponse]:
    contexts = [
        RetrievedContextResponse(
            source="vector",
            text=match.text,
            score=match.similarity,
            document_id=match.document_id,
            chunk_id=match.chunk_id,
            metadata=match.metadata,
        )
        for match in retrieval.vector_matches
    ]
    contexts.extend(
        RetrievedContextResponse(
            source="graph",
            text=chunk.text,
            score=1.0,
            document_id=chunk.document_id,
            chunk_id=chunk.chunk_id,
            metadata={
                **chunk.metadata,
                "previous_chunk_id": chunk.previous_chunk_id,
                "next_chunk_id": chunk.next_chunk_id,
                "parent_chunk_id": chunk.parent_chunk_id,
                "source_elements": [
                    {
                        "element_id": element.element_id,
                        "element_type": element.element_type,
                        "order_index": element.order_index,
                        "text": element.text,
                    }
                    for element in chunk.source_elements
                ],
                "semantic_entities": [
                    {
                        "entity_id": entity.entity_id,
                        "entity_type": entity.entity_type,
                        "name": entity.name,
                        "description": entity.description,
                    }
                    for entity in retrieval.graph_entities
                ],
            },
        )
        for chunk in retrieval.graph_chunks
    )
    return contexts
