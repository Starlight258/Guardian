from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.llm import (
    CircuitBreaker,
    LocalLLMClient,
    ResilientLLMClient,
    _to_anthropic_tool,
)

DUMMY_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "angel_output",
        "description": "Return Angel recall output.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}

ANGEL_PAYLOAD: dict[str, Any] = {
    "content": [
        {
            "type": "tool_use",
            "name": "angel_output",
            "input": {
                "chunk_ids": ["c1"],
                "evidence_sources": ["s1"],
                "relevance_score": 0.9,
                "angel_message": "test",
            },
        }
    ]
}


class _OKClient:
    def complete(self, *, prompt: str, evidence: list, tool_schema: dict) -> dict:
        return ANGEL_PAYLOAD


class _FailClient:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def complete(self, *, prompt: str, evidence: list, tool_schema: dict) -> None:
        raise self._exc


# ── CircuitBreaker ────────────────────────────────────────────────────────────


def test_circuit_opens_after_threshold() -> None:
    breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
    assert breaker.state == "CLOSED"
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == "CLOSED"
    breaker.record_failure()
    assert breaker.state == "OPEN"


def test_circuit_transitions_to_half_open_after_timeout() -> None:
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=0)
    breaker.record_failure()
    assert breaker.state == "HALF_OPEN"


def test_circuit_closes_on_success_from_half_open() -> None:
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=0)
    breaker.record_failure()
    _ = breaker.state  # trigger HALF_OPEN
    breaker.record_success()
    assert breaker.state == "CLOSED"
    assert breaker._failures == 0


def test_circuit_reopens_on_failure_from_half_open() -> None:
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=0)
    breaker.record_failure()
    _ = breaker.state  # trigger HALF_OPEN
    breaker.record_failure()
    assert breaker._state == "OPEN"  # check raw state before time-based transition


# ── ResilientLLMClient ────────────────────────────────────────────────────────


def test_resilient_uses_primary_when_closed() -> None:
    breaker = CircuitBreaker()
    client = ResilientLLMClient(
        primary=_OKClient(),
        fallback=_FailClient(RuntimeError("should not be called")),
        breaker=breaker,
    )
    result = client.complete(prompt="test", evidence=[], tool_schema=DUMMY_SCHEMA)
    assert result == ANGEL_PAYLOAD
    assert breaker.state == "CLOSED"


def test_resilient_routes_to_fallback_when_open() -> None:
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=60)
    breaker.record_failure()
    client = ResilientLLMClient(
        primary=_FailClient(RuntimeError("should not be called")),
        fallback=_OKClient(),
        breaker=breaker,
    )
    result = client.complete(prompt="test", evidence=[], tool_schema=DUMMY_SCHEMA)
    assert result == ANGEL_PAYLOAD


def test_resilient_opens_circuit_after_retryable_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.llm._is_retryable", lambda exc: True)
    breaker = CircuitBreaker(failure_threshold=3)
    client = ResilientLLMClient(
        primary=_FailClient(RuntimeError("5xx")),
        fallback=_OKClient(),
        breaker=breaker,
    )
    for _ in range(3):
        result = client.complete(prompt="test", evidence=[], tool_schema=DUMMY_SCHEMA)
        assert result == ANGEL_PAYLOAD  # fallback is used each time
    assert breaker.state == "OPEN"


def test_resilient_closes_after_probe_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.llm._is_retryable", lambda exc: True)
    breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=0)
    client = ResilientLLMClient(
        primary=_FailClient(RuntimeError("5xx")),
        fallback=_OKClient(),
        breaker=breaker,
    )
    for _ in range(3):
        client.complete(prompt="test", evidence=[], tool_schema=DUMMY_SCHEMA)
    assert breaker._state == "OPEN"  # raw state before time-based transition

    # recovery_timeout=0 → HALF_OPEN on next state read → probe succeeds → CLOSED
    client._primary = _OKClient()
    result = client.complete(prompt="test", evidence=[], tool_schema=DUMMY_SCHEMA)
    assert result == ANGEL_PAYLOAD
    assert breaker.state == "CLOSED"


def test_resilient_reraises_non_retryable_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.llm._is_retryable", lambda exc: False)
    breaker = CircuitBreaker()
    client = ResilientLLMClient(
        primary=_FailClient(ValueError("bad input")),
        fallback=_OKClient(),
        breaker=breaker,
    )
    with pytest.raises(ValueError, match="bad input"):
        client.complete(prompt="test", evidence=[], tool_schema=DUMMY_SCHEMA)
    assert breaker.state == "CLOSED"  # non-retryable errors don't open the circuit


# ── LocalLLMClient ────────────────────────────────────────────────────────────


def test_local_returns_none_on_json_error() -> None:
    mock_openai = MagicMock()
    tool_call = MagicMock()
    tool_call.function.name = "angel_output"
    tool_call.function.arguments = "not-valid-json{"
    mock_openai.OpenAI.return_value.chat.completions.create.return_value.choices[
        0
    ].message.tool_calls = [tool_call]

    with patch.dict("sys.modules", {"openai": mock_openai}):
        client = LocalLLMClient()
        result = client.complete(prompt="test", evidence=[], tool_schema=DUMMY_SCHEMA)

    assert result is None


def test_local_returns_none_on_empty_tool_calls() -> None:
    mock_openai = MagicMock()
    mock_openai.OpenAI.return_value.chat.completions.create.return_value.choices[
        0
    ].message.tool_calls = []

    with patch.dict("sys.modules", {"openai": mock_openai}):
        client = LocalLLMClient()
        result = client.complete(prompt="test", evidence=[], tool_schema=DUMMY_SCHEMA)

    assert result is None


def test_local_returns_none_on_request_failure() -> None:
    mock_openai = MagicMock()
    mock_openai.OpenAI.return_value.chat.completions.create.side_effect = Exception(
        "connection refused"
    )

    with patch.dict("sys.modules", {"openai": mock_openai}):
        client = LocalLLMClient()
        result = client.complete(prompt="test", evidence=[], tool_schema=DUMMY_SCHEMA)

    assert result is None


# ── AnthropicLLMClient ────────────────────────────────────────────────────────


def test_anthropic_client_uses_tool_use_forced() -> None:
    mock_anthropic = MagicMock()
    mock_response = MagicMock()
    mock_anthropic.Anthropic.return_value.messages.create.return_value = mock_response

    with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
        from src.llm import AnthropicLLMClient

        client = AnthropicLLMClient()
        result = client.complete(prompt="test prompt", evidence=[], tool_schema=DUMMY_SCHEMA)

    kwargs = mock_anthropic.Anthropic.return_value.messages.create.call_args.kwargs
    assert kwargs["tool_choice"] == {"type": "tool", "name": "angel_output"}
    assert kwargs["max_tokens"] >= 4096
    assert kwargs["messages"] == [{"role": "user", "content": "test prompt"}]
    assert result == mock_response


# ── _to_anthropic_tool ────────────────────────────────────────────────────────


def test_to_anthropic_tool_converts_function_schema() -> None:
    result = _to_anthropic_tool(DUMMY_SCHEMA)
    assert result["name"] == "angel_output"
    assert result["description"] == "Return Angel recall output."
    assert result["input_schema"] == {"type": "object", "properties": {}, "required": []}
    assert "function" not in result
    assert "type" not in result
