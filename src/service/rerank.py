# Cross-encoder 기반 리랭커: 1차 벡터 검색 후보 풀을 쿼리-문서 쌍으로 다시 채점한다.
from __future__ import annotations

import os
from typing import Protocol

RERANKER_MODEL_ENV = "GUARDIAN_RERANKER_MODEL"
DEFAULT_RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"


class Reranker(Protocol):
    def rerank(self, query: str, documents: list[str]) -> list[float]:
        pass


class CrossEncoderReranker(Reranker):
    def __init__(self, model_name: str | None = None) -> None:
        self._model_name = model_name or os.getenv(RERANKER_MODEL_ENV, DEFAULT_RERANKER_MODEL)
        self._model = None

    def rerank(self, query: str, documents: list[str]) -> list[float]:
        if not documents:
            return []
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self._model_name)

        scores = self._model.predict([(query, document) for document in documents])
        return [float(score) for score in scores]
