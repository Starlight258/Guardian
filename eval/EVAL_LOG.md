# Evaluation Log

Guardian recall 품질 개선 과정을 날짜별로 기록해요.

---

## 2026-05-27 — relevance_score 과대평가 false positive 수정

### 발견

첫 eval 실행 결과:

```
context_precision   1.000  ✓
false_positive_rate 0.333  ✗  (기준: ≤ 0.30)
```

"버스 몇 시에 와" 쿼리가 `.gitignore.md`, `KBO 크롤링 데이터.md`, `TPS.md`에 매칭되어 Angel이 발동됨.

### 분석

케이스별 relevance_score 분포:

| query | should_trigger | score |
|---|---|---|
| 버스 몇 시에 와 | false | **0.759** |
| AI 코딩 워크플로우 정리 | true | 0.710 |
| MCP 서버 만드는 법 | true | 0.670 |
| LLM 프롬프팅 모델별 차이점 | true | 0.619 |
| RAG 구현 어떻게 해 | true | 0.590 |

false positive가 true positive들보다 높은 점수를 받음. threshold 조정으로는 해결 불가 — LLM이 관련 없는 쿼리에 관대한 점수를 주는 것이 근본 원인.

### 수정

`src/service/recall.py` `_build_llm_prompt()`의 `relevance_score` 지시사항 강화:

**Before**
```
- relevance_score: 0.0 to 1.0
```

**After**
```
- relevance_score: 0.0–1.0. Be strict:
  0.8+ only when the evidence directly and specifically answers the query.
  0.5–0.7 for partial relevance.
  Below 0.5 when the connection is tangential, coincidental, or topic-adjacent only.
  When in doubt, score lower — a missed trigger is better than a false one.
```

### 결과

```
context_precision   1.000  ✓
false_positive_rate 0.000  ✓
false_negative_rate 0.000
PASS ✓  (7 cases)
```

---

## 평가 케이스 추가 가이드

`eval/cases.jsonl`에 한 줄씩 추가해요.

```json
{"query": "질문 내용", "should_trigger": true, "expected_source": "노트파일.md"}
{"query": "관련 없는 질문", "should_trigger": false, "expected_source": null}
```

false positive가 발생하면:
1. 어떤 소스에 매칭됐는지 `eval/results/` JSON에서 확인
2. relevance_score가 비정상적으로 높으면 LLM 프롬프트 수정 검토
3. threshold 조정은 score 분포 확인 후 결정 (threshold만 올리면 true positive도 잘릴 수 있음)
