# Guardian

<p align="center">
  <img src="./assets/guardian-cli-angel-terminal-animated.png" width="920" alt="Guardian CLI Angel" />
</p>

<p align="center">
  <b>Capture → Connect → Recall</b>
</p>

<p align="center">
AI와 함께 만든 생각의 흔적을 자동으로 모으고, 연결하고, 다시 꺼내주는 개인 지식 그래프예요.
</p>

---

## What is Guardian?

AI와 작업하다 보면 비슷한 질문을 반복하게 돼요. 예전에 정리했던 노트나 프롬프트가 있어도, 코딩 중에는 다시 찾지 않게 돼요.

Guardian은 Obsidian 노트와 Claude Code 프롬프트를 자동으로 수집하고, 의미 기반으로 연결해서 하나의 그래프로 정리해줘요. 현재 작업과 비슷한 과거 맥락이 감지되면 Angel이 짧은 메시지를 띄워요.

MVP는 개인 AI 학습 흐름의 기억 보조 레이어에 집중해요.

---

## Memory Graph

<p align="center">
  <img src="./assets/guardian-dashboard.png" width="920" alt="Guardian Dashboard" />
</p>

---

## Architecture

```mermaid
flowchart LR
  A[Obsidian Notes] --> C[Capture Layer]
  B[Claude Code Prompts] --> C
  C --> D[Semantic Processing]
  D --> E[Knowledge Graph\nGraphRAG]
  E --> F[Retrieval Agent\nquery expansion → graph traversal]
  F --> G[Response Agent\nmessage generation]
  G --> H{Guardrails\nconfidence threshold}
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
| Agent Layer | Multi-agent — Retrieval Agent + Response Agent |
| Guardrails | Confidence scoring — threshold-based Angel trigger |
| Frontend | React + Vite + d3.js |
| Claude integration | MCP Server + Hooks |
| Evaluation | RAGAS |

---

## Angel Flow

**Retrieval Agent** : 현재 작업 컨텍스트를 받아서 LLM이 검색 쿼리를 재작성(query expansion)하고, Chroma 벡터 검색과 NetworkX 그래프 순회를 조합해 관련 청크를 선별해요.

**Response Agent** : 선별된 청크를 받아서 LLM이 Angel 메시지를 생성하고, 근거가 되는 노트를 함께 첨부해요.

**Guardrails** : Response Agent 출력의 관련성 점수가 threshold 아래면 Angel을 silent drop해요. False positive를 막아서 Angel이 의미 있을 때만 떠요.

---

## Data Sources

| Source | Capture Method |
|---|---|
| Obsidian notes | `watchdog` filesystem watcher |
| Claude Code prompts | `UserPromptSubmit` hook |

---

## Roadmap

| Week | Milestone |
|---|---|
| 1-2 | Capture infrastructure |
| 3-4 | Knowledge graph dashboard |
| 5 | Retrieval Agent + Guardrails |
| 6 | Response Agent + MCP integration |

---

## Status

```text
Status: Designing
Implementation starts: June 2026
```

---

## License

MIT
