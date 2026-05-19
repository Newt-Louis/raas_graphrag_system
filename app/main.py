import importlib
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.api.v1 import home, ingest, embed


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: khởi tạo DB connections
    print("🚀 Starting GraphRAG System...")
    # TODO: init Kùzu, LanceDB, PostgreSQL
    yield
    # Shutdown: cleanup
    print("👋 Shutting down...")


app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG,
    lifespan=lifespan,
)

# CORS - cho phép embed từ domain khác
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============= API ROUTES =============
app.include_router(home.router, prefix="/api/v1/feature1", tags=["Feature 1"])
app.include_router(ingest.router, prefix="/api/v1/documents", tags=["Documents"])
app.include_router(embed.router, prefix="/embed", tags=["Embed"])

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

# ============= STATIC FILES (Vue SPA) =============
STATIC_DIR = settings.STATIC_DIR
ASSETS_DIR = STATIC_DIR / "assets"

# Mount assets (JS, CSS, images, fonts)
if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")


# ============= SPA FALLBACK =============
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
