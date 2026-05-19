import { useMemo, useState } from 'react';
import Icon from './icons';
import { BubbleCluster, GrowthLine, MemoryGraphCanvas, SparkBars } from './charts';

export function StatTile({ stat }) {
  const iconBg = {
    pink: 'rgba(244,114,182,0.14)',
    primary: 'rgba(167,139,250,0.14)',
    green: 'rgba(74,222,128,0.14)',
    cyan: 'rgba(96,165,250,0.14)',
    amber: 'rgba(251,191,36,0.14)',
  }[stat.hue];
  const iconColor = {
    pink: '#f472b6',
    primary: '#a78bfa',
    green: '#4ade80',
    cyan: '#60a5fa',
    amber: '#fbbf24',
  }[stat.hue];
  const I = Icon[stat.icon] || Icon.doc;
  return (
    <div className="stat">
      <div className="stat-head">
        <div className="stat-icon" style={{ background: iconBg, color: iconColor }}>
          <I width="16" height="16" />
        </div>
        <span>{stat.label}</span>
      </div>
      <div className="stat-value">{typeof stat.value === 'number' ? stat.value.toLocaleString() : stat.value}</div>
      <div className={`stat-delta ${stat.deltaCls}`}>{stat.deltaCls === 'flame' ? '🔥 ' : ''}{stat.delta}</div>
      <SparkBars data={stat.spark} hue={stat.hue} />
    </div>
  );
}

export function OverviewPage({ data, onNavigate }) {
  const [recallSelect, setRecallSelect] = useState(null);
  const [range, setRange] = useState('30');
  return (
    <>
      <section className="stat-row">
        {data.stats.map((s) => <StatTile key={s.key} stat={s} />)}
      </section>

      <section className="grid-3">
        <div className="card">
          <div className="card-head">
            <h3 className="card-title">최근 기억 타임라인</h3>
            <button className="card-action" onClick={() => onNavigate('timeline')}>
              <Icon.clock width="12" height="12" /> 라이브
            </button>
          </div>
          {data.timeline.map((g) => (
            <div className="tl-group" key={g.day}>
              <div className="tl-day">{g.day}</div>
              {g.items.map((it, i) => (
                <div className="tl-row" data-src={it.src} key={i}>
                  <div className="tl-time">{it.time}</div>
                  <div className="tl-dot" />
                  <div className="tl-text">{it.text}</div>
                  <div className="tl-badge">{it.src === 'claude' ? 'Claude' : it.src === 'obsidian' ? 'Obsidian' : 'Session'}</div>
                </div>
              ))}
            </div>
          ))}
          <div className="panel-foot">
            <button onClick={() => onNavigate('timeline')}>전체 타임라인 보기 →</button>
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <h3 className="card-title">토픽 클러스터</h3>
            <button className="card-action" onClick={() => onNavigate('topics')}>모두 보기</button>
          </div>
          <BubbleCluster topics={data.topics} onSelect={() => onNavigate('topics')} />
          <div className="panel-foot">
            <button onClick={() => onNavigate('topics')}>모든 토픽 보기 →</button>
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <h3 className="card-title">최근 상기된 기억</h3>
            <button className="card-action" onClick={() => onNavigate('recall')}>Angel 로그</button>
          </div>
          {data.recalls.map((r, i) => (
            <div className="recall-row" key={i} onClick={() => setRecallSelect(i)}>
              <div className="recall-icon" style={{ background: `${r.color}22`, color: r.color }}>{r.ico}</div>
              <div className="recall-text">
                <div className="recall-title">{r.title}</div>
                <div className="recall-meta">{r.when}</div>
              </div>
              <div className="recall-count">{r.count}</div>
            </div>
          ))}
          <div className="panel-foot">
            <button onClick={() => onNavigate('recall')}>모든 상기 기록 보기 →</button>
          </div>
        </div>
      </section>

      <section className="grid-2">
        <div className="card">
          <div className="card-head">
            <h3 className="card-title">기억 성장 추이</h3>
            <div className="range-tabs">
              {['7', '30', '90'].map((r) => (
                <button key={r} className={range === r ? 'active' : ''} onClick={() => setRange(r)}>{r}일</button>
              ))}
            </div>
          </div>
          <GrowthLine points={data.growth} range={parseInt(range, 10)} />
        </div>
        <div className="card">
          <div className="card-head">
            <h3 className="card-title">상위 연결 기억</h3>
            <button className="card-action" onClick={() => onNavigate('graph')}>그래프</button>
          </div>
          <div>
            {data.connections.map((c, i) => (
              <div className="conn-row" key={i}>
                <div className="conn-icon" style={{ background: `${c.aColor}22`, color: c.aColor }}>{c.aIco}</div>
                <div className="conn-name">{c.a}</div>
                <div className="conn-bar" style={{ '--w': c.w }} />
                <div className="conn-name">
                  <span style={{ display: 'inline-block', width: 20, height: 20, lineHeight: '20px', textAlign: 'center', borderRadius: 6, background: `${c.bColor}22`, color: c.bColor, fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 600, marginRight: 6 }}>{c.bIco}</span>
                  {c.b}
                </div>
                <div className="conn-count">연결 {c.count}</div>
              </div>
            ))}
          </div>
          <div className="panel-foot">
            <button onClick={() => onNavigate('graph')}>모든 연결 보기 →</button>
          </div>
        </div>
      </section>
    </>
  );
}

export function MemoryGraphPage({ data }) {
  const [selectedId, setSelectedId] = useState(data.graphNodes[0]?.id);
  const sel = data.graphNodes.find((n) => n.id === selectedId);
  const clusterLabel = { AI: 'AI 개발 도구', async: '비동기 프로그래밍', vec: '벡터 DB & 임베딩', graph: '지식 그래프 구현' };
  const snippet = `이 노드는 ${clusterLabel[sel?.cluster] || ''} 클러스터에 속해요. 새로운 chunk가 추가되면 Chroma top-k retrieval과 NetworkX 인접 노드 주입을 거쳐 Recall Agent로 전달되며, 단일 LLM call로 relevance score가 계산돼요.`;
  const nodeCount = data.graphNodes.length;
  const linkCount = 89;
  const sourceCount = 24;
  return (
    <div className="graph-page">
      <div className="graph-canvas-wrap">
        <div className="graph-overlay-stats">
          <div><span>Nodes</span><b>{nodeCount}</b></div>
          <div><span>Edges</span><b>{linkCount}</b></div>
          <div><span>Sources</span><b>{sourceCount}</b></div>
        </div>
        <MemoryGraphCanvas nodes={data.graphNodes} selectedId={selectedId} onSelect={(n) => setSelectedId(n.id)} />
      </div>
      <div className="graph-detail">
        <h3>chunk #{String(sel?.id).padStart(4, '0')}</h3>
        <div className="graph-field">
          <div className="graph-field-label">Cluster</div>
          <div className="graph-field-value">{clusterLabel[sel?.cluster]}</div>
        </div>
        <div className="graph-field">
          <div className="graph-field-label">Source</div>
          <div className="graph-field-value">python-async-notes.md</div>
        </div>
        <div className="graph-field">
          <div className="graph-field-label">Chunk index</div>
          <div className="graph-field-value">{(sel?.id ?? 0) % 12}</div>
        </div>
        <div className="graph-field">
          <div className="graph-field-label">Tokens</div>
          <div className="graph-field-value">412</div>
        </div>
        <div className="graph-field">
          <div className="graph-field-label">Snippet</div>
          <div className="graph-field-value">{snippet}</div>
        </div>
        <div className="graph-field">
          <div className="graph-field-label">Chunk ID</div>
          <div className="graph-field-value mono">019e3f20-ae06-71b1-a4ed-353ca2c{String(sel?.id || 0).padStart(2, '0')}</div>
        </div>
      </div>
    </div>
  );
}

export function TimelinePage({ data }) {
  const [filter, setFilter] = useState('all');
  const allItems = useMemo(() => {
    const flat = [];
    data.timeline.forEach((g) => {
      g.items.forEach((it) => flat.push({ ...it, day: g.day }));
    });
    const extras = [
      {
        day: '2일 전',
        items: [
          { time: '21:33', src: 'claude', text: '벡터 검색 성능 최적화 전략 논의' },
          { time: '15:08', src: 'obsidian', text: 'BGE-M3 dense retrieval 정리' },
          { time: '11:50', src: 'checkpoint', text: 'session: rag-tuning-week1' },
        ],
      },
      {
        day: '3일 전',
        items: [
          { time: '19:42', src: 'obsidian', text: 'GraphRAG 패턴 비교 노트' },
          { time: '16:11', src: 'claude', text: '그래프 레이아웃 알고리즘 (force-directed)' },
        ],
      },
    ];
    extras.forEach((g) => g.items.forEach((it) => flat.push({ ...it, day: g.day })));
    return flat;
  }, [data]);

  const filtered = filter === 'all' ? allItems : allItems.filter((it) => it.src === filter);
  const grouped = useMemo(() => {
    const out = {};
    filtered.forEach((it) => { (out[it.day] = out[it.day] || []).push(it); });
    return out;
  }, [filtered]);

  return (
    <>
      <div className="tl-filters">
        {[
          ['all', '전체'],
          ['obsidian', 'Obsidian'],
          ['claude', 'Claude'],
          ['checkpoint', 'Session'],
        ].map(([k, lbl]) => (
          <button key={k} className={`tl-chip ${filter === k ? 'active' : ''}`} onClick={() => setFilter(k)}>{lbl}</button>
        ))}
      </div>
      <div className="tl-page">
        <div className="card" style={{ padding: '6px 22px 14px' }}>
          {Object.entries(grouped).map(([day, items]) => (
            <div key={day}>
              <div className="tl-day" style={{ marginTop: 14, marginBottom: 8 }}>{day}</div>
              {items.map((it, i) => (
                <div className="tl-feed-row" data-src={it.src} key={i}>
                  <div className="tl-feed-time">{it.time}</div>
                  <div className="tl-feed-line">
                    <div className="tl-dot" />
                  </div>
                  <div>
                    <div className="tl-feed-title">{it.text}</div>
                    <div className="tl-feed-body">
                      {it.src === 'claude'
                        ? '사용자 prompt event를 trigger로 Recall Agent가 관련 청크를 찾아 Angel 메시지를 생성한 항목이에요.'
                        : it.src === 'obsidian'
                          ? 'Obsidian vault watcher가 markdown 변경을 감지해 chunking + embedding 파이프라인을 거쳐 저장됐어요.'
                          : 'Session 종료 시 hook이 rule-based summary를 만들어 장기 memory source로 저장한 checkpoint예요.'}
                    </div>
                    <div className="tl-feed-meta">
                      <span>chunks: {3 + (i % 4)}</span>
                      <span>tokens: {412 + i * 18}</span>
                      <span>relevance: {(0.62 + (i * 0.05) % 0.3).toFixed(2)}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ))}
        </div>
        <div>
          <div className="card">
            <div className="card-head"><h3 className="card-title">필터</h3></div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-3)', lineHeight: 1.8 }}>
              <div>· 총 항목: <b style={{ color: 'var(--text)' }}>{allItems.length}</b></div>
              <div>· 필터 결과: <b style={{ color: 'var(--primary-2)' }}>{filtered.length}</b></div>
              <div>· 평균 chunks/source: <b style={{ color: 'var(--text)' }}>4.2</b></div>
              <div>· 평균 tokens/chunk: <b style={{ color: 'var(--text)' }}>438</b></div>
            </div>
          </div>
          <div className="card" style={{ marginTop: 14 }}>
            <div className="card-head"><h3 className="card-title">오늘의 Angel</h3></div>
            <div className="angel-bubble" style={{ marginTop: 6 }}>오늘은 비동기 프로그래밍 관련 노트를 가장 많이 만났어요 ✨</div>
          </div>
        </div>
      </div>
    </>
  );
}

export function TopicsPage({ data }) {
  return (
    <>
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ padding: '18px 22px' }}>
          <div className="card-head" style={{ marginBottom: 4 }}>
            <h3 className="card-title">전체 토픽 분포</h3>
            <span className="card-action">{data.topics.length}개 클러스터</span>
          </div>
        </div>
        <div style={{ padding: '0 22px 8px' }}>
          <BubbleCluster topics={data.topics} />
        </div>
      </div>
      <div className="topics-grid">
        {data.topics.map((t) => (
          <div key={t.id} className="topic-card">
            <div className="topic-card-glow" style={{ background: t.color }} />
            <h4 className="topic-card-name">{t.label.replace('\n', ' ')}</h4>
            <div className="topic-card-count">{t.count} <span style={{ fontSize: 13, color: 'var(--text-3)' }}>chunks</span></div>
            <div className="topic-tags">
              <span className="topic-tag">connected: {Math.floor(t.count * 3.4)}</span>
              <span className="topic-tag">sources: {Math.floor(t.count / 4)}</span>
            </div>
            <div className="topic-card-meta">마지막 업데이트 {Math.floor(Math.random() * 60)}분 전</div>
          </div>
        ))}
      </div>
    </>
  );
}

export function RecallHistoryPage({ data }) {
  const [dismissed, setDismissed] = useState(false);
  return (
    <>
      <div className="cli-wrap">
        <div className="cli-bar">
          <div className="cli-traffic"><span /><span /><span /></div>
          <div className="cli-bar-title">&gt;_ claude</div>
          <div style={{ width: 60 }} />
        </div>
        <div className="cli-body">
          <div className="cli-line">
            <span className="bullet">●</span>
            <span className="cli-text"><span className="cli-prompt">claude</span> &gt; explain async decorators in python</span>
          </div>
          <div className="cli-line assist">
            <span className="bullet">●</span>
            <span className="cli-text">
              <span className="cli-prompt-name">Claude</span> &gt; Sure! I'll explain how to use<br />
              <span style={{ paddingLeft: 22, display: 'inline-block' }}>async decorators in Python.</span><br />
              <span style={{ paddingLeft: 22, display: 'inline-block', color: 'var(--text-3)' }}>... (answer)</span>
            </span>
          </div>
          <div style={{ paddingLeft: 22, marginTop: 6 }}>
            <span className="cli-cursor" />
          </div>

          {!dismissed && (
            <div className="cli-card">
              <div className="cli-card-head">
                <Icon.brain width="14" height="14" />
                <span>related memory detected</span>
              </div>
              <div className="cli-card-title">async decorators 정리 노트</div>
              <div className="cli-card-meta">9 days ago · <b>python-async-notes.md</b></div>
              <div className="cli-card-actions">
                <button>[open]</button>
                <button className="dismiss" onClick={() => setDismissed(true)}>[dismiss]</button>
              </div>
            </div>
          )}

          <div className="cli-line" style={{ marginTop: 18, opacity: 0.6 }}>
            <span className="bullet" style={{ color: 'var(--text-4)' }}>○</span>
            <span className="cli-text" style={{ color: 'var(--text-4)' }}>recall.history · 24 events past 7 days · 12 dismissed</span>
          </div>
        </div>
        <div className="cli-foot">
          <div className="cli-foot-cell">
            <Icon.doc width="22" height="22" />
            <div>
              <div>Guardian is listening...</div>
              <div className="cli-foot-sub">Capture → Connect → Recall</div>
            </div>
          </div>
          <div className="cli-foot-cell">
            <Icon.graph width="22" height="22" />
            <div>
              <div>3 related memories found</div>
              <div className="cli-foot-sub">last recall: 12m ago</div>
            </div>
          </div>
          <div className="cli-foot-cell right">
            <span style={{ color: 'var(--green)' }}>●</span>
            <span>Angel: ON</span>
            <img className="pixel-art" src="/assets/angel-head.png" style={{ width: 44, height: 'auto' }} />
            <span style={{ color: 'var(--pink)' }}>♥</span>
          </div>
        </div>
      </div>

      <div className="insight-row" style={{ marginTop: 14 }}>
        <div className="insight-card">
          <div className="insight-eyebrow">RECALL STATS · 7일</div>
          <div className="insight-headline">총 24회 상기 · 평균 confidence 0.72</div>
          <div className="insight-body">false positive rate 8.3% · query rewrite 미사용 · threshold 0.60 유지중</div>
        </div>
        <div className="insight-card">
          <div className="insight-eyebrow">DROPPED · GUARDRAILS</div>
          <div className="insight-headline">12회 silent drop (score &lt; 0.60)</div>
          <div className="insight-body">짧은 prompt event 6건, 컨텍스트 불일치 4건, 중복 2건</div>
        </div>
      </div>
    </>
  );
}

export function InsightsPage({ data }) {
  return (
    <>
      <div className="insight-row">
        <div className="insight-card">
          <div className="insight-eyebrow">✨ THIS WEEK</div>
          <div className="insight-headline">async 관련 노트가 이번 주 가장 많이 상기됐어요</div>
          <div className="insight-body">'async decorators 정리 노트'가 3일 동안 4번 상기됐고, 평균 relevance가 0.81로 가장 높았어요. Claude prompt와 Obsidian 노트 사이의 연결이 14개로 늘었어요.</div>
        </div>
        <div className="insight-card">
          <div className="insight-eyebrow">🌱 GROWING TOPIC</div>
          <div className="insight-headline">'벡터 DB & 임베딩' 클러스터가 빠르게 자라고 있어요</div>
          <div className="insight-body">지난 7일간 chunks가 32 → 87로 증가. BGE-M3, Chroma 메타데이터 필터링, 임베딩 성능 평가 노트가 서로 강하게 연결됐어요.</div>
        </div>
      </div>
      <div className="insight-row">
        <div className="insight-card">
          <div className="insight-eyebrow">⚠️ SIGNAL</div>
          <div className="insight-headline">최근 false positive 비율이 살짝 올라갔어요 (5.2% → 8.3%)</div>
          <div className="insight-body">짧은 prompt event 6건이 length filter를 통과한 것으로 보여요. threshold 미세 조정 또는 length 컷오프를 35자에서 50자로 올리는 걸 고려해볼 만해요.</div>
        </div>
        <div className="insight-card">
          <div className="insight-eyebrow">💤 QUIET CORNER</div>
          <div className="insight-headline">"D3.js" 토픽은 12일째 새 chunks가 없어요</div>
          <div className="insight-body">14개 노드가 모두 17일 이상 상기되지 않았어요. archive 후보로 분류하거나, 관련 작업 재개 시 alert를 받을 수 있어요.</div>
        </div>
      </div>
    </>
  );
}

export function SettingsPage({ data }) {
  const [angelOn, setAngelOn] = useState(true);
  const [threshold, setThreshold] = useState(0.6);
  const [length, setLength] = useState(35);
  const [autoSync, setAutoSync] = useState(true);
  return (
    <>
      <div className="settings-row">
        <div>
          <div className="settings-label">Angel 활성화</div>
          <div className="settings-sub">prompt event가 들어왔을 때 Angel을 띄울지 결정해요.</div>
        </div>
        <div className={`toggle ${angelOn ? 'on' : ''}`} onClick={() => setAngelOn((v) => !v)} />
      </div>
      <div className="settings-row">
        <div>
          <div className="settings-label">Recall threshold</div>
          <div className="settings-sub">이 값보다 낮은 relevance는 silent drop 돼요.</div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <input type="range" min="0" max="1" step="0.05" value={threshold} onChange={(e) => setThreshold(parseFloat(e.target.value))} style={{ accentColor: 'var(--primary)' }} />
          <code>{threshold.toFixed(2)}</code>
        </div>
      </div>
      <div className="settings-row">
        <div>
          <div className="settings-label">Length filter</div>
          <div className="settings-sub">이 길이보다 짧은 prompt event는 처리하지 않아요.</div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <input type="range" min="10" max="100" step="5" value={length} onChange={(e) => setLength(parseInt(e.target.value, 10))} style={{ accentColor: 'var(--primary)' }} />
          <code>{length} chars</code>
        </div>
      </div>
      <div className="settings-row">
        <div>
          <div className="settings-label">Obsidian 자동 동기화</div>
          <div className="settings-sub">filesystem watcher로 vault 변경을 실시간 감지해요.</div>
        </div>
        <div className={`toggle ${autoSync ? 'on' : ''}`} onClick={() => setAutoSync((v) => !v)} />
      </div>
      <div className="settings-row">
        <div>
          <div className="settings-label">Obsidian vault path</div>
          <div className="settings-sub">스캔할 markdown 루트 디렉토리.</div>
        </div>
        <code>~/Documents/Obsidian/main</code>
      </div>
      <div className="settings-row">
        <div>
          <div className="settings-label">Chroma collection</div>
          <div className="settings-sub">embedding이 저장되는 collection 이름.</div>
        </div>
        <code>guardian_v1</code>
      </div>
      <div className="settings-row">
        <div>
          <div className="settings-label">Embedding model</div>
          <div className="settings-sub">현재 사용 중인 dense retrieval 모델.</div>
        </div>
        <code>BAAI/bge-m3</code>
      </div>
    </>
  );
}
