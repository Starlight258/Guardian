// ==UserScript==
// @name         Guardian – ChatGPT capture
// @namespace    guardian
// @version      0.1
// @description  ChatGPT 응답이 끝날 때마다 Guardian에 저장해요
// @match        https://chatgpt.com/*
// @grant        GM_xmlhttpRequest
// @connect      127.0.0.1
// ==/UserScript==

(function () {
  "use strict";

  const GUARDIAN_URL = "http://127.0.0.1:8000";
  const MAX_TURNS = 6; // 최근 N개 턴만 포함 (user + assistant 각 1개 = 1턴)

  function getConversationId() {
    const m = location.pathname.match(/\/c\/([a-zA-Z0-9-]+)/);
    return m ? m[1] : null;
  }

  function extractTurns() {
    const elements = document.querySelectorAll("[data-message-author-role]");
    const turns = [];
    for (const el of elements) {
      const role = el.getAttribute("data-message-author-role");
      const text = el.innerText.trim();
      if (text) turns.push({ role, text });
    }
    return turns;
  }

  function buildSummary(turns) {
    const recent = turns.slice(-MAX_TURNS * 2);
    return recent
      .map(({ role, text }) => {
        const label = role === "user" ? "## User" : "## Assistant";
        return `${label}\n${text}`;
      })
      .join("\n\n");
  }

  function postToGuardian(sessionId, summary, turnCount) {
    const payload = JSON.stringify({
      session_id: sessionId,
      session_summary: summary,
      metadata: { source: "chatgpt", turn: turnCount },
    });

    GM_xmlhttpRequest({
      method: "POST",
      url: `${GUARDIAN_URL}/events/session-checkpoint`,
      headers: { "Content-Type": "application/json" },
      data: payload,
      onerror: () => {},
    });
  }

  let isGenerating = false;

  function onMutation() {
    const stopButton = document.querySelector('[data-testid="stop-button"]');

    if (stopButton && !isGenerating) {
      isGenerating = true;
      return;
    }

    if (!stopButton && isGenerating) {
      isGenerating = false;

      const convId = getConversationId();
      if (!convId) return;

      const turns = extractTurns();
      if (turns.length === 0) return;

      // 교환마다 별도 session_id — Guardian의 session_id dedup을 활용해 중복 저장 방지
      const turnCount = Math.ceil(turns.length / 2);
      const sessionId = `chatgpt-${convId}-${turnCount}`;

      const summary = buildSummary(turns);
      postToGuardian(sessionId, summary, turnCount);
    }
  }

  // SPA 네비게이션 대응: URL이 바뀌면 상태 초기화
  let lastPath = location.pathname;
  setInterval(() => {
    if (location.pathname !== lastPath) {
      lastPath = location.pathname;
      isGenerating = false;
    }
  }, 500);

  const observer = new MutationObserver(onMutation);
  observer.observe(document.body, { childList: true, subtree: true });
})();
