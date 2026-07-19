# Methods Flow Projection

This stage builds the generated files used by the UI methods section, including
the PRISMA-style record and report flow. It does not replace the main-page graph
payloads or the evidence files. It projects one canonical DOI-level corpus
ledger, `data/processed/corpus/candidate_papers.parquet`, into the selection-flow
and bibliography views. That ledger must already contain every screening,
extraction-routing, graph-inclusion, final disposition, and release-provenance
decision. Missing or contradictory decisions stop the build.

The route-native main-page graph payload is generated separately by
`pipeline/publish/export_evidence_payload.py`. The active main-page payload uses
the normalized KG evidence tables by default.

For a correction affecting only selected reports, use
[`docs/scoped_paper_updates.md`](../../docs/scoped_paper_updates.md). That
workflow removes every old raw/evidence row for the DOI scope, requires complete
current replacements, and rebuilds this KG layer without rerunning model
extraction for unaffected reports.

Run:

```bash
python pipeline/kg/build_methods_flow.py \
  --candidate-table data/processed/corpus/candidate_papers.parquet \
  --out-dir data/kg
```

Default outputs are written under `data/kg/`:

- `views/pipeline_status_graph.json`: UI-oriented PRISMA record-and-report flow
  payload.
- `schema/methods_flow.schema.json`: minimal methods-flow payload contract.
- `manifests/build_manifest.json`: counts, input files, and validation notes.

The methods-flow payload and full bibliography are generated solely from the
canonical corpus ledger. Human curation happens upstream in `data/curated/*` or
screening records, and promotion materializes those resolved decisions into the
ledger before this projection runs. The Methods builder never fills gaps from
active graph payloads, normalization audits, extraction pointers, or manual
disposition files.

## Normalized evidence tables

The main KG backbone is the normalized evidence-table layer:

Meta-analysis v2 outputs have a separate fail-closed conversion step. Convert
each extraction run before combining its accepted evidence rows with the routed
evidence input used by the KG builder:

```bash
python pipeline/kg/convert_meta_analysis_v2_to_evidence_rows.py \
  --run-id meta_analysis_v2_remaining_168_20260712
```

The converter preserves result-level estimates, intervals, p values, evidence
counts, heterogeneity, analysis context, network details, risk-of-bias and
certainty summaries, and source provenance. It holds results that lack a stable
subject or entity, bundle multiple estimates, or claim a network result without
network structure. Report-level population or comparator context is used only
when exactly one value is available, and the provenance of that fallback is
recorded. The KG builder also preserves the analysis role, exact endpoint,
population, comparator, follow-up window, included-study count, subgroup or
moderator, sensitivity method, network treatments, effect metric, and dose when
grouping propositions. This prevents distinct pooled estimates from being
collapsed or incorrectly flagged as contradictory.

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

The routed build wrapper is staging-only by default. Once a versioned KG and
payload have been reviewed, use the guarded publisher so extraction, graph,
Methods, and public-site state advance as one release:

```bash
python pipeline/publish/promote_routed_run.py --run-id "$RUN_ID"
```

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

- `papers.parquet`: one row per source report represented in normalized evidence.
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
shown in report detail. It is not automatically made into a graph node.

The overview graph uses a deliberately smaller projection:

- atomic compounds use the canonical registry label;
- class and context strings must map to a controlled family such as
  `Classic psychedelics`,
  `Recreational psychedelic exposure`, `Chemsex`, or `Polysubstance use`;
- bare `Psychedelics` is not an overview label: generic wording is resolved
  from the finding context, or retained in detail as `Psychedelics (mixed or
  unspecified compounds)` when the source provides no greater specificity;
- broad text that explicitly says one or more compounds were predominant, or
  names a drug-specific assisted therapy, projects to those atomic compounds;
  partly specified and fully unspecified groups share the detail-only fallback
  rather than being attributed to the one named drug;
- multi-compound rows use a focal registered compound when one is explicit;
  otherwise, exact lists or separate arms project to each registered compound,
  while supported co-administration projects to a canonical `A + B` node and
  supported sequences to `A + B (sequential)`;
- controlled colloquial aliases are inferred from the canonical combination
  and shown parenthetically, for example `LSD + MDMA (candyflipping)`;
- named-combination aliases are defined once in
  `pipeline/kg/compound_combinations.py` and carried into graph payloads as
  searchable aliases. The automatically inferred set is pharmahuasca
  (`DMT + Harmine/Harmaline`), candyflipping (`LSD + MDMA`), hippy/hippie
  flipping (`Psilocybin + MDMA`), kitty flipping (`Ketamine + MDMA`), nexus
  flipping (`2C-B + MDMA`), and Jedi/twilight flipping
  (`LSD + Psilocybin + MDMA`). Less-established but chemically unambiguous
  terms—soul bombing/wizard flipping, Ali flipping, love flipping, and Selma
  flipping—are recognized only when the source explicitly uses the alias;
- `graph_overview_subjects_json` carries every controlled projection for a
  finding, so one finding can support several graph edges without duplicating
  the finding or losing its exact exposure text;
- broad class/context nodes are retained only when the saved exposure is truly
  nonspecific; contextual exposures such as chemsex are never atomized;
- real-world findings can additionally carry
  `graph_use_context_projections_json`. These preserve the finding once while
  adding explicit `substance -> use context` relationships such as
  `Ketamine -> Chemsex`; they are generated only from finding-level context and
  exposure text, never from report titles or keywords. The substance must also
  pass the normal psychedelic-graph compound scope check, so contextual mentions
  of cocaine, methamphetamine, mephedrone, GHB, or GBL remain in finding detail
  rather than becoming compound nodes;
- `Chemsex` is a controlled child of `Sexualized drug use`. Exact chemsex
  statements remain attached to Chemsex, while broader substance-linked-sex
  statements attach to the parent context. The original
  `context -> outcome/topic` projection remains separate;
- the unresolved psychedelic fallback is searchable but not admitted to the
  overview graph, where it would form a high-degree catch-all hub;
- free-text subjects without a controlled projection remain report-detail only.

For open-ended right-side concepts, pathway/readout and intervention labels are
projected to their controlled parent family. Every overview node, on either side
of the graph, must be supported by at least two distinct studies. Multiple
findings from one report count once. Findings attached only to single-study nodes
remain in the detail bootstrap and search results; only their visual projection
is suppressed. This keeps the exact assay, marker, intervention, dose, and
subgroup information accessible without turning every extracted phrase into a
one-report node.

`graph_admission_status` separates information storage from visible graph
admission. Rows marked `paper_detail` remain in `findings.parquet` but are
excluded from the UI graph bootstrap. Current deterministic holds include
primary-report findings supported only by a background/introduction location,
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
recall or report-level centrality.

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
- `paper_authors.parquet`: ordered source-report author rows with first/last flags.
- `author_resolution_report.json`: structured identity coverage and unresolved-row counts.
- `openalex_author_cache.json`: cached OpenAlex authorship lookups for rebuilds.

The command refuses to replace the author tables unless at least 95% of
authorship rows have an OpenAlex or ORCID identity. Offline builds also require
successful cached authorships for at least 95% of the DOI-bearing paper set. For
a new offline routed run, provide the cache explicitly:

```bash
AUTHOR_CACHE_SEED=/path/to/openalex_author_cache.json \
  scripts/build_routed_kg_payload.sh "$RUN_ID" --offline
```

This table layer is the preferred place to build new graph views. The browser UI
should continue to load compact JSON payloads generated from these tables rather
than loading the whole KG directly.

For a routed run, prefer:

```bash
scripts/build_routed_kg_payload.sh "$RUN_ID"
```

That wrapper rebuilds the evidence tables, author tables, and a versioned payload
in the correct order without changing the active graph. After validating the
versioned run, activate it explicitly with:

```bash
ACTIVATE_DEFAULT=1 scripts/build_routed_kg_payload.sh "$RUN_ID"
```

An activating build also refreshes the Methods PRISMA flow and bibliography from
the same routed KG run. `pipeline/publish/export_evidence_payload.py` validates that
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

- clinical outcomes: conditions, symptoms, safety/adverse events, and outcome scales
  currently have graph rows.
- molecular and biological: targets, pathways/processes, molecular readouts, and
  systems/families currently have canonical graph rows.
- routed extension domains: brain regions/networks/circuits, cognitive or
  behavioral constructs, subjective-experience constructs, PK/exposure
  parameters, intervention components, and public-health measures are supported
  by the normalized table layer before they are promoted into dedicated UI
  views.

Clinical endpoint rows are derived from routed clinical-outcome rows plus the
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

For new routed runs, rebuild the corpus tables, routing tables, routed
extraction outputs, and normalized KG tables, then promote the routed release.
Promotion first validates and updates the canonical corpus ledger, and only
then regenerates the Methods PRISMA flow and bibliography. Do not edit the UI
data by hand.
