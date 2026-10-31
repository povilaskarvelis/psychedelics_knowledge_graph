const fs=require('fs');
const {chromium}=require('/Users/frank/Library/Caches/ms-playwright-go/1.57.0/package');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 try {
  const page=await browser.newPage({viewport:{width:1600,height:1080}});
  await page.goto('http://127.0.0.1:8012/?data-source=local',{waitUntil:'networkidle'});
  await page.getByRole('tab',{name:'Analyze',exact:true}).click();
  await page.locator('.compare-composition-segment').first().waitFor({timeout:120000});
  const result=await page.evaluate(()=>{
   const rows=analysisEvidenceRows({respectEvidenceView:true});
   const items=rows.flatMap(row=>row.items);
   const areas=ENTITY_CATEGORY_OPTIONS.map((area,i)=>({key:area.key,label:area.label,color:CATEGORY_COLORS[i%CATEGORY_COLORS.length]}));
   return {
    source:'Local Analyze view, all compounds and publication types; unique papers per research area per year',
    capturedAt:new Date().toISOString(),
    semantics:'Normalized shares of research-area assignments, not exclusive shares of papers. A paper can contribute to multiple research areas. Complete years only.',
    rows:rows.map(row=>({key:row.key,count:row.count,claims:row.items.length})),
    areas,
    years:Array.from({length:16},(_,i)=>2010+i).map(year=>{
     const annual=items.filter(claim=>parseYearValue(claim.study_year)===year);
     return {year,papers:uniqueStudyCount(annual),counts:ENTITY_CATEGORY_OPTIONS.map(area=>uniqueStudyCount(annual.filter(claim=>claimMatchesEntityViewOption(claim,area))))};
    })
   };
  });
  if(result.years.some(year=>year.counts.reduce((a,b)=>a+b,0)===0))throw new Error('Missing annual data');
  fs.writeFileSync(__dirname+'/src/v13-area-timeline.json',JSON.stringify(result,null,2));
  console.log(JSON.stringify(result));
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
