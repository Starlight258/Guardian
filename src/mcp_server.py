from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from src.db import SessionLocal
from src.service.graph import GraphService
from src.service.recall import RecallAgent, RecallResult

load_dotenv()

mcp = FastMCP(
    "guardian-mcp",
    instructions="Expose a single recall tool that returns Angel context and evidence references.",
)


@dataclass(frozen=True)
class MCPRuntime:
    graph_service: GraphService
    recall_agent: RecallAgent


def _extract_tool_context(arguments: dict[str, Any]) -> str:
    for key in ("context", "prompt", "user_prompt", "message", "text"):
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise ValueError("recall tool requires context text")


def _result_to_payload(result: RecallResult) -> dict[str, Any]:
    return {
        "angel_message": result.angel_message,
        "evidence_source_ids": result.evidence_source_ids,
        "retrieved_chunk_ids": result.retrieved_chunk_ids,
        "relevance_score": result.relevance_score,
        "angel_triggered": result.angel_triggered,
        "drop_reason": result.drop_reason,
        "input_hash": result.input_hash,
    }


@lru_cache(maxsize=1)
def _get_runtime() -> MCPRuntime:
    graph_service = GraphService()
    with SessionLocal() as session:
        graph_service.reconstruct(session)
    return MCPRuntime(
        graph_service=graph_service,
        recall_agent=RecallAgent(graph_service=graph_service),
    )


@mcp.tool()
def recall(
    context: str | None = None,
    prompt: str | None = None,
    user_prompt: str | None = None,
    message: str | None = None,
    text: str | None = None,
    session_id: str | None = None,
    cwd: str | None = None,
    transcript_path: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return Angel recall output and evidence references."""
    arguments = {
        "context": context,
        "prompt": prompt,
        "user_prompt": user_prompt,
        "message": message,
        "text": text,
    }
    resolved_context = _extract_tool_context(arguments)
    runtime = _get_runtime()

    with SessionLocal() as session:
        result = runtime.recall_agent.recall(
            session,
            prompt=resolved_context,
            session_id=session_id,
            cwd=cwd,
            transcript_path=transcript_path,
            metadata=metadata,
        )

    return _result_to_payload(result)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
