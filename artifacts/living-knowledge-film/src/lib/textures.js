import * as THREE from 'three';
import {rng} from './ease';

// Procedural journal pages. All drawing is deterministic.

const PAPER = '#efebe3';
const INK = '#2e3338';
const INK_SOFT = '#6c7277';
const FIG = ['#90baff', '#f1b74b', '#6ee3d7', '#f080a3', '#a7be73'];

export const ATLAS_COLS = 4;
export const ATLAS_ROWS = 3;
export const PAPER_ASPECT = 0.772; // width / height (US letter)

// lines of text as bars. With a recorder (`rec`), each line is split into words (with their own random stream, so a
// page keeps the same layout at any resolution) and its rectangle is kept for highlighter marks.
const bars = (ctx, r, x, y, w, lines, lh, h, color, ragged = 0.35, rec = null, region = '') => {
  ctx.fillStyle = color;
  for (let i = 0; i < lines; i++) {
    const last = i === lines - 1;
    const ww = last ? w * (0.25 + r() * 0.5) : w * (1 - r() * ragged * 0.25);
    if (rec) {
      const words = [];
      const heavy = h > rec.W * 0.02; // title bars: fewer, longer words
      let wx = x;
      while (x + ww - wx > h * 1.6) {
        const want = heavy ? rec.W * (0.05 + rec.wr() * 0.1) : rec.W * (0.022 + rec.wr() * 0.06);
        const len = Math.min(Math.max(want, h * 1.6), x + ww - wx);
        words.push([wx, len]);
        wx += len + (heavy ? h * 0.55 : h * 0.95);
      }
      words.forEach(([wx0, len]) => { ctx.beginPath(); ctx.roundRect(wx0, y + i * lh, len, h, h * 0.32); ctx.fill(); });
      rec.lines.push({x, y: y + i * lh, w: words.length ? words[words.length - 1][0] + words[words.length - 1][1] - x : ww, h, region, words});
    } else {
      ctx.fillRect(x, y + i * lh, ww, h);
    }
  }
  return y + lines * lh;
};

const drawGenericPage = (ctx, ox, oy, W, H, seed, rec = null, opt = {}) => {
  const r = rng(seed);
  const k = W / 512; // pixel constants were set for a 512-px page
  ctx.save();
  ctx.translate(ox, oy);
  ctx.fillStyle = PAPER;
  ctx.fillRect(0, 0, W, H);
  const m = W * 0.08;
  // header rule
  ctx.fillStyle = INK_SOFT;
  ctx.fillRect(m, m * 0.7, W * 0.28, H * 0.006);
  ctx.fillRect(W - m - W * 0.12, m * 0.7, W * 0.12, H * 0.006);
  ctx.fillStyle = opt.rule ?? FIG[seed % FIG.length];
  ctx.globalAlpha = 0.85;
  ctx.fillRect(m, m * 0.7 + H * 0.014, W - 2 * m, H * 0.003);
  ctx.globalAlpha = 1;
  // title
  let y = m * 1.35;
  const titleLines = opt.titleLines ?? 1 + Math.floor(r() * 2) + 1;
  y = bars(ctx, r, m, y, W - 2 * m, titleLines, H * 0.034, H * 0.022, INK, 0.9, rec, 'title');
  y += H * 0.012;
  y = bars(ctx, r, m, y, W * 0.6, 1, H * 0.02, H * 0.009, INK_SOFT, 0.5, rec, 'authors');
  y += H * 0.02;
  // abstract box
  ctx.fillStyle = 'rgba(46,51,56,0.06)';
  const absLines = 5 + Math.floor(r() * 3);
  ctx.fillRect(m - 6 * k, y - 8 * k, W - 2 * m + 12 * k, absLines * H * 0.017 + 16 * k);
  y = bars(ctx, r, m, y, W - 2 * m, absLines, H * 0.017, H * 0.0075, INK_SOFT, 0.2, rec, 'abstract');
  y += H * 0.025;
  // two columns
  const colW = (W - 2 * m - W * 0.04) / 2;
  const figCol = Math.floor(r() * 2);
  const figAt = r();
  let figDone = false;
  for (let c = 0; c < 2; c++) {
    let cy = y;
    const cx = m + c * (colW + W * 0.04);
    while (cy < H - m) {
      if (c === figCol && cy > y + (H - y) * figAt * 0.5 && cy < H - m - H * 0.2 && !figDone) {
        figDone = true;
        const fh = H * (0.12 + r() * 0.06);
        const kind = opt.figure?.kind ?? Math.floor(r() * 3);
        if (rec) rec.figure = {kind, x: cx, y: cy, w: colW, h: fh};
        ctx.strokeStyle = 'rgba(46,51,56,0.35)';
        ctx.lineWidth = 1.2 * k;
        ctx.strokeRect(cx, cy, colW, fh);
        const col = opt.figure?.colors?.[1] ?? FIG[Math.floor(r() * FIG.length)];
        if (kind === 0) {
          const n = 7;
          for (let i = 0; i < n; i++) {
            const bh = fh * (0.2 + r() * 0.65);
            ctx.fillStyle = i % 2 ? col : opt.figure?.colors?.[0] ?? FIG[(seed + 2) % FIG.length];
            ctx.fillRect(cx + 8 * k + i * ((colW - 16 * k) / n), cy + fh - 6 * k - bh, (colW - 16 * k) / n - 4 * k, bh);
          }
        } else if (kind === 1) {
          ctx.strokeStyle = col;
          ctx.lineWidth = 2.2 * k;
          ctx.beginPath();
          let v = fh * 0.7;
          for (let i = 0; i <= 20; i++) {
            v += (r() - 0.62) * fh * 0.08;
            const px = cx + 8 * k + (i / 20) * (colW - 16 * k);
            if (i === 0) ctx.moveTo(px, cy + v); else ctx.lineTo(px, cy + Math.max(8 * k, v));
          }
          ctx.stroke();
        } else {
          for (let i = 0; i < 26; i++) {
            ctx.fillStyle = FIG[Math.floor(r() * FIG.length)];
            ctx.beginPath();
            ctx.arc(cx + 10 * k + r() * (colW - 20 * k), cy + 10 * k + r() * (fh - 20 * k), (2 + r() * 2.2) * k, 0, Math.PI * 2);
            ctx.fill();
          }
        }
        cy += fh + H * 0.012;
        cy = bars(ctx, r, cx, cy, colW, 2, H * 0.013, H * 0.0055, INK_SOFT, 0.3, rec, 'caption') + H * 0.014;
        continue;
      }
      const para = 3 + Math.floor(r() * 7);
      const remain = Math.floor((H - m - cy) / (H * 0.0155));
      const n = Math.min(para, remain);
      if (n <= 0) break;
      cy = bars(ctx, r, cx, cy, colW, n, H * 0.0155, H * 0.0062, 'rgba(46,51,56,0.62)', 0.12, rec, 'body') + H * 0.01;
    }
  }
  ctx.restore();
};

let atlas;
export const paperAtlas = () => {
  if (atlas) return atlas;
  const cw = 512, ch = Math.round(512 / PAPER_ASPECT);
  const cv = document.createElement('canvas');
  cv.width = cw * ATLAS_COLS;
  cv.height = ch * ATLAS_ROWS;
  const ctx = cv.getContext('2d');
  for (let i = 0; i < ATLAS_COLS * ATLAS_ROWS; i++) {
    drawGenericPage(ctx, (i % ATLAS_COLS) * cw, Math.floor(i / ATLAS_COLS) * ch, cw, ch, 101 + i * 17);
  }
  atlas = new THREE.CanvasTexture(cv);
  atlas.colorSpace = THREE.SRGBColorSpace;
  atlas.anisotropy = 8;
  atlas.generateMipmaps = true;
  atlas.minFilter = THREE.LinearMipmapLinearFilter;
  return atlas;
};

// ---- A page at full resolution, with highlight segments --------------------------------------------------------
// spec: an atlas variant 0..11 (the same page as in the pile), or a one-off page {seed, titleLines, figure: {kind, colors},
// rule} that appears nowhere in the pile. segs: context / method / finding marks on words in the abstract and the body.
export const atlasSeed = (v) => 101 + v * 17;
const pageCache = new Map();
export const journalPage = (spec, W = 1400) => {
  const one = typeof spec === 'object';
  const seed = one ? spec.seed : atlasSeed(spec);
  const key = `${one ? JSON.stringify(spec) : spec}-${W}`;
  if (pageCache.has(key)) return pageCache.get(key);
  const H = Math.round(W / PAPER_ASPECT);
  const cv = document.createElement('canvas');
  cv.width = W; cv.height = H;
  const ctx = cv.getContext('2d');
  const rec = {W, lines: [], wr: rng(seed * 31 + 7), figure: null};
  drawGenericPage(ctx, 0, 0, W, H, seed, rec, one ? spec : {});
  const tex = new THREE.CanvasTexture(cv);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 16;
  // marks: a run of 2–3 words on a full line, three in the abstract and three in the body
  const pr = rng(seed * 13 + 5);
  const segs = [];
  const pick = (region, type) => {
    const cands = rec.lines.filter((l) => l.region === region && l.words.length >= 6 && !l.used);
    const l = cands[Math.floor(pr() * cands.length)];
    if (!l) return;
    l.used = true;
    const n = 2 + Math.floor(pr() * 2), s0 = 1 + Math.floor(pr() * (l.words.length - n - 1));
    const a = l.words[s0], b = l.words[s0 + n - 1];
    const x0 = a[0] - l.h * 0.35, x1 = b[0] + b[1] + l.h * 0.35, yc = l.y + l.h / 2, hh = l.h * 0.95;
    segs.push({type, u0: x0 / W, u1: x1 / W, v0: 1 - (yc + hh) / H, v1: 1 - (yc - hh) / H});
  };
  ['context', 'method', 'finding'].forEach((t) => pick('abstract', t));
  ['context', 'method', 'finding'].forEach((t) => pick('body', t));
  const out = {tex, segs, W, H, figure: rec.figure};
  pageCache.set(key, out);
  return out;
};
// the variant and figure kind of every atlas page (for choosing pages by their figure)
export const atlasFigures = () => Array.from({length: ATLAS_COLS * ATLAS_ROWS}, (_, v) => journalPage(v, 512).figure);

// ---- A systematic review / meta-analysis: still a paper, but a different kind of page -----------------------
// Gold masthead band, a PRISMA flow of the screening, and a forest plot ending in the pooled diamond.
let reviewTex;
export const reviewPage = () => {
  if (reviewTex) return reviewTex;
  const W = 1200, H = Math.round(W / PAPER_ASPECT);
  const cv = document.createElement('canvas');
  cv.width = W;
  cv.height = H;
  const ctx = cv.getContext('2d');
  const r = rng(4242);
  const GOLD = '#dda441';
  ctx.fillStyle = PAPER;
  ctx.fillRect(0, 0, W, H);
  const m = W * 0.075;
  ctx.fillStyle = GOLD;
  ctx.fillRect(0, 0, W, H * 0.062);
  ctx.fillStyle = '#2b2108';
  ctx.font = `600 ${Math.round(H * 0.024)}px "IBM Plex Mono", ui-monospace, monospace`;
  ctx.textBaseline = 'middle';
  ctx.fillText('SYSTEMATIC REVIEW & META-ANALYSIS', m, H * 0.032);
  let y = H * 0.1;
  y = bars(ctx, r, m, y, W - 2 * m, 2, H * 0.038, H * 0.025, INK, 0.9);
  y += H * 0.008;
  y = bars(ctx, r, m, y, W * 0.55, 1, H * 0.02, H * 0.009, INK_SOFT, 0.5);
  y += H * 0.035;
  const gap = W * 0.06, colW = (W - 2 * m - gap) / 2, top = y;
  // PRISMA flow: records → screened → assessed → included
  const bh = H * 0.062, bg = H * 0.034;
  ctx.lineWidth = 2.4;
  for (let i = 0; i < 4; i++) {
    const bw = colW * (1 - i * 0.14), bx = m + (colW - bw) / 2, by = top + i * (bh + bg);
    ctx.strokeStyle = i === 3 ? GOLD : 'rgba(46,51,56,0.55)';
    ctx.strokeRect(bx, by, bw, bh);
    bars(ctx, r, bx + bw * 0.12, by + bh * 0.3, bw * 0.76, 2, bh * 0.32, bh * 0.13, INK_SOFT, 0.4);
    if (i < 3) {
      const ax = m + colW / 2, a0 = by + bh + 5, a1 = by + bh + bg - 5;
      ctx.strokeStyle = 'rgba(46,51,56,0.55)';
      ctx.beginPath(); ctx.moveTo(ax, a0); ctx.lineTo(ax, a1); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(ax - 8, a1 - 9); ctx.lineTo(ax, a1); ctx.lineTo(ax + 8, a1 - 9); ctx.stroke();
    }
  }
  // forest plot: one row per study, then the pooled estimate
  const px = m + colW + gap, rows = 10, rh = H * 0.027;
  const x0 = px + colW * 0.36, x1 = px + colW, xN = x0 + (x1 - x0) * 0.38;
  ctx.strokeStyle = 'rgba(46,51,56,0.45)';
  ctx.lineWidth = 1.6;
  ctx.setLineDash([7, 7]);
  ctx.beginPath(); ctx.moveTo(xN, top - rh * 0.3); ctx.lineTo(xN, top + (rows + 1.6) * rh); ctx.stroke();
  ctx.setLineDash([]);
  for (let i = 0; i < rows; i++) {
    const cy = top + (i + 0.5) * rh;
    bars(ctx, r, px, cy - rh * 0.12, colW * 0.28, 1, rh, rh * 0.24, INK_SOFT, 0.5);
    const est = xN + (x1 - x0) * (0.05 + r() * 0.34), ci = (x1 - x0) * (0.05 + r() * 0.15);
    ctx.strokeStyle = INK;
    ctx.lineWidth = 2.4;
    ctx.beginPath(); ctx.moveTo(Math.max(x0, est - ci), cy); ctx.lineTo(Math.min(x1, est + ci), cy); ctx.stroke();
    const s = rh * (0.25 + r() * 0.32);
    ctx.fillStyle = INK;
    ctx.fillRect(est - s / 2, cy - s / 2, s, s);
  }
  const dy = top + (rows + 0.9) * rh, dx = xN + (x1 - x0) * 0.22, dw = (x1 - x0) * 0.1;
  ctx.fillStyle = GOLD;
  ctx.beginPath(); ctx.moveTo(dx - dw, dy); ctx.lineTo(dx, dy - rh * 0.46); ctx.lineTo(dx + dw, dy); ctx.lineTo(dx, dy + rh * 0.46); ctx.closePath(); ctx.fill();
  ctx.strokeStyle = 'rgba(46,51,56,0.5)';
  ctx.lineWidth = 1.6;
  ctx.beginPath(); ctx.moveTo(x0, dy + rh * 0.95); ctx.lineTo(x1, dy + rh * 0.95); ctx.stroke();
  // body text below, two columns
  y = Math.max(top + 4 * (bh + bg), dy + rh * 1.6) + H * 0.02;
  for (let c = 0; c < 2; c++) {
    let cy = y;
    const cx = m + c * (colW + gap);
    while (cy < H - m) {
      const n = Math.min(3 + Math.floor(r() * 6), Math.floor((H - m - cy) / (H * 0.0155)));
      if (n <= 0) break;
      cy = bars(ctx, r, cx, cy, colW, n, H * 0.0155, H * 0.0062, 'rgba(46,51,56,0.62)', 0.12) + H * 0.01;
    }
  }
  reviewTex = new THREE.CanvasTexture(cv);
  reviewTex.colorSpace = THREE.SRGBColorSpace;
  reviewTex.anisotropy = 8;
  reviewTex.generateMipmaps = true;
  reviewTex.minFilter = THREE.LinearMipmapLinearFilter;
  return reviewTex;
};
