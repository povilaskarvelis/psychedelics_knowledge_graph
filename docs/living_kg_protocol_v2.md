# Living KG Protocol V2

This protocol separates source discovery from graph-edge trust. Existing DOIs
remain useful as a paper corpus, but each `DOI + compound + target/indication`
context must carry explicit provenance before it is treated as evidence.

## Paper Identity

Paper identity is DOI-level. When a new literature search finds a DOI that is
already present in the corpus, the paper should not be added or processed again
as a new paper. The rediscovery should be logged for provenance only.

Use the DOI add gate before metadata enrichment:

```bash
python pipeline/ingest/add_new_dois.py --dataset disorder --input data/raw/doi_queue.disorder.discovered.txt
```

The `run_extensive_search.py` wrapper runs this gate automatically after
discovery and passes `doi_queue.<dataset>.new.txt` into metadata enrichment. Run the
standalone command when importing or checking a DOI queue outside the wrapper.

Default outputs:

- `data/raw/doi_queue.<dataset>.new.txt`
- `data/processed/add_new_dois_report_<dataset>.json`
- `data/processed/rediscovered_dois_<dataset>.csv`
- `data/processed/missing_or_invalid_dois_<dataset>.csv`
- `data/processed/input_duplicate_dois_<dataset>.csv`

Only `doi_queue.<dataset>.new.txt` should continue to expensive metadata, PDF,
screening, or extraction steps when the goal is to process newly discovered
papers.

The discovery ledger is not part of the default existing-paper check, because
it is updated during the current discovery run. The gate checks the corpus,
paper libraries, stubs, curated claims, exploratory claims, and known-study set
unless an operator explicitly asks to include ledger history.

## Evidence Layers

1. `candidate_context`: a DOI-context pair found by search, queues, ledgers, or
   inherited artifacts. This is a lead, not a verified edge.
2. `screened_context`: title/abstract screening supports the compound and
   target or indication context, but structured evidence extraction may still
   be incomplete.
3. `verified_evidence`: a curated evidence row with provenance fields such as
   paper type, source type, access level, evidence locator, study design, and
   evidence-specific fields.

The public KG should prefer `verified_evidence`. Methods and audit views may
show candidate and screened contexts when clearly labeled.

## Corpus Migration Audit

Run the audit builder before new large searches:

```bash
python pipeline/validate/build_context_provenance_audit.py --table-out-dir data/processed/corpus
```

Default table outputs:

- `data/processed/corpus/candidate_papers.parquet`
- `data/processed/corpus/candidate_contexts.parquet`
- `data/processed/corpus/candidate_sources.parquet`
- `data/processed/corpus/candidate_corpus_manifest.parquet`

The audit aggregates existing artifacts, including DOI queues, discovery
ledgers, discovery reports, paper libraries, abstract-screening reports, triage
reports, claim stubs, curated claims, exploratory claims, known-study entries,
and local PDFs.

Each context records `context_sources`, including values such as
`queue_discovered_context`, `seed_result_context`, `paper_library_context`,
`triage_matched_context`, `triage_synthesized_context`,
`llm_verified_context`, `claim_stub`, `curated_claim`,
`exploratory_claim`, and `known_study_context`.

## Revalidation Rules

Contexts should be treated as needing revalidation unless they are already
curated evidence and do not trigger audit flags. The first audit flag is
`possible_acronym_collision`, intended to catch short labels such as `DMT`,
`DOI`, `DOM`, `DOB`, `MDA`, and similarly ambiguous target labels.

The flag is conservative. It does not prove a row is wrong. It marks rows that
deserve a human or stricter automated check before they are used as trusted KG
edges.

## Promotion Plan

After rebuilding the provenance audit, build the promotion plan:

```bash
python pipeline/validate/build_context_promotion_plan.py
```

Default outputs:

- `data/processed/context_promotion_plan.json`
- `data/processed/context_promotion_worklist.csv`
- `data/processed/context_edge_rollup.json`
- `data/processed/context_promotion_summary.json`

The plan converts each `DOI + compound + target/indication` context into a
next action:

- `retain_in_curated_kg`: already curated evidence and no blocking audit flag
- `review_possible_acronym_or_entity_collision`: blocked until the short label
  or entity match is rechecked
- `curate_existing_claim_stub`: a claim stub exists but is not promoted
- `review_exploratory_claim_before_public_kg`: evidence exists only in the
  exploratory layer
- `extract_structured_claim_from_full_text`: screened context with local PDF
- `obtain_full_text_or_extract_abstract_only_claim`: screened context without a
  local PDF
- `screen_candidate_context`: discovered context that has not been screened

The edge rollup aggregates multiple papers into one compound-target or
compound-indication edge status. This is the bridge between broad search
coverage and the public KG: an edge can be visible as a gap or candidate before
it becomes a verified KG edge, but only `verified_evidence` should count as
public evidence by default.

The full plan, worklist CSV, and edge rollup are generated artifacts and may be
large. Keep the summary file for review, and regenerate the full artifacts from
the audit when needed.

## Stage Queues

Export actionable queues from the promotion plan:

```bash
python pipeline/validate/export_context_promotion_queues.py
```

Default outputs:

- `data/processed/context_queue_manifest.json`
- `data/processed/context_queues/*.csv`
- `data/raw/doi_queue.<dataset>.context_<stage>.txt`

The generated DOI queues preserve `doi, compound, entity, study_title,
study_year` in the same CSV-style format used by existing DOI queue scripts.
The richer stage CSVs preserve the original `context_id`, source artifacts, and
blocking flags.

Suggested queue order:

1. `noise_review`: resolve possible acronym/entity collisions first.
2. `curation_review`: finish existing stubs before creating duplicate work.
3. `full_text_extraction_ready`: extract structured evidence from local PDFs.
4. `screened_needs_pdf_or_abstract_extraction`: acquire PDFs or explicitly
   mark abstract-only evidence.
5. `abstract_screening_needed`: screen the broader candidate pool.

## Living Update Loop

1. Run discovery with a versioned search manifest.
2. Run the DOI add gate and send only new DOI rows downstream.
3. Rebuild the corpus/context audit.
4. Build the context promotion plan.
5. Export stage-specific promotion queues.
6. Screen candidate contexts and extract verified evidence.
7. Promote only validated rows into curated claims.
8. Export the KG and publish a release manifest with counts, hashes, and audit
   deltas.

This makes updates incremental: new searches fill gaps, while the existing DOI
corpus remains reusable and traceable.

## Corpus Storage and Serving Roadmap

Status: active transition

Near-term goal: use normalized corpus tables as the main downstream input. The
current builder writes these tables under `data/processed/corpus/`. The
canonical derived corpus should be table-shaped so metadata enrichment,
screening, routing, extraction, audits, and methods counts can query it
directly.

Planned internal tables:

- `candidate_papers.parquet`: one row per DOI, including title, abstract,
  bibliographic metadata, metadata/PDF status, and current pipeline status.
- `candidate_contexts.parquet`: one row per DOI plus compound/entity/domain
  context, preserving why the paper entered the corpus.
- `candidate_sources.parquet`: one row per DOI/source/provenance event,
  preserving which search, queue, screen, extraction, or graph step saw the
  paper.
- `paper_metadata_enrichment.parquet`: one row per DOI with enriched
  bibliographic metadata, abstracts when available, provider identifiers, and
  metadata lookup status.
- `candidate_corpus_manifest.parquet`: a small manifest table with schema version, input
  artifacts, generated timestamp, row counts, and hashes.

Terminology TODO for the table-based pipeline:

- Use `evidence_record` for the canonical extracted row and `finding` for the
  human-facing UI label. See `docs/terminology.md`.
- Reserve `claim` for legacy schemas, payload fields, file names, and
  compatibility code in the first-generation graph.
- If graph-ready tables are materialized, treat `evidence_edges` as derived
  views over evidence records rather than the canonical extracted evidence.
- Keep model/extraction confidence separate from evidence certainty or
  risk-of-bias appraisal.

Graph-modeling TODO for the table-based pipeline:

- Keep the normalized Parquet tables as the canonical pipeline store. Graph
  payloads, API/MCP views, and any future RDF or property-graph export should be
  derived from those tables.
- Make relationships first-class edges when they need to be queried, filtered,
  aggregated, visualized, or aligned to external ontologies as relationships.
  Likely edge candidates include `compound -> studied_for_condition ->
  condition`, `compound -> studied_for_symptom -> symptom`,
  `compound -> reports_safety_signal -> adverse_event`, `compound ->
  has_mechanistic_target -> target`, `evidence_record -> supported_by ->
  paper`, and possibly `evidence_record -> measured_with -> outcome_scale`.
- Keep values as properties when they mainly qualify an evidence record rather
  than define a reusable graph relationship. Likely property candidates include
  sample size, assessment timepoint, comparator, dose, route, effect size, p value,
  confidence interval, access level, evidence locator, source excerpt, study
  design, extraction confidence, and risk-of-bias notes.
- Avoid over-assertive relation names such as `improves_symptom` until there is
  an explicit evidence-appraisal layer. Prefer neutral relations such as
  `studied_for_symptom` plus a `result_direction` property.
- Revisit this boundary before creating the next-generation `evidence_records`
  and `evidence_edges` tables, because moving a field from property to edge is
  easiest before downstream API and UI contracts depend on it.

Metadata enrichment is table-native:

```bash
python pipeline/ingest/enrich_paper_metadata.py \
  --papers-table data/processed/corpus/candidate_papers.parquet \
  --output-table data/processed/corpus/paper_metadata_enrichment.parquet \
  --metadata-provider-order openalex
```

The output table is merged back into the next corpus-table rebuild.

Longer-term serving plan:

- Load the normalized corpus and KG tables into Postgres for the public website,
  API, and MCP-facing query tools.
- Use Postgres for paper search, filters, DOI provenance trails, claim/evidence
  queries, and agent access.
- Generate compressed JSON or static chunks only as website delivery artifacts
  when useful; do not treat them as the canonical pipeline store.

This keeps the scientific pipeline reproducible from versioned file artifacts
while leaving a clean path to human browsing and agent queries later.

## Planned Extension Streams

These are not malformed-output retries. They are planned corpus extensions that
start from new search/discovery work and then flow through the same DOI gate,
screening, full-text, extraction, KG, methods-flow, and graph-payload pipeline.

### Brain Regions, Circuits, Networks, and Cognitive-Behavioral Tasks

Status: planned

Goal: add a mechanistic brain-level evidence layer linking compounds to brain
regions, circuits, and functional networks studied in neuroimaging,
electrophysiology, receptor-occupancy, systems-neuroscience, and
cognitive-behavioral task literature.

Examples:

- brain regions: prefrontal cortex, medial prefrontal cortex, hippocampus,
  amygdala, thalamus, claustrum, nucleus accumbens, dorsal raphe nucleus
- functional networks/circuits: default mode network, salience network,
  frontoparietal network, cortico-striatal circuit, thalamo-cortical
  connectivity
- modalities/search families: fMRI connectivity, PET receptor occupancy, EEG,
  MEG, neurophysiology, circuit dynamics, functional connectivity
- cognitive/behavioral task domains: cognitive flexibility, reversal learning,
  extinction learning, fear conditioning, reward learning, emotional processing,
  social cognition, attention, impulsivity, prepulse inhibition, and related
  translational task paradigms

Rationale:

This should be a separate mechanistic category rather than a target or
target-family/system category. Molecular targets describe receptors,
transporters, enzymes, genes, and pathway nodes. Brain regions/networks describe
anatomical or functional neurobiology at a different scale. Keeping them
separate avoids treating a study of `5-HT2A` as if it directly studied the
whole serotonergic system or a brain network. Cognitive-behavioral task domains
also sit at this systems-level mechanistic scale: they are not clinical
conditions or symptoms, but they can be central mechanistic outcomes in
preclinical and human experimental studies.

Next action:

1. Define `brain_region_or_network` and `cognitive_behavioral_task` as
   first-class mechanistic entity kinds in the extraction schema, projection,
   normalization, KG tables, and UI views.
2. Add concise extraction-prompt instructions for region/network and
   cognitive-behavioral task claims, keeping direct evidence separate from
   inferred parent systems or broad clinical interpretations.
3. Seed normalization registries for high-confidence regions, networks, and
   task domains.
4. Run one targeted literature discovery pass for brain-region, circuit,
   network, neuroimaging, electrophysiology, receptor-occupancy,
   cognitive-task, behavioral-task, and translational assay psychedelic studies.
5. Rebuild the unified corpus so new and rediscovered DOIs are retained with
   provenance, while only corpus rows still missing metadata proceed to
   metadata enrichment.
6. Process the new stream through metadata enrichment, PDF/full-text retrieval,
   abstract screening, packet building, extraction, QA, projection,
   normalization, KG table rebuild, methods-flow rebuild, and graph-payload
   export.
7. Record the search manifest, added DOI counts, rediscovered DOI counts,
   extraction counts, retry counts, and final graph/entity deltas.

This stream should also serve as the template for future add-on searches that
start at discovery and append cleanly into the existing corpus and graph.
