const fs=require('fs');
const {chromium}=require('/Users/frank/Library/Caches/ms-playwright-go/1.57.0/package');
(async()=>{
 const b=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const p=await b.newPage();await p.goto('http://127.0.0.1:8011/?data-source=local');
 await p.getByRole('tab',{name:'Analyze',exact:true}).click();
 await p.getByRole('button',{name:/^Psilocybin\s+2,008$/}).waitFor();
 const points=await p.locator('.analytics-gap-point').evaluateAll(es=>es.map(e=>{
  const m=e.getAttribute('aria-label').match(/^(.*): (\d+) primary papers and (\d+) synthesis papers$/);
  return {name:m[1],primary:+m[2],synthesis:+m[3],color:e.querySelector('circle').style.getPropertyValue('--point-color')};
 }));
 const areas=await p.locator('option').evaluateAll(es=>es.map(e=>{const m=e.textContent.match(/^(.*) \(([\d,]+)\)$/);return m?{name:m[1],count:+m[2].replaceAll(',','')}:null}).filter(Boolean));
 fs.writeFileSync(__dirname+'/src/motion-data.json',JSON.stringify({points,areas},null,2));
 console.log({points,areas});await b.close();
})().catch(e=>{console.error(e);process.exitCode=1});
