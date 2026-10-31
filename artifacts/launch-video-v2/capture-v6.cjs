const fs=require('fs');
const {chromium}=require('/Users/frank/Library/Caches/ms-playwright-go/1.57.0/package');
(async()=>{
 const b=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const p=await b.newPage();await p.goto('http://127.0.0.1:8011/?data-source=local');
 await p.getByRole('tab',{name:'Analyze',exact:true}).click();
 await p.getByRole('button',{name:/^Psilocybin\s+2,008$/}).waitFor();
 await p.locator('#explorerEntitySelect').selectOption({label:'Compounds'});
 await p.locator('.explorer-matrix-cell[data-explorer-row-key]').first().waitFor();
 const result=await p.evaluate(()=>{
  const rows=[...document.querySelectorAll('.explorer-matrix-row-button')].map(e=>({key:e.dataset.explorerRowKey,name:e.querySelector('span').textContent}));
  const cells=[...document.querySelectorAll('.explorer-matrix-cell[data-explorer-row-key]')].map(e=>({compound:e.dataset.explorerRowKey,area:e.dataset.explorerDimensionLabel,count:+e.dataset.studyCount,color:e.style.getPropertyValue('--area-color')}));
  return {rows,cells};
 });
 fs.writeFileSync(__dirname+'/src/v6-data.json',JSON.stringify(result,null,2));
 console.log(JSON.stringify({rows:result.rows,cells:result.cells.length}));await b.close();
})().catch(e=>{console.error(e);process.exitCode=1});
