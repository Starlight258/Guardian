# Guardian

<p align="center">
  <img src="https://github.com/user-attachments/assets/d50eb81b-d468-41e6-b310-622dc15dabd4" width="920" alt="Guardian Angel — Claude Code status line" />
</p>

<p align="center">
  <b>Capture → Connect → Recall</b>
</p>

<p align="center">
AI와 함께 만든 생각의 흔적을 자동으로 모으고, 연결하고, 다시 꺼내주는 개인 지식 그래프예요.
</p>

---

## What is Guardian?

AI와 작업하다 보면 비슷한 질문을 반복하게 돼요. 예전에 정리했던 노트나 커밋 맥락이 있어도, 코딩 중에는 다시 찾지 않게 돼요.

Guardian은 Obsidian 노트와 session checkpoint를 자동으로 수집하고, 의미 기반으로 연결해서 하나의 그래프로 정리해줘요. Claude Code와 Codex의 prompt event가 들어오면 현재 작업과 비슷한 과거 맥락을 찾아 Angel이 짧은 메시지를 띄워요.

현재는 Capture, Connect, Recall의 핵심 경로가 동작해요.

- Obsidian 노트와 session checkpoint를 자동 수집해요.
- Chroma + NetworkX로 관련 맥락을 검색하고 연결해요.
- `POST /recall`로 Recall Agent를 호출하고, `recall_logs`에 결과를 저장해요.
- `guardian-mcp` FastMCP 서버로 Claude Code와 Codex 쪽 recall tool을 노출해요.

---

## Memory Graph

<p align="center">
  <img src="./assets/guardian-dashboard.png" width="920" alt="Guardian Dashboard" />
</p>

---

## Getting Started

### 1. API + Frontend

```bash
docker compose up --build
```

첫 실행 시 `BAAI/bge-m3` 모델을 다운받아요. 이후에는 `huggingface_cache` volume에서 재사용해요.

- API: http://127.0.0.1:8000
- Dashboard: http://127.0.0.1:5173

### 2. MCP Server

`.mcp.json`에 등록돼 있어요. Claude Code나 Codex에서 이 프로젝트를 열면 자동으로 실행돼요.

### 3. Ollama (선택사항)

API 장애 시 Circuit Breaker가 자동으로 Ollama로 전환해요. 평소엔 없어도 돼요.

macOS에서는 Docker 대신 로컬 설치를 권장해요. Docker는 Apple Silicon GPU(Metal)를 사용할 수 없어서 속도 차이가 커요.

```bash
brew install ollama
ollama pull qwen2.5:3b
ollama serve
```

### 4. Hooks

#### Claude Code

`~/.claude/settings.json` (전역 설정)에 추가해요.

| Event | What it does |
|---|---|
| `SessionEnd` | 트랜스크립트를 파싱해 요약 후 Guardian에 저장해요. |
| `UserPromptSubmit` | 프롬프트 입력마다 Recall Agent를 트리거해요. |

```json
{
  "hooks": {
    "SessionEnd": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /path/to/hooks/claude_session_summary.py | /path/to/hooks/post_session_to_guardian.sh || true"
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "cat | /path/to/hooks/recall_trigger.sh || true"
          }
        ]
      }
    ]
  }
}
```

- `|| true`: hook 실패 시 Claude Code 흐름을 막지 않아요.
- `claude_session_summary.py`: 트랜스크립트 JSONL에서 Questions / Requests / Actions 섹션을 추출해요.

#### Codex

`~/.codex/config.toml`에 추가해요. Codex는 `SessionEnd`가 없어서 Stop → SessionStart 2단계 파이프라인을 사용해요.

| Event | What it does |
|---|---|
| `Stop` | 각 응답 완료 시 프롬프트를 임시 파일에 수집해요. |
| `SessionStart` | 이전 세션의 수집 파일을 Guardian에 전송해요. |
| `UserPromptSubmit` | 프롬프트 입력마다 Recall Agent를 트리거해요. |

```toml
[[hooks.Stop]]
command = "python3 /path/to/hooks/codex_session_collect.py | /path/to/hooks/post_session_to_guardian.sh || true"

[[hooks.SessionStart]]
command = "python3 /path/to/hooks/codex_session_flush.py || true"

[[hooks.UserPromptSubmit]]
command = "cat | /path/to/hooks/recall_trigger.sh || true"
```


---

## Architecture

```mermaid
flowchart LR
  A[Obsidian Notes] --> C[Capture Layer]
  B[Session Checkpoints] --> C
  C --> D[Semantic Processing]
  D --> E[Knowledge Graph\nGraphRAG]
  P[Claude Code / Codex Prompt Event] --> F[Recall Agent\nretrieval + response]
  E --> F
  F --> H{Guardrails\nconfidence threshold}
  H -->|pass| I[Angel + Dashboard]
  H -->|block| J[silent drop]
```

---

## Tech Stack

| Layer | Choice |
|---|---|
| Language | Python 3.11+ |
| Backend | FastAPI |
| Metadata | SQLite |
| Vector DB | Chroma |
| Graph | NetworkX |
| GraphRAG | Chroma + NetworkX (semantic + structural traversal) |
| Agent Layer | Retrieval before LLM + single LLM response call |
| LLM Resilience | Circuit Breaker (Anthropic API 장애 시 Ollama qwen2.5:3b 자동 전환) |
| Guardrails | Confidence scoring (threshold-based Angel trigger) |
| Frontend | React + Vite + d3.js |
| Claude Code / Codex integration | FastMCP + Hooks |
| Evaluation | RAGAS |

---

## How It Works

단일 에이전트 파이프라인이에요.

**Recall Agent**: 컨텍스트로 Chroma 벡터 검색과 NetworkX 그래프 순회로 연관된 청크를 선별하고, 단일 LLM call로 Angel 메시지와 관련성 점수를 생성해요. 근거가 된 노트나 checkpoint가 첨부돼요.

**Guardrails**: 관련성 점수가 threshold 아래면 Angel을 silent drop해요.

> LLM 기반 query rewrite와 multi-agent 구조는 채택하지 않았어요.
Angel은 백그라운드 트리거라 지연이 길어지면 안 되기 때문이에요.
RAGAS context precision이 0.6 아래로 떨어지거나 false positive rate가 30%를 넘으면 분리해요.

---

## Data Sources

| Source | Capture Method |
|---|---|
| Obsidian notes | `watchdog` filesystem watcher |
| Session checkpoints | session-end hook → rule-based summary |
| Claude Code / Codex prompt events | `UserPromptSubmit` hook → realtime recall trigger |

---

## Evaluation

```bash
bash eval/run.sh                      # 큐레이션 케이스로 평가 (ragas 포함)
bash eval/run.sh --generate           # 케이스 자동 생성 후 평가
bash eval/run.sh --skip-ragas         # ragas 생략 (빠른 평가)
bash eval/run.sh --generate --skip-ragas
```

**케이스 종류**

| 방식 | 파일 | 설명 |
|---|---|---|
| 자동 생성 | `eval/generated_cases.jsonl` | `--generate` 실행 시 Obsidian 노트에서 Claude Haiku가 생성 |
| 수동 큐레이션 | `eval/cases.jsonl` | 직접 작성한 고정 케이스 |

수동 케이스를 추가하려면 `eval/cases.jsonl`에 한 줄씩 추가해요.

```json
{"query": "질문 내용", "should_trigger": true, "expected_source": "노트파일.md"}
{"query": "관련 없는 질문", "should_trigger": false, "expected_source": null}
```

**Metrics**

| Metric | 기준 | 설명 | 엔진 |
|---|---|---|---|
| `context_precision` | ≥ 0.6 | expected_source가 실제 검색 결과에 포함된 비율 | 직접 구현 |
| `false_positive_rate` | ≤ 0.30 | 트리거되면 안 되는 쿼리에서 Angel이 발동된 비율 | 직접 구현 |
| `answer_relevancy` | ≥ 0.7 | angel_message가 쿼리에 실제로 답하는지 | ragas |
| `faithfulness` | ≥ 0.7 | angel_message가 검색 문서 내용에 충실한지 | ragas |

`answer_relevancy`와 `faithfulness`는 Claude Haiku로 채점하므로 실행마다 소량의 API 비용이 발생해요. 결과는 `eval/results/YYYY-MM-DD_HHMMSS.json`에 저장돼요. 기준을 벗어나면 exit 1을 반환해요.

---

## Roadmap

| Status | Milestone |
|---|---|
| Done | Capture infrastructure |
| Done | Knowledge graph dashboard |
| Done | Recall Agent + Guardrails |
| Done | FastMCP recall tool |
| Done | LLM resilience layer (Circuit Breaker → Ollama → Heuristic fallback) |
| Done | Angel status line (Claude Code statusLine integration) |
| Done | RAGAS evaluation loop |

---

## Wiki

[Wiki](https://github.com/Starlight258/Guardian/wiki)

---

## Status

```text
Status: Core capture, recall, dashboard, and MCP recall tool implemented
```

---

## License

MIT
