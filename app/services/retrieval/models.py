from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RetrievalRequest:
    tenant_id: str
    app_id: str
    query: str
    collection_id: str | None = None
    top_k: int = 5
    min_score: float = 0.0


@dataclass
class RetrievedContext:
    source: str
    text: str
    score: float
    document_id: str
    chunk_id: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalResult:
    query: str
    tenant_id: str
    app_id: str
    collection_id: str | None
    contexts: list[RetrievedContext]
    strategy: str = "vector_only"
