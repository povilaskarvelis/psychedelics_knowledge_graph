const { chromium } = require('/Users/frank/Library/Caches/ms-playwright-go/1.57.0/package');
const fs = require('fs');
const path = require('path');

const outputDir = path.resolve(__dirname, 'assets');
fs.mkdirSync(outputDir, { recursive: true });

const baseStyles = `
  * { box-sizing: border-box; }
  html, body { margin: 0; width: 100%; height: 100%; overflow: hidden; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Helvetica Neue", Arial, sans-serif;
    -webkit-font-smoothing: antialiased;
  }
`;

function networkMarkup() {
  const nodes = [
    [122, 180, 9], [246, 122, 5], [335, 236, 7], [460, 153, 4], [582, 260, 8],
    [722, 154, 6], [846, 236, 8], [963, 143, 5], [177, 505, 6], [330, 610, 9],
    [503, 518, 5], [652, 650, 8], [808, 505, 5], [951, 638, 9], [109, 814, 5],
    [267, 891, 8], [456, 803, 6], [598, 914, 5], [777, 820, 8], [966, 897, 5],
  ];
  const links = [[0,1],[0,2],[1,3],[2,3],[2,5],[3,4],[4,5],[5,6],[5,7],[6,7],[0,8],[2,8],[2,9],[4,10],[4,12],[6,12],[8,9],[9,10],[10,11],[10,12],[11,13],[12,13],[8,14],[9,15],[9,16],[10,16],[11,17],[11,18],[12,18],[13,19],[14,15],[15,16],[16,17],[17,18],[18,19]];
  return `<svg class="network" viewBox="0 0 1080 1080" aria-hidden="true">
    <defs><linearGradient id="line" x1="0" x2="1"><stop stop-color="#58d2b2"/><stop offset="1" stop-color="#d5c56e"/></linearGradient></defs>
    ${links.map(([a,b]) => `<line x1="${nodes[a][0]}" y1="${nodes[a][1]}" x2="${nodes[b][0]}" y2="${nodes[b][1]}"/>`).join('')}
    ${nodes.map(([x,y,r], i) => `<circle cx="${x}" cy="${y}" r="${r}" class="${i % 4 === 0 ? 'warm' : ''}"/>`).join('')}
  </svg>`;
}

function fullCard({ eyebrow, headline, subhead, stats = '', footer = '' }) {
  return `<!doctype html><html><head><meta charset="utf-8"><style>${baseStyles}
    body {
      color: #f5fbf8;
      background:
        radial-gradient(circle at 18% 18%, rgba(56,153,129,.24), transparent 34%),
        radial-gradient(circle at 82% 76%, rgba(195,174,85,.15), transparent 30%),
        linear-gradient(145deg, #06100e 0%, #091612 52%, #030807 100%);
    }
    .network { position: absolute; inset: 0; width: 100%; height: 100%; opacity: .19; filter: blur(.15px); }
    .network line { stroke: url(#line); stroke-width: 1.2; opacity: .38; }
    .network circle { fill: #60d6b6; opacity: .85; }
    .network circle.warm { fill: #dac86d; }
    .veil { position: absolute; inset: 0; background: linear-gradient(90deg, rgba(3,8,7,.95) 0%, rgba(3,8,7,.79) 54%, rgba(3,8,7,.34) 100%); }
    .content { position: absolute; left: 78px; right: 72px; top: 82px; bottom: 70px; display: flex; flex-direction: column; justify-content: center; }
    .eyebrow { align-self: flex-start; padding: 12px 18px; border: 1px solid rgba(103,222,190,.48); border-radius: 999px; background: rgba(61,170,141,.12); color: #82e4c7; font-size: 18px; font-weight: 750; letter-spacing: .14em; text-transform: uppercase; }
    h1 { max-width: 900px; margin: 34px 0 24px; font-size: 84px; line-height: .99; letter-spacing: -.055em; font-weight: 760; }
    .sub { max-width: 830px; color: #bdcbc5; font-size: 31px; line-height: 1.35; letter-spacing: -.015em; }
    .stats { display: flex; gap: 18px; margin-top: 48px; }
    .stat { min-width: 250px; padding: 22px 24px; border: 1px solid rgba(154,193,180,.22); border-radius: 18px; background: rgba(14,32,27,.72); box-shadow: 0 18px 50px rgba(0,0,0,.2); }
    .stat strong { display: block; font-size: 38px; letter-spacing: -.035em; color: #fff; }
    .stat span { display: block; margin-top: 4px; color: #9fb3ab; font-size: 18px; }
    .footer { position: absolute; left: 78px; right: 72px; bottom: 66px; display: flex; align-items: center; justify-content: space-between; color: #9fb3ab; font-size: 20px; }
    .brand { color: #eef8f4; font-weight: 700; }
    .url { color: #72ddbf; font-weight: 700; letter-spacing: .01em; }
  </style></head><body>${networkMarkup()}<div class="veil"></div><main class="content">
    <div class="eyebrow">${eyebrow}</div><h1>${headline}</h1><div class="sub">${subhead}</div>${stats}
  </main><div class="footer"><span class="brand">Psychedelics Knowledge Graph</span><span class="url">${footer}</span></div>
  </body></html>`;
}

function overlayCard({ number, headline, subhead }) {
  return `<!doctype html><html><head><meta charset="utf-8"><style>${baseStyles}
    body { background: transparent; color: #f5fbf8; }
    .caption { position: absolute; left: 60px; right: 60px; top: 50px; display: grid; grid-template-columns: 50px 1fr; gap: 18px; align-items: start; }
    .number { margin-top: 5px; width: 42px; height: 42px; display: grid; place-items: center; border-radius: 999px; border: 1px solid rgba(110,224,193,.55); background: rgba(38,112,94,.4); color: #82e4c7; font-size: 17px; font-weight: 800; }
    .copy { padding: 0 0 22px; text-shadow: 0 2px 14px rgba(0,0,0,.65); }
    h2 { margin: 0; font-size: 46px; line-height: 1.02; letter-spacing: -.035em; font-weight: 760; }
    p { margin: 11px 0 0; color: #aebdb7; font-size: 22px; line-height: 1.25; }
    .accent { position: absolute; left: 128px; top: 196px; width: 104px; height: 4px; border-radius: 5px; background: linear-gradient(90deg,#5fdbba,#d9c768); }
    .footer { position: absolute; left: 60px; right: 60px; bottom: 56px; display: flex; justify-content: space-between; align-items: center; color: #879b93; font-size: 17px; font-weight: 650; letter-spacing: .01em; }
    .footer .url { color: #69d7b8; }
    .progress { position: absolute; left: 60px; right: 60px; bottom: 34px; height: 2px; background: rgba(134,161,151,.16); }
    .progress span { display: block; width: ${Number(number) * 25}%; height: 100%; background: linear-gradient(90deg,#5fdbba,#d9c768); }
  </style></head><body><div class="caption"><div class="number">${number}</div><div class="copy"><h2>${headline}</h2><p>${subhead}</p></div></div><div class="accent"></div><div class="footer"><span>Psychedelics Knowledge Graph</span><span class="url">psychedelicskg.com</span></div><div class="progress"><span></span></div></body></html>`;
}

async function screenshotHtml(browser, html, file, omitBackground = false) {
  const page = await browser.newPage({ viewport: { width: 1080, height: 1080 }, deviceScaleFactor: 1 });
  await page.setContent(html, { waitUntil: 'load' });
  await page.screenshot({ path: path.join(outputDir, file), omitBackground });
  await page.close();
}

async function run() {
  const browser = await chromium.launch({
    headless: true,
    executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  });

  await screenshotHtml(browser, fullCard({
    eyebrow: 'Version 2',
    headline: 'Explore the field.<br><span style="color:#73dfc0">Analyze the evidence.</span>',
    subhead: 'A living, source-linked map of psychedelic research.',
    footer: 'psychedelicskg.com',
  }), 'title.png');

  await screenshotHtml(browser, fullCard({
    eyebrow: 'Updated 15 September 2026',
    headline: 'A living map,<br><span style="color:#73dfc0">built to keep up.</span>',
    subhead: 'Open the graph, ask a question, and follow every pattern back to the research behind it.',
    stats: '<div class="stats"><div class="stat"><strong>21,735</strong><span>reports</span></div><div class="stat"><strong>99,100</strong><span>structured findings</span></div></div>',
    footer: 'psychedelicskg.com',
  }), 'end.png');

  const overlays = [
    ['01', 'The literature keeps growing.', 'Now updated through 15 September 2026.'],
    ['02', 'Explore the connections.', 'Move from the field to a topic, finding, and source.'],
    ['03', 'New: Analyze the field.', 'See trends, coverage, compounds, authors, and journals.'],
    ['04', 'Trace patterns back to the papers.', 'Every view remains connected to the underlying publications.'],
  ];
  for (let index = 0; index < overlays.length; index += 1) {
    const [number, headline, subhead] = overlays[index];
    await screenshotHtml(browser, overlayCard({ number, headline, subhead }), `caption-${index + 1}.png`, true);
  }

  await screenshotHtml(browser, fullCard({
    eyebrow: 'Version 2',
    headline: 'Explore the field.<br><span style="color:#73dfc0">Analyze the evidence.</span>',
    subhead: '21,735 reports · 99,100 structured findings',
    footer: 'psychedelicskg.com',
  }), 'thumbnail.png');

  await browser.close();
  console.log(outputDir);
}

run().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
