from __future__ import annotations

import os
from collections.abc import Iterable

import networkx as nx
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from src.crud.graph_edge import list_graph_edges, upsert_graph_edge
from src.models import Chunk
from src.service.embed import (
    ChromaChunkVectorStore,
    ChunkVectorStore,
    Embedder,
    SentenceTransformerEmbedder,
)

SIMILARITY_THRESHOLD_ENV = "GUARDIAN_GRAPH_SIMILARITY_THRESHOLD"
TOP_K_ENV = "GUARDIAN_GRAPH_TOP_K"
DEFAULT_SIMILARITY_THRESHOLD = 0.75
DEFAULT_TOP_K = 10


class GraphService:
    def __init__(
        self,
        *,
        embedder: Embedder | None = None,
        vector_store: ChunkVectorStore | None = None,
        similarity_threshold: float | None = None,
        top_k: int | None = None,
    ) -> None:
        self.embedder = embedder or SentenceTransformerEmbedder()
        self.vector_store = vector_store or ChromaChunkVectorStore()
        if similarity_threshold is None:
            similarity_threshold = float(
                os.getenv(SIMILARITY_THRESHOLD_ENV, DEFAULT_SIMILARITY_THRESHOLD)
            )
        if top_k is None:
            top_k = int(os.getenv(TOP_K_ENV, DEFAULT_TOP_K))
        self.similarity_threshold = similarity_threshold
        self.top_k = top_k
        self.graph = nx.Graph()

    def reconstruct(self, session: Session) -> None:
        graph = nx.Graph()
        try:
            for chunk in session.scalars(select(Chunk)):
                graph.add_node(chunk.id, source_id=chunk.source_id)
            for edge in list_graph_edges(session):
                graph.add_edge(edge.from_chunk_id, edge.to_chunk_id, similarity=edge.similarity)
        except OperationalError as exc:
            if "no such table" not in str(exc):
                raise
        self.graph = graph

    def connect_chunks(self, session: Session, chunks: Iterable[Chunk]) -> None:
        for chunk in chunks:
            embedding = self.embedder.embed(chunk.text)
            candidates = self.vector_store.query_similar(embedding, limit=self.top_k)
            candidate_ids = [
                candidate.chunk_id for candidate in candidates if candidate.chunk_id != chunk.id
            ]
            existing_ids = set()
            if candidate_ids:
                existing_ids = set(
                    session.scalars(select(Chunk.id).where(Chunk.id.in_(candidate_ids)))
                )

            self.graph.add_node(chunk.id, source_id=chunk.source_id)
            for candidate in candidates:
                if candidate.chunk_id == chunk.id:
                    continue
                if candidate.chunk_id not in existing_ids:
                    continue
                if candidate.similarity < self.similarity_threshold:
                    continue

                edge = upsert_graph_edge(
                    session,
                    from_chunk_id=chunk.id,
                    to_chunk_id=candidate.chunk_id,
                    similarity=candidate.similarity,
                )
                self.graph.add_edge(
                    edge.from_chunk_id,
                    edge.to_chunk_id,
                    similarity=edge.similarity,
                )

            self.vector_store.upsert_chunk(chunk, embedding)

    def delete_chunks(self, chunk_ids: list[str]) -> None:
        self.vector_store.delete_chunks(chunk_ids)
        self.graph.remove_nodes_from(chunk_ids)
