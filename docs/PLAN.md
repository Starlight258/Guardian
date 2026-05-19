# PLAN.md — Guardian

## What we're building

Obsidian 노트와 session checkpoint를 자동 수집해 의미 기반 지식 그래프로 연결하고,
Claude Code prompt event로 현재 작업과 관련된 과거 맥락을 조회해 Angel이 Claude Code status line에 짧은 메시지를 띄우는 개인 기억 보조 레이어.

### Capture
- Obsidian: `watchdog` filesystem watcher (create / update / delete / move), 서버 내부 background task
- Claude Code: `UserPromptSubmit` hook → HTTP POST `/events/prompt` → realtime Recall trigger
- Session checkpoint: session-end hook → HTTP POST `/events/session-checkpoint` → session summary 기반 rule-based summary를 장기 memory source로 저장
- 수동 sync 없음, 항상 자동 수집

### Connect
- Length Filter: 50 tokens 미만 early discard
- Chunking: 구조화 노트 → Header 기반 split / 비구조화 → Sliding window (512 tokens, 20% overlap)
- Embedding: `BAAI/bge-m3` 로컬 → Chroma 저장
- Graph: 신규 chunk마다 Chroma top-k 후보만 비교, cosine similarity ≥ 0.75 edge → NetworkX (서버 시작 시 SQLite에서 재구성)
- Storage: SQLite (metadata) + Chroma (vectors), `chunk.id` 공유

### Recall
- 현재 작업 컨텍스트 → Chroma top-k=5 retrieval → NetworkX 인접 노드 주입 → Single LLM call response
- LLM 기반 query rewrite 없음 (MVP에서는 현재 작업 컨텍스트를 검색 입력으로 사용)
- tool_use 강제 (`angel_output` tool), relevance_score < 0.7 → silent drop
- Angel: Claude Code status line 표시, 120자 제한 + 근거 노트 payload 첨부

### Frontend
- React + Vite + d3.js 지식 그래프 대시보드 (폴링, MVP에서 WebSocket 없음)

### Evaluation
- RAGAS (context precision < 0.6 or false positive > 30% → Recall 구조 분리 trigger)

---

## Key decisions

- Guardian 서버는 항상 실행 중 가정
- Obsidian watchdog → endpoint 없이 service 직접 호출
- Claude Code prompt hook → HTTP POST `/events/prompt` (별도 프로세스 IPC), 장기 chunk 저장 없이 realtime recall trigger로 사용
- Session checkpoint → session_id 기준 장기 memory source로 저장, prompt event와 dedupe
- Session checkpoint summary는 session 종료나 session clear 시점에 생성
- Entire checkpoint는 Codex commit에서 안정적인 기준으로 쓰지 않음. session-end hook은 항상 rule-based summary를 생성
- `chunk.id` SQLite ↔ Chroma 공유 — mapping layer 없음
- NetworkX 그래프 서버 시작 시 재구성 (인메모리)
- Graph traversal은 Python에서 인접 노드 추출 후 프롬프트 주입 (모델이 NetworkX 직접 호출 안 함)
- query rewrite 없음 — BGE-M3 dense retrieval이 semantic search 커버, 현재 작업 컨텍스트를 검색 입력으로 사용
- Recall Agent는 검색 이후 단일 LLM call만 수행 (검색 전 query rewrite call 없음)
- `recall_logs`: input_hash, retrieved_chunk_ids, evidence_source_ids, relevance_score, angel_triggered, drop_reason, angel_message(nullable) 저장
- `angel_message` 저장은 기본 활성화하되 config로 비활성화 가능
- `/recall` MCP tool + 대시보드 수동 검색 양쪽에서 호출
- 인증 없음 (단일 사용자, 로컬 전용)
- LLM 호출은 `LLMClient` Protocol로 추상화 — `AnthropicLLMClient` / `LocalLLMClient(Ollama)` 구현, `GUARDIAN_LLM_PROVIDER` 환경변수로 전환
- 로컬 LLM 권장 모델: `qwen2.5:7b` (`GUARDIAN_LOCAL_MODEL` 환경변수) — function calling 신뢰도 · 한국어 두 축 모두 커버
- Circuit Breaker 상태: CLOSED → OPEN(연속 3회 실패) → HALF_OPEN(60초 후) → CLOSED(probe 성공). Model Router 없음 — Recall Agent LLM call point가 하나라 Circuit Breaker로 충분
- `angel_output` tool_use 강제 이유: free-text JSON 파싱 불안정 제거, `response.content[0].input` dict 직접 수신
- LocalLLMClient tool_use 파싱 실패(JSONDecodeError / KeyError / ValidationError) → Angel silent skip (C fallback)

## Constraints

- Embedding 모델 고정: 변경 시 Chroma 전체 재임베딩 필요
- `chunk.id` coupling: SQLite · Chroma 동기화 — delete 이벤트 처리 필수
- Recall 프롬프트 길이: retrieval context 과다 시 800 token 초과 → chunk 수 제한 필요
- 파일 rename/move → `sources.path` 업데이트 (watchdog moved 이벤트)

---

## Feature backlog (ordered by risk)

### F1 — Project scaffold | P0
Files: `pyproject.toml`, `src/main.py`, `src/deps.py`, `src/db.py`, `alembic/`
Success gate: `uv run uvicorn src.main:app` 실행, `GET /health` 200 반환
Hard problem touch: no
`/iterate` command: `/iterate scaffold FastAPI project with SQLite via SQLAlchemy, Alembic migrations for sources/chunks/graph_edges/recall_logs tables, health endpoint`

### F2 — Claude Code prompt event trigger | P0
Files: `src/api/events.py`, `src/schemas/events.py`, `src/service/recall_trigger.py`, `hooks/guardian_hook.sh`
Success gate: `POST /events/prompt` → 현재 작업 컨텍스트로 Recall 호출, 짧은 프롬프트 length filter discard 확인, 장기 chunk 저장 없음
Hard problem touch: no
`/iterate` command: `/iterate implement POST /events/prompt endpoint for Claude Code UserPromptSubmit hook — length filter (50 tokens), call recall trigger with current prompt context, do not persist prompt as long-term chunks. Include guardian_hook.sh that curls this endpoint.`

### F3 — Capture: Obsidian watchdog | P0
Files: `src/service/watcher.py`, `src/service/note_save.py`, `src/crud/source.py`, `src/crud/chunk.py` (update/delete)
Success gate: 파일 create/update/delete/move 이벤트 → SQLite 반영, 300ms debounce 동작
Hard problem touch: no
`/iterate` command: `/iterate implement Obsidian watchdog as FastAPI lifespan background task using watchdog library — handle create/update/delete/move events with 300ms debounce, call ingest service directly (no HTTP)`

### F4 — Connect: Embedding + Graph | P1
Files: `src/service/embed.py`, `src/service/graph.py`, `src/crud/graph_edge.py`
Success gate: chunk 저장 시 Chroma 벡터 저장 확인, Chroma top-k 후보 중 similarity ≥ 0.75 edge SQLite 저장 확인, 서버 재시작 후 NetworkX 그래프 재구성 확인
Hard problem touch: no
`/iterate` command: `/iterate implement BGE-M3 embedding via sentence-transformers, store vectors in Chroma collection 'guardian_chunks', build NetworkX graph edges by comparing each new chunk only against Chroma top-k candidates and storing edges with cosine similarity ≥ 0.75 in graph_edges table, reconstruct graph on server startup`

### F5 — Capture: Session checkpoint memory | P1
Files: `src/service/checkpoint.py`, `src/crud/source.py`, `src/crud/chunk.py`, `hooks/session_checkpoint_guardian.sh`
Success gate: session_id + session summary 저장, 질문성 줄(`?`, `왜`, `고민`, `생각`) 분리, chunking/embedding/graph 연결, 같은 session_id 중복 저장 방지
Hard problem touch: no
`/iterate` command: `/iterate implement session checkpoint memory capture via session-end hook — store session_id and rule-based session summary as long-term source chunks, group question-like summary lines containing ?, 왜, 고민, or 생각, dedupe by session_id`

### F6 — Dashboard (Graph UI) | P2
Files: `frontend/src/`, `src/api/graph.py`
Success gate: `GET /graph/nodes` + `GET /graph/edges` → d3.js force graph 렌더링
Hard problem touch: no
`/iterate` command: `/iterate implement GET /graph/nodes and GET /graph/edges endpoints, React + Vite + d3.js force-directed graph dashboard showing chunks as nodes and similarity edges`

### F7 — Recall Agent | P1
Files: `src/service/recall.py`, `src/api/recall.py`
Success gate: `POST /recall` → tool_use output 파싱, relevance_score ≥ 0.7 시 angel_triggered=True, evidence_sources 포함, recall_logs에 input_hash/retrieved_chunk_ids/evidence_source_ids/drop_reason/angel_message 저장
Hard problem touch: **yes**
`/iterate` command: `/iterate implement Recall Agent — POST /recall endpoint, current context → Chroma top-k=5 retrieval → NetworkX neighbor injection, then single Claude LLM call with tool_use forced (angel_output tool: chunk_ids, evidence_sources, relevance_score, angel_message maxLength 120), Guardrails post-processing, save recall_logs with input_hash/retrieved_chunk_ids/evidence_source_ids/drop_reason/angel_message, with angel_message persistence configurable`

### F9 — LLM Resilience Layer | P2
Files: `src/llm.py`
Success gate:
- `AnthropicLLMClient` 정상 동작 확인
- Anthropic 5xx mock 3회 연속 → `LocalLLMClient` 자동 전환 (OPEN)
- 60초 후 probe 성공 → Anthropic 복귀 (CLOSED)
- LocalLLMClient tool_use 파싱 실패 → `None` 반환, Angel silent skip
Hard problem touch: no
`/iterate` command: `/iterate implement LLMClient Protocol with AnthropicLLMClient and LocalLLMClient (Ollama OpenAI-compatible endpoint, qwen2.5:7b). Circuit Breaker: CLOSED→OPEN on 3 consecutive failures (APIStatusError ≥500 / APIConnectionError / timeout>10s), OPEN→HALF_OPEN after 60s, HALF_OPEN→CLOSED on probe success. LocalLLMClient wraps tool_use parse in try/except returning None on JSONDecodeError/KeyError/ValidationError. GUARDIAN_LLM_PROVIDER and GUARDIAN_LOCAL_MODEL env vars.`

### F8 — MCP Server | P1
Files: `src/mcp_server.py`
Success gate: Claude Code에서 `recall` tool 호출 → Angel status line 표시 + 근거 노트 payload 반환
Hard problem touch: no
`/iterate` command: `/iterate implement MCP server exposing single 'recall' tool that calls POST /recall internally and returns angel_message plus evidence_sources for Claude Code status line display and note references`

---

## Test plan

### Unit tests
- LengthFilter: 50 tokens 미만 → discard, 이상 → pass
- Chunker: header 기반 split → 섹션 수만큼 chunk 생성
- Chunker: sliding window → overlap 20% 보장
- Guardrails: score ≥ 0.7 → triggered=True, 미만 → False
- angel_message 121자 → 120자로 truncation

### Integration tests
- watchdog create event → SQLite sources+chunks 저장
- watchdog delete event → sources soft delete + chunks + graph_edges 삭제
- watchdog move event → sources.path 업데이트
- `POST /events/prompt` 짧은 프롬프트 → length filter discard + 장기 chunk 저장 없음
- Session checkpoint capture → session-end 시점 rule-based summary로 session_id 기준 source+chunks 저장, 중복 session_id 재수집 방지
- `POST /recall` → recall_logs 1건 저장, angel_triggered 값 일치
- `POST /recall` → recall_logs에 retrieved_chunk_ids/evidence_source_ids/drop_reason/angel_message 저장

### Hard problem tests (LLM mock 필수)
- tool_use output 구조 검증: chunk_ids, evidence_sources, relevance_score, angel_message 모두 존재
- relevance_score 0.5 → angel silent drop
- relevance_score 0.8 → Angel trigger
- angel_message 없는 mock output → KeyError 없이 처리
- chunk_ids 빈 배열 → graceful drop

### Not in scope (P2)
- BGE-M3 embedding 품질 — RAGAS로 별도 측정
- NetworkX 그래프 알고리즘 — 라이브러리 신뢰
- d3.js 시각화 — 프론트엔드 수동 확인
- MCP Server 프로토콜 — Claude Code 연동 시 E2E 확인
