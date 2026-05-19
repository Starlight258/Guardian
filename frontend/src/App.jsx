import { useEffect, useMemo, useState } from 'react';
import DATA from './dashboard/data';
import Icon from './dashboard/icons';
import { TweakRadio, TweakSection, TweakToggle, TweaksPanel, useTweaks } from './dashboard/tweaks-panel';
import {
  InsightsPage,
  MemoryGraphPage,
  OverviewPage,
  RecallHistoryPage,
  SettingsPage,
  TimelinePage,
  TopicsPage,
} from './dashboard/pages';

const NAV = [
  { key: 'overview', label: 'Overview', icon: 'home', count: null },
  { key: 'graph', label: 'Memory Graph', icon: 'graph', count: 56 },
  { key: 'timeline', label: 'Timeline', icon: 'clock', count: null },
  { key: 'topics', label: 'Topics', icon: 'tag', count: 28 },
  { key: 'recall', label: 'Recall History', icon: 'heart', count: 24 },
  { key: 'insights', label: 'Insights', icon: 'chart', count: null },
  { key: 'settings', label: 'Settings', icon: 'gear', count: null },
];

const PAGE_TITLES = {
  overview: { title: 'Memory Overview', sub: 'AI와 함께 쌓아가는 당신의 지식 그래프 🌙 ✨' },
  graph: { title: 'Memory Graph', sub: 'chunks · edges · sources — d3 force layout' },
  timeline: { title: 'Timeline', sub: '시간순으로 흐르는 기억의 발자국' },
  topics: { title: 'Topics', sub: 'embedding으로 묶인 의미 클러스터' },
  recall: { title: 'Recall History', sub: 'Claude prompt event가 트리거한 Angel 로그' },
  insights: { title: 'Insights', sub: 'Angel이 발견한 패턴과 신호' },
  settings: { title: 'Settings', sub: 'Recall · Capture · Guardrails 파라미터' },
};

const ANGEL_MOOD_LABEL = {
  watchful: 'Angel: ON',
  sleepy: 'Angel: 휴면',
  excited: 'Angel: 활발',
  off: 'Angel: OFF',
};

const TWEAK_DEFAULTS = {
  theme: 'night',
  angelMood: 'watchful',
  density: 'cozy',
  toastEnabled: true,
  angelScale: 1,
};

function Sidebar({ active, onNavigate, angelMood }) {
  const moodMsgs = DATA.angelMessages[angelMood] || DATA.angelMessages.watchful;
  const [msgIdx, setMsgIdx] = useState(0);
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    if (paused || moodMsgs.length <= 1) return undefined;
    const id = setInterval(() => setMsgIdx((i) => (i + 1) % moodMsgs.length), 5000);
    return () => clearInterval(id);
  }, [moodMsgs, paused]);

  useEffect(() => {
    setMsgIdx(0);
  }, [angelMood]);

  const NavIcon = (key) => Icon[NAV.find((n) => n.key === key).icon];

  return (
    <aside className="sidebar">
      <div className="brand">
        <img src="/assets/angel-brand.png" className="brand-img pixel-art" alt="" />
        <div className="brand-text">
          <div className="brand-name">Guardian</div>
          <div className="brand-tag">Your Memory Guardian</div>
        </div>
      </div>

      <div className="nav-group-label">MAIN</div>
      <nav className="nav">
        {NAV.slice(0, 6).map((item) => {
          const I = Icon[item.icon];
          return (
            <button
              key={item.key}
              className={`nav-item ${active === item.key ? 'active' : ''}`}
              onClick={() => onNavigate(item.key)}
            >
              <I className="nav-icon" width="18" height="18" />
              <span>{item.label}</span>
              {item.count != null && <span className="nav-count">{item.count}</span>}
            </button>
          );
        })}
      </nav>

      <div className="nav-group-label">SYSTEM</div>
      <nav className="nav">
        {NAV.slice(6).map((item) => {
          const I = Icon[item.icon];
          return (
            <button
              key={item.key}
              className={`nav-item ${active === item.key ? 'active' : ''}`}
              onClick={() => onNavigate(item.key)}
            >
              <I className="nav-icon" width="18" height="18" />
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>

      <div className="angel-card" onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)}>
        <div className="angel-card-title">오늘의 Angel</div>
        <div className="angel-bubble" key={msgIdx} style={{ animation: 'fadeIn 400ms ease' }}>
          {moodMsgs[msgIdx]}
        </div>
        <div className="angel-cloud-wrap">
          <img src="/assets/angel-cloud.png" className="angel-cloud-img pixel-art" alt="" />
        </div>
      </div>
    </aside>
  );
}

function Topbar({ page, mood }) {
  const meta = PAGE_TITLES[page];
  return (
    <header className="topbar">
      <div className="topbar-title">
        <h1 className="page-title">{meta.title}</h1>
        <div className="page-sub">{meta.sub}</div>
      </div>
      <div className="topbar-right">
        <div className="status-pill" data-mood={mood}>
          <span className="dot" />
          <span>{ANGEL_MOOD_LABEL[mood]}</span>
        </div>
        <div className="header-angel">
          <div className="header-angel-bubble">
            <b>I'm watching</b>
            <br />
            over your memories! ✨
          </div>
          <img src="/assets/angel-fly.png" className="header-angel-img pixel-art" alt="" />
        </div>
      </div>
    </header>
  );
}

function RecallToast({ onDismiss }) {
  const t = DATA.recallToast;
  const [closing, setClosing] = useState(false);
  const handleDismiss = () => {
    setClosing(true);
    setTimeout(onDismiss, 280);
  };
  return (
    <div className={`recall-toast ${closing ? 'out' : ''}`}>
      <div className="toast-head">
        <Icon.brain width="14" height="14" />
        <span>related memory detected</span>
      </div>
      <div className="toast-title">{t.title}</div>
      <div className="toast-meta">{t.meta} · <b>{t.file}</b></div>
      <div className="toast-actions">
        <button>[open]</button>
        <button className="dismiss" onClick={handleDismiss}>[dismiss]</button>
      </div>
    </div>
  );
}

function Sparkles() {
  const sparkles = useMemo(
    () => Array.from({ length: 18 }).map((_, i) => ({
      id: i,
      left: Math.random() * 100,
      top: Math.random() * 100,
      size: 8 + Math.random() * 8,
      delay: Math.random() * 4,
      glyph: ['✦', '✧', '+', '·'][i % 4],
      color: ['var(--primary)', 'var(--pink)', 'var(--amber)', 'var(--cyan)'][i % 4],
    })),
    [],
  );
  return (
    <>
      {sparkles.map((s) => (
        <div
          key={s.id}
          className="sparkle"
          style={{ left: `${s.left}%`, top: `${s.top}%`, fontSize: s.size, animationDelay: `${s.delay}s`, color: s.color }}
        >
          {s.glyph}
        </div>
      ))}
    </>
  );
}

export default function App() {
  const [page, setPage] = useState('overview');
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
  const [toast, setToast] = useState(false);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', t.theme);
    document.documentElement.setAttribute('data-density', t.density);
  }, [t.theme, t.density]);

  useEffect(() => {
    if (!t.toastEnabled || t.angelMood === 'off') return undefined;
    const id = setTimeout(() => setToast(true), 8000);
    return () => clearTimeout(id);
  }, [page, t.toastEnabled, t.angelMood]);

  const renderPage = () => {
    switch (page) {
      case 'overview':
        return <OverviewPage data={DATA} onNavigate={setPage} />;
      case 'graph':
        return <MemoryGraphPage data={DATA} />;
      case 'timeline':
        return <TimelinePage data={DATA} />;
      case 'topics':
        return <TopicsPage data={DATA} />;
      case 'recall':
        return <RecallHistoryPage data={DATA} />;
      case 'insights':
        return <InsightsPage data={DATA} />;
      case 'settings':
        return <SettingsPage data={DATA} />;
      default:
        return null;
    }
  };

  return (
    <div className="app" data-screen-label={`Guardian - ${PAGE_TITLES[page].title}`}>
      <Sparkles />
      <Sidebar active={page} onNavigate={setPage} angelMood={t.angelMood} />
      <main className="main">
        <Topbar page={page} mood={t.angelMood} />
        {renderPage()}
      </main>
      {toast && <RecallToast onDismiss={() => setToast(false)} />}

      <TweaksPanel title="Tweaks">
        <TweakSection label="Angel" />
        <TweakRadio
          label="Mood"
          value={t.angelMood}
          options={['watchful', 'sleepy', 'excited', 'off']}
          onChange={(v) => setTweak('angelMood', v)}
        />
        <TweakToggle
          label="Recall toast"
          value={t.toastEnabled}
          onChange={(v) => setTweak('toastEnabled', v)}
        />
        <TweakSection label="Theme" />
        <TweakRadio
          label="Background"
          value={t.theme}
          options={['night', 'twilight', 'dawn']}
          onChange={(v) => setTweak('theme', v)}
        />
        <TweakRadio
          label="Density"
          value={t.density}
          options={['cozy', 'compact']}
          onChange={(v) => setTweak('density', v)}
        />
      </TweaksPanel>
    </div>
  );
}
