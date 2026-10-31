const fs=require('fs');
const {chromium}=require('/Users/frank/Library/Caches/ms-playwright-go/1.57.0/package');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const page=await browser.newPage({viewport:{width:1600,height:1080}});
 await page.goto('http://127.0.0.1:8012/?data-source=local',{waitUntil:'networkidle'});
 await page.locator('#graph path[data-compound="Psilocybin"][data-target="Major depressive disorder"]').dispatchEvent('click');
 await page.locator('.sample-heatmap-svg').waitFor();
 const sample=await page.locator('.sample-heatmap-svg').evaluate(e=>({labels:[...e.querySelectorAll('text')].map(x=>x.textContent),cells:[...e.querySelectorAll('.sample-heatmap-target')].map(x=>({...x.dataset}))}));
 await page.getByRole('tab',{name:'Analyze',exact:true}).click();
 await page.locator('.compare-composition-segment').first().waitFor({timeout:120000});
 const areas=await page.locator('.compare-composition-row').evaluateAll(es=>es.map(e=>({label:e.querySelector('strong').textContent,segments:[...e.querySelectorAll('.compare-composition-segment')].map(s=>({source:s.dataset.compareSourceKey,key:s.dataset.compareAreaKey,label:s.getAttribute('aria-label'),color:s.style.getPropertyValue('--segment-color')}))})));
 fs.writeFileSync(__dirname+'/src/v10-areas.json',JSON.stringify(areas,null,2));
 console.log(JSON.stringify(areas));
 fs.writeFileSync(__dirname+'/src/v10-sample.json',JSON.stringify(sample,null,2));
 console.log('sample cells',sample.cells.length);
 await browser.close();
})().catch(e=>{console.error(e);process.exitCode=1});
