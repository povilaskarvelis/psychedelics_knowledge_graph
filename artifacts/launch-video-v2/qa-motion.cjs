const {bundle}=require('@remotion/bundler');
const {selectComposition,renderStill}=require('@remotion/renderer');
const fs=require('fs');
(async()=>{
 const serveUrl=await bundle({entryPoint:require.resolve('./src/index.jsx')});
 const composition=await selectComposition({serveUrl,id:'Motion'});
 fs.mkdirSync('dist/motion-qa',{recursive:true});
 for(const frame of [35,95,225,390,555,737,854,957,1170,1370,1530,1590,1800,2010]){
  await renderStill({serveUrl,composition,frame,output:`dist/motion-qa/${String(frame).padStart(4,'0')}.png`});
  console.log('checked',frame);
 }
})().catch(e=>{console.error(e);process.exitCode=1});
