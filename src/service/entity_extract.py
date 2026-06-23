# 엔티티/관계 추출: 청크 텍스트에서 GraphRAG용 엔티티-관계 그래프 재료를 뽑아낸다.
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Protocol

ENTITY_EXTRACT_MODEL_ENV = "GUARDIAN_ENTITY_EXTRACT_MODEL"
DEFAULT_ENTITY_EXTRACT_MODEL = "claude-haiku-4-5-20251001"
ENTITY_EXTRACT_MAX_TOKENS = 4096

_ENTITY_EXTRACT_TOOL_NAME = "extracted_graph"
_ENTITY_EXTRACT_TOOL_SCHEMA: dict[str, Any] = {
    "name": _ENTITY_EXTRACT_TOOL_NAME,
    "description": "Return entities and relations extracted from the text.",
    "input_schema": {
        "type": "object",
        "properties": {
            "entities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "entity_type": {"type": "string"},
                    },
                    "required": ["name", "entity_type"],
                    "additionalProperties": False,
                },
            },
            "relations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "source": {"type": "string"},
                        "target": {"type": "string"},
                        "relation_type": {"type": "string"},
                        "description": {"type": "string"},
                    },
                    "required": ["source", "target", "relation_type", "description"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["entities", "relations"],
        "additionalProperties": False,
    },
}

_EXTRACT_PROMPT_TEMPLATE = (
    "다음 텍스트에서 핵심 엔티티(기술, 개념, 프로젝트, 파일, 결정 등)와 "
    "엔티티 간 관계를 추출해줘.\n"
    "- 엔티티 이름은 텍스트에 실제로 등장한 표현을 그대로 써.\n"
    "- relation의 source/target은 반드시 entities 목록에 있는 이름과 정확히 같아야 해.\n"
    "- 너무 일반적이거나 사소한 엔티티는 빼고 핵심적인 것만 추출해.\n"
    "- 관계가 명확하지 않으면 relations는 빈 배열로 둬.\n\n"
    "텍스트:\n{text}"
)


@dataclass(frozen=True)
class ExtractedEntity:
    name: str
    entity_type: str


@dataclass(frozen=True)
class ExtractedRelation:
    source: str
    target: str
    relation_type: str
    description: str


@dataclass(frozen=True)
class ExtractionResult:
    entities: list[ExtractedEntity] = field(default_factory=list)
    relations: list[ExtractedRelation] = field(default_factory=list)


class EntityExtractor(Protocol):
    def extract(self, text: str) -> ExtractionResult:
        pass


class AnthropicEntityExtractor(EntityExtractor):
    def __init__(
        self,
        *,
        model: str | None = None,
        max_tokens: int = ENTITY_EXTRACT_MAX_TOKENS,
    ) -> None:
        self._model = model or os.getenv(ENTITY_EXTRACT_MODEL_ENV, DEFAULT_ENTITY_EXTRACT_MODEL)
        self._max_tokens = max_tokens
        self._client = None

    def extract(self, text: str) -> ExtractionResult:
        import anthropic

        if self._client is None:
            self._client = anthropic.Anthropic()

        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            tools=[_ENTITY_EXTRACT_TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": _ENTITY_EXTRACT_TOOL_NAME},
            messages=[{"role": "user", "content": _EXTRACT_PROMPT_TEMPLATE.format(text=text)}],
        )
        return _parse_extraction_response(response)


def _parse_extraction_response(response: Any) -> ExtractionResult:
    for block in response.content:
        if (
            getattr(block, "type", None) == "tool_use"
            and getattr(block, "name", None) == _ENTITY_EXTRACT_TOOL_NAME
        ):
            return _extraction_result_from_payload(block.input)
    return ExtractionResult()


def _extraction_result_from_payload(payload: dict[str, Any]) -> ExtractionResult:
    entities: list[ExtractedEntity] = []
    entity_names: set[str] = set()
    for item in payload.get("entities", []):
        name = item.get("name")
        entity_type = item.get("entity_type")
        if not name or not entity_type:
            continue
        entities.append(ExtractedEntity(name=name, entity_type=entity_type))
        entity_names.add(name)

    relations: list[ExtractedRelation] = []
    for item in payload.get("relations", []):
        source = item.get("source")
        target = item.get("target")
        relation_type = item.get("relation_type")
        description = item.get("description", "")
        if not source or not target or not relation_type:
            continue
        if source == target:
            continue
        if source not in entity_names or target not in entity_names:
            continue
        relations.append(
            ExtractedRelation(
                source=source,
                target=target,
                relation_type=relation_type,
                description=description,
            )
        )

    return ExtractionResult(entities=entities, relations=relations)
