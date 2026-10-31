const fs=require('fs'),path=require('path');
const {chromium}=require('/Users/frank/Library/Caches/ms-playwright-go/1.57.0/package');
const out=path.join(__dirname,'public/story');fs.mkdirSync(out,{recursive:true});
fs.copyFileSync(path.resolve(__dirname,'../../favicon.svg'),path.join(out,'favicon.svg'));
(async()=>{
 const db=JSON.parse(fs.readFileSync(path.resolve(__dirname,'../../data/kg/views/methods_bibliography.json'),'utf8'));
 const names=['Psilocybin','MDMA','LSD','Ketamine','Ayahuasca','DMT'];
 const papers=names.flatMap(compound=>{
  const re=new RegExp('\\b'+compound+'\\b','i');
  const rows=db.rows.filter(r=>db.string_table[r[16]]==='Represented in graph'&&re.test(r[2])&&r[3]&&r[4]>=2000&&r[2].length<200);
  return Array.from({length:24},(_,i)=>{const r=rows[Math.floor(i*rows.length/24)];return {compound,title:r[2],year:r[4],journal:r[5],doi:r[1]}});
 });
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 await page.goto('http://127.0.0.1:8011/?data-source=local',{waitUntil:'networkidle'});
 await page.getByRole('tab',{name:'Analyze',exact:true}).click();
 await page.getByRole('button',{name:/^Psilocybin\s+2,008$/}).waitFor();
 const timeline=await page.locator('.analysis-publication-svg').evaluate(e=>[...e.querySelectorAll('g[aria-label]')].map(g=>{const label=g.getAttribute('aria-label');const m=label.match(/(\d+): (\d+) unique papers; (\d+) primary studies, (\d+) reviews, (\d+) meta-analyses/);return m?{year:+m[1],total:+m[2],primary:+m[3],reviews:+m[4],meta:+m[5]}:null}).filter(Boolean));
 const broad=[];
 for(const name of names){
  if(broad.length){await page.goto('http://127.0.0.1:8011/?data-source=local',{waitUntil:'networkidle'});await page.getByRole('tab',{name:'Analyze',exact:true}).click();}
  const button=page.getByRole('button',{name:new RegExp('^'+name+'\\s+[\\d,]+$')});await button.waitFor();await button.click();
  const svg=page.locator('.analytics-network-panel svg');await svg.waitFor();
  broad.push({compound:name,areas:await svg.evaluate(e=>[...e.querySelectorAll('path')].map((p,i)=>({name:[...e.querySelectorAll('text')][i+1]?.textContent,color:p.getAttribute('stroke'),width:+p.getAttribute('stroke-width')})))});
 }
 fs.writeFileSync(path.join(__dirname,'src/story-data.json'),JSON.stringify({papers,timeline,broad},null,2));
 console.log(JSON.stringify({papers:papers.length,timeline:timeline.length,broad:broad.map(x=>[x.compound,x.areas.length])}));await browser.close();
})().catch(e=>{console.error(e);process.exitCode=1});
