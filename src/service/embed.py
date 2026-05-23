# 임베딩(BAAI/bge-m3)과 Chroma 벡터 스토어로 청크 유사도 검색을 제공한다.
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from src.models import Chunk

EMBEDDING_MODEL_ENV = "GUARDIAN_EMBEDDING_MODEL"
CHROMA_PATH_ENV = "GUARDIAN_CHROMA_PATH"
DEFAULT_EMBEDDING_MODEL = "BAAI/bge-m3"
DEFAULT_CHROMA_PATH = "data/chroma"
CHROMA_COLLECTION_NAME = "guardian_chunks"


class Embedder(Protocol):
    def embed(self, text: str) -> list[float]:
        pass


class SentenceTransformerEmbedder(Embedder):
    def __init__(self, model_name: str | None = None) -> None:
        self._model_name = model_name or os.getenv(EMBEDDING_MODEL_ENV, DEFAULT_EMBEDDING_MODEL)
        self._model = None

    def embed(self, text: str) -> list[float]:
        # 시작 지연을 막기 위해 첫 호출 시 모델을 로드한다.
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)

        embedding = self._model.encode([text], normalize_embeddings=True)[0]
        return embedding.tolist()


@dataclass(frozen=True)
class VectorSearchResult:
    chunk_id: str
    similarity: float


class ChunkVectorStore(Protocol):
    def upsert_chunk(self, chunk: Chunk, embedding: list[float]) -> None:
        pass

    def query_similar(self, embedding: list[float], *, limit: int) -> list[VectorSearchResult]:
        pass

    def delete_chunks(self, chunk_ids: list[str]) -> None:
        pass


class ChromaChunkVectorStore(ChunkVectorStore):
    def __init__(
        self,
        *,
        path: Path | str | None = None,
        collection_name: str = CHROMA_COLLECTION_NAME,
    ) -> None:
        import chromadb

        self._path = Path(path or os.getenv(CHROMA_PATH_ENV, DEFAULT_CHROMA_PATH))
        self._path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(self._path))
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert_chunk(self, chunk: Chunk, embedding: list[float]) -> None:
        self._collection.upsert(
            ids=[chunk.id],
            embeddings=[embedding],
            documents=[chunk.text],
            metadatas=[
                {
                    "source_id": chunk.source_id,
                    "chunk_index": chunk.chunk_index,
                    "token_count": chunk.token_count,
                    "content_hash": chunk.content_hash,
                }
            ],
        )

    def query_similar(self, embedding: list[float], *, limit: int) -> list[VectorSearchResult]:
        if limit <= 0:
            return []

        count = self._collection.count()
        if count == 0:
            return []

        result = self._collection.query(
            query_embeddings=[embedding],
            n_results=min(limit, count),
            include=["distances"],
        )
        ids = result.get("ids", [[]])[0]
        distances = result.get("distances", [[]])[0]
        return [
            VectorSearchResult(chunk_id=chunk_id, similarity=1.0 - float(distance))
            for chunk_id, distance in zip(ids, distances, strict=False)
        ]

    def delete_chunks(self, chunk_ids: list[str]) -> None:
        if chunk_ids:
            self._collection.delete(ids=chunk_ids)
