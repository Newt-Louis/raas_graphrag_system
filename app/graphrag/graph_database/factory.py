from __future__ import annotations

from app.core.config import settings
from app.graphrag.graph_database.kuzu_store import KuzuGraphStore


def get_kuzu_graph_store() -> KuzuGraphStore:
    return KuzuGraphStore(db_path=settings.KUZU_DB_PATH)
