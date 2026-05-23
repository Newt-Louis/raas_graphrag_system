from fastapi import APIRouter

router = APIRouter(prefix="/home", tags=["home"])


@router.get("")
async def query(question: str):
    """Endpoint GraphRAG query"""
    # TODO: gọi service GraphRAG
    return {"answer": f"Trả lời cho: {question}"}


@router.post("")
async def ingest_document(file_path: str):
    """Endpoint ingest document"""
    return {"status": "success"}