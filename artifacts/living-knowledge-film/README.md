# Living Knowledge — launch film

A 1:46 vision film about AI-built, living knowledge graphs as scientific infrastructure. Psychedelics
Knowledge Graph appears as the first one built, shown with the real product, before the film zooms out to every field. The script and shot list are in
[SCRIPT.md](SCRIPT.md).

## Stack

- **Remotion 4** timeline, rendered headless. WebGL runs through ANGLE (`--gl=angle`).
- **Three.js** with custom GLSL shaders:
  - instanced paper fields: lighting, fog, glow, aging, and a dissolve through a sheet of light
  - GPU graph in the "spectrum" look (`LOOKS` in `src/three/Graph.jsx`): every cluster is a dandelion — a hub,
    sub-hubs on stems, leaves on straight spokes. Each cluster takes a hue from a ramp sampled at its place in the
    Act II frame (`CLUSTER_RANK` in `src/data/extGraph.js`), so colour flows across the field from teal to gold.
    Crisp flat dots with a dark rim and pixel caps, threads alpha-blended in their clusters' colours (dense regions
    saturate to their hue, never to white), no bloom. Nodes are instanced quads: at rest each is exactly its dot, and
    while it moves it stretches along its path over a half-frame shutter, so flights are motion-blurred the way a camera
    would see them. In the coalescence every piece travels with its page (`modeOf` 2, `group`: from the page's place on
    the wall to the paper's place in the graph, drawing in as it goes, all paths bending the same way around the axis),
    then unfolds into its own place, where the graph's threads grow as it lands; pieces start a little larger (`open`)
    and settle from the type colours into their cluster's colour. The graph takes the flow diagram's teal as it lands on
    it in Act III; Act IV draws every other field in its own hue (`fieldLook`). Also: focus, selection and
    gold-highlight states. Point sizes follow the device pixel ratio, so a 2x render downscaled to
    1080p gives silk-thin threads
  - page pieces (`src/three/Shards.jsx`): the papers that arrive in the living graph are drawn as their pieces — the
    title band (the paper itself) and one piece of the columns per extracted item. Pages fly in at one steady pace
    (paths are parametrized by arc length, and each sets off out of view so it is seen whole before it comes apart);
    each piece leaves its page at the page's speed, tumbles, takes its highlighter colour, rounds into a node and slows
    only as it lands, where the graph's node takes over. Paper is motion-blurred over the same half-frame shutter as the
    nodes: each piece is averaged over the ground it swept, and pieces still on their page are blurred as the whole page,
    so no seam opens between them
  - Act I's pile: per decade, stacks of jittered slabs (a hand-made pile, not a histogram), page tops, reams on the
    sides, loose sheets on the floor, rain onto the growth front, and papers rushing past the lens
  - illegible, procedurally drawn pages (`src/lib/textures.js`): the pile's atlas, and `journalPage`, which draws an
    atlas page, or a one-off page (`{seed, titleLines, figure, rule}`), at full resolution with word bars and the
    highlighter segments used up close (the Pages composition shows the atlas, or candidates passed as props); and a systematic review / meta-analysis page (`reviewPage`: gold masthead, PRISMA flow,
    forest plot with the pooled diamond) bound into a thicker document with a gold spine
- **postprocessing**: faint grain, and bloom only for Act II's blade of light. No vignette, depth of field or chromatic aberration:
  their smooth falloffs banded into visible rings on the near-black background. Wired directly in
  `src/three/Post.jsx`, because the R3F wrapper doesn't render under Remotion's `frameloop="never"`.
- **Motion**: closed-form damped springs (`src/lib/spring.js`) drive cameras, cursors, panels and markers.
  Every frame is still a pure function of time.
- **Typography**: Space Grotesk, IBM Plex Sans and IBM Plex Mono, matching the site. Type is composed into each
  shot rather than subtitled (`Block` in `src/ui/Type.jsx`: hand-broken lines, each with its own mask, and
  highlighter marks that sweep in with the page highlights). Acts I–III keep a type column on the right with the
  picture on the left; the turning points (thesis, Act II's opening, the finale) are set large and centred.
- **Score**: synthesized in Python in `scripts/score.py` at 120 bpm: drums, sidechained bass and supersaw chords,
  arps, risers and impacts. Every act boundary and key word lands on a beat (15 frames) or a bar (60 frames).

## Layout

```
src/Film.jsx            master timeline (T): act offsets and crossfades
src/scenes/ActOne.jsx   A — one continuous move right: 1665 → the pile explodes → one paper flies out → findings, methods and context buried in prose → links → review → out of date → search and screening → from scratch
src/scenes/Thesis.jsx   the turn, on black: stored. synthesized. accessed.
src/scenes/ActTwo.jsx   B — statement on black, wall of literature read right to left by a blade, drop into one graph (papers as nodes), new papers coming apart on their way in
src/scenes/ActThree.jsx S — the product as motion graphics from real numbers: a drill-down (field → compound → pair → findings → one finding → its paper), Analyze as a snapshot of the whole field (publication history, coverage, gaps), an MCP session, the graph again
src/scenes/ActFour.jsx  D — pull back to a network of fields joined by arcs → end card
src/three/              PaperField, Graph, Particles/LightSheet, Post, camera rig
src/data/graph.json     illustrative 3D graph layout (scripts/build-graph.mjs, deterministic)
src/data/extGraph.js    the same graph re-laid-out as dandelion clusters on a flattened sphere, with paper nodes linked to what was extracted from them
public/product/         live captures of psychedelicskg.com (scripts/capture-explorer.mjs: explorer states at 2x)
src/data/flows.json     geometry of the live flow diagram (points along every flow), where Act III's graph lands
src/data/product.js     the real numbers Act III draws (Psilocybin, Psilocybin → MDD and its findings, the RCT we open and its paper, the publication history, population coverage, the evidence-coverage matrix, the MCP answer)
public/audio/score.wav  generated by scripts/score.py
```

Scene-local frame constants (`A`, `B`, `S`, `D`) and the master offsets (`T` in `Film.jsx`) sit on the
120 bpm grid. The music landmarks (`EV` at the top of `scripts/score.py`) are global frames. If you retime a scene,
update both and regenerate the score. The GraphLook composition is a sandbox for tuning the graph style (frame n % 10
picks a look), and Pages is a contact sheet of the paper pages with their highlight segments.

## Reproduce

```sh
npm install
node scripts/build-graph.mjs            # graph layout
node scripts/capture-explorer.mjs       # fresh explorer captures + flow geometry (needs Google Chrome)
python3 scripts/score.py                # score → public/audio/score.wav
npx remotion studio src/index.jsx       # interactive preview (use Chrome; WebGL)
npx remotion render src/index.jsx LivingKnowledgeSilent dist/film-4k.mp4 \
  --gl=angle --scale=2 --concurrency=4 --codec=h264 --crf=13 --pixel-format=yuv420p   # 2x supersampled
ffmpeg -i dist/film-4k.mp4 -vf scale=1920:1080:flags=lanczos ...   # downscale, then mux the mastered score (-14 LUFS, ≤ -1 dBTP)
node scripts/stills.mjs /tmp/stills 1 ActTwo:250 ActThree:560   # bundle once, render stills for review
```

A full render takes a few minutes on an M-series Mac (the 2x render a little longer).

## Content notes

- Pages in Act I are illegible word bars, so no topic shows. Figures sit in their own boxes; nothing overlaps the text. The search, results and screening counts in Act I
  are illustrative.
- Act III is real: captures of psychedelicskg.com (the full-page capture releases the sticky nav so scrolling
  shows it once), and the agent's results come from the public API (PTSD: 469 papers, 513 relationships).
- MCP tool names and arguments in the agent scene (`search_concepts` with `query`, `find_relationships` with
  `object_ids`) are the real ones from `services/query_api/mcp_server.py`.
- Closing numbers (21,735 publications) and screens come from the live site, captured 2026-09-27.
- Analyze: the publication history is the site's Publication history panel (unique papers per year, stacked as primary
  studies, reviews and meta-analyses; checked against the live site 2026-10-30). The film shows 2000–2025, so the
  partial year 2026 doesn't read as a drop. Coverage (rows Compound, columns
  Population / model, all areas) and the gaps matrix (rows Topic, columns Compound, within Conditions) are the site's
  Evidence coverage, read with Papers set to Primary studies and to Meta-analyses on 2026-09-28/29. The graph makes no
  claims about the strength of evidence, so the film doesn't either. Coverage cells count
  papers, so a pair can read one or two higher than the explorer's study count for the same edge.
