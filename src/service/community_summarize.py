# 커뮤니티 요약: 탐지된 엔티티 커뮤니티를 LLM으로 요약하고 DB에 저장한다.
from __future__ import annotations

import os
from typing import Any, Protocol
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models import CommunitySummary, Entity, EntityRelation
from src.service.entity_graph import EntityGraphService

COMMUNITY_SUMMARY_MODEL_ENV = "GUARDIAN_COMMUNITY_SUMMARY_MODEL"
DEFAULT_COMMUNITY_SUMMARY_MODEL = "claude-haiku-4-5-20251001"
COMMUNITY_SUMMARY_MAX_TOKENS = 4096
MIN_COMMUNITY_SIZE_FOR_SUMMARY = 2

_SUMMARY_TOOL_NAME = "community_summary"
_SUMMARY_TOOL_SCHEMA: dict[str, Any] = {
    "name": _SUMMARY_TOOL_NAME,
    "description": "Return a concise summary of this entity community.",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
        },
        "required": ["summary"],
        "additionalProperties": False,
    },
}

_SUMMARY_PROMPT_TEMPLATE = (
    "다음은 하나의 커뮤니티(주제적으로 연결된 엔티티 묶음)에 속한 엔티티와 관계입니다.\n"
    "이 커뮤니티가 전체적으로 무엇에 관한 것인지 2~3문장으로 요약해줘.\n"
    "구체적인 엔티티 이름과 관계를 활용해서 한국어로 작성해.\n\n"
    "엔티티:\n{entities}\n\n"
    "관계:\n{relations}"
)


class CommunitySummarizer(Protocol):
    def summarize(self, *, entities: list[str], relations: list[str]) -> str:
        pass


class AnthropicCommunitySummarizer(CommunitySummarizer):
    def __init__(
        self,
        *,
        model: str | None = None,
        max_tokens: int = COMMUNITY_SUMMARY_MAX_TOKENS,
    ) -> None:
        self._model = model or os.getenv(
            COMMUNITY_SUMMARY_MODEL_ENV, DEFAULT_COMMUNITY_SUMMARY_MODEL
        )
        self._max_tokens = max_tokens
        self._client = None

    def summarize(self, *, entities: list[str], relations: list[str]) -> str:
        import anthropic

        if self._client is None:
            self._client = anthropic.Anthropic()

        prompt = _SUMMARY_PROMPT_TEMPLATE.format(
            entities="\n".join(f"- {name}" for name in entities),
            relations="\n".join(f"- {relation}" for relation in relations) or "(없음)",
        )
        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            tools=[_SUMMARY_TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": _SUMMARY_TOOL_NAME},
            messages=[{"role": "user", "content": prompt}],
        )
        for block in response.content:
            if (
                getattr(block, "type", None) == "tool_use"
                and getattr(block, "name", None) == _SUMMARY_TOOL_NAME
            ):
                return block.input.get("summary", "")
        return ""


def recompute_communities(
    session: Session,
    *,
    entity_graph_service: EntityGraphService,
    summarizer: CommunitySummarizer | None = None,
) -> list[CommunitySummary]:
    """전체 커뮤니티를 다시 탐지하고 요약을 새로 만든다 (기존 요약은 모두 교체한다)."""
    summarizer = summarizer or AnthropicCommunitySummarizer()
    communities = entity_graph_service.detect_communities()

    for entity in session.scalars(select(Entity)):
        entity.community_id = None
    session.flush()
    for summary in session.scalars(select(CommunitySummary)):
        session.delete(summary)
    session.flush()

    created: list[CommunitySummary] = []
    for entity_ids in communities:
        if len(entity_ids) < MIN_COMMUNITY_SIZE_FOR_SUMMARY:
            continue

        entities = list(
            session.scalars(select(Entity).where(Entity.id.in_(entity_ids)).order_by(Entity.name))
        )
        if not entities:
            continue

        relation_lines = _relation_lines(session, entity_ids, entities)
        summary_text = summarizer.summarize(
            entities=[entity.name for entity in entities],
            relations=relation_lines,
        )
        if not summary_text:
            continue

        community = CommunitySummary(
            id=str(uuid4()),
            summary=summary_text,
            entity_count=len(entities),
        )
        session.add(community)
        session.flush()
        for entity in entities:
            entity.community_id = community.id
        created.append(community)

    return created


def _relation_lines(session: Session, entity_ids: set[str], entities: list[Entity]) -> list[str]:
    relations = list(
        session.scalars(
            select(EntityRelation).where(
                EntityRelation.source_entity_id.in_(entity_ids),
                EntityRelation.target_entity_id.in_(entity_ids),
            )
        )
    )
    entity_by_id = {entity.id: entity for entity in entities}
    return [
        f"{entity_by_id[relation.source_entity_id].name} -[{relation.relation_type}]-> "
        f"{entity_by_id[relation.target_entity_id].name}: {relation.description}"
        for relation in relations
        if relation.source_entity_id in entity_by_id and relation.target_entity_id in entity_by_id
    ]
