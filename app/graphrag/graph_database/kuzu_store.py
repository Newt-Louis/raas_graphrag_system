from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.graphrag.graph_database.models import (
    GraphChunkContext,
    GraphContextResult,
    GraphDatabaseScope,
    GraphElementContext,
    GraphIngestResult,
)
from app.services.ingestion.models import IngestionBundle


class KuzuGraphStoreError(RuntimeError):
    pass


class KuzuGraphStore:
    """Kuzu adapter for tenant/app scoped document structure graph."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def persist_graph(self, bundle: IngestionBundle) -> int:
        result = self.ingest_bundle(bundle)
        return result.stored_count

    def ingest_bundle(self, bundle: IngestionBundle) -> GraphIngestResult:
        parsed = bundle.parsed_document
        scope = GraphDatabaseScope(
            tenant_id=parsed.scope.tenant_id,
            app_id=parsed.scope.app_id,
            collection_id=parsed.scope.collection_id,
        )
        connection = self._connection()
        try:
            self.ensure_schema(connection)
            document_node_id = _document_node_id(scope, parsed.source.document_id)
            self._upsert_document(connection, scope, document_node_id, bundle)

            stored_count = 1
            element_node_ids: dict[str, str] = {}
            for element in parsed.elements:
                element_node_id = _record_node_id(scope, "element", element.element_id)
                element_node_ids[element.element_id] = element_node_id
                self._upsert_element(connection, scope, element_node_id, bundle, element)
                self._merge_relation(connection, "HAS_ELEMENT", document_node_id, element_node_id)
                stored_count += 1

            chunk_node_ids: dict[str, str] = {}
            for chunk in bundle.chunks:
                chunk_node_id = _record_node_id(scope, "chunk", chunk.chunk_id)
                chunk_node_ids[chunk.chunk_id] = chunk_node_id
                self._upsert_chunk(connection, scope, chunk_node_id, chunk)
                self._merge_relation(connection, "HAS_CHUNK", document_node_id, chunk_node_id)
                for element_id in chunk.source_element_ids:
                    element_node_id = element_node_ids.get(element_id)
                    if element_node_id:
                        self._merge_relation(connection, "DERIVED_FROM", chunk_node_id, element_node_id)
                stored_count += 1

            sorted_chunks = sorted(bundle.chunks, key=lambda chunk: chunk.chunk_index)
            for previous, current in zip(sorted_chunks, sorted_chunks[1:], strict=False):
                self._merge_relation(
                    connection,
                    "NEXT_CHUNK",
                    chunk_node_ids[previous.chunk_id],
                    chunk_node_ids[current.chunk_id],
                )
            for chunk in bundle.chunks:
                if chunk.parent_chunk_id and chunk.parent_chunk_id in chunk_node_ids:
                    self._merge_relation(
                        connection,
                        "PARENT_CHUNK",
                        chunk_node_ids[chunk.chunk_id],
                        chunk_node_ids[chunk.parent_chunk_id],
                    )

            return GraphIngestResult(
                tenant_id=scope.tenant_id,
                app_id=scope.app_id,
                collection_id=scope.collection_id,
                document_id=parsed.source.document_id,
                stored_count=stored_count,
                store_path=str(self.db_path),
            )
        except Exception as exc:
            if isinstance(exc, KuzuGraphStoreError):
                raise
            raise KuzuGraphStoreError(f"Graph ingest failed for document {parsed.source.document_id}.") from exc
        finally:
            connection.close()

    def chunk_context(
        self,
        *,
        scope: GraphDatabaseScope,
        chunk_ids: list[str],
    ) -> GraphContextResult:
        connection = self._connection()
        try:
            self.ensure_schema(connection)
            chunks = [
                context
                for chunk_id in dict.fromkeys(chunk_ids)
                if (context := self._chunk_context(connection, scope, chunk_id)) is not None
            ]
            return GraphContextResult(
                tenant_id=scope.tenant_id,
                app_id=scope.app_id,
                collection_id=scope.collection_id,
                chunks=chunks,
            )
        except Exception as exc:
            if isinstance(exc, KuzuGraphStoreError):
                raise
            raise KuzuGraphStoreError("Graph context query failed.") from exc
        finally:
            connection.close()

    def delete_document(self, *, scope: GraphDatabaseScope, document_id: str) -> int:
        connection = self._connection()
        document_node_id = _document_node_id(scope, document_id)
        try:
            self.ensure_schema(connection)
            deleted = 0
            chunk_rows = _rows(
                connection.execute(
                    """
                    MATCH (d:Document {id: $document_node_id})-[:HAS_CHUNK]->(c:Chunk)
                    RETURN c.id
                    """,
                    {"document_node_id": document_node_id},
                )
            )
            element_rows = _rows(
                connection.execute(
                    """
                    MATCH (d:Document {id: $document_node_id})-[:HAS_ELEMENT]->(e:Element)
                    RETURN e.id
                    """,
                    {"document_node_id": document_node_id},
                )
            )
            for row in chunk_rows:
                connection.execute("MATCH (c:Chunk {id: $id}) DETACH DELETE c", {"id": row[0]})
                deleted += 1
            for row in element_rows:
                connection.execute("MATCH (e:Element {id: $id}) DETACH DELETE e", {"id": row[0]})
                deleted += 1
            connection.execute("MATCH (d:Document {id: $id}) DETACH DELETE d", {"id": document_node_id})
            return deleted + 1
        except Exception as exc:
            if isinstance(exc, KuzuGraphStoreError):
                raise
            raise KuzuGraphStoreError(f"Graph delete failed for document {document_id}.") from exc
        finally:
            connection.close()

    def ensure_schema(self, connection=None) -> None:
        owns_connection = connection is None
        connection = connection or self._connection()
        try:
            for statement in _SCHEMA_STATEMENTS:
                connection.execute(statement)
        finally:
            if owns_connection:
                connection.close()

    def _connection(self, *, read_only: bool = False):
        try:
            import kuzu

            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            database = kuzu.Database(self.db_path, read_only=read_only)
            return kuzu.Connection(database)
        except Exception as exc:
            raise KuzuGraphStoreError(f"Graph database is unavailable at {self.db_path}.") from exc

    def _upsert_document(
        self,
        connection,
        scope: GraphDatabaseScope,
        document_node_id: str,
        bundle: IngestionBundle,
    ) -> None:
        source = bundle.parsed_document.source
        connection.execute(
            """
            MERGE (d:Document {id: $id})
            SET
                d.tenant_id = $tenant_id,
                d.app_id = $app_id,
                d.collection_id = $collection_id,
                d.document_id = $document_id,
                d.filename = $filename,
                d.title = $title,
                d.sha256 = $sha256,
                d.extension = $extension,
                d.metadata_json = $metadata_json
            """,
            {
                "id": document_node_id,
                "tenant_id": scope.tenant_id,
                "app_id": scope.app_id,
                "collection_id": _collection_value(scope.collection_id),
                "document_id": source.document_id,
                "filename": source.filename,
                "title": bundle.parsed_document.title or "",
                "sha256": source.sha256,
                "extension": source.extension,
                "metadata_json": _json(
                    {
                        "content_type": source.content_type,
                        "byte_size": source.byte_size,
                        "stored_path": str(source.stored_path) if source.stored_path else None,
                        "warnings": bundle.warnings,
                    }
                ),
            },
        )

    def _upsert_element(
        self,
        connection,
        scope: GraphDatabaseScope,
        element_node_id: str,
        bundle: IngestionBundle,
        element,
    ) -> None:
        source = bundle.parsed_document.source
        connection.execute(
            """
            MERGE (e:Element {id: $id})
            SET
                e.tenant_id = $tenant_id,
                e.app_id = $app_id,
                e.collection_id = $collection_id,
                e.document_id = $document_id,
                e.element_id = $element_id,
                e.element_type = $element_type,
                e.order_index = $order_index,
                e.level = $level,
                e.page_number = $page_number,
                e.sheet_name = $sheet_name,
                e.slide_number = $slide_number,
                e.text = $text,
                e.metadata_json = $metadata_json
            """,
            {
                "id": element_node_id,
                "tenant_id": scope.tenant_id,
                "app_id": scope.app_id,
                "collection_id": _collection_value(scope.collection_id),
                "document_id": source.document_id,
                "element_id": element.element_id,
                "element_type": element.element_type.value,
                "order_index": int(element.order),
                "level": int(element.level or 0),
                "page_number": int(element.page_number or 0),
                "sheet_name": element.sheet_name or "",
                "slide_number": int(element.slide_number or 0),
                "text": element.text or "",
                "metadata_json": _json(
                    {
                        "parent_path": element.parent_path,
                        "table": element.table,
                        "image_ref": element.image_ref,
                        **(element.metadata or {}),
                    }
                ),
            },
        )

    def _upsert_chunk(self, connection, scope: GraphDatabaseScope, chunk_node_id: str, chunk) -> None:
        connection.execute(
            """
            MERGE (c:Chunk {id: $id})
            SET
                c.tenant_id = $tenant_id,
                c.app_id = $app_id,
                c.collection_id = $collection_id,
                c.document_id = $document_id,
                c.chunk_id = $chunk_id,
                c.chunk_index = $chunk_index,
                c.text = $text,
                c.strategy = $strategy,
                c.parent_chunk_id = $parent_chunk_id,
                c.is_embeddable = $is_embeddable,
                c.content_hash = $content_hash,
                c.metadata_json = $metadata_json
            """,
            {
                "id": chunk_node_id,
                "tenant_id": scope.tenant_id,
                "app_id": scope.app_id,
                "collection_id": _collection_value(scope.collection_id),
                "document_id": chunk.document_id,
                "chunk_id": chunk.chunk_id,
                "chunk_index": int(chunk.chunk_index),
                "text": chunk.text,
                "strategy": chunk.strategy.value,
                "parent_chunk_id": chunk.parent_chunk_id or "",
                "is_embeddable": bool(chunk.is_embeddable),
                "content_hash": chunk.content_hash,
                "metadata_json": _json(
                    {
                        "source_element_ids": chunk.source_element_ids,
                        **(chunk.metadata or {}),
                    }
                ),
            },
        )

    def _merge_relation(self, connection, rel_type: str, from_id: str, to_id: str) -> None:
        from_label, to_label = _RELATION_ENDPOINTS[rel_type]
        connection.execute(
            f"""
            MATCH (a:{from_label} {{id: $from_id}}), (b:{to_label} {{id: $to_id}})
            MERGE (a)-[:{rel_type}]->(b)
            """,
            {"from_id": from_id, "to_id": to_id},
        )

    def _chunk_context(self, connection, scope: GraphDatabaseScope, chunk_id: str) -> GraphChunkContext | None:
        chunk_node_id = _record_node_id(scope, "chunk", chunk_id)
        chunk_rows = _rows(
            connection.execute(
                """
                MATCH (c:Chunk {id: $id})
                RETURN c.document_id, c.chunk_id, c.text, c.chunk_index, c.parent_chunk_id, c.metadata_json
                """,
                {"id": chunk_node_id},
            )
        )
        if not chunk_rows:
            return None

        row = chunk_rows[0]
        element_rows = _rows(
            connection.execute(
                """
                MATCH (c:Chunk {id: $id})-[:DERIVED_FROM]->(e:Element)
                RETURN e.element_id, e.element_type, e.text, e.order_index, e.metadata_json
                ORDER BY e.order_index
                """,
                {"id": chunk_node_id},
            )
        )
        previous_rows = _rows(
            connection.execute(
                """
                MATCH (previous:Chunk)-[:NEXT_CHUNK]->(c:Chunk {id: $id})
                RETURN previous.chunk_id
                """,
                {"id": chunk_node_id},
            )
        )
        next_rows = _rows(
            connection.execute(
                """
                MATCH (c:Chunk {id: $id})-[:NEXT_CHUNK]->(next:Chunk)
                RETURN next.chunk_id
                """,
                {"id": chunk_node_id},
            )
        )
        parent_rows = _rows(
            connection.execute(
                """
                MATCH (c:Chunk {id: $id})-[:PARENT_CHUNK]->(parent:Chunk)
                RETURN parent.chunk_id
                """,
                {"id": chunk_node_id},
            )
        )
        return GraphChunkContext(
            document_id=str(row[0]),
            chunk_id=str(row[1]),
            text=str(row[2] or ""),
            chunk_index=int(row[3] or 0),
            parent_chunk_id=str(parent_rows[0][0]) if parent_rows else str(row[4] or "") or None,
            previous_chunk_id=str(previous_rows[0][0]) if previous_rows else None,
            next_chunk_id=str(next_rows[0][0]) if next_rows else None,
            metadata=_dict(row[5]),
            source_elements=[
                GraphElementContext(
                    element_id=str(element_row[0]),
                    element_type=str(element_row[1]),
                    text=str(element_row[2] or ""),
                    order_index=int(element_row[3] or 0),
                    metadata=_dict(element_row[4]),
                )
                for element_row in element_rows
            ],
        )


_SCHEMA_STATEMENTS = [
    """
    CREATE NODE TABLE IF NOT EXISTS Document(
        id STRING,
        tenant_id STRING,
        app_id STRING,
        collection_id STRING,
        document_id STRING,
        filename STRING,
        title STRING,
        sha256 STRING,
        extension STRING,
        metadata_json STRING,
        PRIMARY KEY(id)
    )
    """,
    """
    CREATE NODE TABLE IF NOT EXISTS Element(
        id STRING,
        tenant_id STRING,
        app_id STRING,
        collection_id STRING,
        document_id STRING,
        element_id STRING,
        element_type STRING,
        order_index INT64,
        level INT64,
        page_number INT64,
        sheet_name STRING,
        slide_number INT64,
        text STRING,
        metadata_json STRING,
        PRIMARY KEY(id)
    )
    """,
    """
    CREATE NODE TABLE IF NOT EXISTS Chunk(
        id STRING,
        tenant_id STRING,
        app_id STRING,
        collection_id STRING,
        document_id STRING,
        chunk_id STRING,
        chunk_index INT64,
        text STRING,
        strategy STRING,
        parent_chunk_id STRING,
        is_embeddable BOOL,
        content_hash STRING,
        metadata_json STRING,
        PRIMARY KEY(id)
    )
    """,
    "CREATE REL TABLE IF NOT EXISTS HAS_ELEMENT(FROM Document TO Element)",
    "CREATE REL TABLE IF NOT EXISTS HAS_CHUNK(FROM Document TO Chunk)",
    "CREATE REL TABLE IF NOT EXISTS DERIVED_FROM(FROM Chunk TO Element)",
    "CREATE REL TABLE IF NOT EXISTS NEXT_CHUNK(FROM Chunk TO Chunk)",
    "CREATE REL TABLE IF NOT EXISTS PARENT_CHUNK(FROM Chunk TO Chunk)",
]

_RELATION_ENDPOINTS = {
    "HAS_ELEMENT": ("Document", "Element"),
    "HAS_CHUNK": ("Document", "Chunk"),
    "DERIVED_FROM": ("Chunk", "Element"),
    "NEXT_CHUNK": ("Chunk", "Chunk"),
    "PARENT_CHUNK": ("Chunk", "Chunk"),
}


def _document_node_id(scope: GraphDatabaseScope, document_id: str) -> str:
    return _record_node_id(scope, "document", document_id)


def _record_node_id(scope: GraphDatabaseScope, record_type: str, record_id: str) -> str:
    collection_id = _collection_value(scope.collection_id)
    return f"{scope.tenant_id}:{scope.app_id}:{collection_id}:{record_type}:{record_id}"


def _collection_value(collection_id: str | None) -> str:
    return collection_id or ""


def _json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _dict(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        decoded = json.loads(str(raw))
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _rows(result) -> list[list[Any]]:
    rows: list[list[Any]] = []
    while result.has_next():
        rows.append(result.get_next())
    return rows
