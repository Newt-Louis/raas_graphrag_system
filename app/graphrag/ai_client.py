from __future__ import annotations

from typing import Any

from app.ai_gateway import AIGateway, GatewayRequestContext, RotationResult


class GraphRAGAIClient:
    """
    Interface GraphRAG dùng để gọi model qua AI Gateway.

    Lớp này giữ GraphRAG không phụ thuộc vào provider/key/quota. GraphRAG chỉ truyền
    scope tenant/app, nội dung cần embedding hoặc messages đã dựng prompt.
    """

    def __init__(self, gateway: AIGateway) -> None:
        self.gateway = gateway

    async def embed_documents(
        self,
        texts: list[Any],
        *,
        tenant_id: str,
        app_id: str,
        collection_id: str | None = None,
        profile_id: str | None = None,
        expected_dim: int | None = None,
        **overrides: Any,
    ) -> RotationResult:
        overrides.setdefault("task_type", "RETRIEVAL_DOCUMENT")
        return await self.gateway.embed(
            texts,
            profile_id=profile_id,
            expected_dim=expected_dim,
            context=GatewayRequestContext(
                tenant_id=tenant_id,
                app_id=app_id,
                collection_id=collection_id,
                endpoint="graphrag.documents.embedding",
            ),
            **overrides,
        )

    async def embed_query(
        self,
        query: str,
        *,
        tenant_id: str,
        app_id: str,
        session_id: str | None = None,
        profile_id: str | None = None,
        expected_dim: int | None = None,
        **overrides: Any,
    ) -> RotationResult:
        overrides.setdefault("task_type", "RETRIEVAL_QUERY")
        return await self.gateway.embed(
            [query],
            profile_id=profile_id,
            expected_dim=expected_dim,
            context=GatewayRequestContext(
                tenant_id=tenant_id,
                app_id=app_id,
                session_id=session_id,
                endpoint="graphrag.query.embedding",
            ),
            **overrides,
        )

    async def synthesize_answer(
        self,
        messages: list[dict[str, Any]],
        *,
        tenant_id: str,
        app_id: str,
        session_id: str | None = None,
        profile_id: str | None = None,
        **overrides: Any,
    ) -> RotationResult:
        return await self.gateway.complete(
            messages,
            profile_id=profile_id,
            context=GatewayRequestContext(
                tenant_id=tenant_id,
                app_id=app_id,
                session_id=session_id,
                endpoint="graphrag.answer.llm",
            ),
            **overrides,
        )

    async def extract_graph_semantics(
        self,
        messages: list[dict[str, Any]],
        *,
        tenant_id: str,
        app_id: str,
        collection_id: str | None = None,
        profile_id: str | None = None,
        **overrides: Any,
    ) -> RotationResult:
        return await self.gateway.complete(
            messages,
            profile_id=profile_id,
            context=GatewayRequestContext(
                tenant_id=tenant_id,
                app_id=app_id,
                collection_id=collection_id,
                endpoint="graphrag.graph.entity_extraction",
            ),
            **overrides,
        )
