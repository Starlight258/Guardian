# Guardian Hook Flow

AI 세션 프롬프트를 Guardian 지식 그래프에 저장하는 훅 파이프라인 설명.

---

## 개요

두 AI 도구(Claude Code, Codex)는 훅을 통해 Guardian에 프롬프트를 저장한다.
각 프롬프트는 SQLite(`data/guardian.db`)와 Chroma 벡터 DB에 저장된다.

---

## Claude Code 훅 파이프라인

설정 파일: `~/.claude/settings.json`

### UserPromptSubmit — recall만, 저장 안 함

```
UserPromptSubmit → recall_trigger.sh → POST /events/prompt
```

- 사용자가 메시지를 입력할 때마다 발동
- Guardian에서 관련 과거 컨텍스트를 recall해 Claude 응답에 참고시키는 용도
- **저장하지 않음** — recall 전용 엔드포인트(`/events/prompt`)

### SessionEnd — 세션 요약 저장

```
SessionEnd → claude_session_summary.py → post_session_to_guardian.sh → POST /events/session-checkpoint
```

| 단계 | 설명 |
|---|---|
| `SessionEnd` | Claude Code 세션 종료 시 발동 |
| `claude_session_summary.py` | 트랜스크립트 JSONL을 파싱해 Questions / Requests / Actions 섹션 추출 |
| `post_session_to_guardian.sh` | `async curl`로 Guardian API에 POST (블로킹 없음) |

#### claude_session_summary.py 처리 내용

- 트랜스크립트 포맷: `{"type":"user","message":{"role":"user","content":[...]}}` — `message` 키 하위에 중첩
- `_NOISE_PREFIXES`: `<`, `[Request interrupted`, `<local-command`, `<task-notification`, `<command-` 등 시스템 주입 필터링
- `_MIN_MSG_LEN = 4`: 너무 짧은 메시지("응", "ㅇ") 필터링
- `?`, `왜`, `고민`, `생각` 포함 → **Questions** 섹션
- 나머지 → **Requests** 섹션
- `Edit`/`Write`/`Bash` 도구 사용 → **Actions** 섹션

---

## Codex 훅 파이프라인

설정 파일: `~/.codex/config.toml`

Codex는 `SessionEnd` 훅이 없다. 대신 **Stop(턴 종료)**에 임시 파일에 수집하고, **다음 SessionStart**에 Guardian으로 전송하는 2단계 파이프라인을 사용한다.

### UserPromptSubmit — recall만

```
UserPromptSubmit → recall_trigger.sh → POST /events/prompt
```

Claude와 동일. recall 전용.

### Stop (각 턴) — 임시 파일에 수집

```
Stop → codex_session_collect.py → pending_{id}.md (tempdir)
```

| 단계 | 설명 |
|---|---|
| `Stop` | Codex가 각 응답을 완료할 때마다 발동 |
| `codex_session_collect.py` | `~/.codex/history.jsonl`에서 현재 `session_id`의 새 프롬프트만 읽음 |
| `pending_{id}.md` | `/var/folders/.../T/guardian_codex_pending_{session_id}.md`에 append |

임시 파일 포맷:

```md
# Session checkpoint

Session: codex-{session_id}
CWD: {cwd}

## Prompts

- 프롬프트 내용 1
- 프롬프트 내용 2

<!-- last_ts: 1779613761 -->
```

- `last_ts`를 `.state.json`에 저장해 중복 수집 방지
- macOS tempdir: `tempfile.gettempdir()` = `/var/folders/...` (NOT `/tmp`)

### SessionStart (다음 세션) — Guardian에 전송

```
SessionStart → codex_session_flush.py → post_session_to_guardian.sh → POST /events/session-checkpoint
```

| 단계 | 설명 |
|---|---|
| `SessionStart` | 새 Codex 세션 시작 시 발동 |
| `codex_session_flush.py` | tempdir에서 `guardian_codex_pending_*.md` 전체 스캔 |
| | 현재 session_id 파일은 건너뜀 (아직 진행 중) |
| | 나머지 파일을 `post_session_to_guardian.sh`로 전송 후 삭제 |
| `post_session_to_guardian.sh` | `async curl & disown`으로 Guardian API POST |

---

## Guardian API

```
POST /events/session-checkpoint
{
  "session_id": "...",
  "session_summary": "## Prompts\n- ...\n## Requests\n- ...",
  "metadata": {"cwd": "...", "source": "session-end"}
}
```

Guardian은 받은 요약을 `session_checkpoint` 타입 Source로 SQLite에 upsert하고, Chroma에 임베딩한다.

### guard CLI (`~/.zshrc`)

```bash
guard               # 최근 5개 세션 프롬프트
guard 진라면        # "진라면" 포함 최근 20개
```

출력:
```
2026-05-23 12:34:56  [claude]  진라면 레시피 찾아줘
2026-05-23 10:11:22  [codex]   진라면 끓이는 방법 구현해줘
```

`[claude]` / `[codex]` 태그는 `session_id.startswith("codex-")`로 구분.

---

## Entire을 사용하지 않는 이유

Guardian 훅은 Entire CLI를 사용하지 않고 직접 파이프라인을 구현했다.

### 1. 속도 — 매 프롬프트마다 블로킹

Entire 훅은 프롬프트 제출마다 동기적으로 실행된다. 검색 인덱싱이나 네트워크 요청이 포함되면 AI 응답이 그만큼 지연된다. Guardian 훅은 `async curl & disown`으로 백그라운드 전송해 지연 없음.

### 2. 의존성 없음 — 협업 환경 호환

팀 프로젝트나 다른 사람의 머신에서는 Entire이 설치되어 있지 않을 수 있다. Guardian 훅은 표준 Python 3와 curl만 사용해 어디서나 동작한다.

### 3. 커스텀 수집 로직

Entire의 기본 인덱싱은 프롬프트 원문을 그대로 저장한다. Guardian은:
- 시스템 주입 메시지 필터링 (`_NOISE_PREFIXES`)
- 최소 길이 필터 (`_MIN_MSG_LEN = 4`)
- Questions vs Requests 분류
- Codex의 Stop/SessionStart 2단계 파이프라인으로 세션 단위 수집

---

## 파일 목록

| 파일 | 역할 |
|---|---|
| `hooks/recall_trigger.sh` | Claude/Codex 공용 recall 트리거 |
| `hooks/claude_session_summary.py` | Claude 트랜스크립트 파싱 → 요약 JSON 출력 |
| `hooks/codex_session_collect.py` | Codex Stop 훅 — history.jsonl → pending.md |
| `hooks/codex_session_flush.py` | Codex SessionStart 훅 — pending.md → Guardian |
| `hooks/post_session_to_guardian.sh` | async curl로 Guardian API POST |
