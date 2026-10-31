// New phrases assembled from individual performed guitar notes, not the old lick.
// All event times are beats; each phrase follows its place in the backing cycle.
const {execFileSync}=require('node:child_process');
const path=require('node:path');
const [source,destination,bpmText]=process.argv.slice(2);
const beat=60/Number(bpmText);
const phrases={
 leadConditions:[[0,57,.9],[1.25,60,.75],[2,65,1.2],[3.5,67,.55],[4.25,62,1],[5.5,65,.7],[6.5,70,1.1]],
 leadLandscape:[[0,58,1.25],[1.75,65,.7],[2.75,67,1.1],[4,74,.85],[5.25,70,1.4],[7,67,.65]],
 leadPatterns:[[.25,65,.65],[1,60,.65],[2.5,69,1.2],[4.25,62,.65],[5,65,.8],[6.5,70,1.1]],
 leadAuthors:[[0,58,.65],[.75,67,.7],[2,70,1.3],[3.5,65,.5],[4.25,62,.8],[5.5,67,.7],[6.5,70,1.15]],
};
// Stable notes from the recorded instrument, with natural articulation retained.
const anchors=[{note:55,start:.045,length:.49},{note:58,start:.86,length:.62},{note:70,start:2.76,length:.43}];
for(const [name,events] of Object.entries(phrases)){
 const filters=[`[0:a]aresample=48000,asplit=${events.length}${events.map((_,i)=>`[s${i}]`).join('')}`];
 events.forEach(([at,note,hold],i)=>{
  const anchor=anchors.reduce((a,b)=>Math.abs(a.note-note)<Math.abs(b.note-note)?a:b);
  const rate=Math.pow(2,(note-anchor.note)/12);
  const natural=anchor.length/rate;
  // Small duration changes only; echoes provide the sustain instead of freezing notes.
  const length=Math.min(hold*beat,.85),tempo=Math.max(.68,Math.min(1.35,natural/length));
  const actual=natural/tempo;
  const gain=[.88,.71,.8,.72,.87,.73,.78][i];
  filters.push(`[s${i}]atrim=start=${anchor.start}:duration=${anchor.length},asetpts=PTS-STARTPTS,asetrate=${48000*rate},aresample=48000,atempo=${tempo},afade=t=in:d=0.018,afade=t=out:st=${Math.max(.02,actual-.15)}:d=0.15,volume=${gain},adelay=${Math.round(at*beat*48000)}S:all=1[n${i}]`);
 });
 const samples=Math.round(8*beat*48000);
 filters.push(`${events.map((_,i)=>`[n${i}]`).join('')}amix=inputs=${events.length}:normalize=0,highpass=f=180,lowpass=f=4700,chorus=0.85:0.9:27|41:0.10|0.08:0.17|0.23:0.45|0.55,aecho=0.9:0.85:${Math.round(beat*750)}|${Math.round(beat*1500)}:0.28|0.12,asetpts=N/SR/TB,apad=whole_len=${samples},atrim=end_sample=${samples},afade=t=out:st=${7.6*beat}:d=${.4*beat}[out]`);
 execFileSync('ffmpeg',['-hide_banner','-loglevel','error','-y','-i',source,'-filter_complex',filters.join(';'),'-map','[out]','-t',String(8*beat),'-c:a','pcm_f32le',path.join(destination,name+'.wav')],{timeout:15000});
}
