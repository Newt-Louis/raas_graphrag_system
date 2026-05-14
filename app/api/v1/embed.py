from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse
from app.core.config import settings

router = APIRouter()


@router.get("/feature1", response_class=HTMLResponse)
async def embed_feature1(
    primary_color: str = "#3b82f6",
    theme: str = "light",
    api_key: str | None = None,
):
    """
    Endpoint trả về giao diện Feature 1 để embed vào phần mềm khác.
    Phần mềm khác chỉ cần:
    <iframe src="https://your-domain.com/embed/feature1?primary_color=%23ff0000" />
    """
    # Đơn giản nhất: trả index.html (Vue Router sẽ route đến /embed/feature1)
    return FileResponse(settings.STATIC_DIR / "index.html")


@router.get("/feature2", response_class=HTMLResponse)
async def embed_feature2(
    primary_color: str = "#3b82f6",
    theme: str = "light",
):
    return FileResponse(settings.STATIC_DIR / "index.html")