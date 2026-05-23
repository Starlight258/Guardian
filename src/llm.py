# LLM 클라이언트: Anthropic, Ollama(로컬), 서킷 브레이커 래퍼.
from __future__ import annotations

import json
import logging
import os
import time
from threading import Lock
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.service.recall import RecallEvidence

logger = logging.getLogger(__name__)

CIRCUIT_FAILURE_THRESHOLD = 3
CIRCUIT_RECOVERY_TIMEOUT = 60.0
DEFAULT_ANTHROPIC_MODEL = "claude-opus-4-7"
DEFAULT_LOCAL_MODEL = "qwen2.5:3b"
DEFAULT_ANTHROPIC_TIMEOUT = 10.0
DEFAULT_LOCAL_TIMEOUT = 30.0
OLLAMA_BASE_URL = "http://localhost:11434/v1"


class CircuitBreaker:
    # CLOSED → OPEN(3회 연속 실패) → HALF_OPEN(60초 후) → CLOSED(프로브 성공)

    def __init__(
        self,
        *,
        failure_threshold: int = CIRCUIT_FAILURE_THRESHOLD,
        recovery_timeout: float = CIRCUIT_RECOVERY_TIMEOUT,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._failures = 0
        self._state = "CLOSED"
        self._opened_at: float | None = None
        self._lock = Lock()

    @property
    def state(self) -> str:
        with self._lock:
            if self._state == "OPEN" and self._opened_at is not None:
                if time.monotonic() - self._opened_at >= self._recovery_timeout:
                    self._state = "HALF_OPEN"
                    logger.info("Circuit breaker → HALF_OPEN")
            return self._state

    def record_success(self) -> None:
        with self._lock:
            if self._state != "CLOSED":
                logger.info("Circuit breaker → CLOSED")
            self._failures = 0
            self._state = "CLOSED"
            self._opened_at = None

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self._failure_threshold or self._state == "HALF_OPEN":
                if self._state != "OPEN":
                    logger.warning(
                        "Circuit breaker → OPEN after %d failures", self._failures
                    )
                self._state = "OPEN"
                self._opened_at = time.monotonic()


class AnthropicLLMClient:
    def __init__(
        self,
        *,
        model: str = DEFAULT_ANTHROPIC_MODEL,
        max_tokens: int = 4096,
        timeout: float = DEFAULT_ANTHROPIC_TIMEOUT,
    ) -> None:
        import anthropic

        self._client = anthropic.Anthropic()
        self._model = model
        self._max_tokens = max_tokens
        self._timeout = timeout

    def complete(
        self,
        *,
        prompt: str,
        evidence: list[RecallEvidence],
        tool_schema: dict[str, Any],
    ) -> Any:
        del evidence
        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            tools=[_to_anthropic_tool(tool_schema)],
            tool_choice={"type": "tool", "name": "angel_output"},
            messages=[{"role": "user", "content": prompt}],
            timeout=self._timeout,
        )
        return response


class LocalLLMClient:
    def __init__(
        self,
        *,
        model: str | None = None,
        base_url: str = OLLAMA_BASE_URL,
        timeout: float = DEFAULT_LOCAL_TIMEOUT,
    ) -> None:
        self._model = model or os.getenv("GUARDIAN_LOCAL_MODEL", DEFAULT_LOCAL_MODEL)
        self._base_url = base_url
        self._timeout = timeout

    def complete(
        self,
        *,
        prompt: str,
        evidence: list[RecallEvidence],
        tool_schema: dict[str, Any],
    ) -> dict[str, Any] | None:
        del evidence
        try:
            import openai

            client = openai.OpenAI(
                base_url=self._base_url,
                api_key="ollama",
                timeout=self._timeout,
            )
            response = client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                tools=[tool_schema],
                tool_choice={"type": "function", "function": {"name": "angel_output"}},
            )
            message = response.choices[0].message
            tool_calls = message.tool_calls
            if not tool_calls:
                return None
            tool_call = tool_calls[0]
            if tool_call.function.name != "angel_output":
                return None
            input_data = json.loads(tool_call.function.arguments)
            return {
                "content": [
                    {"type": "tool_use", "name": "angel_output", "input": input_data}
                ]
            }
        except (json.JSONDecodeError, KeyError, AttributeError, TypeError, ValueError) as exc:
            logger.warning("LocalLLMClient tool_use parse failed: %s", exc)
            return None
        except Exception as exc:
            logger.warning("LocalLLMClient request failed: %s", exc)
            return None


class ResilientLLMClient:
    # Anthropic + 서킷 브레이커. OPEN 상태면 LocalLLMClient로 전환한다.

    def __init__(
        self,
        *,
        primary: AnthropicLLMClient,
        fallback: LocalLLMClient,
        breaker: CircuitBreaker,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._breaker = breaker

    def complete(
        self,
        *,
        prompt: str,
        evidence: list[RecallEvidence],
        tool_schema: dict[str, Any],
    ) -> Any:
        if self._breaker.state == "OPEN":
            logger.info("Circuit breaker OPEN — routing to local LLM")
            return self._fallback.complete(
                prompt=prompt, evidence=evidence, tool_schema=tool_schema
            )

        try:
            result = self._primary.complete(
                prompt=prompt, evidence=evidence, tool_schema=tool_schema
            )
            self._breaker.record_success()
            return result
        except Exception as exc:
            if _is_retryable(exc):
                logger.warning("Anthropic API failure: %s", exc)
                self._breaker.record_failure()
                return self._fallback.complete(
                    prompt=prompt, evidence=evidence, tool_schema=tool_schema
                )
            raise


def _is_retryable(exc: Exception) -> bool:
    # 5xx, 연결 오류, 타임아웃만 폴백 트리거. 4xx(인증, 할당량 초과)는 그대로 raise한다.
    try:
        import anthropic

        if isinstance(exc, anthropic.APIStatusError):
            return exc.status_code >= 500
        if isinstance(exc, (anthropic.APIConnectionError, anthropic.APITimeoutError)):
            return True
    except ImportError:
        pass
    return False


def _to_anthropic_tool(schema: dict[str, Any]) -> dict[str, Any]:
    # OpenAI 함수 스키마를 Anthropic tool 형식으로 변환한다.
    if "function" in schema:
        fn = schema["function"]
        return {
            "name": fn["name"],
            "description": fn.get("description", ""),
            "input_schema": fn.get("parameters", {}),
        }
    return schema


def make_llm_client() -> Any:
    # GUARDIAN_LLM_PROVIDER=local이면 LocalLLMClient, 기본은 ResilientLLMClient를 반환한다.
    provider = os.getenv("GUARDIAN_LLM_PROVIDER", "anthropic")
    if provider == "local":
        return LocalLLMClient()
    return ResilientLLMClient(
        primary=AnthropicLLMClient(),
        fallback=LocalLLMClient(),
        breaker=CircuitBreaker(),
    )
