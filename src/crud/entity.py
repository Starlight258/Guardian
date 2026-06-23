from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models import ChunkEntity, Entity, EntityRelation


def normalize_entity_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


def get_or_create_entity(session: Session, *, name: str, entity_type: str) -> Entity:
    normalized_name = normalize_entity_name(name)
    entity = session.scalar(
        select(Entity).where(
            Entity.normalized_name == normalized_name,
            Entity.entity_type == entity_type,
        )
    )
    if entity is None:
        entity = Entity(
            id=str(uuid4()),
            name=name,
            normalized_name=normalized_name,
            entity_type=entity_type,
            mention_count=1,
        )
        session.add(entity)
        session.flush()
    else:
        entity.mention_count += 1
    return entity


def record_chunk_entity(
    session: Session,
    *,
    chunk_id: str,
    entity_id: str,
    mention_text: str,
) -> ChunkEntity | None:
    existing = session.scalar(
        select(ChunkEntity).where(
            ChunkEntity.chunk_id == chunk_id,
            ChunkEntity.entity_id == entity_id,
        )
    )
    if existing is not None:
        return None
    chunk_entity = ChunkEntity(chunk_id=chunk_id, entity_id=entity_id, mention_text=mention_text)
    session.add(chunk_entity)
    session.flush()
    return chunk_entity


def upsert_entity_relation(
    session: Session,
    *,
    source_entity_id: str,
    target_entity_id: str,
    relation_type: str,
    description: str,
    source_chunk_id: str,
) -> EntityRelation:
    relation = session.scalar(
        select(EntityRelation).where(
            EntityRelation.source_entity_id == source_entity_id,
            EntityRelation.target_entity_id == target_entity_id,
            EntityRelation.relation_type == relation_type,
        )
    )
    if relation is None:
        relation = EntityRelation(
            source_entity_id=source_entity_id,
            target_entity_id=target_entity_id,
            relation_type=relation_type,
            description=description,
            weight=1,
            source_chunk_id=source_chunk_id,
        )
        session.add(relation)
        session.flush()
    else:
        relation.weight += 1
    return relation


def list_entity_relations(session: Session) -> list[EntityRelation]:
    return list(session.scalars(select(EntityRelation)))
