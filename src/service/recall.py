# Recall Agent: GraphRAG로 유사 청크를 검색하고 LLM을 호출해 Angel 메시지를 생성한다.
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy.orm import Session

from src.models import Chunk, RecallLog
from src.service.graph import GraphService
from src.utils import hash_text

RECALL_TOP_K = 5
RECALL_RELEVANCE_THRESHOLD = 0.7
RECALL_ANGEL_MESSAGE_MAX_LENGTH = 120
RECALL_MAX_EVIDENCE_ITEMS = 10
RECALL_DROP_REASON_NO_CONTEXT = "missing_context"
RECALL_DROP_REASON_NO_RESULTS = "no_retrieval_results"
RECALL_DROP_REASON_INVALID_TOOL_USE = "invalid_tool_use"
RECALL_DROP_REASON_LOW_SCORE = "below_threshold"
RECALL_DROP_REASON_EMPTY_CHUNK_IDS = "empty_chunk_ids"


@dataclass(frozen=True)
class RecallContext:
    text: str
    session_id: str | None = None
    cwd: str | None = None
    transcript_path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RecallEvidence:
    chunk_id: str
    source_id: str
    source_type: str
    title: str | None
    path: str | None
    chunk_index: int
    text: str
    similarity: float
    relation: str
    neighbor_of: str | None = None


@dataclass(frozen=True)
class RecallToolOutput:
    chunk_ids: list[str]
    evidence_sources: list[str]
    relevance_score: float
    angel_message: str


@dataclass(frozen=True)
class RecallResult:
    status: str
    input_hash: str
    retrieved_chunk_ids: list[str]
    evidence_source_ids: list[str]
    relevance_score: float | None
    angel_triggered: bool
    drop_reason: str | None
    angel_message: str | None


class RecallLLMClient(Protocol):
    def complete(
        self,
        *,
        prompt: str,
        evidence: list[RecallEvidence],
        tool_schema: dict[str, Any],
    ) -> Any:
        pass


class HeuristicRecallLLMClient:
    # LLM 없이 Claude의 tool-use 응답 형태를 흉내 내는 폴백 클라이언트.

    def complete(
        self,
        *,
        prompt: str,
        evidence: list[RecallEvidence],
        tool_schema: dict[str, Any],
    ) -> dict[str, Any]:
        del tool_schema

        if not evidence:
            output = {
                "chunk_ids": [],
                "evidence_sources": [],
                "relevance_score": 0.0,
                "angel_message": "",
            }
            return {
                "content": [
                    {"type": "tool_use", "name": "angel_output", "input": output},
                ]
            }

        selected = evidence[: min(3, len(evidence))]
        chunk_ids = [item.chunk_id for item in selected]
        evidence_sources = _unique_preserve_order(item.source_id for item in selected)
        best_similarity = max(item.similarity for item in selected)
        message = _build_angel_message(prompt, selected)

        output = {
            "chunk_ids": chunk_ids,
            "evidence_sources": evidence_sources,
            "relevance_score": round(min(0.99, best_similarity), 3),
            "angel_message": message[:RECALL_ANGEL_MESSAGE_MAX_LENGTH],
        }
        return {
            "content": [
                {"type": "tool_use", "name": "angel_output", "input": output},
            ]
        }


def _build_angel_message(prompt: str, evidence: list[RecallEvidence]) -> str:
    snippets = ", ".join(
        _compact_text(item.title or item.path or item.chunk_id, limit=24) for item in evidence[:2]
    )
    prompt_preview = _compact_text(prompt, limit=60)
    if snippets:
        return f"관련 맥락: {snippets}. 현재 작업: {prompt_preview}"
    return f"현재 작업: {prompt_preview}"


def _compact_text(text: str, *, limit: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 1)].rstrip() + "…"


def _unique_preserve_order(values: list[str] | tuple[str, ...] | Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _truncate_message(message: str, *, limit: int = RECALL_ANGEL_MESSAGE_MAX_LENGTH) -> str:
    compact = " ".join(message.split())
    return compact[:limit]


def _serialize_input(context: RecallContext) -> str:
    payload = {
        "context": context.text,
        "session_id": context.session_id,
        "cwd": context.cwd,
        "transcript_path": context.transcript_path,
        "metadata": context.metadata,
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _extract_recall_context(
    *,
    prompt: str,
    session_id: str | None = None,
    cwd: str | None = None,
    transcript_path: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> RecallContext:
    return RecallContext(
        text=prompt.strip(),
        session_id=session_id,
        cwd=cwd,
        transcript_path=transcript_path,
        metadata=metadata or {},
    )


def _extract_tool_output(response: Any) -> RecallToolOutput | None:
    # Anthropic SDK 객체와 dict(로컬 LLM / 휴리스틱 클라이언트) 두 형태를 모두 처리한다.
    if response is None:
        return None

    if isinstance(response, dict):
        if {"chunk_ids", "evidence_sources", "relevance_score", "angel_message"}.issubset(
            response.keys()
        ):
            return _tool_output_from_mapping(response)
        content = response.get("content")
        if isinstance(content, list):
            for item in content:
                tool_output = _parse_content_item(item)
                if tool_output is not None:
                    return tool_output
        return None

    content = getattr(response, "content", None)
    if isinstance(content, list):
        for item in content:
            tool_output = _parse_content_item(item)
            if tool_output is not None:
                return tool_output

    tool_name = getattr(response, "name", None)
    tool_input = getattr(response, "input", None)
    if tool_name == "angel_output" and isinstance(tool_input, dict):
        return _tool_output_from_mapping(tool_input)

    return None


def _parse_content_item(item: Any) -> RecallToolOutput | None:
    if isinstance(item, dict):
        if item.get("type") == "tool_use" and item.get("name") == "angel_output":
            tool_input = item.get("input")
            if isinstance(tool_input, dict):
                return _tool_output_from_mapping(tool_input)
        if item.get("name") == "angel_output" and isinstance(item.get("input"), dict):
            return _tool_output_from_mapping(item["input"])
        return None

    if getattr(item, "type", None) == "tool_use" and getattr(item, "name", None) == "angel_output":
        tool_input = getattr(item, "input", None)
        if isinstance(tool_input, dict):
            return _tool_output_from_mapping(tool_input)

    return None


def _tool_output_from_mapping(mapping: dict[str, Any]) -> RecallToolOutput | None:
    chunk_ids = mapping.get("chunk_ids")
    evidence_sources = mapping.get("evidence_sources")
    relevance_score = mapping.get("relevance_score")
    angel_message = mapping.get("angel_message")
    if not isinstance(chunk_ids, list) or not isinstance(evidence_sources, list):
        return None
    if relevance_score is None:
        return None
    try:
        relevance = float(relevance_score)
    except (TypeError, ValueError):
        return None
    if not isinstance(angel_message, str):
        return None
    return RecallToolOutput(
        chunk_ids=[str(chunk_id) for chunk_id in chunk_ids if str(chunk_id)],
        evidence_sources=[str(source_id) for source_id in evidence_sources if str(source_id)],
        relevance_score=relevance,
        angel_message=angel_message,
    )


class RecallAgent:
    def __init__(
        self,
        *,
        graph_service: GraphService,
        llm_client: RecallLLMClient | None = None,
        top_k: int = RECALL_TOP_K,
        relevance_threshold: float = RECALL_RELEVANCE_THRESHOLD,
        persist_angel_message: bool = True,
    ) -> None:
        self.graph_service = graph_service
        self.llm_client = llm_client or HeuristicRecallLLMClient()
        self.top_k = top_k
        self.relevance_threshold = relevance_threshold
        self.persist_angel_message = persist_angel_message

    def recall(
        self,
        session: Session,
        *,
        prompt: str,
        session_id: str | None = None,
        cwd: str | None = None,
        transcript_path: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RecallResult:
        context = _extract_recall_context(
            prompt=prompt,
            session_id=session_id,
            cwd=cwd,
            transcript_path=transcript_path,
            metadata=metadata,
        )
        input_hash = hash_text(_serialize_input(context))
        if not context.text:
            return self._save_result(
                session,
                input_hash=input_hash,
                retrieved_chunk_ids=[],
                evidence_source_ids=[],
                relevance_score=None,
                angel_triggered=False,
                drop_reason=RECALL_DROP_REASON_NO_CONTEXT,
                angel_message=None,
            )

        retrieved_evidence = self._retrieve_evidence(session, context)
        retrieved_chunk_ids = [item.chunk_id for item in retrieved_evidence]
        if not retrieved_evidence:
            return self._save_result(
                session,
                input_hash=input_hash,
                retrieved_chunk_ids=[],
                evidence_source_ids=[],
                relevance_score=None,
                angel_triggered=False,
                drop_reason=RECALL_DROP_REASON_NO_RESULTS,
                angel_message=None,
            )

        tool_schema = self._build_tool_schema()
        response = self.llm_client.complete(
            prompt=self._build_llm_prompt(context=context, evidence=retrieved_evidence),
            evidence=retrieved_evidence,
            tool_schema=tool_schema,
        )
        tool_output = _extract_tool_output(response)
        if tool_output is None:
            return self._save_result(
                session,
                input_hash=input_hash,
                retrieved_chunk_ids=retrieved_chunk_ids,
                evidence_source_ids=self._evidence_source_ids(retrieved_evidence),
                relevance_score=None,
                angel_triggered=False,
                drop_reason=RECALL_DROP_REASON_INVALID_TOOL_USE,
                angel_message=None,
            )

        chunk_ids = _unique_preserve_order(tool_output.chunk_ids)
        evidence_source_ids = _unique_preserve_order(tool_output.evidence_sources)
        if not chunk_ids:
            return self._save_result(
                session,
                input_hash=input_hash,
                retrieved_chunk_ids=retrieved_chunk_ids,
                evidence_source_ids=(
                    evidence_source_ids or self._evidence_source_ids(retrieved_evidence)
                ),
                relevance_score=tool_output.relevance_score,
                angel_triggered=False,
                drop_reason=RECALL_DROP_REASON_EMPTY_CHUNK_IDS,
                angel_message=None,
            )

        relevance_score = min(1.0, max(0.0, tool_output.relevance_score))
        if relevance_score < self.relevance_threshold:
            return self._save_result(
                session,
                input_hash=input_hash,
                retrieved_chunk_ids=retrieved_chunk_ids,
                evidence_source_ids=(
                    evidence_source_ids or self._evidence_source_ids(retrieved_evidence)
                ),
                relevance_score=relevance_score,
                angel_triggered=False,
                drop_reason=RECALL_DROP_REASON_LOW_SCORE,
                angel_message=None,
            )

        final_message = _truncate_message(tool_output.angel_message)
        if not final_message:
            return self._save_result(
                session,
                input_hash=input_hash,
                retrieved_chunk_ids=retrieved_chunk_ids,
                evidence_source_ids=(
                    evidence_source_ids or self._evidence_source_ids(retrieved_evidence)
                ),
                relevance_score=relevance_score,
                angel_triggered=False,
                drop_reason=RECALL_DROP_REASON_INVALID_TOOL_USE,
                angel_message=None,
            )

        return self._save_result(
            session,
            input_hash=input_hash,
            retrieved_chunk_ids=retrieved_chunk_ids,
            evidence_source_ids=(
                evidence_source_ids or self._evidence_source_ids(retrieved_evidence)
            ),
            relevance_score=relevance_score,
            angel_triggered=True,
            drop_reason=None,
            angel_message=final_message,
        )

    def _retrieve_evidence(
        self,
        session: Session,
        context: RecallContext,
    ) -> list[RecallEvidence]:
        # 벡터 검색으로 직접 매칭을 찾고, 그래프 이웃으로 컨텍스트를
        # MAX_EVIDENCE_ITEMS까지 확장한다.
        embedding = self.graph_service.embedder.embed(context.text)
        candidates = self.graph_service.vector_store.query_similar(embedding, limit=self.top_k)

        evidence_by_id: dict[str, RecallEvidence] = {}
        ordered_ids: list[str] = []
        for candidate in candidates:
            if candidate.chunk_id in evidence_by_id:
                continue
            chunk = session.get(Chunk, candidate.chunk_id)
            if chunk is None:
                continue
            evidence = self._chunk_to_evidence(
                chunk=chunk,
                similarity=candidate.similarity,
                relation="retrieved",
            )
            evidence_by_id[chunk.id] = evidence
            ordered_ids.append(chunk.id)

        for chunk_id in list(ordered_ids):
            if len(evidence_by_id) >= RECALL_MAX_EVIDENCE_ITEMS:
                break
            if not self.graph_service.graph.has_node(chunk_id):
                continue
            for neighbor_id in self.graph_service.graph.neighbors(chunk_id):
                if len(evidence_by_id) >= RECALL_MAX_EVIDENCE_ITEMS:
                    break
                if neighbor_id in evidence_by_id:
                    continue
                neighbor_chunk = session.get(Chunk, neighbor_id)
                if neighbor_chunk is None:
                    continue
                edge_data = self.graph_service.graph.get_edge_data(chunk_id, neighbor_id) or {}
                similarity = float(edge_data.get("similarity", 0.0))
                evidence_by_id[neighbor_id] = self._chunk_to_evidence(
                    chunk=neighbor_chunk,
                    similarity=similarity,
                    relation="neighbor",
                    neighbor_of=chunk_id,
                )
                ordered_ids.append(neighbor_id)

        return [evidence_by_id[chunk_id] for chunk_id in ordered_ids if chunk_id in evidence_by_id]

    def _chunk_to_evidence(
        self,
        chunk: Chunk,
        similarity: float,
        relation: str,
        neighbor_of: str | None = None,
    ) -> RecallEvidence:
        source = chunk.source
        return RecallEvidence(
            chunk_id=chunk.id,
            source_id=source.id,
            source_type=source.source_type,
            title=source.title,
            path=source.path,
            chunk_index=chunk.chunk_index,
            text=chunk.text,
            similarity=similarity,
            relation=relation,
            neighbor_of=neighbor_of,
        )

    def _build_llm_prompt(self, *, context: RecallContext, evidence: list[RecallEvidence]) -> str:
        lines = [
            "You are Recall Agent.",
            "Use the evidence below to decide whether Angel should trigger.",
            "You must return the angel_output tool only.",
            "",
            "Current context:",
            context.text,
            "",
            "Evidence:",
        ]
        for index, item in enumerate(evidence, start=1):
            lines.extend(
                [
                    (
                        f"{index}. relation={item.relation} "
                        f"chunk_id={item.chunk_id} source_id={item.source_id}"
                    ),
                    (
                        "   source_type="
                        f"{item.source_type} title={item.title or ''} path={item.path or ''}"
                    ),
                    f"   chunk_index={item.chunk_index} similarity={item.similarity:.3f}",
                    f"   text={_compact_text(item.text, limit=240)}",
                ]
            )
            if item.neighbor_of is not None:
                lines.append(f"   neighbor_of={item.neighbor_of}")
        lines.extend(
            [
                "",
                "Return JSON for angel_output with:",
                "- chunk_ids: selected chunk ids",
                "- evidence_sources: source ids used",
                "- relevance_score: 0.0 to 1.0",
                f"- angel_message: max {RECALL_ANGEL_MESSAGE_MAX_LENGTH} chars",
            ]
        )
        return "\n".join(lines)

    def _build_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "angel_output",
                "description": "Return Angel recall output.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "chunk_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Selected chunk ids.",
                        },
                        "evidence_sources": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Source ids backing the answer.",
                        },
                        "relevance_score": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 1,
                        },
                        "angel_message": {
                            "type": "string",
                            "maxLength": RECALL_ANGEL_MESSAGE_MAX_LENGTH,
                        },
                    },
                    "required": [
                        "chunk_ids",
                        "evidence_sources",
                        "relevance_score",
                        "angel_message",
                    ],
                    "additionalProperties": False,
                },
            },
        }

    def _evidence_source_ids(self, evidence: list[RecallEvidence]) -> list[str]:
        return _unique_preserve_order(item.source_id for item in evidence)

    def _save_result(
        self,
        session: Session,
        *,
        input_hash: str,
        retrieved_chunk_ids: list[str],
        evidence_source_ids: list[str],
        relevance_score: float | None,
        angel_triggered: bool,
        drop_reason: str | None,
        angel_message: str | None,
    ) -> RecallResult:
        stored_message = angel_message if (angel_triggered and self.persist_angel_message) else None
        log = RecallLog(
            input_hash=input_hash,
            retrieved_chunk_ids=retrieved_chunk_ids,
            evidence_source_ids=evidence_source_ids,
            relevance_score=relevance_score,
            angel_triggered=angel_triggered,
            drop_reason=drop_reason,
            angel_message=stored_message,
        )
        session.add(log)
        session.commit()
        return RecallResult(
            status="accepted" if angel_triggered else "dropped",
            input_hash=input_hash,
            retrieved_chunk_ids=retrieved_chunk_ids,
            evidence_source_ids=evidence_source_ids,
            relevance_score=relevance_score,
            angel_triggered=angel_triggered,
            drop_reason=drop_reason,
            angel_message=stored_message,
        )
