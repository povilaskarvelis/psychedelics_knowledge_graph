# Publish Prep: Evidence Payload Export

This step exports compact route-native evidence files for the web UI. The
public site reads a manifest plus graph, dashboard, and detail bootstrap files
keyed by the actual routed extraction domains, not by the old two-dataset UI
split.

The browser can still render the existing graph, cards, filters, and
bibliography layout. It derives its display grouping from each finding's
`domain` and `entity_kind` after loading the compact detail bootstrap.

Paper payloads and the public query catalogue carry compact provider-backed
funding fields (`funders`, `grant_ids`, provider/status fields, and counts).
The complete assertion-level funding provenance remains in the versioned KG
table rather than being duplicated into every finding or turned into evidence
edges.

## Run

Build a versioned routed KG and payload without changing the public graph:

```bash
RUN_ID=gemini3_flash_YYYYMMDD_first_batch
scripts/build_routed_kg_payload.sh "$RUN_ID"
```

After reviewing that versioned run, promote it without rebuilding it:

```bash
python pipeline/publish/promote_routed_run.py --run-id "$RUN_ID"
```

If the evidence snapshot is unchanged and only authors, public export logic,
API fields, or browser payloads changed, use the synchronized public refresh:

```bash
bash scripts/refresh_public_release.sh
```

It regenerates the graph and API from the current KG run, binds both manifests
to one new public release ID, validates and rebuilds the site, publishes the
allowlisted graph and Methods artifacts to the public R2 bucket and the API
runtime to its separate private R2 bucket, and triggers the configured API
deploy hook. After both active pointers have been verified, it deletes
superseded browser/API release objects and older local versioned release
directories, leaving only the active run. Generated public payloads are no
longer committed to Git. It never changes extraction or evidence decisions.

The promoter validates the KG, payload, author tables, and extraction inputs;
materializes every final graph decision into the canonical
`candidate_papers.parquet` corpus ledger; serializes promotions with a lock;
stages the Methods and `dist/` rebuilds; and updates the extraction and
public-graph compatibility pointers to the same release. The promotion fails if
the routed output stream contains any legacy v1 meta-analysis or review
contract; those archived outputs are audit-only and must be re-extracted through
the dedicated current secondary-literature pipelines. It also fails if
any selected report lacks a final disposition or if screening, routing, graph,
or release decisions contradict one another. `ACTIVATE_DEFAULT=1
scripts/build_routed_kg_payload.sh "$RUN_ID"` remains a one-command
build-and-promote shorthand and uses the same guarded promoter.

The wrapper is non-activating by default. This keeps historical or diagnostic
rebuilds from changing the public graph by accident. The publisher validates
the local pointer and every required graph and Methods artifact before switching
the R2 pointer. The promoter separately checks that the extraction pointer,
public pointer, and canonical corpus identify the same release; that deeper check
stays in promotion because its extraction and Parquet inputs are intentionally
not part of a clean deployment checkout.

Promotion copies reused combined extraction outputs into the promoted run
directory before activation. This makes the active release self-contained and
allows history pruning to fail closed if any pointer still depends on an older
run.

If the KG tables have already been rebuilt and only the public payload needs to
be regenerated, make sure `pipeline/kg/build_author_tables.py` has run after the
last `papers.parquet` change. The exporter checks `authors.parquet`,
`paper_authors.parquet`, and
`author_resolution_report.json` against `papers.parquet` by default and fails
when the author layer is missing or stale. `--allow-stale-authors` is available
only for deliberate diagnostic exports.

Promotion also rebuilds the Methods PRISMA flow and unified bibliography solely
from the updated canonical corpus ledger. The Methods build has no fallback to
the routed KG, active pointers, normalization audit, or disposition override
file. Do not run a separate bibliography step afterward.

## Outputs

- `data/processed/graph_payload_active.json`
- `data/processed/extraction/active_routed_run.json`
- `data/processed/graph_payload_runs/<RUN_ID>/graph_payload_manifest.json`
- `data/processed/graph_payload_runs/<RUN_ID>/graph_bootstrap_<source>.json`
- `data/processed/graph_payload_runs/<RUN_ID>/dashboard_bootstrap_<source>.json`
- `data/processed/graph_payload_runs/<RUN_ID>/detail_bootstrap_<source>.json`
- `data/kg/views/pipeline_status_graph.json`
- `data/kg/views/methods_bibliography.json`
- `data/kg/views/graph_inclusion_dispositions.json`

These are generated local outputs. The graph and Methods files are uploaded
together under one immutable public R2 release and are not copied into the
Netlify bundle or committed to Git.

## Contract

The extraction and public graph pointers are compatibility views for different
consumers, not independent evidence switches. They contain the same evidence
`release_id` after guarded promotion. The public graph pointer also has a
`public_release_id`, shared by its graph manifest and the API manifest whenever
either public representation is regenerated. The extraction pointer additionally names
the combined raw outputs and evidence rows required by the next scoped update;
the public graph pointer names only compact browser artifacts.

`graph_payload_manifest.json` contains:

- `schema_version`
- `evidence_source`
- `kg_dir`
- `row_count`
- `release_id` (the synchronized public graph/API revision)
- `evidence_release_id` (the unchanged underlying evidence snapshot)
- `files` (path, byte size, and SHA-256 for every browser payload)
- `author_tables`
- `summary_stats`
- `graph_bootstraps`
- `dashboard_bootstraps`
- `detail_bootstraps`

Each generated Methods artifact also contains the canonical graph `run_id` and
evidence `release_id`. The local preview server and public R2 publisher require
those values to match the graph manifest, so a stale bibliography or Methods
flow cannot be mixed into a candidate or published release.

## Review before R2 publication

Build and promote a candidate locally without setting `PUBLISH_QUERY_API_R2=1`.
Promotion updates the local graph pointer and rebuilds the matching Methods
artifacts, but does not change either R2 bucket. Review that exact candidate with:

```bash
bash scripts/preview_site.sh local
```

The preview URL contains `?data-source=local`, and internal navigation preserves
the selection across Graph and Methods. After approval, publish the already-
validated release with the R2 commands in `docs/r2_deployment.md`; commit and
deploy code changes separately when there are any.

Preview mode must always be explicit. A public preview cannot serve a URL that
requests `data-source=local`, and a local preview refuses to start unless every
allowlisted file belongs to the same release.

`summary_stats.paper_counts` is the generated source of truth for the four
public header metrics: primary studies, reviews, meta-analyses, and their total
represented anywhere in the underlying normalized evidence graph. These values
are deduplicated by DOI, then OpenAlex ID, then title and year, and regenerated
whenever the routed KG payload is exported. A report does not need to appear in
the visual overview to count as graph-represented. Reports that are not
represented are explained, with final plain-language reasons, in the Methods
page PRISMA flow. `visualized_overview_represented` retains the stricter
visual-overview counts for diagnostics; primary studies and reviews use the
two-report overview-node rule, while meta-analyses use a one-report rule.

`graph_bootstrap_<source>.json` contains aggregate graph edges for
fast initial rendering: compound, graph-anchor entity label, graph-anchor
entity kind, finding count, study count, and full-text-seen counts. It is
intentionally limited to graph-visible anchor kinds. Metadata/detail kinds such
as outcome scales, compound classes, symptoms and outcomes, brain measures, and
pharmacokinetic parameters stay out of this aggregate graph file.

`dashboard_bootstrap_<source>.json` contains the complete condition rows and
supporting outcome-scale rows needed for the initial right-hand dashboard and
year bounds. It uses the same compact columnar encoding as the detail payload,
but excludes unrelated entity views so the graph and default dashboard can
paint together before the full corpus is downloaded. The full detail payload
replaces this provisional working set without changing the rendered summaries.

`detail_bootstrap_<source>.json` contains the row-level public UI
data in a compact field/value/row representation:

- `fields[]`
- `values[]`
- `rows[]`

The decoded rows are flat and route-native. Important fields include:

- `domain`
- `finding_type`
- `evidence_type`
- `compound`
- `entity_label`
- `entity_kind`
- `text_depth`
- report metadata such as `study_doi`, `openalex_id`, `study_title`, and `study_year`
- domain-specific evidence fields such as `support`, `effect_size`,
  `outcome_measure`, `sample_size_total`, `mechanism_type`, `assay_type`, and
  `assessment_timepoint`
- meta-analysis fields currently rendered by the interface, such as result
  role, population, comparator, follow-up window, included-study count,
  heterogeneity summary, subgroup or moderator, risk-of-bias summary, and
  evidence strength

The field list is a default-private publication allowlist. Unused statistical,
network-meta-analysis, quotation, extraction-warning, normalization, and graph
audit fields are excluded even if they exist in the internal findings table.
The exporter fails if a forbidden internal field is added to the browser
contract without an explicit policy and test change.

Detail rows may include metadata/detail entity kinds that are not graph
anchors, such as `outcome_scale`, `compound`, `symptom_problem`, and
`pharmacokinetic_parameter`. These feed right-panel facets and evidence cards;
they are not top-level graph views.

The meta-analysis right panel uses clickable stacked-bar filters for synthesis
design, comparator, follow-up window, and included-study count.
Article-text filtering is handled by the shared control above the graph, and
population and result role remain finding context rather than composition plots. More
sparsely reported assessments such as heterogeneity, risk of bias, and certainty
are shown in finding cards when present rather than treated as complete
composition fields.

Primary-research and review graph nodes require support from at least two source
reports. Meta-analysis nodes are exempt from that replication threshold because
each source report already represents a synthesis and the meta-analysis graph is
comparatively sparse.

The public export does not use the old `claim_type` field, does not split
routed findings into multiple legacy export files, and does not publish the
heavy full-evidence JSON dump.
