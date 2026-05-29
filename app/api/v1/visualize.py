from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.graphrag.graph_database import get_kuzu_graph_store
from app.graphrag.vector_database import VectorDatabasePipelineError
from app.graphrag.vector_database.factory import get_lancedb_vector_store
from app.schemas.visualize import (
    VectorEmbeddingProfileHealthResponse,
    VectorHealthRequest,
    VectorSearchDebugRequest,
    VectorSearchDebugResponse,
)
from app.services.ai_gateway_runtime import AIGatewayRuntimeError
from app.services.visualize import VectorVisualizationService, VisualizeInputError

router = APIRouter(prefix="/visualize", tags=["visualize"])


@router.post("/vector/search", response_model=VectorSearchDebugResponse)
async def search_vector_debugger(
    payload: VectorSearchDebugRequest,
    db: Session = Depends(get_db),
) -> VectorSearchDebugResponse:
    service = _vector_service(db)
    try:
        return await service.search_debug(payload)
    except VisualizeInputError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except AIGatewayRuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except VectorDatabasePipelineError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.post("/vector/health", response_model=VectorEmbeddingProfileHealthResponse)
def vector_embedding_health(
    payload: VectorHealthRequest,
    db: Session = Depends(get_db),
) -> VectorEmbeddingProfileHealthResponse:
    service = _vector_service(db)
    try:
        return service.embedding_health(payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


def _vector_service(db: Session) -> VectorVisualizationService:
    return VectorVisualizationService(
        db=db,
        vector_store=get_lancedb_vector_store(),
        graph_store=get_kuzu_graph_store(),
    )
