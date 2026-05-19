export const DATA = {
  stats: [
    { key: 'total', icon: 'doc', label: '총 기억', value: 3842, delta: '+128 오늘', deltaCls: 'up', spark: [12, 14, 18, 22, 20, 26, 30, 28, 32, 40, 44, 42, 50, 58, 62, 68, 72, 80, 88, 96, 104, 112, 128, 124, 138, 140, 148, 160, 164, 172], hue: 'pink' },
    { key: 'edges', icon: 'link', label: '연결된 기억', value: 12456, delta: '+312 오늘', deltaCls: 'up', spark: [40, 45, 48, 52, 55, 60, 68, 72, 78, 85, 92, 98, 108, 118, 128, 140, 154, 168, 180, 196, 212, 228, 244, 260, 278, 290, 302, 314, 328, 340], hue: 'primary' },
    { key: 'topics', icon: 'tag', label: '주요 주제', value: 28, delta: '+2 오늘', deltaCls: 'up', spark: [12, 12, 13, 13, 14, 14, 15, 16, 16, 17, 18, 18, 19, 20, 20, 21, 21, 22, 23, 23, 24, 24, 25, 25, 26, 26, 27, 27, 28, 28], hue: 'green' },
    { key: 'activity', icon: 'clock', label: '최근 활동', value: '6.7h', delta: '+1.3h 오늘', deltaCls: 'up', spark: [2, 3, 4, 3, 5, 6, 4, 7, 5, 8, 6, 9, 7, 4, 5, 8, 9, 6, 7, 8, 5, 9, 6, 7, 8, 6, 8, 7, 6.7, 7], hue: 'cyan' },
    { key: 'streak', icon: 'flame', label: '연속 활동일', value: 14, delta: '현재 기록', deltaCls: 'flame', spark: [1, 2, 3, 4, 5, 6, 7, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8, 12, 13, 14], hue: 'amber' },
  ],

  timeline: [
    {
      day: '오늘',
      items: [
        { time: '10:42', src: 'claude', text: 'async 데코레이터를 사용한 병렬 처리' },
        { time: '09:15', src: 'obsidian', text: '벡터 DB 업데이트 전략 정리' },
        { time: '08:30', src: 'obsidian', text: 'Memex 논문 읽고 정리' },
      ],
    },
    {
      day: '어제',
      items: [
        { time: '22:14', src: 'claude', text: 'FastAPI 의존성 주입 패턴' },
        { time: '18:47', src: 'claude', text: 'Chroma 메타데이터 필터링' },
        { time: '17:02', src: 'obsidian', text: '지식 그래프 시각화 아이디어' },
        { time: '14:30', src: 'checkpoint', text: 'session: angel-recall-tuning' },
      ],
    },
  ],

  topics: [
    { id: 'ai', label: 'AI\n개발 도구', count: 128, r: 64, cx: 0.50, cy: 0.50, color: '#a78bfa' },
    { id: 'async', label: '비동기\n프로그래밍', count: 96, r: 54, cx: 0.20, cy: 0.32, color: '#f472b6' },
    { id: 'vec', label: '벡터 DB\n& 임베딩', count: 87, r: 52, cx: 0.82, cy: 0.30, color: '#34d399' },
    { id: 'prompt', label: '프롬프트\n엔지니어링', count: 74, r: 46, cx: 0.22, cy: 0.74, color: '#60a5fa' },
    { id: 'graph', label: '지식 그래프\n구현', count: 65, r: 42, cx: 0.78, cy: 0.74, color: '#fbbf24' },
    { id: 'mini1', label: 'RAG', count: 32, r: 22, cx: 0.50, cy: 0.16, color: '#c084fc' },
    { id: 'mini2', label: 'D3.js', count: 18, r: 18, cx: 0.66, cy: 0.86, color: '#fb923c' },
    { id: 'mini3', label: 'Hooks', count: 14, r: 16, cx: 0.36, cy: 0.92, color: '#22d3ee' },
  ],

  recalls: [
    { ico: 'F', color: '#fb923c', title: 'FastAPI 의존성 주입 패턴', when: '어제 22:14', count: '상기 3회' },
    { ico: 'C', color: '#a78bfa', title: 'Chroma 메타데이터 필터링', when: '어제 18:47', count: '상기 2회' },
    { ico: 'A', color: '#f472b6', title: 'async 데코레이터 패턴', when: '오늘 10:42', count: '상기 2회' },
    { ico: 'V', color: '#34d399', title: '벡터 검색 성능 최적화', when: '2일 전 21:33', count: '상기 1회' },
    { ico: 'G', color: '#fbbf24', title: '그래프 레이아웃 알고리즘', when: '3일 전 16:11', count: '상기 1회' },
  ],

  growth: (() => {
    const pts = [];
    let v = 380;
    for (let i = 0; i < 30; i += 1) {
      v += 60 + Math.round(Math.sin(i / 3) * 30) + Math.round(Math.random() * 60);
      pts.push({ day: i, value: Math.min(3842, v + i * 80) });
    }
    pts[pts.length - 1].value = 3842;
    return pts;
  })(),

  connections: [
    { aIco: 'A', aColor: '#f472b6', a: 'async 데코레이터 패턴', bIco: 'P', bColor: '#a78bfa', b: '병렬 처리 최적화', count: 24, w: '100%' },
    { aIco: 'V', aColor: '#34d399', a: '벡터 임베딩 모델 비교', bIco: 'E', bColor: '#fbbf24', b: '임베딩 성능 평가', count: 18, w: '76%' },
    { aIco: 'P', aColor: '#60a5fa', a: '프롬프트 템플릿 설계', bIco: 'C', bColor: '#fb923c', b: 'Claude 프롬프트 최적화', count: 15, w: '62%' },
    { aIco: 'G', aColor: '#fbbf24', a: '지식 그래프 스키마 설계', bIco: 'D', bColor: '#c084fc', b: '그래프 시각화 구현', count: 12, w: '50%' },
    { aIco: 'M', aColor: '#a78bfa', a: '메모리 시스템 아키텍처', bIco: 'R', bColor: '#f472b6', b: 'RAG 시스템 구현', count: 11, w: '46%' },
  ],

  angelMessages: {
    watchful: [
      '비슷한 맥락의 기억을 찾았어요 ✨',
      '오늘 14개 기억을 정리했어요',
      "I'm watching over your memories! ✨",
      'async 관련 노트 3개를 새로 연결했어요',
      '구름 위에서 지켜보고 있어요 ☁️',
    ],
    sleepy: [
      '잠시 쉬고 있어요... 💤',
      '낮은 활동이 감지되어 휴면 모드예요',
      '필요할 때 깨워주세요',
    ],
    excited: [
      '오늘 활동이 평소의 2배예요! 🎉',
      '새로운 토픽 클러스터를 발견했어요!',
      '연결이 폭발적으로 늘고 있어요 ✨',
    ],
    off: ['Angel은 꺼져 있어요'],
  },

  recallToast: {
    title: 'async decorators 정리 노트',
    meta: '9 days ago',
    file: 'python-async-notes.md',
    label: 'related memory detected',
  },

  graphNodes: (() => {
    const out = [];
    const clusters = [
      { cx: 0.30, cy: 0.35, color: '#a78bfa', n: 14, key: 'AI' },
      { cx: 0.72, cy: 0.30, color: '#f472b6', n: 11, key: 'async' },
      { cx: 0.62, cy: 0.72, color: '#34d399', n: 10, key: 'vec' },
      { cx: 0.22, cy: 0.78, color: '#fbbf24', n: 8, key: 'graph' },
    ];
    let id = 0;
    clusters.forEach((cluster) => {
      for (let i = 0; i < cluster.n; i += 1) {
        const a = (i / cluster.n) * Math.PI * 2 + Math.random() * 0.5;
        const r = 0.05 + Math.random() * 0.13;
        out.push({
          id: id += 1,
          cluster: cluster.key,
          color: cluster.color,
          x: cluster.cx + Math.cos(a) * r,
          y: cluster.cy + Math.sin(a) * r * 0.85,
          size: 5 + Math.random() * 6,
        });
      }
    });
    return out;
  })(),
};

export default DATA;
