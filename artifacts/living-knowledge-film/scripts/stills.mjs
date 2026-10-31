// Render a list of stills with one bundle: node scripts/stills.mjs <outDir> <scale> Comp:frame [Comp:frame ...]
import path from 'path';
import {bundle} from '@remotion/bundler';
import {renderStill, selectComposition} from '@remotion/renderer';

const [outDir, scale, ...jobs] = process.argv.slice(2);
const serveUrl = await bundle({entryPoint: path.resolve('src/index.jsx')});
const comps = new Map();
for (const job of jobs) {
  const [id, frame] = job.split(':');
  if (!comps.has(id)) comps.set(id, await selectComposition({serveUrl, id, inputProps: {}, chromiumOptions: {gl: 'angle'}}));
  const output = path.join(outDir, `${id}-${frame}.png`);
  await renderStill({serveUrl, composition: comps.get(id), frame: +frame, output, scale: +scale, chromiumOptions: {gl: 'angle'}, overwrite: true, logLevel: 'error'});
  console.log(output);
}
