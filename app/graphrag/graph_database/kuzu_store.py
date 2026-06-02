from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Sequence

from llama_index.core.graph_stores.types import (
    KG_NODES_KEY,
    KG_RELATIONS_KEY,
    ChunkNode,
    EntityNode,
    LabelledNode,
    PropertyGraphStore,
    Relation,
    Triplet,
)
from llama_index.core.indices.property_graph import PropertyGraphIndex
from llama_index.core.indices.property_graph.transformations import ImplicitPathExtractor
from llama_index.core.schema import TextNode
from llama_index.core.vector_stores.types import VectorStoreQuery

from app.graphrag.graph_database.models import (
    GraphChunkContext,
    GraphContextResult,
    GraphDatabaseScope,
    GraphDocumentChunkStats,
    GraphElementContext,
    GraphEntityContext,
    GraphIngestResult,
    GraphSemanticPersistResult,
    GraphTraversalResult,
    GraphVisualizationEdge,
    GraphVisualizationNode,
    GraphVisualizationResult,
    SemanticExtraction,
)
from app.services.ingestion.models import IngestionBundle


class KuzuGraphStoreError(RuntimeError):
    pass


class KuzuGraphStore(PropertyGraphStore):
    """Tenant-scoped LlamaIndex PropertyGraphStore bridge backed by Kuzu."""

    supports_structured_queries = True
    supports_vector_queries = False

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
        try:
            self.ensure_schema()
            self._property_graph_index().insert_nodes(self._structure_llama_nodes(bundle))

            return GraphIngestResult(
                tenant_id=scope.tenant_id,
                app_id=scope.app_id,
                collection_id=scope.collection_id,
                document_id=parsed.source.document_id,
                stored_count=1 + len(parsed.elements) + len(bundle.chunks),
                store_path=str(self.db_path),
            )
        except Exception as exc:
            if isinstance(exc, KuzuGraphStoreError):
                raise
            raise KuzuGraphStoreError(f"Graph ingest failed for document {parsed.source.document_id}.") from exc

    def _property_graph_index(self) -> PropertyGraphIndex:
        return PropertyGraphIndex(
            nodes=[],
            property_graph_store=self,
            kg_extractors=[ImplicitPathExtractor()],
            embed_kg_nodes=False,
            use_async=False,
        )

    def _structure_llama_nodes(self, bundle: IngestionBundle) -> list[TextNode]:
        parsed = bundle.parsed_document
        scope = GraphDatabaseScope(
            tenant_id=parsed.scope.tenant_id,
            app_id=parsed.scope.app_id,
            collection_id=parsed.scope.collection_id,
        )
        document_node_id = _document_node_id(scope, parsed.source.document_id)
        document_node = EntityNode(
            name=document_node_id,
            label="Document",
            properties={
                **_scope_params(scope),
                "document_id": parsed.source.document_id,
                "filename": parsed.source.filename,
                "title": parsed.title,
                "sha256": parsed.source.sha256,
                "extension": parsed.source.extension,
                "metadata": {
                    "content_type": parsed.source.content_type,
                    "byte_size": parsed.source.byte_size,
                    "stored_path": str(parsed.source.stored_path) if parsed.source.stored_path else None,
                    "warnings": bundle.warnings,
                },
            },
        )
        element_nodes = {
            element.element_id: EntityNode(
                name=_record_node_id(scope, "element", element.element_id),
                label="Element",
                properties={
                    **_scope_params(scope),
                    "document_id": parsed.source.document_id,
                    "element_id": element.element_id,
                    "element_type": element.element_type.value,
                    "order_index": element.order,
                    "level": element.level,
                    "page_number": element.page_number,
                    "sheet_name": element.sheet_name,
                    "slide_number": element.slide_number,
                    "text": element.text,
                    "metadata": {
                        "parent_path": element.parent_path,
                        "table": element.table,
                        "image_ref": element.image_ref,
                        **(element.metadata or {}),
                    },
                },
            )
            for element in parsed.elements
        }
        chunk_node_ids = {
            chunk.chunk_id: _record_node_id(scope, "chunk", chunk.chunk_id)
            for chunk in bundle.chunks
        }
        next_chunk_ids: dict[str, str] = {}
        chunk_sequences: dict[str, list] = {}
        for chunk in sorted(bundle.chunks, key=lambda item: item.chunk_index):
            role = str(chunk.metadata.get("chunk_role") or "chunk")
            chunk_sequences.setdefault(role, []).append(chunk)
        for sequence in chunk_sequences.values():
            next_chunk_ids.update(
                {
                    previous.chunk_id: current.chunk_id
                    for previous, current in zip(sequence, sequence[1:], strict=False)
                }
            )

        nodes: list[TextNode] = []
        for chunk in bundle.chunks:
            chunk_node_id = chunk_node_ids[chunk.chunk_id]
            chunk_elements = [
                element_nodes[element_id]
                for element_id in chunk.source_element_ids
                if element_id in element_nodes
            ]
            relations = [
                Relation(source_id=document_node_id, target_id=chunk_node_id, label="HAS_CHUNK"),
                *[
                    Relation(source_id=document_node_id, target_id=element.id, label="HAS_ELEMENT")
                    for element in chunk_elements
                ],
                *[
                    Relation(source_id=chunk_node_id, target_id=element.id, label="DERIVED_FROM")
                    for element in chunk_elements
                ],
            ]
            next_chunk_id = next_chunk_ids.get(chunk.chunk_id)
            if next_chunk_id:
                relations.append(
                    Relation(
                        source_id=chunk_node_id,
                        target_id=chunk_node_ids[next_chunk_id],
                        label="NEXT_CHUNK",
                    )
                )
            if chunk.parent_chunk_id and chunk.parent_chunk_id in chunk_node_ids:
                relations.append(
                    Relation(
                        source_id=chunk_node_id,
                        target_id=chunk_node_ids[chunk.parent_chunk_id],
                        label="PARENT_CHUNK",
                    )
                )
            nodes.append(
                TextNode(
                    id_=chunk_node_id,
                    text=chunk.text,
                    metadata={
                        **_scope_params(scope),
                        "graph_document_id": chunk.document_id,
                        "chunk_id": chunk.chunk_id,
                        "chunk_index": chunk.chunk_index,
                        "strategy": chunk.strategy.value,
                        "parent_chunk_id": chunk.parent_chunk_id,
                        "is_embeddable": chunk.is_embeddable,
                        "content_hash": chunk.content_hash,
                        "metadata": {
                            "source_element_ids": chunk.source_element_ids,
                            **(chunk.metadata or {}),
                        },
                        KG_NODES_KEY: [document_node, *chunk_elements],
                        KG_RELATIONS_KEY: relations,
                    },
                )
            )
        return nodes

    def chunk_context(
        self,
        *,
        scope: GraphDatabaseScope,
        chunk_ids: list[str],
    ) -> GraphContextResult:
        try:
            from app.graphrag.graph_database.query_engine import LlamaIndexGraphQueryEngine

            return LlamaIndexGraphQueryEngine(self).chunk_context(scope=scope, chunk_ids=chunk_ids)
        except Exception as exc:
            if isinstance(exc, KuzuGraphStoreError):
                raise
            raise KuzuGraphStoreError("Graph context query failed.") from exc

    def persist_semantic_extraction(
        self,
        *,
        scope: GraphDatabaseScope,
        document_id: str,
        chunk_id: str,
        extraction: SemanticExtraction,
    ) -> GraphSemanticPersistResult:
        connection = self._connection()
        try:
            self.ensure_schema(connection)
            chunk_node_id = _record_node_id(scope, "chunk", chunk_id)
            context = self._chunk_context(connection, scope, chunk_id)
            if context is None:
                raise KuzuGraphStoreError(f"Chunk {chunk_id} does not exist in the scoped graph.")
            entity_nodes: list[EntityNode] = []
            relations: list[Relation] = []
            entity_node_ids: dict[str, str] = {}
            for entity in extraction.entities:
                entity_node_id = _entity_node_id(scope, entity.entity_type, entity.normalized_name)
                entity_node_ids[entity.local_id] = entity_node_id
                entity_nodes.append(
                    EntityNode(
                        name=entity_node_id,
                        label="Entity",
                        properties={
                            **_scope_params(scope),
                            "entity_type": entity.entity_type,
                            "name": entity.name,
                            "normalized_name": entity.normalized_name,
                            "description": entity.description,
                            "metadata": entity.metadata,
                        },
                    )
                )
                relations.append(
                    Relation(
                        source_id=entity_node_id,
                        target_id=chunk_node_id,
                        label="MENTIONED_IN",
                        properties={"document_id": document_id, "chunk_id": chunk_id},
                    )
                )

            relation_count = 0
            for relation in extraction.relations:
                source_id = entity_node_ids.get(relation.source_id)
                target_id = entity_node_ids.get(relation.target_id)
                if source_id is None or target_id is None:
                    continue
                relations.append(
                    Relation(
                        source_id=source_id,
                        target_id=target_id,
                        label="SEMANTIC_RELATION",
                        properties={
                            "relation_type": relation.relation_type,
                            "description": relation.description,
                            "confidence": relation.confidence,
                            "metadata": relation.metadata,
                        },
                    )
                )
                relation_count += 1
            self._property_graph_index().insert_nodes(
                [
                    TextNode(
                        id_=chunk_node_id,
                        text=context.text,
                        metadata={
                            **_scope_params(scope),
                            "graph_document_id": document_id,
                            "chunk_id": chunk_id,
                            KG_NODES_KEY: entity_nodes,
                            KG_RELATIONS_KEY: relations,
                        },
                    )
                ]
            )
            return GraphSemanticPersistResult(
                entity_count=len(entity_node_ids),
                relation_count=relation_count,
                mention_count=len(entity_node_ids),
            )
        except Exception as exc:
            if isinstance(exc, KuzuGraphStoreError):
                raise
            raise KuzuGraphStoreError(f"Semantic graph ingest failed for chunk {chunk_id}.") from exc
        finally:
            connection.close()

    def entity_context(
        self,
        *,
        scope: GraphDatabaseScope,
        entity_names: list[str],
        hops: int = 2,
    ) -> GraphTraversalResult:
        try:
            from app.graphrag.graph_database.query_engine import LlamaIndexGraphQueryEngine

            return LlamaIndexGraphQueryEngine(self).entity_context(
                scope=scope,
                entity_names=entity_names,
                hops=hops,
            )
        except Exception as exc:
            if isinstance(exc, KuzuGraphStoreError):
                raise
            raise KuzuGraphStoreError("Semantic entity context query failed.") from exc

    def semantic_context_for_chunks(
        self,
        *,
        scope: GraphDatabaseScope,
        chunk_ids: list[str],
        hops: int = 1,
    ) -> GraphTraversalResult:
        try:
            from app.graphrag.graph_database.query_engine import LlamaIndexGraphQueryEngine

            return LlamaIndexGraphQueryEngine(self).semantic_context_for_chunks(
                scope=scope,
                chunk_ids=chunk_ids,
                hops=hops,
            )
        except Exception as exc:
            if isinstance(exc, KuzuGraphStoreError):
                raise
            raise KuzuGraphStoreError("Semantic chunk context query failed.") from exc

    def graph_visualization(
        self,
        *,
        scope: GraphDatabaseScope,
        document_id: str | None = None,
        include_structure: bool = True,
        include_semantic: bool = True,
        limit: int = 2_000,
    ) -> GraphVisualizationResult:
        connection = self._connection()
        try:
            self.ensure_schema(connection)
            nodes: list[GraphVisualizationNode] = []
            edges: list[GraphVisualizationEdge] = []
            if include_structure:
                nodes.extend(self._structure_visualization_nodes(connection, scope, document_id))
                edges.extend(self._structure_visualization_edges(connection, scope, document_id))
            if include_semantic:
                nodes.extend(self._semantic_visualization_nodes(connection, scope, document_id))
                included_ids = {node.id for node in nodes}
                edges.extend(self._semantic_visualization_edges(connection, scope, document_id, included_ids))

            deduplicated_nodes = list({node.id: node for node in nodes}.values())[:limit]
            included_ids = {node.id for node in deduplicated_nodes}
            deduplicated_edges = [
                edge
                for edge in {edge.id: edge for edge in edges}.values()
                if edge.source in included_ids and edge.target in included_ids
            ][: limit * 4]
            return GraphVisualizationResult(
                tenant_id=scope.tenant_id,
                app_id=scope.app_id,
                collection_id=scope.collection_id,
                document_id=document_id,
                nodes=deduplicated_nodes,
                edges=deduplicated_edges,
            )
        except Exception as exc:
            if isinstance(exc, KuzuGraphStoreError):
                raise
            raise KuzuGraphStoreError("Graph visualization query failed.") from exc
        finally:
            connection.close()

    def document_chunk_stats(
        self,
        *,
        scope: GraphDatabaseScope,
        document_id: str | None = None,
    ) -> dict[str, GraphDocumentChunkStats]:
        connection = self._connection()
        try:
            self.ensure_schema(connection)
            where_clauses = [
                "c.tenant_id = $tenant_id",
                "c.app_id = $app_id",
                "c.collection_id = $collection_id",
            ]
            params = {
                "tenant_id": scope.tenant_id,
                "app_id": scope.app_id,
                "collection_id": _collection_value(scope.collection_id),
            }
            if document_id:
                where_clauses.append("c.document_id = $document_id")
                params["document_id"] = document_id

            rows = _rows(
                connection.execute(
                    f"""
                    MATCH (c:Chunk)
                    WHERE {" AND ".join(where_clauses)}
                    RETURN c.document_id, c.is_embeddable
                    """,
                    params,
                )
            )
        except Exception as exc:
            if isinstance(exc, KuzuGraphStoreError):
                raise
            raise KuzuGraphStoreError("Graph document chunk stats query failed.") from exc
        finally:
            connection.close()

        counts: dict[str, dict[str, int]] = {}
        for row in rows:
            current_document_id = str(row[0])
            entry = counts.setdefault(current_document_id, {"chunks": 0, "embeddable": 0})
            entry["chunks"] += 1
            if bool(row[1]):
                entry["embeddable"] += 1
        return {
            current_document_id: GraphDocumentChunkStats(
                document_id=current_document_id,
                chunk_count=entry["chunks"],
                embeddable_chunk_count=entry["embeddable"],
            )
            for current_document_id, entry in counts.items()
        }

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
            self._delete_orphan_entities(connection, scope)
            return deleted + 1
        except Exception as exc:
            if isinstance(exc, KuzuGraphStoreError):
                raise
            raise KuzuGraphStoreError(f"Graph delete failed for document {document_id}.") from exc
        finally:
            connection.close()

    @property
    def client(self):
        """Expose a Kuzu connection for LlamaIndex structured-query integrations."""
        return self._connection()

    def upsert_nodes(self, nodes: Sequence[LabelledNode]) -> None:
        connection = self._connection()
        try:
            self.ensure_schema(connection)
            for node in nodes:
                properties = dict(node.properties or {})
                scope = _scope_from_properties(properties)
                if isinstance(node, ChunkNode):
                    chunk = SimpleNamespace(
                        document_id=str(properties.get("graph_document_id") or properties.get("document_id") or ""),
                        chunk_id=str(properties.get("chunk_id") or node.id),
                        chunk_index=int(properties.get("chunk_index") or 0),
                        text=node.text,
                        strategy=SimpleNamespace(value=str(properties.get("strategy") or "")),
                        parent_chunk_id=properties.get("parent_chunk_id"),
                        is_embeddable=bool(properties.get("is_embeddable", True)),
                        content_hash=str(properties.get("content_hash") or ""),
                        source_element_ids=list((properties.get("metadata") or {}).get("source_element_ids") or []),
                        metadata=properties,
                    )
                    self._upsert_chunk(connection, scope, node.id, chunk)
                    continue
                if not isinstance(node, EntityNode):
                    continue
                if node.label == "Document":
                    self._upsert_llama_document(connection, scope, node)
                elif node.label == "Element":
                    self._upsert_llama_element(connection, scope, node)
                else:
                    entity = SimpleNamespace(
                        entity_type=str(properties.get("entity_type") or node.label),
                        name=str(properties.get("name") or node.name),
                        normalized_name=str(properties.get("normalized_name") or _normalized_name(node.name)),
                        description=str(properties.get("description") or ""),
                        metadata=dict(properties.get("metadata") or {}),
                    )
                    self._upsert_entity(connection, scope, node.id, entity)
        finally:
            connection.close()

    def upsert_relations(self, relations: list[Relation]) -> None:
        connection = self._connection()
        try:
            self.ensure_schema(connection)
            for relation in relations:
                properties = dict(relation.properties or {})
                if relation.label in _RELATION_ENDPOINTS:
                    self._merge_relation(connection, relation.label, relation.source_id, relation.target_id)
                elif relation.label == "MENTIONED_IN":
                    self._merge_mention(
                        connection,
                        relation.source_id,
                        relation.target_id,
                        str(properties.get("document_id") or ""),
                        str(properties.get("chunk_id") or ""),
                    )
                elif relation.label == "SEMANTIC_RELATION":
                    semantic_relation = SimpleNamespace(
                        relation_type=str(properties.get("relation_type") or "RELATED_TO"),
                        description=str(properties.get("description") or ""),
                        confidence=float(properties.get("confidence") or 0.0),
                        metadata=dict(properties.get("metadata") or {}),
                    )
                    self._merge_semantic_relation(
                        connection,
                        relation.source_id,
                        relation.target_id,
                        semantic_relation,
                    )
        finally:
            connection.close()

    def get(
        self,
        properties: dict | None = None,
        ids: list[str] | None = None,
    ) -> list[LabelledNode]:
        connection = self._connection()
        try:
            self.ensure_schema(connection)
            nodes: list[LabelledNode] = []
            for label in ("Document", "Element", "Chunk", "Entity"):
                where = ""
                params: dict[str, Any] = {}
                if ids is not None:
                    where = "WHERE n.id IN $ids"
                    params["ids"] = ids
                rows = _rows(
                    connection.execute(
                        f"MATCH (n:{label}) {where} RETURN n.id, n.metadata_json, "
                        + ("n.text" if label == "Chunk" else "''"),
                        params,
                    )
                )
                for row in rows:
                    node_properties = _dict(row[1])
                    if properties and any(node_properties.get(key) != value for key, value in properties.items()):
                        continue
                    if label == "Chunk":
                        nodes.append(ChunkNode(id_=str(row[0]), text=str(row[2] or ""), properties=node_properties))
                    else:
                        nodes.append(EntityNode(name=str(row[0]), label=label, properties=node_properties))
            return nodes
        finally:
            connection.close()

    def get_triplets(
        self,
        entity_names: list[str] | None = None,
        relation_names: list[str] | None = None,
        properties: dict | None = None,
        ids: list[str] | None = None,
    ) -> list[Triplet]:
        connection = self._connection()
        try:
            self.ensure_schema(connection)
            triplets: list[Triplet] = []
            for relation_table, (source_label, target_label) in _ALL_RELATION_ENDPOINTS.items():
                rows = _rows(
                    connection.execute(
                        f"MATCH (source:{source_label})-[r:{relation_table}]->(target:{target_label}) "
                        "RETURN source.id, target.id"
                    )
                )
                for row in rows:
                    source_id, target_id = str(row[0]), str(row[1])
                    if ids and source_id not in ids and target_id not in ids:
                        continue
                    relation = Relation(source_id=source_id, target_id=target_id, label=relation_table)
                    if relation_names and relation.label not in relation_names:
                        continue
                    nodes = self.get(ids=[source_id, target_id])
                    by_id = {node.id: node for node in nodes}
                    if source_id not in by_id or target_id not in by_id:
                        continue
                    triplets.append((by_id[source_id], relation, by_id[target_id]))
            return triplets
        finally:
            connection.close()

    def get_rel_map(
        self,
        graph_nodes: list[LabelledNode],
        depth: int = 2,
        limit: int = 30,
        ignore_rels: list[str] | None = None,
    ) -> list[Triplet]:
        ignored = set(ignore_rels or [])
        frontier = {node.id for node in graph_nodes}
        seen = set(frontier)
        selected: list[Triplet] = []
        for _ in range(max(0, min(depth, 5))):
            if not frontier or len(selected) >= limit:
                break
            current = [
                triplet
                for triplet in self.get_triplets(ids=list(frontier))
                if triplet[1].label not in ignored
            ]
            selected.extend(current[: max(0, limit - len(selected))])
            next_frontier = {
                node.id
                for source, _, target in current
                for node in (source, target)
                if node.id not in seen
            }
            seen.update(next_frontier)
            frontier = next_frontier
        return selected

    def delete(
        self,
        entity_names: list[str] | None = None,
        relation_names: list[str] | None = None,
        properties: dict | None = None,
        ids: list[str] | None = None,
    ) -> None:
        connection = self._connection()
        try:
            self.ensure_schema(connection)
            selected_ids = list(ids or entity_names or [])
            for node_id in selected_ids:
                for label in ("Document", "Element", "Chunk", "Entity"):
                    connection.execute(f"MATCH (n:{label} {{id: $id}}) DETACH DELETE n", {"id": node_id})
        finally:
            connection.close()

    def structured_query(self, query: str, param_map: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        connection = self._connection()
        try:
            result = connection.execute(query, param_map or {})
            column_names = result.get_column_names()
            return [dict(zip(column_names, row, strict=True)) for row in result]
        finally:
            connection.close()

    def vector_query(self, query: VectorStoreQuery, **kwargs: Any) -> tuple[list[LabelledNode], list[float]]:
        """Vector retrieval stays in the LlamaIndex LanceDB adapter."""
        return [], []

    def get_schema(self, refresh: bool = False) -> dict[str, list[str]]:
        return {
            "nodes": ["Document", "Element", "Chunk", "Entity"],
            "relations": list(_ALL_RELATION_ENDPOINTS),
        }

    def _upsert_llama_document(self, connection, scope: GraphDatabaseScope, node: EntityNode) -> None:
        properties = dict(node.properties or {})
        connection.execute(
            """
            MERGE (d:Document {id: $id})
            SET d.tenant_id = $tenant_id, d.app_id = $app_id, d.collection_id = $collection_id,
                d.document_id = $document_id, d.filename = $filename, d.title = $title,
                d.sha256 = $sha256, d.extension = $extension, d.metadata_json = $metadata_json
            """,
            {
                "id": node.id,
                **_scope_params(scope),
                "document_id": str(properties.get("document_id") or ""),
                "filename": str(properties.get("filename") or ""),
                "title": str(properties.get("title") or ""),
                "sha256": str(properties.get("sha256") or ""),
                "extension": str(properties.get("extension") or ""),
                "metadata_json": _json(properties),
            },
        )

    def _upsert_llama_element(self, connection, scope: GraphDatabaseScope, node: EntityNode) -> None:
        properties = dict(node.properties or {})
        connection.execute(
            """
            MERGE (e:Element {id: $id})
            SET e.tenant_id = $tenant_id, e.app_id = $app_id, e.collection_id = $collection_id,
                e.document_id = $document_id, e.element_id = $element_id, e.element_type = $element_type,
                e.order_index = $order_index, e.level = $level, e.page_number = $page_number,
                e.sheet_name = $sheet_name, e.slide_number = $slide_number, e.text = $text,
                e.metadata_json = $metadata_json
            """,
            {
                "id": node.id,
                **_scope_params(scope),
                "document_id": str(properties.get("document_id") or ""),
                "element_id": str(properties.get("element_id") or ""),
                "element_type": str(properties.get("element_type") or ""),
                "order_index": int(properties.get("order_index") or 0),
                "level": int(properties.get("level") or 0),
                "page_number": int(properties.get("page_number") or 0),
                "sheet_name": str(properties.get("sheet_name") or ""),
                "slide_number": int(properties.get("slide_number") or 0),
                "text": str(properties.get("text") or ""),
                "metadata_json": _json(properties),
            },
        )

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

    def _upsert_entity(self, connection, scope: GraphDatabaseScope, entity_node_id: str, entity) -> None:
        connection.execute(
            """
            MERGE (e:Entity {id: $id})
            SET
                e.tenant_id = $tenant_id,
                e.app_id = $app_id,
                e.collection_id = $collection_id,
                e.entity_type = $entity_type,
                e.name = $name,
                e.normalized_name = $normalized_name,
                e.description = $description,
                e.metadata_json = $metadata_json
            """,
            {
                "id": entity_node_id,
                **_scope_params(scope),
                "entity_type": entity.entity_type,
                "name": entity.name,
                "normalized_name": entity.normalized_name,
                "description": entity.description,
                "metadata_json": _json(entity.metadata),
            },
        )

    def _merge_mention(
        self,
        connection,
        entity_node_id: str,
        chunk_node_id: str,
        document_id: str,
        chunk_id: str,
    ) -> None:
        connection.execute(
            """
            MATCH (e:Entity {id: $entity_id}), (c:Chunk {id: $chunk_node_id})
            MERGE (e)-[r:MENTIONED_IN]->(c)
            SET r.document_id = $document_id, r.chunk_id = $chunk_id
            """,
            {
                "entity_id": entity_node_id,
                "chunk_node_id": chunk_node_id,
                "document_id": document_id,
                "chunk_id": chunk_id,
            },
        )

    def _merge_semantic_relation(self, connection, source_id: str, target_id: str, relation) -> None:
        connection.execute(
            """
            MATCH (source:Entity {id: $source_id}), (target:Entity {id: $target_id})
            MERGE (source)-[r:SEMANTIC_RELATION {relation_type: $relation_type}]->(target)
            SET
                r.description = $description,
                r.confidence = $confidence,
                r.metadata_json = $metadata_json
            """,
            {
                "source_id": source_id,
                "target_id": target_id,
                "relation_type": relation.relation_type,
                "description": relation.description,
                "confidence": float(relation.confidence),
                "metadata_json": _json(relation.metadata),
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

    def _semantic_context(
        self,
        connection,
        scope: GraphDatabaseScope,
        seed_ids: list[str],
        *,
        hops: int,
    ) -> GraphTraversalResult:
        entity_ids = list(dict.fromkeys(seed_ids))
        frontier = list(entity_ids)
        for _ in range(max(0, min(int(hops), 5))):
            if not frontier:
                break
            rows = _rows(
                connection.execute(
                    """
                    MATCH (source:Entity)-[:SEMANTIC_RELATION]->(target:Entity)
                    WHERE source.tenant_id = $tenant_id
                      AND source.app_id = $app_id
                      AND source.collection_id = $collection_id
                      AND (source.id IN $entity_ids OR target.id IN $entity_ids)
                    RETURN source.id, target.id
                    """,
                    {**_scope_params(scope), "entity_ids": frontier},
                )
            )
            known = set(entity_ids)
            frontier = []
            for row in rows:
                for entity_id in (str(row[0]), str(row[1])):
                    if entity_id not in known:
                        known.add(entity_id)
                        entity_ids.append(entity_id)
                        frontier.append(entity_id)

        entity_rows = (
            _rows(
                connection.execute(
                    """
                    MATCH (e:Entity)
                    WHERE e.id IN $entity_ids
                    RETURN e.id, e.entity_type, e.name, e.description
                    """,
                    {"entity_ids": entity_ids},
                )
            )
            if entity_ids
            else []
        )
        chunk_rows = (
            _rows(
                connection.execute(
                    """
                    MATCH (e:Entity)-[:MENTIONED_IN]->(c:Chunk)
                    WHERE e.id IN $entity_ids
                      AND c.tenant_id = $tenant_id
                      AND c.app_id = $app_id
                      AND c.collection_id = $collection_id
                    RETURN DISTINCT c.chunk_id
                    """,
                    {**_scope_params(scope), "entity_ids": entity_ids},
                )
            )
            if entity_ids
            else []
        )
        return GraphTraversalResult(
            tenant_id=scope.tenant_id,
            app_id=scope.app_id,
            collection_id=scope.collection_id,
            entities=[
                GraphEntityContext(
                    entity_id=str(row[0]),
                    entity_type=str(row[1]),
                    name=str(row[2]),
                    description=str(row[3] or ""),
                )
                for row in entity_rows
            ],
            chunk_ids=[str(row[0]) for row in chunk_rows],
        )

    def _seed_entity_ids_for_chunks(self, connection, chunk_node_ids: list[str]) -> list[str]:
        if not chunk_node_ids:
            return []
        rows = _rows(
            connection.execute(
                """
                MATCH (e:Entity)-[:MENTIONED_IN]->(c:Chunk)
                WHERE c.id IN $chunk_node_ids
                RETURN DISTINCT e.id
                """,
                {"chunk_node_ids": chunk_node_ids},
            )
        )
        return [str(row[0]) for row in rows]

    def _delete_orphan_entities(self, connection, scope: GraphDatabaseScope) -> None:
        params = _scope_params(scope)
        entity_rows = _rows(
            connection.execute(
                """
                MATCH (e:Entity)
                WHERE e.tenant_id = $tenant_id
                  AND e.app_id = $app_id
                  AND e.collection_id = $collection_id
                RETURN e.id
                """,
                params,
            )
        )
        mentioned_rows = _rows(
            connection.execute(
                """
                MATCH (e:Entity)-[:MENTIONED_IN]->(:Chunk)
                WHERE e.tenant_id = $tenant_id
                  AND e.app_id = $app_id
                  AND e.collection_id = $collection_id
                RETURN DISTINCT e.id
                """,
                params,
            )
        )
        mentioned_ids = {str(row[0]) for row in mentioned_rows}
        for row in entity_rows:
            entity_id = str(row[0])
            if entity_id not in mentioned_ids:
                connection.execute("MATCH (e:Entity {id: $id}) DETACH DELETE e", {"id": entity_id})

    def _structure_visualization_nodes(
        self,
        connection,
        scope: GraphDatabaseScope,
        document_id: str | None,
    ) -> list[GraphVisualizationNode]:
        where_document, params = _document_where(scope, document_id, alias="n")
        nodes: list[GraphVisualizationNode] = []
        for label, fields in (
            ("Document", "n.id, n.document_id, n.title, n.filename, n.metadata_json"),
            (
                "Element",
                "n.id, n.element_id, n.element_type, n.text, n.metadata_json, "
                "n.page_number, n.sheet_name, n.slide_number",
            ),
            ("Chunk", "n.id, n.chunk_id, n.chunk_index, n.text, n.metadata_json"),
        ):
            rows = _rows(connection.execute(f"MATCH (n:{label}) WHERE {where_document} RETURN {fields}", params))
            for row in rows:
                properties = _dict(row[4])
                properties.update({"record_id": str(row[1]), "detail": str(row[3] or "")})
                if label == "Element":
                    properties.update(
                        {
                            "element_type": str(row[2] or ""),
                            "page_number": int(row[5] or 0) or None,
                            "sheet_name": str(row[6] or "") or None,
                            "slide_number": int(row[7] or 0) or None,
                        }
                    )
                if label == "Chunk":
                    properties["chunk_index"] = int(row[2] or 0)
                nodes.append(
                    GraphVisualizationNode(
                        id=str(row[0]),
                        node_type=label,
                        label=_structure_node_label(
                            node_type=label,
                            record_id=str(row[1]),
                            value=row[2],
                            detail=str(row[3] or ""),
                            properties=properties,
                        ),
                        properties=properties,
                    )
                )
        return nodes

    def _structure_visualization_edges(
        self,
        connection,
        scope: GraphDatabaseScope,
        document_id: str | None,
    ) -> list[GraphVisualizationEdge]:
        params: dict[str, Any] = _scope_params(scope)
        document_filter = ""
        if document_id:
            params["document_id"] = document_id
            document_filter = "AND source.document_id = $document_id"
        edges: list[GraphVisualizationEdge] = []
        for from_label, relation_type, to_label in (
            ("Document", "HAS_ELEMENT", "Element"),
            ("Document", "HAS_CHUNK", "Chunk"),
            ("Chunk", "DERIVED_FROM", "Element"),
            ("Chunk", "NEXT_CHUNK", "Chunk"),
            ("Chunk", "PARENT_CHUNK", "Chunk"),
        ):
            rows = _rows(
                connection.execute(
                    f"""
                    MATCH (source:{from_label})-[:{relation_type}]->(target:{to_label})
                    WHERE source.tenant_id = $tenant_id
                      AND source.app_id = $app_id
                      AND source.collection_id = $collection_id
                      {document_filter}
                    RETURN source.id, target.id
                    """,
                    params,
                )
            )
            edges.extend(_visualization_edge(str(row[0]), str(row[1]), relation_type) for row in rows)
        return edges

    def _semantic_visualization_nodes(
        self,
        connection,
        scope: GraphDatabaseScope,
        document_id: str | None,
    ) -> list[GraphVisualizationNode]:
        params: dict[str, Any] = _scope_params(scope)
        document_filter = ""
        if document_id:
            params["document_id"] = document_id
            document_filter = "AND c.document_id = $document_id"
        rows = _rows(
            connection.execute(
                f"""
                MATCH (e:Entity)-[:MENTIONED_IN]->(c:Chunk)
                WHERE e.tenant_id = $tenant_id
                  AND e.app_id = $app_id
                  AND e.collection_id = $collection_id
                  {document_filter}
                RETURN DISTINCT e.id, e.entity_type, e.name, e.description, e.metadata_json
                """,
                params,
            )
        )
        return [
            GraphVisualizationNode(
                id=str(row[0]),
                node_type="Entity",
                label=str(row[2]),
                properties={
                    **_dict(row[4]),
                    "entity_type": str(row[1]),
                    "description": str(row[3] or ""),
                },
            )
            for row in rows
        ]

    def _semantic_visualization_edges(
        self,
        connection,
        scope: GraphDatabaseScope,
        document_id: str | None,
        included_ids: set[str],
    ) -> list[GraphVisualizationEdge]:
        params: dict[str, Any] = _scope_params(scope)
        document_filter = ""
        if document_id:
            params["document_id"] = document_id
            document_filter = "AND target.document_id = $document_id"
        relation_rows = _rows(
            connection.execute(
                """
                MATCH (source:Entity)-[r:SEMANTIC_RELATION]->(target:Entity)
                WHERE source.tenant_id = $tenant_id
                  AND source.app_id = $app_id
                  AND source.collection_id = $collection_id
                RETURN source.id, target.id, r.relation_type, r.description, r.confidence, r.metadata_json
                """,
                _scope_params(scope),
            )
        )
        mention_rows = _rows(
            connection.execute(
                f"""
                MATCH (source:Entity)-[r:MENTIONED_IN]->(target:Chunk)
                WHERE source.tenant_id = $tenant_id
                  AND source.app_id = $app_id
                  AND source.collection_id = $collection_id
                  {document_filter}
                RETURN source.id, target.id, r.document_id, r.chunk_id
                """,
                params,
            )
        )
        edges = [
            _visualization_edge(
                str(row[0]),
                str(row[1]),
                str(row[2]),
                {
                    **_dict(row[5]),
                    "description": str(row[3] or ""),
                    "confidence": float(row[4] or 0),
                },
            )
            for row in relation_rows
            if str(row[0]) in included_ids and str(row[1]) in included_ids
        ]
        edges.extend(
            _visualization_edge(
                str(row[0]),
                str(row[1]),
                "MENTIONED_IN",
                {"document_id": str(row[2]), "chunk_id": str(row[3])},
            )
            for row in mention_rows
        )
        return edges


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
    """
    CREATE NODE TABLE IF NOT EXISTS Entity(
        id STRING,
        tenant_id STRING,
        app_id STRING,
        collection_id STRING,
        entity_type STRING,
        name STRING,
        normalized_name STRING,
        description STRING,
        metadata_json STRING,
        PRIMARY KEY(id)
    )
    """,
    "CREATE REL TABLE IF NOT EXISTS HAS_ELEMENT(FROM Document TO Element)",
    "CREATE REL TABLE IF NOT EXISTS HAS_CHUNK(FROM Document TO Chunk)",
    "CREATE REL TABLE IF NOT EXISTS DERIVED_FROM(FROM Chunk TO Element)",
    "CREATE REL TABLE IF NOT EXISTS NEXT_CHUNK(FROM Chunk TO Chunk)",
    "CREATE REL TABLE IF NOT EXISTS PARENT_CHUNK(FROM Chunk TO Chunk)",
    """
    CREATE REL TABLE IF NOT EXISTS MENTIONED_IN(
        FROM Entity TO Chunk,
        document_id STRING,
        chunk_id STRING
    )
    """,
    """
    CREATE REL TABLE IF NOT EXISTS SEMANTIC_RELATION(
        FROM Entity TO Entity,
        relation_type STRING,
        description STRING,
        confidence DOUBLE,
        metadata_json STRING
    )
    """,
]

_RELATION_ENDPOINTS = {
    "HAS_ELEMENT": ("Document", "Element"),
    "HAS_CHUNK": ("Document", "Chunk"),
    "DERIVED_FROM": ("Chunk", "Element"),
    "NEXT_CHUNK": ("Chunk", "Chunk"),
    "PARENT_CHUNK": ("Chunk", "Chunk"),
}

_ALL_RELATION_ENDPOINTS = {
    **_RELATION_ENDPOINTS,
    "MENTIONED_IN": ("Entity", "Chunk"),
    "SEMANTIC_RELATION": ("Entity", "Entity"),
}


def _document_node_id(scope: GraphDatabaseScope, document_id: str) -> str:
    return _record_node_id(scope, "document", document_id)


def _entity_node_id(scope: GraphDatabaseScope, entity_type: str, normalized_name: str) -> str:
    digest = sha256(f"{entity_type.casefold()}:{normalized_name}".encode("utf-8")).hexdigest()
    return _record_node_id(scope, "entity", digest)


def _record_node_id(scope: GraphDatabaseScope, record_type: str, record_id: str) -> str:
    collection_id = _collection_value(scope.collection_id)
    return f"{scope.tenant_id}:{scope.app_id}:{collection_id}:{record_type}:{record_id}"


def _collection_value(collection_id: str | None) -> str:
    return collection_id or ""


def _scope_params(scope: GraphDatabaseScope) -> dict[str, str]:
    return {
        "tenant_id": scope.tenant_id,
        "app_id": scope.app_id,
        "collection_id": _collection_value(scope.collection_id),
    }


def _scope_from_properties(properties: dict[str, Any]) -> GraphDatabaseScope:
    tenant_id = str(properties.get("tenant_id") or "").strip()
    app_id = str(properties.get("app_id") or "").strip()
    if not tenant_id or not app_id:
        raise KuzuGraphStoreError("LlamaIndex graph node is missing tenant/app scope.")
    return GraphDatabaseScope(
        tenant_id=tenant_id,
        app_id=app_id,
        collection_id=str(properties.get("collection_id") or "") or None,
    )


def _document_where(scope: GraphDatabaseScope, document_id: str | None, *, alias: str) -> tuple[str, dict[str, Any]]:
    where = [
        f"{alias}.tenant_id = $tenant_id",
        f"{alias}.app_id = $app_id",
        f"{alias}.collection_id = $collection_id",
    ]
    params: dict[str, Any] = _scope_params(scope)
    if document_id:
        where.append(f"{alias}.document_id = $document_id")
        params["document_id"] = document_id
    return " AND ".join(where), params


def _normalized_name(value: str) -> str:
    return " ".join(str(value).casefold().split())


def _structure_node_label(
    *,
    node_type: str,
    record_id: str,
    value: Any,
    detail: str,
    properties: dict[str, Any],
) -> str:
    if node_type == "Document":
        return _excerpt(str(value or detail or record_id), limit=84)
    if node_type == "Chunk":
        chunk_number = int(value or 0) + 1
        return f"Chunk {chunk_number}: {_excerpt(detail, limit=72)}"

    element_type = str(value or "element").replace("_", " ").strip().title()
    location = _element_location(properties)
    excerpt = _excerpt(detail, limit=72)
    if excerpt:
        return f"{element_type}{location}: {excerpt}"
    return f"{element_type}{location}"


def _element_location(properties: dict[str, Any]) -> str:
    if properties.get("page_number"):
        return f" - page {properties['page_number']}"
    if properties.get("slide_number"):
        return f" - slide {properties['slide_number']}"
    if properties.get("sheet_name"):
        return f" - sheet {properties['sheet_name']}"
    return ""


def _excerpt(value: str, *, limit: int) -> str:
    clean_value = " ".join(str(value or "").split())
    if len(clean_value) <= limit:
        return clean_value
    return f"{clean_value[: limit - 3].rstrip()}..."


def _visualization_edge(
    source: str,
    target: str,
    relation_type: str,
    properties: dict[str, Any] | None = None,
) -> GraphVisualizationEdge:
    edge_id = sha256(f"{source}:{relation_type}:{target}".encode("utf-8")).hexdigest()
    return GraphVisualizationEdge(
        id=edge_id,
        source=source,
        target=target,
        relation_type=relation_type,
        properties=properties or {},
    )


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
