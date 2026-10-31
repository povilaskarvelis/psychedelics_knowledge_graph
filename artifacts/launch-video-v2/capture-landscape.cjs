const {chromium} = require('/Users/frank/Library/Caches/ms-playwright-go/1.57.0/package');
const fs = require('fs');
const path = require('path');
const out = path.join(__dirname, 'public/landscape');
fs.mkdirSync(out, {recursive:true});
(async () => {
  const browser = await chromium.launch({headless:true, executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  const page = await browser.newPage({viewport:{width:1440,height:1000},deviceScaleFactor:2});
  await page.goto('http://127.0.0.1:8011/?data-source=local',{waitUntil:'networkidle'});
  await page.getByRole('tab',{name:'Analyze',exact:true}).click();
  await page.getByRole('button',{name:/^Psilocybin\s+2,008$/}).click();
  await page.getByRole('heading',{name:'Publication history',exact:true}).waitFor();
  const timeline = await page.locator('.analytics-focus-timeline-panel svg').evaluate(e => [...e.querySelectorAll('g[aria-label]')].map(g => {
    const label=g.getAttribute('aria-label');
    const match=label.match(/^(\d+): (\d+) unique papers/);
    return match ? {year:Number(match[1]),papers:Number(match[2]),label} : null;
  }).filter(Boolean));
  const connections = await page.locator('.analytics-network-panel svg').evaluate(e=>({
    viewBox:e.getAttribute('viewBox'),
    paths:[...e.querySelectorAll('path')].map(p=>({d:p.getAttribute('d'),stroke:p.getAttribute('stroke'),width:p.getAttribute('stroke-width')})),
    circles:[...e.querySelectorAll('circle')].map(p=>({cx:+p.getAttribute('cx'),cy:+p.getAttribute('cy'),r:+p.getAttribute('r'),fill:getComputedStyle(p).fill,stroke:getComputedStyle(p).stroke})),
    texts:[...e.querySelectorAll('text')].map(p=>({x:+p.getAttribute('x'),y:+p.getAttribute('y'),text:p.textContent,anchor:p.getAttribute('text-anchor')}))
  }));
  for (const [heading,file] of [['Connections','connections'],['Publication history','history'],['Area profile','areas']]) {
    const panel=page.getByRole('heading',{name:heading,exact:true}).locator('..').locator('..');
    await panel.screenshot({path:path.join(out,file+'.png'),animations:'disabled'});
  }
  await page.evaluate(()=>window.scrollTo(0,0));
  await page.screenshot({path:path.join(out,'product.png'),animations:'disabled'});
  const bibliography=JSON.parse(fs.readFileSync(path.resolve(__dirname,'../../data/kg/views/methods_bibliography.json'),'utf8'));
  const dois=['10.1001/jamapsychiatry.2020.3285','10.1002/hbm.22833','10.1111/add.70152'];
  const papers=dois.map(doi=>{
    const row=bibliography.rows.find(r=>r[1]===doi);
    if(!row) throw new Error('Missing paper '+doi);
    return {title:row[2],year:row[4],journal:row[5],doi};
  });
  fs.writeFileSync(path.join(__dirname,'src/landscape-data.json'),JSON.stringify({timeline,papers,connections},null,2));
  console.log(JSON.stringify(connections,null,2));
  await browser.close();
})().catch(e=>{console.error(e);process.exitCode=1});
