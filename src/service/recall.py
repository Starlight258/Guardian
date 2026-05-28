# Recall Agent: GraphRAG로 유사 청크를 검색하고 LLM을 호출해 Angel 메시지를 생성한다.
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy.orm import Session

from src.models import Chunk, RecallLog
from src.service.graph import GraphService
from src.utils import hash_text

_ANGEL_STATE_PATH = Path.home() / ".guardian" / "angel-state.json"


class Mood(StrEnum):
    FOCUSED = "focused"
    HAPPY = "happy"
    EXCITED = "excited"
    TIRED = "tired"
    THINKING = "thinking"


def _write_angel_state(
    message: str,
    *,
    evidence: list[RecallEvidence] | None = None,
    recall_count: int = 0,
) -> None:
    """Write Angel's recall result to the status line state file. Silently no-ops on failure."""
    try:
        _ANGEL_STATE_PATH.parent.mkdir(exist_ok=True)
        existing: dict = {}
        if _ANGEL_STATE_PATH.exists():
            try:
                existing = json.loads(_ANGEL_STATE_PATH.read_text())
            except Exception:
                pass

        source_title = None
        source_file = None
        source_path = None
        if evidence:
            first = evidence[0]
            source_title = first.title
            source_file = Path(first.path).name if first.path else None
            source_path = first.path if first.path else None

        now = int(time.time())
        try:
            current_mood = Mood(existing.get("mood", Mood.FOCUSED.value))
        except ValueError:
            current_mood = Mood.FOCUSED
        new_mood = Mood.EXCITED if current_mood is not Mood.TIRED else Mood.TIRED
        existing.update({
            "message": message,
            "message_ts": now,
            "mood": new_mood.value,
            "mood_ts": now,
            "source_title": source_title,
            "source_file": source_file,
            "source_path": source_path,
            "recall_count": (existing.get("recall_count") or 0) + 1,
            "last_recall_ts": now,
        })
        _ANGEL_STATE_PATH.write_text(json.dumps(existing, ensure_ascii=False))
    except Exception:
        pass


RECALL_TOP_K = 5
RECALL_RELEVANCE_THRESHOLD = 0.5
QUERY_REWRITE_THRESHOLD = 80  # chars — longer queries get LLM rewrite
RECALL_ANGEL_MESSAGE_MAX_LENGTH = 120
RECALL_MAX_EVIDENCE_ITEMS = 10
RECALL_DROP_REASON_NO_CONTEXT = "missing_context"
RECALL_DROP_REASON_NO_RESULTS = "no_retrieval_results"
RECALL_DROP_REASON_INVALID_TOOL_USE = "invalid_tool_use"
RECALL_DROP_REASON_LOW_SCORE = "below_threshold"
RECALL_DROP_REASON_EMPTY_CHUNK_IDS = "empty_chunk_ids"


def _clean_query(text: str) -> str:
    """Deterministic noise reduction: strip repeated chars, normalize whitespace, truncate."""
    import re
    text = re.sub(r'(.)\1{3,}', r'\1', text)   # xxxxxxxx → x
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:150]


def _rewrite_query(text: str) -> str:
    """LLM rewrite to extract core technical intent. Falls back to input on any error."""
    import os
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=80,
            messages=[{
                "role": "user",
                "content": (
                    "다음 텍스트에서 기술적 핵심 의도만 한 문장으로 추출해줘. "
                    "감탄사, 반복 문자, 일상 표현은 제거하고 한국어로.\n\n"
                    f"{text}"
                ),
            }],
        )
        rewritten = response.content[0].text.strip()
        return rewritten if rewritten else text
    except Exception:
        return text


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
    del prompt
    if not evidence:
        return "관련 컨텍스트를 찾았어요"

    best = evidence[0]
    score = best.similarity

    if score >= 0.88:
        intro = "딱 맞아요!"
    elif score >= 0.78:
        intro = "이거요:"
    else:
        intro = "참고:"

    raw_title = best.title or (Path(best.path).stem if best.path else best.chunk_id)
    title = _compact_text(raw_title, limit=18)

    snippet = ""
    if best.text:
        clean = best.text.lstrip("#> -\n").strip().split("\n")[0]
        snippet = _compact_text(clean, limit=80)

    second = ""
    if len(evidence) >= 2:
        raw2 = evidence[1].title or (Path(evidence[1].path).stem if evidence[1].path else "")
        second = _compact_text(raw2, limit=14)

    if snippet:
        return f"{intro} {snippet}"
    if second:
        return f"{intro} {title} (+{second})"
    return f"{intro} {title}"


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
        llm_prompt = self._build_llm_prompt(context=context, evidence=retrieved_evidence)
        response = self.llm_client.complete(
            prompt=llm_prompt,
            evidence=retrieved_evidence,
            tool_schema=tool_schema,
        )
        if response is None:
            response = HeuristicRecallLLMClient().complete(
                prompt=llm_prompt,
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

        if self.persist_angel_message:
            _write_angel_state(
                final_message,
                evidence=retrieved_evidence,
                recall_count=len(chunk_ids),
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
        search_text = _clean_query(context.text)
        if len(search_text) > QUERY_REWRITE_THRESHOLD:
            search_text = _rewrite_query(search_text)
        embedding = self.graph_service.embedder.embed(search_text)
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
                "- relevance_score: 0.0–1.0. Be strict:"
                " 0.8+ only when the evidence directly and specifically answers the query."
                " 0.5–0.7 for partial relevance."
                " Below 0.5 when the connection is tangential, coincidental, or"
                " topic-adjacent only."
                " When in doubt, score lower — a missed trigger is better than a false one.",
                f"- angel_message: max {RECALL_ANGEL_MESSAGE_MAX_LENGTH} chars."
                " Pull ONE specific fact, comparison, or decision point directly"
                " from the note text that the user might actually need right now."
                " Be concrete — quote numbers, names, or conclusions if present."
                " Do NOT describe what the note is about."
                " Do NOT start with 'Found', 'The note', or 'Based on'."
                " Do NOT repeat the user's input.",
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
        stored_message = angel_message if angel_triggered else None
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
