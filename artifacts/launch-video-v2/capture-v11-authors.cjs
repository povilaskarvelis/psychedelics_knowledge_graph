const fs=require('fs');
const {chromium}=require('/Users/frank/Library/Caches/ms-playwright-go/1.57.0/package');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const page=await browser.newPage({viewport:{width:1600,height:1100}});
 await page.goto('http://127.0.0.1:8012/?data-source=local',{waitUntil:'networkidle'});
 await page.getByRole('tab',{name:'Analyze',exact:true}).click();
 await page.locator('#explorerEntitySelect').selectOption({label:'Authors'});
 await page.locator('.explorer-matrix-row-button').first().waitFor({timeout:120000});
 const top=await page.locator('.explorer-matrix-row-button').evaluateAll(es=>es.slice(0,4).map(e=>({key:e.dataset.explorerRowKey,name:e.querySelector('span').textContent})));
 const authors=[];
 for(const author of top){
  await page.goto('http://127.0.0.1:8012/?data-source=local',{waitUntil:'networkidle'});
  await page.getByRole('tab',{name:'Analyze',exact:true}).click();
  await page.locator('#explorerEntitySelect').selectOption({label:'Authors'});
  await page.locator('.explorer-matrix-row-button').first().waitFor({timeout:120000});
  await page.locator('#explorerSearchInput').fill(author.name);
  await page.locator('#explorerSearchOptions [data-explorer-search-key]').filter({hasText:author.name}).first().click();
  await page.waitForFunction(key=>explorerFocus?.key===key&&explorerSearchMatrix&&explorerRowForFocus(explorerSearchMatrix)?.claims?.length>0,author.key,{timeout:120000});
  const record=await page.evaluate(()=>{
   const row=explorerRowForFocus(explorerSearchMatrix);
   return {key:row.key,name:row.label,studyCount:row.studyCount,compounds:summarizeExplorerRelationships(row.claims,Infinity).map(c=>({key:c.key,name:c.label,count:c.studyCount,areas:[...c.areas.entries()].map(([key,a])=>({key,name:ENTITY_CATEGORY_OPTIONS.find(o=>o.key===key).label,count:a.studies.size,color:explorerAreaColor(key)}))}))};
  });
  authors.push(record);
 }
 fs.writeFileSync(__dirname+'/src/v11-authors.json',JSON.stringify({selection:'First four in overall author view, ordered by indexed study activity; not citation influence',authors},null,2));
 console.log(JSON.stringify(authors.map(a=>({name:a.name,studies:a.studyCount,compounds:a.compounds.map(c=>[c.name,c.count])}))));
 await browser.close();
})().catch(e=>{console.error(e);process.exitCode=1});
