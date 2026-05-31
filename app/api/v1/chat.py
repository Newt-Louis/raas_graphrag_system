from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.graphrag.vector_database import VectorDatabasePipelineError
from app.schemas.chat import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatRetrieveRequest,
    ChatRetrieveResponse,
    RetrievedContextResponse,
)
from app.services.ai_gateway_runtime import AIGatewayRuntimeError
from app.services.chat import ChatCompletionError, ChatCompletionService
from app.services.retrieval.factory import get_retrieval_orchestrator
from app.services.retrieval.models import RetrievalRequest


router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/completions", response_model=ChatCompletionResponse)
async def complete_chat(
    payload: ChatCompletionRequest,
    db: Session = Depends(get_db),
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


@router.post("/retrieve", response_model=ChatRetrieveResponse)
async def retrieve_chat_context(request: ChatRetrieveRequest) -> ChatRetrieveResponse:
    orchestrator = get_retrieval_orchestrator()
    try:
        result = orchestrator.retrieve(
            RetrievalRequest(
                tenant_id=request.tenant_id,
                app_id=request.app_id,
                collection_id=request.collection_id,
                query=request.message,
                top_k=request.top_k,
                min_score=request.min_score,
            )
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    return ChatRetrieveResponse(
        tenant_id=result.tenant_id,
        app_id=result.app_id,
        collection_id=result.collection_id,
        query=result.query,
        strategy=result.strategy,
        contexts=[
            RetrievedContextResponse(
                source=context.source,
                text=context.text,
                score=context.score,
                document_id=context.document_id,
                chunk_id=context.chunk_id,
                metadata=context.metadata,
            )
            for context in result.contexts
        ],
    )
