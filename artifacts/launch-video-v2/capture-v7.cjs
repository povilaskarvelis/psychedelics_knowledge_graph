const fs=require('fs');const path=require('path');
const {chromium}=require('/Users/frank/Library/Caches/ms-playwright-go/1.57.0/package');
const out=path.join(__dirname,'public/v7');fs.mkdirSync(out,{recursive:true});
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const page=await browser.newPage({viewport:{width:1440,height:1100},deviceScaleFactor:2});
 await page.goto('http://127.0.0.1:8011/?data-source=local',{waitUntil:'networkidle'});
 await page.locator('#graph svg').waitFor();
 await page.addStyleTag({content:'.local-preview-badge{display:none!important}'});
 const graph=await page.locator('#graph svg').evaluate(e=>({
  viewBox:e.getAttribute('viewBox'),
  edges:[...e.querySelectorAll('path[data-compound]')].map(p=>({compound:p.dataset.compound,target:p.dataset.target,count:+p.dataset.claimCount,d:p.getAttribute('d'),width:+p.getAttribute('stroke-width'),stroke:p.style.stroke})),
  nodes:[...e.querySelectorAll('circle')].map(c=>({x:+c.getAttribute('cx'),y:+c.getAttribute('cy'),r:+c.getAttribute('r'),fill:getComputedStyle(c).fill,stroke:getComputedStyle(c).stroke})),
  labels:[...e.querySelectorAll('text')].map(t=>({name:t.textContent,x:+t.getAttribute('x'),y:+t.getAttribute('y'),anchor:t.getAttribute('text-anchor')})),
 }));
 await page.locator('#graph').screenshot({path:path.join(out,'explore-full.png')});
 await page.locator('#graph path[data-compound="Psilocybin"][data-target="Major depressive disorder"]').dispatchEvent('click');
 await page.waitForFunction(()=>document.querySelector('#graphDetail')?.innerText.includes('Psilocybin'));
 const details={};
 for(const name of ['Sample sizes','Administration route','Dosing schedule','Comparators','Follow-up windows','Study designs','Authors']){
  const panel=page.locator('#graphDetail .trend-card').filter({has:page.getByRole('heading',{name,exact:true})});
  if(await panel.count()){details[name]=await panel.innerText();await panel.screenshot({path:path.join(out,name.toLowerCase().replaceAll(' ','-')+'.png')});}
 }
 const edgeText=await page.locator('#graphDetail').innerText();
 await page.locator('#graphDetail').screenshot({path:path.join(out,'explore-detail.png')});
 const cards=await page.locator('.card').evaluateAll(es=>es.slice(0,8).map(e=>e.innerText));
 await page.getByRole('tab',{name:'Analyze',exact:true}).click();
 await page.getByRole('button',{name:/^Psilocybin\s+2,008$/}).waitFor();
 const momentum=await page.locator('.analytics-momentum-row').evaluateAll(es=>es.map(e=>({label:e.querySelector('strong')?.textContent,summary:e.querySelector('small')?.textContent,svg:e.querySelector('svg')?.outerHTML})));
 const mp=page.locator('.analytics-momentum-panel').first();await mp.screenshot({path:path.join(out,'momentum.png')});
 const scope=await mp.innerText();
 await page.locator('#explorerEntitySelect').selectOption({label:'Authors'});
 await page.locator('.explorer-matrix-row-button').first().waitFor();
 const authorRows=await page.locator('.explorer-matrix-row-button').evaluateAll(es=>es.map(e=>({key:e.dataset.explorerRowKey,name:e.querySelector('span')?.textContent})));
 const authorCells=await page.locator('.explorer-matrix-cell[data-explorer-row-key]').evaluateAll(es=>es.map(e=>({key:e.dataset.explorerRowKey,area:e.dataset.explorerDimensionLabel,count:+e.dataset.studyCount,color:e.style.getPropertyValue('--area-color')})));
 await page.locator('#graph').screenshot({path:path.join(out,'authors-full.png')});
 const author=page.getByRole('button',{name:/Explore Robin Carhart.Harris across/});
 if(await author.count()){await author.click();await page.locator('.analytics-network-panel').waitFor();await page.locator('.analytics-network-panel').screenshot({path:path.join(out,'author-connections.png')});}
 const result={graph,details,edgeText,cards,momentum,scope,authorRows,authorCells};
 fs.writeFileSync(__dirname+'/src/v7-data.json',JSON.stringify(result,null,2));
 console.log(JSON.stringify({graphEdges:graph.edges.length,graphLabels:graph.labels.slice(0,8),details,cards:cards.slice(0,2),momentum,scope,authorRows:authorRows.slice(0,8)},null,2));await browser.close();
})().catch(e=>{console.error(e);process.exitCode=1});
