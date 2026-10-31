import graph from './graph.json';
import {hash} from '../lib/ease';

// The film's graph with the papers themselves as nodes (type 6), each linked to what was extracted from it.
// Node record: [x, y, z, type, cluster, size, order, late]; edge: [a, b, kind] (kind 4 = paper → content).
export const WALL_COLS = 40, WALL_ROWS = 22, WALL = WALL_COLS * WALL_ROWS;

const nodes = graph.nodes.map((n) => [...n]);
const edges = graph.edges.map((e) => [...e]);

// Layout: every cluster is a "dandelion" — its hub at the centre, sub-hubs on a shell around it, and each sub-hub's
// leaves fanning outward in a floret. Clusters sit on a flattened sphere; the shared hubs gather at the core.
{
  const K = 1 + Math.max(...nodes.map((n) => n[4]));
  const golden = Math.PI * (3 - Math.sqrt(5));
  const fib = (i, n) => { const y = 1 - (2 * (i + 0.5)) / n, r = Math.sqrt(Math.max(0, 1 - y * y)), a = i * golden; return [Math.cos(a) * r, y, Math.sin(a) * r]; };
  // one cluster at the heart, the rest around it at two depths, so the graph is full rather than a hollow shell
  const centre = Array.from({length: K}, (_, k) => {
    if (k === 0) return [0, 0, 0];
    const j = k - 1, n = K - 1;
    const y = 1 - (2 * (j + 0.5)) / n, r = Math.sqrt(1 - y * y), a = j * golden + 0.6, R = j % 2 ? 11.2 : 8.2;
    return [Math.cos(a) * r * R, y * R * 0.7, Math.sin(a) * r * R];
  });
  const role = nodes.map((n) => (n[5] > 3 ? 'hub' : n[5] > 1.6 ? 'sub' : 'leaf'));
  const parent = new Map();
  edges.forEach(([a, b, k]) => {
    if (k !== 0) return;
    [[a, b], [b, a]].forEach(([x, y]) => {
      if (parent.has(x) || nodes[x][4] !== nodes[y][4] || nodes[x][4] < 0) return;
      if ((role[x] === 'leaf' && role[y] !== 'leaf') || (role[x] === 'sub' && role[y] === 'hub')) parent.set(x, y);
    });
  });
  const kids = new Map();
  parent.forEach((p, c) => { if (!kids.has(p)) kids.set(p, []); kids.get(p).push(c); });
  const add = (a, b, s) => [a[0] + b[0] * s, a[1] + b[1] * s, a[2] + b[2] * s];
  const basis = (w) => {
    const t = Math.abs(w[1]) < 0.9 ? [0, 1, 0] : [1, 0, 0];
    let u = [w[1] * t[2] - w[2] * t[1], w[2] * t[0] - w[0] * t[2], w[0] * t[1] - w[1] * t[0]];
    const l = Math.hypot(...u); u = u.map((v) => v / l);
    return [u, [w[1] * u[2] - w[2] * u[1], w[2] * u[0] - w[0] * u[2], w[0] * u[1] - w[1] * u[0]]];
  };
  // leaves fan out in a cone around their parent's outward direction, layered by type:
  // findings nearest the stem, methods in between, context at the tips
  const LAYER = {1: 0.6, 4: 0.8, 2: 1, 3: 1, 5: 1, 0: 0.9};
  const floret = (origin, w, list, R, cone) => {
    const [u, v] = basis(w), m = list.length, c0 = Math.cos(cone);
    list.forEach((i, q) => {
      const ct = 1 - ((q + 0.5) / m) * (1 - c0), st = Math.sqrt(1 - ct * ct), ph = q * golden;
      const d = [0, 1, 2].map((k) => u[k] * st * Math.cos(ph) + v[k] * st * Math.sin(ph) + w[k] * ct);
      const p = add(origin, d, R * (LAYER[nodes[i][3]] ?? 1) * (0.9 + 0.22 * hash(i * 3.71)) * (0.8 + 0.3 * ct));
      nodes[i][0] = +p[0].toFixed(3); nodes[i][1] = +p[1].toFixed(3); nodes[i][2] = +p[2].toFixed(3);
    });
  };
  const spin = (d, k) => { const a = hash(k * 7.3) * 6.28, b = hash(k * 3.1) * 6.28;
    const x1 = d[0] * Math.cos(a) - d[2] * Math.sin(a), z1 = d[0] * Math.sin(a) + d[2] * Math.cos(a);
    return [x1, d[1] * Math.cos(b) - z1 * Math.sin(b), d[1] * Math.sin(b) + z1 * Math.cos(b)]; };
  nodes.forEach((n, h) => {
    if (role[h] !== 'hub' || n[4] < 0) return;
    const C = centre[n[4]];
    n[0] = C[0]; n[1] = C[1]; n[2] = C[2];
    const ch = kids.get(h) || [];
    const subs = ch.filter((i) => role[i] === 'sub'), direct = ch.filter((i) => role[i] === 'leaf');
    subs.forEach((sIdx, j) => {
      const d = spin(fib(j, subs.length), n[4]);
      const S = add(C, d, 2.0);
      nodes[sIdx][0] = +S[0].toFixed(3); nodes[sIdx][1] = +S[1].toFixed(3); nodes[sIdx][2] = +S[2].toFixed(3);
      floret(S, d, kids.get(sIdx) || [], 1.5, 0.95);
    });
    floret(C, spin([0, 1, 0], n[4] + 5), direct, 1.2, Math.PI);
  });
  // the shared hubs (and anything unattached) gather near the core
  nodes.forEach((n, i) => {
    if (n[4] < 0) { const d = fib(i % 8, 8); n[0] = d[0] * 1.6; n[1] = d[1] * 1.6; n[2] = d[2] * 1.6; n[5] = Math.min(n[5], 1.5); }
    else if (role[i] !== 'hub' && !parent.has(i) && !(kids.get(i) || []).length) { const C = centre[n[4]]; n[0] = C[0] + (hash(i) - 0.5) * 3; n[1] = C[1] + (hash(i * 2) - 0.5) * 3; n[2] = C[2] + (hash(i * 3) - 0.5) * 3; }
  });
}

const centroid = (ids) => {
  const c = [0, 0, 0];
  ids.forEach((i) => { c[0] += nodes[i][0]; c[1] += nodes[i][1]; c[2] += nodes[i][2]; });
  return c.map((v) => v / Math.max(1, ids.length));
};

const byCluster = (late) => {
  const out = {};
  graph.nodes.forEach((n, i) => { if (!!n[7] !== late || n[4] < 0) return; (out[n[4]] ||= []).push(i); });
  return out;
};

// chunk each cluster's nodes, ordered around the cluster, into papers
const chunkPapers = (groups, total) => {
  const all = Object.values(groups).reduce((s, g) => s + g.length, 0);
  const keys = Object.keys(groups);
  let assigned = 0;
  const out = [];
  keys.forEach((k, idx) => {
    const ids = groups[k];
    const cc = centroid(ids);
    ids.sort((a, b) => Math.atan2(nodes[a][2] - cc[2], nodes[a][0] - cc[0]) - Math.atan2(nodes[b][2] - cc[2], nodes[b][0] - cc[0]));
    const g = idx === keys.length - 1 ? total - assigned : Math.round((ids.length / all) * total);
    assigned += g;
    for (let q = 0; q < g; q++) {
      const a = Math.floor((q * ids.length) / g), b = Math.floor(((q + 1) * ids.length) / g);
      out.push({members: ids.slice(a, b), cluster: +k});
    }
  });
  return out;
};

const wallPapers = chunkPapers(byCluster(false), WALL);
const lateGroups = byCluster(true);
const latePapers = chunkPapers(lateGroups, Math.round(Object.values(lateGroups).reduce((s, g) => s + g.length, 0) / 7)); // ~7 pieces each

const addPaper = (p, late) => {
  const c = centroid(p.members);
  const ids = graph.nodes.map((n, i) => i).filter((i) => graph.nodes[i][4] === p.cluster);
  const cc = centroid(ids);
  const d = [c[0] - cc[0], c[1] - cc[1], c[2] - cc[2]];
  const L = Math.hypot(...d) || 1;
  const pos = cc.map((v, k) => v + (d[k] / L) * (4.3 + hash(nodes.length * 1.7) * 0.5) + (hash(nodes.length * 3.1 + k) - 0.5) * 0.3);
  p.node = nodes.length;
  nodes.push([+pos[0].toFixed(3), +pos[1].toFixed(3), +pos[2].toFixed(3), 6, p.cluster, 0.85, 0, late ? 1 : 0]);
  p.members.forEach((m) => edges.push([p.node, m, 4]));
};
wallPapers.forEach((p) => addPaper(p, false));
latePapers.forEach((p) => addPaper(p, true));

// clusters ranked left to right as the Act II camera sees the living graph, so a colour ramp can flow across it
export const CLUSTER_RANK = (() => {
  const K = 1 + Math.max(...graph.nodes.map((n) => n[4]));
  const a = 0.25, GPz = -9, P = [-12, 7, 19], L = [7.46, 0.3, -6.1];
  const Fw = L.map((v, k) => v - P[k]), fl = Math.hypot(...Fw); Fw.forEach((v, k) => { Fw[k] = v / fl; });
  const Rt = [-Fw[2], 0, Fw[0]], rl = Math.hypot(...Rt); Rt.forEach((v, k) => { Rt[k] = v / rl; });
  const key = Array.from({length: K}, (_, k) => {
    const ids = nodes.map((n, i) => i).filter((i) => nodes[i][4] === k);
    const c = [0, 1, 2].map((j) => ids.reduce((s2, i) => s2 + nodes[i][j], 0) / Math.max(1, ids.length));
    const w = [c[0] * Math.cos(a) + c[2] * Math.sin(a), c[1], -c[0] * Math.sin(a) + c[2] * Math.cos(a) + GPz];
    const d = w.map((v, j) => v - P[j]);
    const z = d[0] * Fw[0] + d[1] * Fw[1] + d[2] * Fw[2];
    return (d[0] * Rt[0] + d[2] * Rt[2]) / Math.max(1, z); // screen x (perspective)
  });
  const order = key.map((v, k) => k).sort((p, q) => key[p] - key[q]);
  const rank = new Array(K);
  order.forEach((k, r) => { rank[k] = r / Math.max(1, K - 1); });
  return rank;
})();

// shuffle the wall so neighbouring pages come from different corners of the graph
const wallOrder = wallPapers.map((p, i) => i).sort((a, b) => hash(a * 5.17 + 1) - hash(b * 5.17 + 1));
export const EXT = {nodes, edges, topics: graph.topics, globals: graph.globals, N0: graph.nodes.length,
  wallPapers: wallOrder.map((i) => wallPapers[i]), latePapers};
