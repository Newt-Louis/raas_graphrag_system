from fastapi import APIRouter, HTTPException, status

from app.services.retrieval.factory import get_retrieval_orchestrator
from app.services.retrieval.models import RetrievalRequest

router = APIRouter(prefix="/home", tags=["home"])


@router.get("")
async def query(
    question: str,
    tenant_id: str,
    app_id: str,
    collection_id: str | None = None,
    top_k: int = 5,
):
    """Compatibility endpoint for scoped GraphRAG retrieval."""
    result = get_retrieval_orchestrator().retrieve(
        RetrievalRequest(
            tenant_id=tenant_id,
            app_id=app_id,
            collection_id=collection_id,
            query=question,
            top_k=top_k,
        )
    )
    return {
        "query": result.query,
        "tenant_id": result.tenant_id,
        "app_id": result.app_id,
        "collection_id": result.collection_id,
        "strategy": result.strategy,
        "contexts": [
            {
                "source": context.source,
                "text": context.text,
                "score": context.score,
                "document_id": context.document_id,
                "chunk_id": context.chunk_id,
                "metadata": context.metadata,
            }
            for context in result.contexts
        ],
    }


@router.post("")
async def ingest_document():
    """Compatibility response for the old home ingest path."""
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Use POST /api/v1/ingest with multipart upload and tenant/app scope.",
    )
