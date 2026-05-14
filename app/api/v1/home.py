from fastapi import APIRouter

router = APIRouter()


@router.post("/query")
async def query(question: str):
    """Endpoint GraphRAG query"""
    # TODO: gọi service GraphRAG
    return {"answer": f"Trả lời cho: {question}"}


@router.post("/ingest")
async def ingest_document(file_path: str):
    """Endpoint ingest document"""
    return {"status": "success"}