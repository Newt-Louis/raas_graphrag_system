from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.graphrag.vector_database import VectorDatabasePipelineError, VectorDatabaseScope
from app.services.ai_gateway_runtime import AIGatewayRuntimeError
from app.services.retrieval import GraphRAGRetrievalService

router = APIRouter(prefix="/home", tags=["home"])


@router.get("")
async def query(
    question: str,
    tenant_id: str,
    app_id: str,
    collection_id: str | None = None,
    top_k: int = 5,
    db: Session = Depends(get_db),
):
    """Compatibility endpoint for scoped GraphRAG retrieval."""
    try:
        retrieval = await GraphRAGRetrievalService(db).retrieve(
            scope=VectorDatabaseScope(
                tenant_id=tenant_id,
                app_id=app_id,
                collection_id=collection_id,
            ),
            query=question,
            top_k=top_k,
            min_similarity=settings.RETRIEVAL_MIN_SCORE,
        )
    except AIGatewayRuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except VectorDatabasePipelineError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    contexts = [
        {
            "source": "vector",
            "text": match.text,
            "score": match.similarity,
            "document_id": match.document_id,
            "chunk_id": match.chunk_id,
            "metadata": match.metadata,
        }
        for match in retrieval.vector_matches
    ]
    contexts.extend(
        {
            "source": "graph",
            "text": chunk.text,
            "score": 1.0,
            "document_id": chunk.document_id,
            "chunk_id": chunk.chunk_id,
            "metadata": chunk.metadata,
        }
        for chunk in retrieval.graph_chunks
    )
    return {
        "query": retrieval.query,
        "tenant_id": tenant_id,
        "app_id": app_id,
        "collection_id": collection_id,
        "strategy": retrieval.strategy,
        "contexts": contexts,
    }


@router.post("")
async def ingest_document():
    """Compatibility response for the old home ingest path."""
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Use POST /api/v1/ingest with multipart upload and tenant/app scope.",
    )
