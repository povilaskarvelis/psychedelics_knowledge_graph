// Capture the live explorer for the psychedelic-science sequence: three real states at 2x, plus the exact
// geometry of the flow diagram (points along every visible flow, node centres) so the film's graph can land on it.
import puppeteer from 'puppeteer-core';
import fs from 'node:fs';
const S1 = 470; // scroll that frames the flow diagram
const browser = await puppeteer.launch({executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: 'new',
  args: ['--hide-scrollbars', '--force-color-profile=srgb']});
const page = await browser.newPage();
await page.setViewport({width: 1600, height: 1000, deviceScaleFactor: 2});
await page.emulateMediaFeatures([{name: 'prefers-color-scheme', value: 'dark'}, {name: 'prefers-reduced-motion', value: 'reduce'}]);
await page.goto('https://psychedelicskg.com/', {waitUntil: 'networkidle0', timeout: 120000});
await new Promise((r) => setTimeout(r, 4000));
await page.evaluate((y) => window.scrollTo(0, y), S1);
await new Promise((r) => setTimeout(r, 1200));
const geo = await page.evaluate(() => {
  const svg = [...document.querySelectorAll('svg')].sort((a, b) => b.querySelectorAll('path').length - a.querySelectorAll('path').length)[0];
  const inView = (y) => y > 40 && y < 1000;
  const flows = [...svg.querySelectorAll('path')].map((p) => {
    const L = p.getTotalLength(), m = p.getScreenCTM(), cs = getComputedStyle(p);
    const n = Math.max(8, Math.round(L / 14));
    const pts = [];
    for (let k = 0; k <= n; k++) {
      const q = p.getPointAtLength((k / n) * L);
      pts.push([+(m.a * q.x + m.c * q.y + m.e).toFixed(1), +(m.b * q.x + m.d * q.y + m.f).toFixed(1)]);
    }
    return {pts, w: parseFloat(cs.strokeWidth) || 1, stroke: cs.stroke, op: parseFloat(cs.strokeOpacity) * parseFloat(cs.opacity || 1)};
  }).filter((f) => f.pts.some(([, y]) => inView(y)));
  const nodes = [...svg.querySelectorAll('circle')].map((c) => { const r = c.getBoundingClientRect(); return [+(r.x + r.width / 2).toFixed(1), +(r.y + r.height / 2).toFixed(1), +(r.width / 2).toFixed(1)]; })
    .filter(([, y]) => inView(y));
  const labels = [...svg.querySelectorAll('text')].map((t) => { const r = t.getBoundingClientRect(); return [t.textContent.trim(), +(r.x).toFixed(1), +(r.y + r.height / 2).toFixed(1), +(r.width).toFixed(1)]; })
    .filter(([, , y]) => inView(y));
  return {flows, nodes, labels, scrollY};
});
fs.writeFileSync('public/product/flows.json', JSON.stringify(geo));
fs.writeFileSync('src/data/flows.json', JSON.stringify(geo));
console.log('flows', geo.flows.length, 'nodes', geo.nodes.length, 'labels', geo.labels.length, 'scrollY', geo.scrollY);
await page.screenshot({path: 'public/product/explore-default.png'});
// hover a compound: its flows light up, with a tooltip
const HERO = 'Psilocybin';
const pos = geo.labels.find(([t]) => t === HERO);
const circle = geo.nodes.filter(([x, y]) => Math.abs(y - pos[2]) < 14 && x > pos[1]).sort((a, b) => a[0] - b[0])[0];
console.log('hover target', HERO, circle);
await page.mouse.move(circle[0], circle[1], {steps: 6});
await new Promise((r) => setTimeout(r, 1200));
await page.screenshot({path: 'public/product/explore-hover.png'});
// click: the explorer focuses on that compound
await page.mouse.click(circle[0], circle[1]);
await new Promise((r) => setTimeout(r, 2500));
await page.mouse.move(1590, 990);
await new Promise((r) => setTimeout(r, 600));
console.log('scroll after click', await page.evaluate(() => scrollY));
await page.screenshot({path: 'public/product/explore-focus.png'});
// release the sticky / fixed navigation so the full-page capture has it once, at the top (the film overlays its own)
const released = await page.evaluate(() => [...document.querySelectorAll('body *')].flatMap((e) => {
  const p = getComputedStyle(e).position;
  if (p === 'sticky') { e.style.setProperty('position', 'relative', 'important'); e.style.setProperty('top', '0px', 'important'); return [`sticky ${e.tagName}.${e.className}`]; }
  if (p === 'fixed') { e.style.setProperty('position', 'absolute', 'important'); e.style.setProperty('top', '0px', 'important'); return [`fixed ${e.tagName}.${e.className}`]; }
  return [];
}));
console.log('released', released);
await new Promise((r) => setTimeout(r, 600));
await page.screenshot({path: 'public/product/explore-focus-full.png', fullPage: true});
fs.writeFileSync('public/product/capture-meta.json', JSON.stringify({S1, hero: HERO, hover: circle, capturedAt: new Date().toISOString()}));
await browser.close();
