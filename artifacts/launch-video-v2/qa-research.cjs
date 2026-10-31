const {bundle}=require('@remotion/bundler');
const {selectComposition,renderStill}=require('@remotion/renderer');
const fs=require('fs');
(async()=>{
 const serveUrl=await bundle({entryPoint:require.resolve('./src/index.jsx')});
 const composition=await selectComposition({serveUrl,id:'Research'});
 fs.mkdirSync('dist/research-qa',{recursive:true});
 for(const frame of [40,120,200,260,325,440,615,759,944,1150,1260,1460,1640]){
  await renderStill({serveUrl,composition,frame,output:`dist/research-qa/${String(frame).padStart(4,'0')}.png`});
  console.log('checked',frame);
 }
})().catch(e=>{console.error(e);process.exitCode=1});
