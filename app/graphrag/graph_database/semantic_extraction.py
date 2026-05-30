from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from app.graphrag.ai_client import GraphRAGAIClient
from app.graphrag.graph_database.models import (
    SemanticEntity,
    SemanticExtraction,
    SemanticRelation,
)
from app.graphrag.graph_database.ontology import (
    SOFTWARE_OPERATIONS_ONTOLOGY,
    GraphOntology,
)


class SemanticExtractionError(RuntimeError):
    pass


class SemanticGraphExtractor:
    def __init__(
        self,
        ai_client: GraphRAGAIClient,
        *,
        profile_id: str | None = None,
        ontology: GraphOntology = SOFTWARE_OPERATIONS_ONTOLOGY,
    ) -> None:
        self.ai_client = ai_client
        self.profile_id = profile_id
        self.ontology = ontology

    async def extract_chunk(
        self,
        text: str,
        *,
        tenant_id: str,
        app_id: str,
        collection_id: str | None = None,
    ) -> SemanticExtraction:
        result = await self.ai_client.extract_graph_semantics(
            [
                {
                    "role": "system",
                    "content": "Return JSON only. Extract facts stated in the document chunk.",
                },
                {"role": "user", "content": self.ontology.extraction_prompt(text)},
            ],
            tenant_id=tenant_id,
            app_id=app_id,
            collection_id=collection_id,
            profile_id=self.profile_id,
            temperature=0,
        )
        if not result.success:
            raise SemanticExtractionError(result.final_reason or "Semantic graph extraction failed.")
        return parse_semantic_extraction(result.data, ontology=self.ontology)


def parse_semantic_extraction(
    raw: Any,
    *,
    ontology: GraphOntology = SOFTWARE_OPERATIONS_ONTOLOGY,
) -> SemanticExtraction:
    payload = _json_object(raw)
    allowed_entity_types = {value.casefold(): value for value in ontology.entity_types}
    allowed_relation_types = {value.casefold(): value for value in ontology.relation_types}

    entities: list[SemanticEntity] = []
    entity_ids: set[str] = set()
    for item in _list(payload.get("entities")):
        local_id = str(item.get("id") or "").strip()
        name = str(item.get("name") or "").strip()
        entity_type = allowed_entity_types.get(str(item.get("type") or "").strip().casefold())
        if not local_id or not name or entity_type is None or local_id in entity_ids:
            continue
        entity_ids.add(local_id)
        entities.append(
            SemanticEntity(
                local_id=local_id,
                entity_type=entity_type,
                name=name,
                normalized_name=_normalize_name(name),
                description=str(item.get("description") or "").strip(),
                metadata=_dict(item.get("metadata")),
            )
        )

    relations: list[SemanticRelation] = []
    relation_keys: set[tuple[str, str, str]] = set()
    for item in _list(payload.get("relations")):
        source_id = str(item.get("source_id") or item.get("from_id") or "").strip()
        target_id = str(item.get("target_id") or item.get("to_id") or "").strip()
        relation_type = allowed_relation_types.get(str(item.get("type") or "").strip().casefold())
        key = (source_id, relation_type or "", target_id)
        if (
            not source_id
            or not target_id
            or relation_type is None
            or source_id not in entity_ids
            or target_id not in entity_ids
            or key in relation_keys
        ):
            continue
        relation_keys.add(key)
        relations.append(
            SemanticRelation(
                source_id=source_id,
                target_id=target_id,
                relation_type=relation_type,
                description=str(item.get("description") or "").strip(),
                confidence=_confidence(item.get("confidence")),
                metadata=_dict(item.get("metadata")),
            )
        )
    return SemanticExtraction(entities=entities, relations=relations)


def _json_object(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        raise SemanticExtractionError("LLM semantic extraction response is not a JSON object.")
    text = raw.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1)
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SemanticExtractionError("LLM semantic extraction response is not valid JSON.") from exc
    if not isinstance(decoded, dict):
        raise SemanticExtractionError("LLM semantic extraction response is not a JSON object.")
    return decoded


def _list(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalize_name(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _confidence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 1.0

