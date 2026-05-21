async function get(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

export const fetchStats = () => get('/graph/stats');
export const fetchNodes = () => get('/graph/nodes');
export const fetchEdges = () => get('/graph/edges');
