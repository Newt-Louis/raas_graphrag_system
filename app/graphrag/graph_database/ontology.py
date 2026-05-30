from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GraphOntology:
    entity_types: tuple[str, ...]
    relation_types: tuple[str, ...]

    def extraction_prompt(self, text: str) -> str:
        return EXTRACTION_PROMPT.format(
            entity_types=", ".join(self.entity_types),
            relation_types=", ".join(self.relation_types),
            text=text,
        )


# The platform ingests operational documentation for external software. Keep the
# ontology broad enough for product, API, permission, workflow and incident docs
# without accepting arbitrary labels emitted by an LLM.
SOFTWARE_OPERATIONS_ONTOLOGY = GraphOntology(
    entity_types=(
        "Person",
        "Organization",
        "Team",
        "Role",
        "Location",
        "Concept",
        "Technology",
        "SoftwareApplication",
        "SoftwareModule",
        "Feature",
        "UserInterface",
        "ApiEndpoint",
        "DataEntity",
        "Database",
        "Configuration",
        "Permission",
        "Workflow",
        "Task",
        "Event",
        "Error",
        "Policy",
        "Product",
    ),
    relation_types=(
        "RELATED_TO",
        "PART_OF",
        "DEPENDS_ON",
        "USES",
        "INTEGRATES_WITH",
        "EXPOSES",
        "CALLS",
        "READS_FROM",
        "WRITES_TO",
        "CONFIGURES",
        "REQUIRES",
        "GRANTS",
        "PERMITS",
        "DENIES",
        "TRIGGERS",
        "PRECEDES",
        "PRODUCES",
        "RESOLVES",
        "AFFECTS",
        "IMPLEMENTS",
        "MANAGES",
        "ASSIGNED_TO",
        "WORKS_AT",
    ),
)


EXTRACTION_PROMPT = """
Extract semantic entities and relations from the document chunk below.

Allowed entity types:
{entity_types}

Allowed relation types:
{relation_types}

Return only valid JSON with this shape:
{{
  "entities": [
    {{
      "id": "e1",
      "type": "Technology",
      "name": "LanceDB",
      "description": "Vector database"
    }}
  ],
  "relations": [
    {{
      "source_id": "e1",
      "type": "RELATED_TO",
      "target_id": "e2",
      "description": "Optional explanation",
      "confidence": 0.9
    }}
  ]
}}

Rules:
- Use only the allowed types.
- Entity ids are local to this response and must be referenced by relations.
- Do not infer facts that are not present in the text.
- Omit duplicates and return empty arrays when nothing relevant exists.

Document chunk:
{text}
""".strip()

