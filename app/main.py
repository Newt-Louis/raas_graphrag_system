import importlib
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app.core.config import settings
from app.graphrag.graph_database import get_kuzu_graph_store


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting GraphRAG System...")
    get_kuzu_graph_store().ensure_schema()
    yield
    print("Shutting down...")


app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def include_routers_automatically():
    api_dir = Path(__file__).parent / "api"
    base_module = f"{__package__}.api"

    for version_dir in sorted(api_dir.iterdir()):
        if not version_dir.is_dir() or version_dir.name.startswith("__"):
            continue
        version = version_dir.name
        for file in sorted(version_dir.glob("*.py")):
            if file.name.startswith("__"):
                continue

            module_name = f"{base_module}.{version}.{file.stem}"

            try:
                module = importlib.import_module(module_name)
                if hasattr(module, "router"):
                    app.include_router(module.router,prefix=f"/api/{version}")
            except Exception as e:
                print(f"⚠️ Không thể load route từ {file.name}: {e}")
                raise

include_routers_automatically()

STATIC_DIR = settings.STATIC_DIR
ASSETS_DIR = STATIC_DIR / "assets"
if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")

# Mọi route không khớp API → trả về index.html (Vue Router xử lý)
@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    """
    Phục vụ Vue SPA - mọi route không phải /api hoặc /assets
    đều trả về index.html để Vue Router xử lý client-side routing.
    """
    # Nếu là request file cụ thể (vd: favicon.ico) → trả file đó
    requested_file = STATIC_DIR / full_path
    if requested_file.is_file():
        return FileResponse(requested_file)

    # Còn lại → trả index.html (Vue SPA)
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)

    return {"detail": "UI chưa được build. Chạy `pnpm build` trong thư mục ui/"}
