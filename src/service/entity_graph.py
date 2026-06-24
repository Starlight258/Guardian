# 엔티티 그래프 서비스: 추출된 엔티티/관계를 저장하고, 커뮤니티 탐지용 NetworkX 그래프를 유지한다.
from __future__ import annotations

import networkx as nx
from sqlalchemy.orm import Session

from src.crud.entity import (
    get_or_create_entity,
    list_chunk_ids_for_entity,
    list_entity_ids_for_chunk,
    list_entity_relations,
    record_chunk_entity,
    upsert_entity_relation,
)
from src.models import Chunk
from src.service.entity_extract import AnthropicEntityExtractor, EntityExtractor, ExtractionResult

MIN_COMMUNITY_SIZE = 1


class EntityGraphService:
    def __init__(self, *, extractor: EntityExtractor | None = None) -> None:
        self.extractor = extractor or AnthropicEntityExtractor()
        self.graph = nx.Graph()

    def reconstruct(self, session: Session) -> None:
        graph = nx.Graph()
        for relation in list_entity_relations(session):
            graph.add_edge(
                relation.source_entity_id,
                relation.target_entity_id,
                relation_type=relation.relation_type,
                weight=relation.weight,
            )
        self.graph = graph

    def extract_and_store(self, session: Session, chunk: Chunk) -> ExtractionResult:
        """청크에서 엔티티/관계를 추출해 DB에 upsert하고, 인메모리 그래프도 갱신한다."""
        result = self.extractor.extract(chunk.text)

        entity_ids: dict[str, str] = {}
        for entity in result.entities:
            stored = get_or_create_entity(session, name=entity.name, entity_type=entity.entity_type)
            entity_ids[entity.name] = stored.id
            record_chunk_entity(
                session,
                chunk_id=chunk.id,
                entity_id=stored.id,
                mention_text=entity.name,
            )
            self.graph.add_node(stored.id)

        for relation in result.relations:
            source_id = entity_ids.get(relation.source)
            target_id = entity_ids.get(relation.target)
            if source_id is None or target_id is None:
                continue
            stored_relation = upsert_entity_relation(
                session,
                source_entity_id=source_id,
                target_entity_id=target_id,
                relation_type=relation.relation_type,
                description=relation.description,
                source_chunk_id=chunk.id,
            )
            self.graph.add_edge(
                source_id,
                target_id,
                relation_type=stored_relation.relation_type,
                weight=stored_relation.weight,
            )

        return result

    def find_related_chunk_ids(
        self,
        session: Session,
        chunk_id: str,
        *,
        exclude_chunk_ids: set[str],
        max_results: int,
    ) -> list[str]:
        """청크가 언급한 엔티티의 그래프 이웃 엔티티를 따라가, 그 이웃을 언급하는
        다른 청크 id를 찾는다 (entity-graph local search)."""
        if max_results <= 0:
            return []

        related: list[str] = []
        seen = set(exclude_chunk_ids) | {chunk_id}
        for entity_id in list_entity_ids_for_chunk(session, chunk_id):
            if entity_id not in self.graph:
                continue
            for neighbor_id in self.graph.neighbors(entity_id):
                for related_chunk_id in list_chunk_ids_for_entity(session, neighbor_id):
                    if related_chunk_id in seen:
                        continue
                    seen.add(related_chunk_id)
                    related.append(related_chunk_id)
                    if len(related) >= max_results:
                        return related
        return related

    def detect_communities(self) -> list[set[str]]:
        """modularity 기반 커뮤니티 탐지. 엣지가 없는 고립 노드는 각자 1개 커뮤니티로 취급."""
        if self.graph.number_of_edges() == 0:
            return [{node} for node in self.graph.nodes]

        communities = nx.algorithms.community.greedy_modularity_communities(
            self.graph, weight="weight"
        )
        return [set(community) for community in communities if len(community) >= MIN_COMMUNITY_SIZE]
