import { useEffect, useState } from 'react';
import { fetchEdges, fetchNodes, fetchStats } from './api';
import DATA from './data';

const SRC_COLOR = {
  claude: '#f472b6',
  obsidian: '#a78bfa',
  checkpoint: '#34d399',
  default: '#60a5fa',
};

const CLUSTER_POS = {
  claude:      { cx: 0.72, cy: 0.30 },
  obsidian:    { cx: 0.30, cy: 0.35 },
  checkpoint:  { cx: 0.22, cy: 0.78 },
};
const DEFAULT_POS = { cx: 0.62, cy: 0.72 };

function relativeDay(isoStr) {
  const diffMs = Date.now() - new Date(isoStr).getTime();
  const days = Math.floor(diffMs / 86400000);
  if (days === 0) return '오늘';
  if (days === 1) return '어제';
  return `${days}일 전`;
}

function timeStr(isoStr) {
  const d = new Date(isoStr);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

function buildStats(apiStats, growth30d) {
  const sparkVals = growth30d.map((p) => p.value);
  return [
    {
      ...DATA.stats[0],
      value: apiStats.total_chunks,
      delta: `+${apiStats.chunks_today} 오늘`,
      deltaCls: apiStats.chunks_today > 0 ? 'up' : 'neutral',
      spark: sparkVals,
    },
    {
      ...DATA.stats[1],
      value: apiStats.total_edges,
      delta: `+${apiStats.edges_today} 오늘`,
      deltaCls: apiStats.edges_today > 0 ? 'up' : 'neutral',
      spark: sparkVals.map((v) => Math.floor(v * 3.2)),
    },
    {
      ...DATA.stats[2],
      value: apiStats.total_sources,
      delta: `+${apiStats.sources_today} 오늘`,
      deltaCls: apiStats.sources_today > 0 ? 'up' : 'neutral',
    },
    DATA.stats[3],
    DATA.stats[4],
  ];
}

function buildTimeline(recentSources) {
  const grouped = {};
  recentSources.forEach((src) => {
    const day = relativeDay(src.created_at);
    if (!grouped[day]) grouped[day] = [];
    const name = src.title
      || (src.path ? src.path.split('/').pop().replace(/\.md$/, '') : `source ${src.id.slice(0, 8)}`);
    grouped[day].push({ time: timeStr(src.created_at), src: src.source_type, text: name });
  });
  return Object.entries(grouped).map(([day, items]) => ({ day, items }));
}

function buildTopics(sourceTypeCounts) {
  const SHAPES = {
    claude:     { label: 'Claude\n대화',           color: '#f472b6', cx: 0.72, cy: 0.30 },
    obsidian:   { label: 'Obsidian\n노트',         color: '#a78bfa', cx: 0.30, cy: 0.35 },
    checkpoint: { label: 'Session\nCheckpoint',    color: '#34d399', cx: 0.22, cy: 0.78 },
  };
  const total = Object.values(sourceTypeCounts).reduce((s, c) => s + c, 0) || 1;
  return Object.entries(sourceTypeCounts).map(([type, count]) => {
    const cfg = SHAPES[type] || { label: type, color: '#60a5fa', cx: 0.62, cy: 0.72 };
    return {
      id: type,
      label: cfg.label,
      count,
      r: 20 + Math.round((count / total) * 50),
      cx: cfg.cx,
      cy: cfg.cy,
      color: cfg.color,
    };
  });
}

function buildConnections(topConnections) {
  const colors = ['#f472b6', '#a78bfa', '#34d399', '#60a5fa', '#fbbf24', '#fb923c'];
  const maxSim = topConnections[0]?.similarity || 1;
  return topConnections.map((conn, i) => ({
    aIco: (conn.from_label[0] || 'A').toUpperCase(),
    aColor: colors[i % colors.length],
    a: conn.from_label,
    bIco: (conn.to_label[0] || 'B').toUpperCase(),
    bColor: colors[(i + 2) % colors.length],
    b: conn.to_label,
    count: Math.round(conn.similarity * 100),
    w: `${Math.round((conn.similarity / maxSim) * 100)}%`,
  }));
}

function buildGraphNodes(nodes) {
  const clusterTotals = {};
  nodes.forEach((n) => {
    const c = n.source_type || 'default';
    clusterTotals[c] = (clusterTotals[c] || 0) + 1;
  });
  const clusterIdx = {};
  return nodes.map((node) => {
    const c = node.source_type || 'default';
    const idx = clusterIdx[c] || 0;
    clusterIdx[c] = idx + 1;
    const total = clusterTotals[c];
    const pos = CLUSTER_POS[c] || DEFAULT_POS;
    const angle = (idx / total) * Math.PI * 2;
    const r = 0.04 + Math.floor(idx / 10) * 0.03;
    return {
      id: node.id,
      cluster: c,
      color: SRC_COLOR[c] || SRC_COLOR.default,
      x: Math.max(0.03, Math.min(0.97, pos.cx + Math.cos(angle) * r)),
      y: Math.max(0.03, Math.min(0.97, pos.cy + Math.sin(angle) * r * 0.85)),
      size: 4 + Math.min((node.token_count || 100) / 80, 9),
      label: node.label,
      snippet: node.snippet,
      source_type: node.source_type,
      source_title: node.source_title,
      source_path: node.source_path,
      chunk_index: node.chunk_index,
      token_count: node.token_count,
    };
  });
}

export default function useGuardianData() {
  const [data, setData] = useState(DATA);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    Promise.all([fetchStats(), fetchNodes(), fetchEdges()])
      .then(([stats, nodes, edges]) => {
        const graphNodes = buildGraphNodes(nodes);
        const growth = stats.growth_30d.map((p, i) => ({ day: i, value: p.value }));
        setData({
          ...DATA,
          stats: buildStats(stats, stats.growth_30d),
          timeline: buildTimeline(stats.recent_sources),
          topics: buildTopics(stats.source_type_counts),
          graphNodes,
          growth,
          connections: buildConnections(stats.top_connections),
          _edgeCount: edges.length,
          _sourceCount: stats.total_sources,
        });
        setLoading(false);
      })
      .catch((e) => {
        console.warn('[Guardian] API unavailable, showing demo data:', e.message);
        setError(e);
        setLoading(false);
      });
  }, []);

  return { data, loading, error };
}
