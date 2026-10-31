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
   yearMinFilter.value='1950';
   yearMaxFilter.value='2026';
   const rows=analysisEvidenceRows({respectEvidenceView:true});
   const items=rows.flatMap(row=>row.items);
   const areas=ENTITY_CATEGORY_OPTIONS.map((area,i)=>({key:area.key,label:area.label,color:CATEGORY_COLORS[i%CATEGORY_COLORS.length]}));
   return {
    source:'Local Analyze view, all compounds and publication types; unique papers per research area per year',
    capturedAt:new Date().toISOString(),
    semantics:'Normalized shares of research-area assignments, not exclusive shares of papers. A paper can contribute to multiple research areas. 1950–2025 complete years; 2026 available papers to date.',
    rows:rows.map(row=>({key:row.key,count:row.count,claims:row.items.length})),
    areas,
    years:Array.from({length:77},(_,i)=>1950+i).map(year=>{
     const annual=items.filter(claim=>parseYearValue(claim.study_year)===year);
     return {year,papers:uniqueStudyCount(annual),counts:ENTITY_CATEGORY_OPTIONS.map(area=>uniqueStudyCount(annual.filter(claim=>claimMatchesEntityViewOption(claim,area))))};
    })
   };
  });
  if(result.years.at(-1).papers!==1441)throw new Error('Unexpected current-year count');
  fs.writeFileSync(__dirname+'/src/v22-area-timeline.json',JSON.stringify(result,null,2));
  console.log(JSON.stringify({years:result.years.length,last:result.years.at(-1)}));
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
