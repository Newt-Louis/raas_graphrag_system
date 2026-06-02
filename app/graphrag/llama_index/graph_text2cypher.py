from __future__ import annotations

import re

from llama_index.core.indices.property_graph import TextToCypherRetriever
from llama_index.core.llms import LLM

from app.graphrag.graph_database import GraphDatabaseScope, KuzuGraphStore


class CypherGuardrailError(RuntimeError):
    """Câu Cypher do LLM sinh ra vi phạm guardrail read-only."""


# Chặn mọi từ khoá ghi/DDL của Kùzu/OpenCypher. Text-to-cypher chỉ được đọc.
_WRITE_KEYWORDS = re.compile(
    r"(?i)\b(CREATE|MERGE|SET|DELETE|DETACH|DROP|ALTER|COPY|INSTALL|LOAD|REMOVE|RENAME|TRUNCATE)\b"
)


def read_only_cypher_validator(cypher_query: str) -> str:
    """Guardrail: chỉ chấp nhận truy vấn Cypher read-only, đã làm sạch."""
    cleaned = (cypher_query or "").strip()
    fenced = re.fullmatch(r"```(?:cypher|opencypher)?\s*(.*?)\s*```", cleaned, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        cleaned = fenced.group(1).strip()
    cleaned = cleaned.rstrip(";").strip()
    if not cleaned:
        raise CypherGuardrailError("LLM không sinh được câu Cypher.")
    if _WRITE_KEYWORDS.search(cleaned):
        raise CypherGuardrailError("Chỉ cho phép truy vấn Cypher read-only; phát hiện thao tác ghi.")
    if not re.search(r"(?i)\b(MATCH|RETURN|WITH|UNWIND|CALL)\b", cleaned):
        raise CypherGuardrailError("Câu Cypher không hợp lệ (thiếu MATCH/RETURN).")
    return cleaned


def build_text_to_cypher_template(scope: GraphDatabaseScope) -> str:
    """Prompt ép LLM sinh OpenCypher read-only, đúng schema và đúng scope tenant/app.

    Chỉ ``{schema}`` và ``{question}`` là placeholder cho TextToCypherRetriever điền;
    giá trị scope được nhúng sẵn dạng literal để không thành biến template.
    """
    collection_clause = (
        f" AND n.collection_id = '{scope.collection_id}'" if scope.collection_id else ""
    )
    scope_rule = (
        "- ALWAYS scope every matched node n by "
        f"n.tenant_id = '{scope.tenant_id}' AND n.app_id = '{scope.app_id}'"
        f"{collection_clause}.\n"
    )
    return (
        "You are an expert at writing READ-ONLY OpenCypher queries for a Kùzu property graph.\n\n"
        "Graph schema:\n{schema}\n\n"
        "Rules:\n"
        "- Generate exactly ONE read-only OpenCypher query that best answers the question.\n"
        "- Use ONLY the node labels, relationship types and properties in the schema above. "
        "Never invent labels, relationships or properties.\n"
        "- READ-ONLY: never use CREATE, MERGE, SET, DELETE, DETACH, DROP, ALTER, COPY, INSTALL, LOAD or REMOVE.\n"
        + scope_rule
        + "- Match entities by Entity.normalized_name CONTAINS a lowercased, unaccented keyword from the question.\n"
        "- For relationships between entities, traverse SEMANTIC_RELATION and return relation_type and description.\n"
        "- Return human-readable columns (names, descriptions, relation_type, chunk text) and end with LIMIT 30.\n"
        "- Output ONLY the Cypher query. No prose, no explanation, no markdown fences.\n\n"
        "Question: {question}\n\n"
        "OpenCypher query:"
    )


def build_kuzu_text2cypher_retriever(
    *,
    graph_store: KuzuGraphStore,
    llm: LLM,
    scope: GraphDatabaseScope,
    include_raw_response_as_metadata: bool = True,
) -> TextToCypherRetriever:
    """Dựng TextToCypherRetriever của LlamaIndex trên Kùzu với guardrail read-only."""
    return TextToCypherRetriever(
        graph_store=graph_store,
        llm=llm,
        text_to_cypher_template=build_text_to_cypher_template(scope),
        cypher_validator=read_only_cypher_validator,
        include_raw_response_as_metadata=include_raw_response_as_metadata,
    )
