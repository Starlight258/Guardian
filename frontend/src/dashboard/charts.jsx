import { useEffect, useMemo, useRef, useState } from 'react';

export function SparkBars({ data, hue = 'primary' }) {
  const max = Math.max(...data);
  const colorMap = {
    primary: '#a78bfa',
    pink: '#f472b6',
    green: '#4ade80',
    amber: '#fbbf24',
    cyan: '#60a5fa',
  };
  const color = colorMap[hue] || colorMap.primary;
  return (
    <svg className="stat-spark" viewBox={`0 0 ${data.length * 4} 32`} preserveAspectRatio="none">
      {data.map((v, i) => {
        const h = Math.max(2, (v / max) * 28);
        const opacity = 0.3 + 0.7 * (i / data.length);
        return (
          <rect
            key={i}
            x={i * 4 + 0.6}
            y={32 - h}
            width={2.8}
            height={h}
            fill={color}
            opacity={opacity}
            rx={0.5}
          />
        );
      })}
    </svg>
  );
}

export function BubbleCluster({ topics, onSelect }) {
  const stageRef = useRef(null);
  const [size, setSize] = useState({ w: 320, h: 290 });
  const [hover, setHover] = useState(null);

  useEffect(() => {
    if (!stageRef.current) return undefined;
    const ro = new ResizeObserver((entries) => {
      const r = entries[0].contentRect;
      setSize({ w: r.width, h: r.height });
    });
    ro.observe(stageRef.current);
    return () => ro.disconnect();
  }, []);

  return (
    <div className="topic-stage" ref={stageRef}>
      <svg className="topic-svg" viewBox={`0 0 ${size.w} ${size.h}`}>
        <defs>
          {topics.map((t) => (
            <radialGradient key={t.id} id={`bg-${t.id}`} cx="0.35" cy="0.35" r="0.7">
              <stop offset="0%" stopColor={t.color} stopOpacity="0.75" />
              <stop offset="60%" stopColor={t.color} stopOpacity="0.35" />
              <stop offset="100%" stopColor={t.color} stopOpacity="0.1" />
            </radialGradient>
          ))}
        </defs>
        {topics.map((t) => {
          const cx = t.cx * size.w;
          const cy = t.cy * size.h;
          const lines = t.label.split('\n');
          const labelDy = -8 - (lines.length - 1) * 7;
          return (
            <g
              key={t.id}
              className="topic-bubble"
              onMouseEnter={() => setHover(t.id)}
              onMouseLeave={() => setHover(null)}
              onClick={() => onSelect && onSelect(t)}
            >
              <circle cx={cx} cy={cy} r={t.r + 6} fill={t.color} opacity="0.08" />
              <circle
                cx={cx}
                cy={cy}
                r={t.r}
                fill={`url(#bg-${t.id})`}
                stroke={t.color}
                strokeWidth={hover === t.id ? 1.5 : 1}
                strokeOpacity="0.6"
              />
              {lines.map((line, i) => (
                <text key={i} x={cx} y={cy + labelDy + i * 14} className="topic-bubble-label">{line}</text>
              ))}
              <text x={cx} y={cy + labelDy + lines.length * 14 + 4} className="topic-bubble-count">{t.count}</text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

export function GrowthLine({ points, range = 30 }) {
  const wrapRef = useRef(null);
  const [size, setSize] = useState({ w: 560, h: 260 });
  const [hoverIdx, setHoverIdx] = useState(null);

  useEffect(() => {
    if (!wrapRef.current) return undefined;
    const ro = new ResizeObserver((entries) => {
      const r = entries[0].contentRect;
      setSize({ w: r.width, h: r.height });
    });
    ro.observe(wrapRef.current);
    return () => ro.disconnect();
  }, []);

  const pad = { l: 44, r: 16, t: 18, b: 30 };
  const innerW = size.w - pad.l - pad.r;
  const innerH = size.h - pad.t - pad.b;
  const data = points.slice(-range);
  const maxV = 4000;
  const minV = 0;

  const px = (i) => pad.l + (i / (data.length - 1)) * innerW;
  const py = (v) => pad.t + (1 - (v - minV) / (maxV - minV)) * innerH;

  const pathD = useMemo(
    () => data.map((p, i) => `${i === 0 ? 'M' : 'L'} ${px(i)} ${py(p.value)}`).join(' '),
    [data, size],
  );
  const areaD = `${pathD} L ${px(data.length - 1)} ${pad.t + innerH} L ${px(0)} ${pad.t + innerH} Z`;

  const xLabels = [0, 7, 14, 21, 28].filter((i) => i < data.length);
  const xLabelText = ['May 5', 'May 12', 'May 19', 'May 26', 'Jun 2'];
  const yTicks = [0, 1000, 2000, 3000, 4000];

  const hoverPoint = hoverIdx != null ? data[hoverIdx] : null;
  const hoverX = hoverIdx != null ? px(hoverIdx) : 0;
  const hoverY = hoverPoint ? py(hoverPoint.value) : 0;

  return (
    <div className="growth-stage" ref={wrapRef}>
      <svg className="growth-svg" viewBox={`0 0 ${size.w} ${size.h}`} preserveAspectRatio="none">
        <defs>
          <linearGradient id="growthGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#a78bfa" stopOpacity="0.32" />
            <stop offset="100%" stopColor="#a78bfa" stopOpacity="0" />
          </linearGradient>
        </defs>
        {yTicks.map((v) => (
          <g key={v}>
            <line className="growth-grid" x1={pad.l} x2={size.w - pad.r} y1={py(v)} y2={py(v)} />
            <text className="growth-axis" x={pad.l - 8} y={py(v) + 4} textAnchor="end">{v === 0 ? '0' : v >= 1000 ? `${v / 1000}K` : v}</text>
          </g>
        ))}
        <path className="growth-area" d={areaD} />
        <path className="growth-line" d={pathD} />
        {data.map((p, i) => (
          <circle
            key={i}
            className="growth-dot"
            cx={px(i)}
            cy={py(p.value)}
            r={i === hoverIdx ? 5 : 3.5}
            onMouseEnter={() => setHoverIdx(i)}
            onMouseLeave={() => setHoverIdx(null)}
          />
        ))}
        {xLabels.map((i, idx) => (
          <text key={i} className="growth-axis" x={px(i)} y={pad.t + innerH + 18} textAnchor="middle">{xLabelText[idx]}</text>
        ))}
        {hoverPoint && <line x1={hoverX} x2={hoverX} y1={pad.t} y2={pad.t + innerH} stroke="#a78bfa" strokeOpacity="0.35" strokeDasharray="2 2" />}
      </svg>
      {hoverPoint && (
        <div className="growth-tooltip" style={{ left: hoverX, top: hoverY - 12 }}>
          <div>{hoverPoint.value.toLocaleString()} 기억</div>
          <div className="growth-tooltip-day">day {hoverIdx + 1} / {data.length}</div>
        </div>
      )}
    </div>
  );
}

export function MemoryGraphCanvas({ nodes, selectedId, onSelect }) {
  const wrapRef = useRef(null);
  const [size, setSize] = useState({ w: 800, h: 600 });

  useEffect(() => {
    if (!wrapRef.current) return undefined;
    const ro = new ResizeObserver((entries) => {
      const r = entries[0].contentRect;
      setSize({ w: r.width, h: r.height });
    });
    ro.observe(wrapRef.current);
    return () => ro.disconnect();
  }, []);

  const positionedNodes = useMemo(
    () => nodes.map((n) => ({
      ...n,
      px: n.x * size.w,
      py: n.y * size.h,
    })),
    [nodes, size],
  );

  const links = useMemo(() => {
    const out = [];
    positionedNodes.forEach((a, i) => {
      positionedNodes.forEach((b, j) => {
        if (i >= j) return;
        const dx = a.px - b.px;
        const dy = a.py - b.py;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (a.cluster === b.cluster && dist < 110) out.push({ s: i, t: j, d: dist, intra: true });
        else if (a.cluster !== b.cluster && dist < 220 && Math.random() < 0.04) out.push({ s: i, t: j, d: dist, intra: false });
      });
    });
    return out;
  }, [positionedNodes]);

  return (
    <div ref={wrapRef} style={{ width: '100%', height: '100%' }}>
      <svg viewBox={`0 0 ${size.w} ${size.h}`}>
        {links.map((l, i) => {
          const a = positionedNodes[l.s];
          const b = positionedNodes[l.t];
          const isHl = selectedId != null && (a.id === selectedId || b.id === selectedId);
          return (
            <line
              key={i}
              className={`graph-link ${isHl ? 'hl' : ''}`}
              x1={a.px}
              y1={a.py}
              x2={b.px}
              y2={b.py}
              strokeWidth={l.intra ? 1 : 0.6}
            />
          );
        })}
        {positionedNodes.map((n) => (
          <circle
            key={n.id}
            className="graph-node"
            cx={n.px}
            cy={n.py}
            r={n.id === selectedId ? n.size + 3 : n.size}
            fill={n.color}
            stroke={n.id === selectedId ? '#fff' : 'rgba(255,255,255,0.15)'}
            strokeWidth={n.id === selectedId ? 2 : 1}
            onClick={() => onSelect && onSelect(n)}
          />
        ))}
      </svg>
    </div>
  );
}
