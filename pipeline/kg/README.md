# Methods Flow Projection

This stage builds the generated files used by the UI methods section, including
the PRISMA-style paper flow. It does not replace the main-page graph payloads or
the evidence files. It projects the current corpus manifest, paper libraries,
abstract-screening reports, full-text conversion status, and the normalized KG
evidence table into a paper-flow view.

The route-native main-page graph payload is generated separately by
`pipeline/publish/export_evidence_payload.py`. The active main-page payload uses
the normalized KG evidence tables by default.

For a correction affecting only selected papers, use
[`docs/scoped_paper_updates.md`](../../docs/scoped_paper_updates.md). That
workflow removes every old raw/evidence row for the DOI scope, requires complete
current replacements, and rebuilds this KG layer without rerunning model
extraction for unaffected papers.

Run:

```bash
python pipeline/kg/build_methods_flow.py --refresh-kg-tables
```

Default outputs are written under `data/kg/`:

- `views/pipeline_status_graph.json`: UI-oriented PRISMA paper-flow payload.
- `schema/methods_flow.schema.json`: minimal methods-flow payload contract.
- `manifests/build_manifest.json`: counts, input files, and validation notes.

The methods-flow payload is generated from pipeline artifacts. Human curation
should continue to happen in `data/curated/*` or upstream review files.

The final PRISMA inclusion count is derived from the normalized KG evidence table.
The flow also reads the active extraction output named by
`data/processed/extraction/projection_report.json`, so full-text and abstract
branches can show Gemini-excluded, human-review, no-promoted-KG, and
not-yet-extracted counts separately.

## Normalized evidence tables

The main KG backbone is the normalized evidence-table layer:

```bash
RUN_ID=gemini3_flash_YYYYMMDD_first_batch
python pipeline/kg/convert_routed_extractions_to_evidence_rows.py \
  --run-id "$RUN_ID" \
  --input-jsonl "data/processed/extraction/routed_runs/$RUN_ID/route_extraction_outputs.jsonl" \
  --use-default-active-route-table
python pipeline/kg/build_evidence_tables.py --source-preset routed --run-id "$RUN_ID"
```

Routed extraction builds are versioned by default under
`data/processed/kg_routed_runs/<RUN_ID>/`.

When a reviewed routed run should replace the current KG table, make that
promotion explicit:

```bash
python pipeline/kg/build_evidence_tables.py \
  --source-preset routed \
  --run-id "$RUN_ID" \
  --out-dir data/processed/kg \
  --allow-current-overwrite
```

Each KG output directory contains:

- `papers.parquet`: one row per source paper represented in normalized evidence.
- `entities.parquet`: compounds plus normalized graph entities.
- `findings.parquet`: one rich normalized finding row per routed evidence record.
- `evidence_edges.parquet`: graph-oriented compound-to-entity evidence edges.
- `normalization_audit.parquet`: rows held back from graph promotion because a
  compound or right-side graph entity could not be normalized cleanly.
- `manifest.json`: table counts, source counts, and entity-kind summaries.
- `kg.duckdb`: optional local DuckDB database materialized when the `duckdb`
  Python package is installed.

The routed table layer preserves the complete extracted graph subject before
normalization. `graph_subject_kind` distinguishes an `atomic_compound` from a
`compound_class`, `compound_combination`, `exposure_context`, or
`treatment_regimen`. The exact text remains in `graph_subject_label` and is
shown in paper detail. It is not automatically made into a graph node.

The overview graph uses a deliberately smaller projection:

- atomic compounds use the canonical registry label;
- class and context strings must map to a controlled family such as
  `Serotonergic psychedelics`, `Mixed psychedelic compounds`,
  `Recreational psychedelic exposure`, `Chemsex`, or `Polysubstance use`;
- bare `Psychedelics` is not an overview label: generic wording is resolved
  from the claim context, or retained as `Unspecified psychedelic compounds`
  when the source provides no greater specificity;
- multi-compound rows use a focal registered compound when one is explicit,
  otherwise the controlled `Multi-compound exposure` summary;
- free-text subjects without a controlled projection remain paper-detail only.

For open-ended right-side concepts, pathway/readout and intervention labels are
projected to their controlled parent family. Every overview node, on either side
of the graph, must be supported by at least two distinct studies. Multiple
findings from one paper count once. Findings attached only to single-study nodes
remain in the detail bootstrap and search results; only their visual projection
is suppressed. This keeps the exact assay, marker, intervention, dose, and
subgroup information accessible without turning every extracted phrase into a
one-paper node.

`graph_admission_status` separates information storage from visible graph
admission. Rows marked `paper_detail` remain in `findings.parquet` but are
excluded from the UI graph bootstrap. Current deterministic holds include
primary-paper claims supported only by a background/introduction location,
extraction rows explicitly marked for human review, and structurally identical
propositions with conflicting normalized directions.

To apply these rules to an existing saved routed-evidence array without any
model call, enrich it into a new run directory and rebuild that run:

```bash
python pipeline/kg/enrich_saved_routed_evidence_rows.py \
  --input-json path/to/existing/routed_evidence_rows.json \
  --output-json data/processed/extraction/routed_runs/<new-run>/routed_evidence_rows.json \
  --report-json data/processed/extraction/routed_runs/<new-run>/deterministic_enrichment_report.json

python pipeline/kg/build_evidence_tables.py \
  --source-preset routed \
  --run-id <new-run> \
  --skip-duckdb
```

Compare the versioned result with its baseline using
`pipeline/validate/evaluate_deterministic_projection.py`. Its recovery counts
measure downstream representation only and must not be reported as extraction
recall or paper-level centrality.

The legacy current KG under `data/processed/kg/` may still contain
`claims.parquet` while the old pipeline is retained for comparison. New routed
KG runs use `findings.parquet` and `finding_id`.

Author identity is resolved as a separate KG-side layer after `papers.parquet`
exists:

```bash
python pipeline/kg/build_author_tables.py \
  --papers "data/processed/kg_routed_runs/$RUN_ID/papers.parquet" \
  --out-dir "data/processed/kg_routed_runs/$RUN_ID" \
  --cache "data/processed/kg_routed_runs/$RUN_ID/openalex_author_cache.json"
```

This writes:

- `authors.parquet`: one row per resolved author identity.
- `paper_authors.parquet`: ordered paper-author rows with first/last flags.
- `author_resolution_report.json`: OpenAlex vs fallback resolution counts.
- `openalex_author_cache.json`: cached OpenAlex authorship lookups for rebuilds.

This table layer is the preferred place to build new graph views. The browser UI
should continue to load compact JSON payloads generated from these tables rather
than loading the whole KG directly.

For a routed run, prefer:

```bash
scripts/build_routed_kg_payload.sh "$RUN_ID"
```

That wrapper rebuilds the evidence tables, author tables, and public payload in
the correct order. `pipeline/publish/export_evidence_payload.py` validates that
the author layer is present and newer than `papers.parquet` before writing UI
payloads, unless `--allow-stale-authors` is passed for a diagnostic export.

The converter reads route extraction outputs plus `route_extraction_tasks.jsonl`
and keeps one row per extracted finding or review/synthesis item. With
`--run-id`, it writes to
`data/processed/extraction/routed_runs/<RUN_ID>/routed_evidence_rows.json`.
The routed table builder reads the canonical routed evidence row file for the
selected run; the current-source builder does not mix routed extraction rows
into `data/processed/kg/` by accident.

The extraction-to-KG mapping is documented in
`docs/extraction_to_kg_mapping.md`, with the machine-readable mapping in
`schema/extraction_to_kg_mapping.json`. Use that mapping before adding or
renaming extraction fields that are meant to become graph nodes or graph-edge
attributes.

Seed alias vocabularies for newer node kinds are in
`schema/kg_node_vocabularies.json`. The evidence-table builder uses this file
to canonicalize common labels such as `DMN` to `Default mode network` while
pilot outputs reveal which aliases need to be added next.

The current main UI views are driven by `evidence_edges.entity_kind`:

- clinical: conditions, symptoms, safety/adverse events, and outcome scales
  currently have graph rows.
- mechanistic: targets, pathways/processes, molecular readouts, and
  systems/families currently have canonical graph rows.
- routed extension domains: brain regions/networks/circuits, cognitive or
  behavioral constructs, subjective-experience constructs, PK/exposure
  parameters, intervention components, and public-health measures are supported
  by the normalized table layer before they are promoted into dedicated UI
  views.

Clinical endpoint rows are derived from raw disorder extraction rows plus the
normalization audit. They keep only rows with canonicalized compounds and label
the endpoint separately from the condition field, so endpoint views do not
pollute the default condition graph.

Functional/patient-reported endpoints are retained in the raw extraction
details but are not promoted into a standalone graph layer. In practice this
category was too narrow and too ambiguous: wellbeing, quality of life,
functioning, and social connectedness often behave more like contextual outcome
details than stable graph nodes. If we revisit this later, it should be as a
new explicitly defined view rather than as a generic function bucket.

Condition versus symptom routing is row-aware. Broad condition strings such as
`depression`, `anxiety`, and `pain` are not promoted to visible condition nodes
unless the text also names a specific graphable condition. Specific diagnoses or
indications, such as major depressive disorder, treatment-resistant depression,
bipolar depression, social anxiety disorder, chronic pain, neuropathic pain, or
migraine, remain eligible for the condition view. Endpoint-only symptom rows
still route to symptom/problem labels rather than condition nodes.

For new search runs, rebuild the corpus tables, routing tables, routed
extraction outputs, and normalized KG tables before rerunning
`python pipeline/kg/build_methods_flow.py --refresh-kg-tables`. The methods
PRISMA flow should be regenerated from pipeline artifacts rather than edited in
UI data by hand.
