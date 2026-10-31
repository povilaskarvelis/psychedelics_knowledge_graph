// Deterministic 3D layout for the film's illustrative knowledge graph.
import {forceSimulation, forceLink, forceManyBody, forceX, forceY, forceZ} from 'd3-force-3d';
import fs from 'node:fs';

let s = 20260927;
const R = () => { s |= 0; s = (s + 0x6d2b79f5) | 0; let t = Math.imul(s ^ (s >>> 15), 1 | s); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
const pick = (arr) => arr[Math.floor(R() * arr.length)];
const TYPE = {concept: 0, finding: 1, intervention: 2, population: 3, method: 4, outcome: 5};
const leafTypes = [...Array(50).fill(1), ...Array(13).fill(5), ...Array(13).fill(2), ...Array(12).fill(3), ...Array(12).fill(4)];

const K = 10, SUB = 7, LEAF = 230, GLOBAL_METHODS = 8;
const nodes = [], links = [];
const add = (n) => { n.id = nodes.length; nodes.push(n); return n.id; };

// cluster centres on a wide, shallow ellipsoid
const centres = [];
for (let k = 0; k < K; k++) {
  const a = (k / K) * Math.PI * 2 + R() * 0.4;
  const r = 19 + R() * 6;
  centres.push([Math.cos(a) * r * 1.3, (R() - 0.5) * 16, Math.sin(a) * r * 0.95]);
}

const topics = [], subs = [];
for (let k = 0; k < K; k++) {
  const t = add({type: TYPE.concept, cluster: k, size: 3.2, hub: 2});
  topics.push(t);
  subs[k] = [];
  for (let j = 0; j < SUB; j++) {
    const id = add({type: pick([2, 5, 3, 4, 2, 5]), cluster: k, size: 1.9 + R() * 0.5, hub: 1});
    subs[k].push(id);
    links.push({source: id, target: t, kind: 0, dist: 3});
  }
}
const globals = [];
for (let g = 0; g < GLOBAL_METHODS; g++) {
  globals.push(add({type: TYPE.method, cluster: -1, size: 2.3, hub: 1}));
}
for (let k = 0; k < K; k++) {
  const leaves = [];
  for (let j = 0; j < LEAF; j++) {
    const type = pick(leafTypes);
    const id = add({type, cluster: k, size: 0.55 + R() * 0.5, hub: 0});
    leaves.push(id);
    links.push({source: id, target: R() < 0.8 ? pick(subs[k]) : topics[k], kind: 0, dist: 1.3});
    if (type === TYPE.finding) {
      if (R() < 0.05) links.push({source: id, target: pick(subs[(k + (R() < 0.5 ? 1 : K - 1)) % K]), kind: 1, dist: 6});
      if (R() < 0.03) links.push({source: id, target: pick(globals), kind: 1, dist: 6});
    }
  }
  // findings connect to entity leaves of the same cluster (the extracted structure)
  leaves.forEach((id) => {
    if (nodes[id].type !== TYPE.finding) return;
    const n = 1 + Math.floor(R() * 2);
    for (let q = 0; q < n; q++) {
      const other = pick(leaves);
      if (other !== id && nodes[other].type !== TYPE.finding) links.push({source: id, target: other, kind: 0, dist: 0.9});
    }
  });
}
// backbone between neighbouring topics
for (let k = 0; k < K; k++) {
  links.push({source: topics[k], target: topics[(k + 1) % K], kind: 2, dist: 12});
  if (k % 3 === 0) links.push({source: topics[k], target: topics[(k + 4) % K], kind: 2, dist: 16});
}

nodes.forEach((n) => {
  const c = n.cluster >= 0 ? centres[n.cluster] : [0, 0, 0];
  n.x = c[0] + (R() - 0.5) * 4; n.y = c[1] + (R() - 0.5) * 4; n.z = c[2] + (R() - 0.5) * 4;
});

const sim = forceSimulation(nodes, 3)
  .force('link', forceLink(links).id((d) => d.id).distance((l) => l.dist).strength((l) => (l.kind === 0 ? 0.7 : 0.06)))
  .force('charge', forceManyBody().strength((d) => (d.hub === 2 ? -30 : d.hub === 1 ? -10 : -1.6)).distanceMax(7))
  .force('x', forceX((d) => (d.cluster >= 0 ? centres[d.cluster][0] : 0)).strength((d) => (d.cluster >= 0 ? 0.09 : 0.01)))
  .force('y', forceY((d) => (d.cluster >= 0 ? centres[d.cluster][1] : 0)).strength((d) => (d.cluster >= 0 ? 0.09 : 0.01)))
  .force('z', forceZ((d) => (d.cluster >= 0 ? centres[d.cluster][2] : 0)).strength((d) => (d.cluster >= 0 ? 0.09 : 0.01)))
  .stop();
for (let i = 0; i < 500; i++) sim.tick();

// centre and normalise
const m = [0, 0, 0];
nodes.forEach((n) => { m[0] += n.x; m[1] += n.y; m[2] += n.z; });
m.forEach((v, i) => (m[i] = v / nodes.length));
let maxR = 0;
nodes.forEach((n) => { n.x -= m[0]; n.y -= m[1]; n.z -= m[2]; maxR = Math.max(maxR, Math.hypot(n.x, n.y, n.z)); });
const scale = 14 / maxR;

// assembly order: hubs first; ~12% of leaves arrive later ("living" updates)
const out = {
  nodes: nodes.map((n) => {
    const late = n.hub === 0 && R() < 0.12 ? 1 : 0;
    const order = n.hub ? R() * 0.25 : 0.1 + R() * 0.9;
    return [+(n.x * scale).toFixed(3), +(n.y * scale).toFixed(3), +(n.z * scale).toFixed(3), n.type, n.cluster, +n.size.toFixed(2), +order.toFixed(4), late];
  }),
  edges: links.map((l) => [l.source.id, l.target.id, l.kind]),
  topics,
  globals,
};
fs.writeFileSync(new URL('../src/data/graph.json', import.meta.url), JSON.stringify(out));
console.log('nodes', out.nodes.length, 'edges', out.edges.length, 'late', out.nodes.filter((n) => n[7]).length);
