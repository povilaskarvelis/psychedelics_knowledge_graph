const {execFileSync,spawnSync}=require('node:child_process');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');

// All pitched parts share the Tokyo Dreams session and its chord progression.
// Decode CAF once to avoid AAC priming offsets at every repeat. All phrase
// changes follow an 85 BPM grid; reverb/delay tails overlap phrase boundaries.
const root='/Library/Audio/Apple Loops/Apple/07 Chillwave';
const smoothIntro=process.argv.includes('--smooth-intro');
const softToolsFade=process.argv.includes('--soft-tools-fade');
const wovenGuitars=softToolsFade||process.argv.includes('--woven-guitars');
const variedLead=process.argv.includes('--varied-lead');
const mellowTools=wovenGuitars||variedLead||process.argv.includes('--mellow-tools');
const inspiringLead=process.argv.includes('--inspiring-lead');
const impactTools=inspiringLead||process.argv.includes('--impact-tools');
const alignedTools=mellowTools||impactTools||process.argv.includes('--aligned-tools');
const riffIntro=alignedTools||process.argv.includes('--riff-intro');
const experimental=riffIntro||smoothIntro||process.argv.includes('--takeoff');
const energized=experimental||process.argv.includes('--energized');
const omitPad=energized||process.argv.includes('--no-pad');
const bpm=experimental?92:energized?98:85;
const version=softToolsFade?'v73':wovenGuitars?'v72':variedLead?'v71':mellowTools?'v65':inspiringLead?'v64':impactTools?'v63':alignedTools?'v62':riffIntro?'v61':smoothIntro?'v60':experimental?'v59':energized?'v58':omitPad?'v57':'v56';
const output=`public/story/product-${version}-soundtrack.wav`;
const temp=fs.mkdtempSync(path.join(os.tmpdir(),`pkg-${version}-`));
const duration=(alignedTools?2906:2944)/30, beat=60/bpm, phrase=16*beat, reveal=434/30;
const sources=[
 ['guitar','Tokyo Dreams Guitar',90],
 ['delay','Tokyo Dreams Delay Guitar',90],
 ['lead','Tokyo Dreams Lead Guitar',90],
 ['bass','Tokyo Dreams Bass',90],
 ['pad','Tokyo Dreams Pad',90],
 ['drums1','Acoustic Layers Beat 01',85],
 ['drums2','Acoustic Layers Beat 02',85],
 ['drums3','Acoustic Layers Beat 03',85],
];
if(experimental&&!riffIntro)sources.push(['lift','Tokyo Dreams Guitar',90]);
if(inspiringLead)sources.push(['leadLift','Tokyo Dreams Lead Guitar',90],['leadAnswer','Tokyo Dreams Lead Guitar',90]);
const variedNames=['leadConditions','leadLandscape','leadPatterns','leadAuthors'];
if(variedLead){
 execFileSync(process.execPath,[path.join(__dirname,'compose-v71-guitar.cjs'),path.join(root,'Tokyo Dreams Lead Guitar.caf'),temp,String(bpm)]);
 sources.push(...variedNames.map(id=>[id,'',bpm]));
}
const run=args=>execFileSync('ffmpeg',['-hide_banner','-y',...args],{encoding:'utf8',maxBuffer:8*1024*1024});
for(const [id,name,sourceBpm] of sources){
 if(variedLead&&variedNames.includes(id))continue;
 if(id==='leadLift'||id==='leadAnswer'){
  // Revoice the performed notes, retaining their bends and guitar articulation.
  // F/B-flat half: A–C–D–F. E-flat/G-minor half: B-flat–E-flat–F–G.
  const shifts=id==='leadLift'?[2,2,-8,-4]:[3,5,-5,-2];
  const boundaries=[0,2/3,8/3,10/3,16/3];
  const parts=shifts.map((shift,i)=>{
   const ratio=Math.pow(2,shift/12);
   const length=(boundaries[i+1]-boundaries[i])*90/bpm;
   return `[s${i}]atrim=start=${boundaries[i]}:end=${boundaries[i+1]},asetpts=PTS-STARTPTS,asetrate=${48000*ratio},aresample=48000,atempo=${(bpm/90)/ratio},apad,atrim=duration=${length+(i<3?.018:0)},afade=t=in:d=0.008,afade=t=out:st=${Math.max(0,length-.025)}:d=0.04[n${i}]`;
  });
  const filter=['aresample=48000,asplit=4[s0][s1][s2][s3]',...parts,'[n0][n1]acrossfade=d=0.018:c1=qsin:c2=qsin[j1]','[j1][n2]acrossfade=d=0.018:c1=qsin:c2=qsin[j2]','[j2][n3]acrossfade=d=0.018:c1=qsin:c2=qsin,apad,atrim=duration='+phrase/2+'[out]'].join(';');
  run(['-loglevel','error','-i',path.join(root,name+'.caf'),'-filter_complex',filter,'-map','[out]','-c:a','pcm_f32le',path.join(temp,id+'.wav')]);
  continue;
 }
 if(id==='lift'){
  if(smoothIntro){
   execFileSync('/Users/frank/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3',[path.join(__dirname,'guitar-resonance.py'),path.join(root,name+'.caf'),path.join(temp,id+'.wav')]);
   continue;
  }
  run(['-loglevel','error','-i',path.join(root,name+'.caf'),'-af','aresample=48000,atrim=start=0.35:duration=1.5,asetpts=PTS-STARTPTS,atempo=0.5,atempo=0.5,atempo=0.5,apad,atrim=duration=12','-c:a','pcm_f32le',path.join(temp,id+'.wav')]);
  continue;
 }
 run(['-loglevel','error','-i',path.join(root,name+'.caf'),'-af',`aresample=48000,atempo=${bpm/sourceBpm},apad,atrim=duration=${id==='lead'||id.startsWith('drums')?phrase/2:phrase},asetpts=PTS-STARTPTS`,'-c:a','pcm_f32le',path.join(temp,id+'.wav')]);
}
const clips=[];
function clip(id,start,length,gain,fx='',fadeIn=.05,fadeOut=.12,offset=0){
 if(omitPad&&id==='pad')return;
 if(wovenGuitars&&id==='lead')return;
 if(variedLead&&id==='lead'){
  const section=Math.floor((start-reveal+.001)/phrase);
  id=section===0?'leadConditions':section===3?'leadLandscape':section===4?'leadPatterns':'leadAuthors';
  fx='anull';
  fadeIn=.035;
  fadeOut=.10;
  gain*=1.35;
 }
 if(inspiringLead&&id==='lead'){
  const half=Math.round((start-reveal)/(phrase/2))%2;
  id=half?'leadLift':'leadAnswer';
 }
 clips.push({id,start,length,gain,fx,fadeIn,fadeOut,offset});
}
const guitarFX='highpass=f=140,lowpass=f=6800,aphaser=in_gain=0.9:out_gain=1:delay=1.4:decay=0.12:speed=0.15:type=s,aecho=0.9:0.8:529|1059:0.20|0.09';
const delayFX='highpass=f=240,lowpass=f=5800,aecho=0.9:0.8:529|1059|1588:0.24|0.12|0.05';
const leadFX='highpass=f=190,lowpass=f=6400,chorus=0.7:0.85:32|43:0.15|0.12:0.22|0.28:0.6|0.8,aecho=0.9:0.8:529|1059:0.24|0.12';
const padFX='highpass=f=180,lowpass=f=3400';
if(experimental){
 const dotted=Math.round(beat*750),q=Math.round(beat*1000);
 const dry='highpass=f=130,lowpass=f=6600';
 const space=dry+`,aphaser=in_gain=0.9:out_gain=1:delay=2.1:decay=0.23:speed=0.18:type=s,aecho=0.9:0.8:${dotted}|${q*2}|${q*3}:0.27|0.13|0.055`;
 const wide='highpass=f=210,lowpass=f=6000,chorus=0.8:0.85:29|43:0.12|0.10:0.19|0.24:0.5|0.7'+`,aecho=0.9:0.8:${dotted}|${q*2}:0.25|0.12`;
 const mechanical=dry+`,tremolo=f=${bpm/60*2}:d=0.40,aecho=0.9:0.8:${Math.round(q/2)}:0.12`;
 // A single stretched chord replaces competing forward/reversed progressions.
 if(riffIntro){
  const offset=phrase-(reveal%phrase);
  clip('guitar',0,reveal,.20,dry+`,aecho=0.9:0.8:${dotted}|${q*2}:0.18|0.07,volume='0.25+0.75*min(t/${reveal},1)':eval=frame`,1.2,.025,offset);
  clip('delay',0,reveal,.04,`highpass=f=250,lowpass=f=2800,aecho=0.9:0.8:${q}|${q*2}|${q*3}:0.25|0.13|0.065,volume='0.3+0.7*min(t/${reveal},1)':eval=frame`,3,.55,offset);
 }else{
 clip('lift',0,12,smoothIntro?.42:.27,smoothIntro?"highpass=f=140,lowpass=f=3000,volume='0.4+0.6*min(t/9,1)':eval=frame":'highpass=f=180,lowpass=f=4200,aphaser=in_gain=0.9:out_gain=1:delay=2.7:decay=0.28:speed=0.13:type=s'+`,aecho=0.9:0.8:${q}|${q*2}:0.32|0.17,volume='0.35+0.65*min(t/10,1)':eval=frame`,3.0,2.1);
 const entry=9.7;
 clip('guitar',entry,reveal-entry,.16,space,2.4,.025,phrase-(reveal-entry));
 }
 clip('drums3',reveal-2*beat,2*beat,.047,'highpass=f=1100,lowpass=f=5800',.6,.02,2*beat);
 for(let section=0;section<8;section++){
  const start=reveal+section*phrase,length=Math.min(phrase,duration-start);
  const technical=section>=6,broad=section>=3&&section<=5,echoBreak=section===2;
  clip('bass',start,length,technical?.21:.185,'highpass=f=38,lowpass=f=1500',.02,section===7?3:.05);
  // Riff recedes for an echo breakdown, then returns in a wider register.
  if(mellowTools&&section===5){
   // At the tools downbeat, continue the same guitar performance/phase dry.
   // The outgoing echo is faded separately below, not layered over the drop.
   clip('guitar',start,phrase/2,.17,space,.08,.025);
   clip('guitar',start+phrase/2,phrase/2,.155,dry+`,aecho=0.9:0.8:${dotted}:0.10`,.025,.12,phrase/2);
  }else{
   clip('guitar',start,length,echoBreak?.085:broad?.17:technical?.155:.23,technical?(riffIntro?dry+`,aecho=0.9:0.8:${dotted}:0.10`:mechanical):space,.08,section===7?3:.12);
  }
  for(let half=0;half<2;half++){
   const s=start+half*phrase/2,l=Math.min(phrase/2,duration-s);
   if(l<=0)continue;
   const pattern=mellowTools&&section===5&&half===1?2:riffIntro&&technical?[2,3,3,2][(section-6)*2+half]:[1,2,2,3,3,1,2,3,1,3,3,2,2,3,3,1][section*2+half];
   const eq=echoBreak&&half===0?'highpass=f=1000,lowpass=f=4800':'highpass=f=65,lowpass=f=7000';
   clip('drums'+pattern,s,l,echoBreak&&half===0?.065:technical?.125:.11,eq,.01,section===7&&half===1?Math.min(3,l-.05):.035);
  }
  if(echoBreak)clip('delay',start,length,.145,wide,.8,.5);
  if(broad){
   if(wovenGuitars){
    // A single continuous performance per phrase, in phase with the bass and
    // rhythm guitar. Change its prominence and space, not its performed notes.
    const half=phrase/2;
    const foreground=section===4?`0.72+0.28*clip((t-${half-2*beat})/${2*beat},0,1)`:'1';
    const tone=section===5?
     `highpass=f=210,lowpass=f=5000,aecho=0.9:0.8:${dotted}:0.15`:
     section===4?`highpass=f=210,lowpass=f=5400,aecho=0.9:0.8:${dotted}|${q*2}:0.22|0.09`:wide;
    clip('delay',start,length,section===3?.165:section===4?.16:.145,tone+`,volume='${foreground}':eval=frame`,section===3?1.1:.75,.5);
   }else clip('delay',start,length,.12,wide,.75,.5);
   // Alternating answering phrases instead of a constant lead loop.
   clip('lead',start+(section%2?0:phrase/2),phrase/2,.11,wide,.18,.55);
  }
  if(section===0){
   clip('lead',start+phrase/2,phrase/2,.085,wide,.2,.5);
   if(wovenGuitars)clip('delay',start+6*beat,10*beat,.12,
    `highpass=f=230,lowpass=f=5000,aecho=0.9:0.8:${dotted}|${q*2}:0.20|0.08`,2*beat,.6,6*beat);
  }
  if(technical){
   // Four-beat call/response guitar delays, phase aligned to the chord cycle.
   for(let bar=0;bar<4;bar++){
    const s=start+bar*4*beat;
    if(s+2*beat>duration)break;
    if(!riffIntro)clip('delay',s,2*beat,.078,mechanical,.09,.35,(bar*4*beat)%phrase);
    clip('drums3',s+2.5*beat,beat*.65,.035,'highpass=f=1500,lowpass=f=6300'+`,aecho=0.8:0.7:${Math.round(q/2)}:0.18`,.008,.09,beat*2);
   }
  }
 }
 // Additional changes follow the presentation while the beat grid continues.
 const broadStart=47.667,phase=(broadStart-reveal)%phrase;
 if(!wovenGuitars)clip('delay',broadStart,phrase-phase,.12,wide,1.2,.4,phase);
 for(const t of [35.3,43.067]){
  const offset=(t-reveal)%phrase;
  clip('guitar',t,beat,.09,`highpass=f=600,lowpass=f=4500,aecho=0.9:0.8:${dotted}|${q*2}|${q*3}:0.37|0.23|0.12`,.04,.24,offset);
 }
}else if(energized){
 const eighth=Math.round(beat*750),quarter=Math.round(beat*1000);
 const guitar='highpass=f=130,lowpass=f=6900,aphaser=in_gain=0.9:out_gain=1:delay=1.8:decay=0.18:speed=0.21:type=s'+`,aecho=0.9:0.8:${eighth}|${eighth*2}:0.19|0.08`;
 const expansive='highpass=f=220,lowpass=f=6000'+`,aecho=0.9:0.8:${eighth}|${quarter*2}|${quarter*3}:0.27|0.14|0.06`;
 const lead='highpass=f=190,lowpass=f=6200,chorus=0.7:0.85:32|43:0.15|0.12:0.22|0.28:0.6|0.8'+`,aecho=0.9:0.8:${eighth}|${eighth*2}:0.23|0.10`;
 // One uninterrupted intro per guitar stem: no edit at the histogram handoff.
 const introOffset=phrase-(reveal%phrase);
 clip('guitar',0,reveal,.15,guitar+",volume='0.55+0.45*min(t/14.467,1)':eval=frame",1.7,.06,introOffset);
 clip('delay',0,reveal,.125,'areverse,highpass=f=260,lowpass=f=5200,aphaser=in_gain=0.9:out_gain=1:delay=2.4:decay=0.25:speed=0.17:type=s'+`,aecho=0.9:0.8:${eighth}|${quarter*2}:0.29|0.15,volume='0.5+0.5*min(t/14.467,1)':eval=frame`,2.2,.65,introOffset);
 // Filtered percussion develops before the full groove lands on the reveal.
 clip('drums3',reveal-phrase/2,phrase/2,.043,'highpass=f=800,lowpass=f=4200',1.9,.035);
 const gg=[.24,.19,.21,.19,.21,.23,.19,.18];
 for(let section=0;section<8;section++){
  const start=reveal+section*phrase;
  const technical=section>=6;
  clip('guitar',start,phrase,gg[section],technical?'highpass=f=150,lowpass=f=6500'+`,aecho=0.9:0.8:${eighth}:0.10`:guitar,.03,.05);
  clip('bass',start,phrase,technical?.22:.195,'highpass=f=38,lowpass=f=1700',.02,.05);
  for(let half=0;half<2;half++){
   const pattern=technical?[2,3,3,2][(section-6)*2+half]:[1,2,1,3,2,1,3,2,2,3,1,3][section*2+half];
   clip('drums'+pattern,start+half*phrase/2,phrase/2,technical?.14:.125,'highpass=f=60,lowpass=f=7400',.008,.025);
  }
  if([0,2,4,5].includes(section))clip('lead',start+phrase/2,phrase/2,.115,lead,.12,.25);
  if([1,3,4,5].includes(section))clip('delay',start,phrase,section>=3?.13:.085,expansive,.55,.3);
  // Sparse offbeat percussion answers the main pattern in the tools/update act.
  if(technical)for(let bar=0;bar<4;bar++){
   clip('drums3',start+(bar*4+2.5)*beat,beat*.65,.036,'highpass=f=1400,lowpass=f=6500'+`,aecho=0.8:0.7:${Math.round(beat*500)}:0.16`,.008,.08,beat*2);
  }
 }
 // Broader research views widen the guitar field at their actual entrance.
 const broadStart=47.667,phase=(broadStart-reveal)%phrase;
 clip('delay',broadStart,phrase-phase,.11,expansive,1.15,.35,phase);
 // Both tools and incoming papers share the final rhythmic section.
 const ending=reveal+8*phrase;
 clip('guitar',ending,duration-ending,.15,guitar,.04,2.3);
 clip('bass',ending,duration-ending,.12,'highpass=f=38,lowpass=f=1300',.02,2.5);
 clip('drums2',ending,duration-ending,.075,'highpass=f=90,lowpass=f=6200',.01,2.6);
}else{
// Opening starts within the phrase preceding the reveal, preserving harmony.
const previous=reveal-phrase;
clip('pad',0,previous,.16,padFX,1.2,.65,phrase-previous);
clip('delay',0,previous,.10,delayFX,1.1,.4,phrase-previous);
if(omitPad)clip('guitar',0,previous,.09,guitarFX,1.2,.4,phrase-previous);
clip('pad',previous,phrase,.14,padFX,.7,.6);
clip('guitar',previous,phrase,.13,guitarFX,.8,.4);
// A reverse guitar swell resolves on the graph title, followed by the band.
clip('delay',reveal-2.2,2.2,.10,'areverse,highpass=f=280,lowpass=f=4400,aecho=0.8:0.7:529:0.20',.8,.08);
const guitarGains=[.24,.18,.22,.23,.17,.23,.16];
const bassGains=[.19,.16,.17,.19,.16,.19,.14];
for(let section=0;section<7;section++){
 const start=reveal+section*phrase;
 clip('guitar',start,phrase,guitarGains[section],guitarFX,.06,.08);
 clip('bass',start,phrase,bassGains[section],'highpass=f=38,lowpass=f=1600',.025,.09);
 // Alternate drums on eight-bar phrases; retain a continuous beat phase.
 for(let half=0;half<2;half++){
  const id=['drums1','drums2','drums3'][Math.floor(section/2)%3];
  const gain=section===6?.052:section===4?.075:.105;
  clip(id,start+half*phrase/2,phrase/2,gain,'highpass=f=60,lowpass=f=7000',.008,.035);
 }
 // Guitar phrases answer the main rhythm, with whole phrases left open.
 if([0,2,5].includes(section))clip('lead',start+phrase/2,phrase/2,.105,leadFX,.12,.3);
 if([1,3,6].includes(section))clip('delay',start,phrase,.105,delayFX,.5,.35);
 if([0,4,6].includes(section))clip('pad',start,phrase,.08,padFX,.9,.7);
}
const ending=reveal+7*phrase;
clip('guitar',ending,3.1,.15,guitarFX,.07,1.8);
clip('pad',ending,3.1,.12,padFX,.3,1.9);
// Gentle reverse swells lead into the analysis and tools without resetting
// the underlying groove. They reuse the same guitar's pitch and timbre.
for(const t of [47.667,72.933])clip('delay',t-1.7,1.7,.045,'areverse,highpass=f=450,lowpass=f=4000,aecho=0.8:0.7:529:0.12',.8,.12);
}

if(smoothIntro){
 const change=72.933,dotted=Math.round(beat*750);
 // Restore the direct, percussion-led entrance at the tools scene itself.
 const before=clips.filter(c=>c.start<change).map(c=>{
  if(c.start+c.length<=change)return c;
  const length=change-c.start;
  return {...c,length,fadeIn:Math.min(c.fadeIn,length/3),fadeOut:Math.min(.10,length/3)};
 });
 clips.splice(0,clips.length,...before);
 for(let half=0,start=change;start<duration;half++,start=change+half*phrase/2){
  const length=Math.min(phrase/2,duration-start),offset=(start-reveal)%phrase;
  const ending=start>91;
  clip('drums'+[2,3,3,2][half%4],start,length,.14,'highpass=f=60,lowpass=f=7400',.008,ending?Math.min(2.8,length/2):.025);
  clip('bass',start,length,.22,'highpass=f=38,lowpass=f=1700',.025,ending?Math.min(2.5,length/2):.05,offset);
  clip('guitar',start,length,.15,`highpass=f=150,lowpass=f=6500,aecho=0.9:0.8:${dotted}:0.10`,.04,ending?Math.min(2.5,length/2):.07,offset);
  for(let bar=0;bar<2;bar++){
   const at=start+(bar*4+2.5)*beat;
   if(at+beat*.65>duration)continue;
   clip('drums3',at,beat*.65,.036,`highpass=f=1400,lowpass=f=6500,aecho=0.8:0.7:${Math.round(beat*500)}:0.16`,.008,.08,beat*2);
  }
 }
}
if(impactTools&&!mellowTools){
 const drop=reveal+88*beat;
 clip('drums1',drop,.36,.10,'highpass=f=34,lowpass=f=1100',.003,.18);
 clip('bass',drop,beat,.05,'highpass=f=35,lowpass=f=350',.008,.25,(drop-reveal)%phrase);
}
const uses=Object.fromEntries(sources.map(([id])=>[id,clips.filter(c=>c.id===id).length]));
const counts=Object.fromEntries(sources.map(([id])=>[id,0]));
const filters=[];
sources.forEach(([id],i)=>{
 const n=uses[id];
 if(n)filters.push(`[${i}:a]asplit=${n}${Array.from({length:n},(_,j)=>`[${id}${j}]`).join('')}`);
 else filters.push(`[${i}:a]anullsink`);
});
clips.forEach((c,i)=>{
 const loop=energized&&c.id!=='lift'?`aloop=loop=-1:size=${Math.round(48000*(c.id==='lead'||c.id.startsWith('drums')?phrase/2:phrase))},`:'';
 const reverseFirst=energized&&c.fx.startsWith('areverse,');
 const effect=reverseFirst?c.fx.slice('areverse,'.length):c.fx;
 // Change orchestration on the existing beat, never restart the drum/bass clips.
 // Post-effects attenuation also removes the higher echo tails at the drop.
 const toolsBeat=reveal+(alignedTools?88:90)*beat;
 const outgoingGuitar=mellowTools&&c.id==='guitar'&&Math.abs(c.start+c.length-toolsBeat)<.001;
 const after=mellowTools?(c.id.startsWith('lead')||c.id==='delay'||outgoingGuitar?0:c.id==='guitar'?.85:1):riffIntro?(c.id.startsWith('lead')||c.id==='delay'?0:c.id==='guitar'?.42:c.id.startsWith('drums')?1.22:c.id==='bass'?1.08:1):1;
 const softenDelay=softToolsFade&&c.id==='delay';
 const fadeStart=softenDelay?toolsBeat-.70:mellowTools&&after===0?toolsBeat-.14:toolsBeat;
 const fadeLength=softenDelay?1.25:mellowTools?.18:.09;
 const change=after===1?'':softenDelay?
  `,volume='0.5+0.5*cos(PI*clip((t+${c.start}-${fadeStart})/${fadeLength},0,1))':eval=frame`:
  `,volume='1+(${after}-1)*clip((t+${c.start}-${fadeStart})/${fadeLength},0,1)':eval=frame`;
 filters.push(`[${c.id}${counts[c.id]++}]${loop}atrim=start=${c.offset}:duration=${c.length},asetpts=PTS-STARTPTS,${reverseFirst?'areverse,':''}afade=t=in:d=${c.fadeIn},afade=t=out:st=${c.length-c.fadeOut}:d=${c.fadeOut},${effect},volume=${c.gain}${change},adelay=${Math.round(c.start*48000)}S:all=1[c${i}]`);
});
filters.push(`${clips.map((_,i)=>`[c${i}]`).join('')}amix=inputs=${clips.length}:normalize=0,highpass=f=30,acompressor=threshold=0.32:ratio=1.5:attack=30:release=220,afade=t=out:st=${94.3-(alignedTools?38/30:0)}:d=3.8,apad,atrim=duration=${duration}[mix]`);
const premaster=path.join(temp,'premaster.wav');
run(['-loglevel','error',...sources.flatMap(([id])=>['-i',path.join(temp,id+'.wav')]),'-filter_complex',filters.join(';'),'-map','[mix]','-ar','48000','-c:a','pcm_f32le',premaster]);
const analysis=spawnSync('ffmpeg',['-hide_banner','-i',premaster,'-af','loudnorm=I=-16:LRA=11:TP=-1.5:print_format=json','-f','null','-'],{encoding:'utf8',maxBuffer:8*1024*1024});
if(analysis.status!==0)throw Error(analysis.stderr);
const stats=JSON.parse(analysis.stderr.match(/\{[^{}]+\}/s)[0]);
const normalize=`loudnorm=I=-16:LRA=11:TP=-1.5:measured_I=${stats.input_i}:measured_LRA=${stats.input_lra}:measured_TP=${stats.input_tp}:measured_thresh=${stats.input_thresh}:offset=${stats.target_offset}:linear=true`;
run(['-loglevel','error','-i',premaster,'-af',`${normalize},aresample=48000,apad,atrim=end_sample=${Math.round(duration*48000)}`,'-map_metadata','-1','-c:a','pcm_s24le',output]);
console.log(JSON.stringify({duration,bpm,clips:clips.length,omitPad,premaster:stats,output},null,2));
fs.rmSync(temp,{recursive:true});
