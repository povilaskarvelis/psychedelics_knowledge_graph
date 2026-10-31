# Knowledge graph processing

## Saved-extraction coverage audit

Before requesting another extraction, reconcile the complete staged cohort with
the existing answers and graph tables:

```bash
python -m pipeline.kg.audit_saved_extraction_coverage \
  --release /path/to/frozen-release \
  --kg /path/to/staged-kg-tables \
  --out /path/to/new-coverage-audit
```

The frozen release supplies `selected_dois.txt` and `inputs/` with the primary,
review and meta task/output JSONL files and its DOI alias registry. The audit
writes separate report, task/profile, area/family and normalization-reason
inventories. It canonicalizes report identifiers on both sides of the join and
counts guideline recommendations as objects. It does not alter source data or
the graph, and refuses to overwrite a completed audit.

An empty profile response does not mean that the paper has no findings in other
profiles. Shared extraction profiles are not interchangeable with graph areas;
area accounting uses actual evidence-edge kinds and the graph-view contract.
Main-admitted findings, visible area membership, paper-detail findings and
normalization audits remain distinct. These processing inventories are not
error estimates. Source review must distinguish correctly empty results,
evidence saved elsewhere, blocked saved objects and findings absent from saved
answers. Missing results cannot be manufactured by normalization. For blocked
objects, first check whether the saved fields support a deterministic repair;
missing or incorrect source fields may instead require source correction or
targeted extraction. Preserve mixed-exposure and comparator attribution when
repairing saved objects.

## Methods flow projection

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

### Combined historical + update releases

An updated KG is assembled as one release, not published as a disconnected
"new papers" graph. `assemble_combined_release.py` starts from the historical
routed evidence, applies complete-paper overlays for new primary, review-v2,
and meta-analysis-v2 outputs, canonicalizes DOI aliases, and applies the
current candidate-eligibility gate. If an overlay contains a DOI, its complete
previous evidence contribution is replaced; stale findings from a newly
excluded report cannot survive through the base release.

The assembler also removes obsolete V1 review/meta-analysis audit outputs and
fails closed if any meta-analysis evidence row is not from the V2 converter.
This prevents a historical V1 secondary extraction contract from surviving in
or re-entering a current combined release.

For an overlay that legitimately produces no evidence rows for some papers,
pass `--evidence-replacement-cohort LABEL=PATH`. The cohort declares every DOI
whose complete prior contribution must be replaced, so a valid zero-result
extraction deletes stale evidence instead of silently leaving it behind.

```bash
python pipeline/kg/assemble_combined_release.py \
  --run-id "$RUN_ID" \
  --base-evidence data/processed/extraction/routed_runs/<base>/routed_evidence_rows.json \
  --evidence-overlay primary_update=<primary-evidence.json> \
  --evidence-overlay review_update_v2=<review-v2-evidence.json> \
  --evidence-overlay meta_analysis_update_v2=<meta-v2-evidence.json> \
  --base-outputs data/processed/extraction/routed_runs/<base>/route_extraction_outputs.jsonl \
  --output-overlay primary_update=<primary-outputs.jsonl> \
  --candidate-table data/processed/corpus/candidate_papers.parquet \
  --doi-alias-registry pipeline/validate/doi_alias_registry.json \
  --out-dir "data/processed/extraction/routed_runs/$RUN_ID"
```

The subsequent KG build reads that combined evidence run. It writes compact
funding summaries on `papers.parquet` and a release-scoped
`paper_funding.parquet` containing the full normalized provider assertions.
Funding is paper metadata/provenance, not a scientific finding edge.
The KG build applies `pipeline/validate/doi_alias_registry.json` to both paper
and funding identities before writing release-scoped assertions.

Before Methods promotion, `update_corpus_graph_status.py` reconciles every
selected report to a represented finding, normalization-audit decision,
explicit disposition, or terminal completed-extraction outcome supplied with
one or more `--extraction-results` JSONL files. A selected report absent from
all of those sources stops the release and is an extraction gap; it is never
silently labeled as a completed no-finding report.

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
RUN_ID=luna_v5_YYYYMMDD_first_batch
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
- `paper_funding.parquet`: provider-attributed funder/award assertions for the
  DOI set in this KG release.
- `entities.parquet`: compounds plus normalized graph entities.
- `findings.parquet`: one rich normalized finding row per routed evidence record.
- `evidence_edges.parquet`: graph-oriented compound-to-entity evidence edges.
- `normalization_audit.parquet`: rows held back from graph promotion because a
  compound or right-side graph entity could not be normalized cleanly.
- `research_area_review_queue.parquet`: deterministic research-area flags,
  including unresolved normalization records.
- `manifest.json`: table counts, source counts, and entity-kind summaries.
- `kg.duckdb`: optional local DuckDB database materialized when the `duckdb`
  Python package is installed.

### Research-area adjudication overlay

The routing queue is advisory. To persist a review decision for every queued
record and materialize only high-confidence graph holds, apply the versioned
overlay after a candidate build:

```bash
python pipeline/validate/apply_research_area_adjudications.py \
  --candidate-dir data/processed/kg_routed_runs/<RUN_ID> \
  --out-dir data/processed/kg_routed_runs/<RUN_ID>_adjudicated \
  --audit docs/evaluation/research_area_audit_2026-09-06/high_confidence_findings.csv \
  --reviewed-at 2026-09-06
```

This step makes no model calls. It writes
`research_area_adjudications.parquet`/`.csv` and a queue with decisions joined
back to each record. `corrected` rows with a `hold_*` action lose their
evidence edge and remain in paper detail; rows with
`route_to_existing_replacement_projection` retain the deterministic
replacement edge. `unresolved` rows keep their original graph projection and
carry an explicit reason for later source-level review. The overlay is a
versioned staging output and is not the active release until it passes the
normal promotion checks.

For a follow-up semantic pass over unresolved rows that are still visible in
the main graph, apply the second-pass overlay:

```bash
python pipeline/validate/apply_research_area_second_pass.py \
  --first-pass-dir data/processed/kg_routed_runs/<RUN_ID>_adjudicated \
  --out-dir data/processed/kg_routed_runs/<RUN_ID>_second_pass \
  --reviewed-at 2026-09-06
```

This pass is deterministic and makes no model/API calls. It reviews the saved
support statement together with the current area and normalized entity kind,
groups repeated exact statement/projection rows, and records one decision for
each group. It writes
`research_area_second_pass_decisions.parquet`/`.csv`, updates the combined
adjudication ledger, and removes only explicitly corrected `hold_*` edges from
the staged evidence table. Rows already held in paper detail and
normalization-audit records remain unresolved until a source-level review can
provide a safe replacement. The output remains a versioned staging overlay.

Molecular finding subtopics are assigned by the versioned taxonomy recorded in
`manifest.json` as `molecular_subtopic_taxonomy_version`. The matcher first uses
the exact normalized entity and readout fields. Only when those fields do not
identify a specific subtopic does it consult supporting finding text, assay,
tissue, and system context. Broad `Other` assignments remain residual rather
than satisfying the coverage audit. For every molecular parent with at least 50
primary-evidence findings, the build fails closed when more than 20% remain
residual; the threshold is not relaxed for new extraction batches.

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

Reviewed identity corrections live in `author_identity_overrides.json`. Profile
merges use the existing `overrides` records; `authorship_overrides` correct a
specific DOI and author position before ORCID propagation. Each scoped record
requires exact expected source names/identifiers, replacement identifiers,
reviewer/date, reason, and source links. Changed source records or propagation
that restores a rejected ORCID stop the build for renewed review. Authorship
tables retain original identifiers in `source_*` columns and link corrections
through `identity_review_id`; the OpenAlex cache is not rewritten.

The override file also stores reviewed identity decisions that do not fit a
single OpenAlex-to-ORCID mapping:

- `profile_alias_reviews` joins duplicate OpenAlex profiles when no verified
  ORCID is available.
- `orcid_alias_reviews` joins two ORCIDs verified to belong to one researcher.
- `distinct_identity_reviews` records same-name groups verified to contain
  different people, so future audits do not reopen the same case.

All three require a review ID, reason, reviewer/date, and source links. A scoped
DOI-and-position correction has precedence over these broader mappings. The
builder also rejects any broader mapping or another authorship row that would
reintroduce the ORCID explicitly rejected by that scoped review.

`author_list_reviews` stores publication-specific corrections to complete author
lists. Each review fingerprints the original ordered source names and identifiers,
then explicitly selects retained source positions and (where a source profile was
shifted onto another name) the identity donor position. Unsupported profile matches
can be cleared to name-only identities. There is no global name deduplication:
consortium credits and unresolved same-name cases remain available for review.
Changed source fingerprints stop the build. Output rows retain original source
position/name/identifiers and `author_list_review_id`; the resolution report records
removed positions. Review decisions, including attempted-but-unresolved cases,
are documented under `docs/evaluation/author_identity_*/`.

Every `scripts/build_routed_kg_payload.sh` run writes this audit under the
run's `author_identity_audit/` directory before exporting browser or API
payloads. When `REVIEW_BASELINE_DIR` is set, it also writes focused
`new_name_candidates.json`, `new_priority_name_candidates.json`, and
`new_same_paper_name_collisions.json` queues. New duplicate positions,
one identity attached to different names on a paper, or orphan authorships stop
the build. Repeated publication-supplied bylines with the same name remain in
the review artifacts without blocking the build.
Name/coauthor similarity remains a review signal and never merges identities
automatically.

Name-only authorships are joined to a unique structured identity only when the
exact name has at least two shared coauthors, the identities never co-occur on a
paper, and the name-only row is not protected by a source review. Exact name
alone is deliberately insufficient for common names.

To generate the same review artifacts directly:

```bash
python pipeline/validate/audit_author_identities.py \
  --kg-dir "data/processed/kg_routed_runs/$RUN_ID" \
  --out-dir "data/processed/evaluation/author_identity/$RUN_ID" \
  --baseline-dir "data/processed/kg_routed_runs/$BASELINE_RUN_ID" \
  --fail-on-new-integrity-errors
```

This standalone audit distinguishes possible name splits, repeated identities
within papers, and conflicting ORCIDs. Candidate counts are not confirmed-error
counts. Confirm corrections against independent author/publication records and
rebuild into a staging directory before promoting new graph payloads.

The command refuses to replace the author tables unless at least 95% of
authorship rows have an OpenAlex or ORCID identity. Offline builds also require
successful cached authorships for at least 95% of the DOI-bearing paper set. For
a new offline routed run, provide the cache explicitly:

```bash
AUTHOR_CACHE_SEED=/path/to/openalex_author_cache.json \
  scripts/build_routed_kg_payload.sh "$RUN_ID" --offline
```

Cached DOI keys alone do not establish report identity. The author builder
rejects conflicting DOI values and clearly unrelated source titles, retries
suspect cache entries during online builds, and retains supplied citation names
without borrowing the unrelated work's author identifiers. Subtitles and markup
differences are allowed. An existing source-reviewed byline with an unchanged
fingerprint takes precedence over the lexical title check, including verified
translated titles. Unresolved identifier conflicts stay out of public author
facets; they do not exclude papers or their scientific findings.

Author-only refreshes can reuse the saved scientific KG tables: rebuild these
two author tables, run the audit against the last reviewed release, then export
with the normal author freshness check enabled. Do not carry a diagnostic
`--allow-stale-authors` export into a final release. The 29 October 2026 audit
and source decisions are under
`data/processed/model_runs/luna_v5_20261017/author_identity_refresh_20261029/`.

The follow-up source decisions and full saved-answer replay are under
`data/processed/model_runs/luna_v5_20261017/author_and_coverage_repairs_20261029/`.
Those decisions include report-scoped corrections for namesake ORCIDs and
verified split profiles. A blank same-name ORCID record is not globally aliased
to an established researcher. Aggregate author confidence also preserves the
conflict status of its authorships, so the summary author table cannot silently
restore a quarantined profile to public facets.

When `EVIDENCE_RUN_ID` points to an existing KG run, the integrated builder
automatically seeds the new candidate from that run's author cache. Set
`AUTHOR_CACHE_SEED` only to override that source explicitly. Missing offline
cache inputs and active/baseline carry-forward targets are rejected before the
expensive evidence build begins.

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

Compound identities and aliases are maintained in
`data/curated/entity_registry.json`, with the compound allowlist in
`pipeline/config.example.yaml`. Phencyclidine is an eligible graph compound;
`PCP` and `phencyclidine (PCP)` normalize to `Phencyclidine`. It is not a
reference/control-only compound. Substituted PCP analogues keep their own
identities and are not automatically merged into the parent. Adding the registry
entry prepares future normalization; it does not rebuild or publish the graph.

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

## Research-area routing and review queue

`research_area_review.py` supplies conservative routing boundaries and advisory
review flags. It makes no model/API calls. The builder now writes
`research_area_review_queue.parquet` alongside its evidence tables, including
flagged normalized findings and flagged normalization failures. The manifest's
`research_area_review` section records the rule version and counts by reason
and record type.

Current deterministic changes protect negated/population psychosis context,
resolve explicit depression/suicidality endpoints in those rows, retain serious
psychosis in Safety rather than transient Cognition, and route narrow explicit
safety endpoints out of clinical outcomes. Ketamine-to-ketamine-associated-
uropathy condition projections are held in paper detail: the exposure is not
established as a treatment, and surgery/cessation outcomes require review.

The fields on findings and review-queue rows distinguish:

- `research_area_input_json`: source classification/anchor before these routing
  rules; this is not an independently reviewed classification.
- `research_area_routing_version` and `research_area_rule_actions_json`:
  automatic routing provenance. Existing normalization fields retain their
  additional normalization reasons.
- `research_area_classification_origin`: the candidate builder writes
  `deterministic`; the adjudication overlay changes corrected rows to
  `agent_reviewed` and leaves unresolved rows deterministic.
- `research_area_review_status`: `pending` or `not_flagged`. Neither means an
  adjudicator has accepted the finding; `not_flagged` does not certify accuracy.
- `research_area_review_reasons_json`: explainable ambiguity triggers, separate
  from extraction's `needs_human_review` admission flag.
- `research_area_evidence_fingerprint`: hash of DOI, compound, saved support,
  quote and location, allowing a future adjudication to detect changed evidence.

Review flags do not change admission. Explicit routing/admission boundaries
still can. The queue therefore includes both graph-admitted findings and
already-held records. `record_type=normalization_audit` rows do not have a
normalized finding ID; use their evidence fingerprint and source metadata.
The raw extraction files are never modified.

For a staged build and comparison against the September audit:

```bash
python pipeline/kg/build_evidence_tables.py \
  --run-id research_area_routing_20260906 \
  --evidence-run-id full_corpus_normalization_patch_qa_20260724 \
  --skip-duckdb
python pipeline/validate/evaluate_research_area_routing.py \
  --audit docs/evaluation/research_area_audit_2026-09-06/high_confidence_findings.csv \
  --candidate-dir data/processed/kg_routed_runs/research_area_routing_20260906 \
  --out-dir docs/evaluation/research_area_routing_2026-09-06/full
```

The comparison distinguishes remaining flags, held projections, changed
projections, normalization-review records and missing matches. Absence alone is
not counted as a correction. This step does not promote or publish the graph.
Apply the adjudication overlay shown above to persist the current conservative
decisions; unresolved records remain explicit for later source-level review.

For a release candidate, follow the deterministic pass with the replayable QA
gate:

```bash
python pipeline/validate/apply_research_area_release_qa.py \
  --second-pass-dir "data/processed/kg_routed_runs/$SECOND_PASS_RUN" \
  --out-dir "data/processed/kg_routed_runs/$RELEASE_RUN" \
  --overrides data/curated/research_area_release_qa_overrides.json \
  --run-id "$RELEASE_RUN"
```

The gate records review provenance in `research_area_release_qa.parquet` and
finalizes all second-pass decisions in `research_area_final_decisions.parquet`.
The current policy reviews every proposed correction, every unresolved
main-graph row using source context, and a hash-stable stratified sample of
automatic confirmations. A release is eligible for promotion only when its
final corrected findings have no evidence edges, its final confirmed findings
all have edges, and the main-graph second-pass scope has no unresolved rows.

Research-area views are selected from the normalized `entity_kind` contract.
The extraction `domain` remains useful provenance, but a domain mismatch alone
does not establish a wrong visible area. Version v3 of
`research_area_second_pass.py` applies this rule so valid safety and condition
projections are not suppressed merely because their extraction domain differs.
# Normalization contract repairs (26 October 2026)

The `general_primary` fallback retains its explicit `entity_or_endpoint`,
measurement method, sample/system and result as a `reported_measurement` in paper
detail. It never defaults a sample description to a clinical diagnosis. These
generic findings need an explicit compatible domain mapping before entering the
main graph.

Equivalent psychedelic-assisted therapy labels share the existing controlled
therapy projection across subject kinds. Exact drug identities, including the
verified mebufotenin/GH001 aliases of 5-MeO-DMT, remain in the compound registry.
This does not authorize mapping modified analogues to their parent drug.

Review conversion selects a uniquely eligible typed subject independently of
anchor order, excludes comparator anchors from that selection, and preserves
ambiguous recovered multi-drug relationships in detail. Explicit preclinical
behavioral outcomes use the behavioral domain; genuine animal safety outcomes
remain on the existing safety normalization path. Scope and prominence gates
remain in force. `normalization_contract_version` records this revision in new
build manifests.

### Deterministic normalization integrity checks

The standard routed converters and `build_evidence_tables.py` now preserve the
roles recorded in saved extraction fields when choosing subjects and graph
objects. These rules run on future builds as well as saved-output replays:

- Named review anchors can project to their declared compatible domains. A
  comparator or a context mention does not become the actor, and an ambiguous
  multi-drug proposition stays in detail rather than selecting its first drug.
- Meta-analysis rows retain the statistical unit (pooled interventions, control
  arms and comparisons), dependent outcome and multiplicity adjustment. One
  estimate is not copied across several drugs or conditions. Explicitly
  secondary, uncorrected neuroimaging peaks remain in detail alongside corrected
  main results; this is not a general significance filter and null findings are
  preserved. Statistical validation distinguishes percentage scales from real
  multi-estimate bundles without rewriting the reported values. An empty optional
  heterogeneity object is missing metadata, not uncertainty in the effect itself;
  its warning is retained while independent QA flags and extraction uncertainties
  continue to require review.
- Compound matching preserves stereochemistry and distinguishes an administered
  drug from a different analogue, metabolite or nonchemical reference. Exact
  registered identities and explicit coadministration must survive the guards.
  An independently named registered drug can retain a shared qualitative result
  when the saved statement explicitly assigns that result to the same complete
  actor list, even if other list members are unregistered analogues. Unknown
  members keep their literal identities; group statistics remain attached to
  the complete original finding rather than becoming separate drug estimates.
- Endpoint mapping follows the measured construct. Examples include craving,
  animal drug discrimination, human self-reported affect, isolated enzyme
  activity and PTSD symptom scores. Symptoms do not establish a diagnosis.
  Explicit clinical safety endpoints take precedence over incidental context.
  An explicitly drug-free manipulation or spontaneous clinical symptom is kept
  as its literal exposure context, not a drug-class finding. Nonhuman behavioral
  phenotypes remain distinct from measured human subjective experiences. Named
  instruments without a faithful controlled construct remain literal measurements
  in detail rather than inheriting a broader category from a shared keyword.
- Neural mapping first resolves supported anatomical names. A complete anatomical
  combination may expand only when every component resolves to the same compatible
  kind. Otherwise a supported neural readout can remain literal paper detail.
  Structural tracts, gene-expression/enrichment results, transient phase locking
  and symptom associations must not be relabelled as functional networks,
  measured plasticity, steady-state responses or symptom endpoints by keyword
  overlap. A typed neural measurement retains its domain through later routing.
- Primary neural results explicitly reported as exploratory differences that
  failed their stated correction remain in detail. Unknown correction status,
  null findings and mixed records containing corrected results are not suppressed
  by this rule. Explicit baseline/control-only contrasts are not attributed to a
  later drug intervention; actual treatment-response predictors remain eligible.
- `measured_endpoint_repairs.py` handles bounded, explicit field-role mistakes:
  provider-vignette attitudes, descriptive administrative drug-associated case
  counts, named regions in otherwise unresolved self-connectivity observations,
  symptom-score endpoints and measured in-vivo drug concentrations. Combined
  analyte concentrations remain aggregate detail, not a single-drug estimate.
  Version 2 can also use a separately declared two-region connectivity pair
  when both names resolve. Both anatomical projections retain the original
  connection contrast and share one proposition; they are not two activation
  results. Missing or unresolvable components cannot justify a partial fallback.
- Explicit global neural entropy, criticality and functional-harmonic/hierarchy
  readouts use the existing brain-measure detail families. They do not become
  anatomical nodes. A molecular gene-expression assay is not neural entropy.
- Controlled behavioral vocabulary additions are reviewed endpoint identities
  and close synonyms in `schema/kg_node_vocabularies.json`, with source examples
  in the 29 October follow-up owner. Original tasks, populations, designs and
  quantitative results remain attached. No diagnosis, human subjective effect
  or individual-drug estimate is inferred from the vocabulary match.
  Generic entries marked `exact_only_terms` resolve only as complete field
  values, never as substrings of a more specific construct. All vocabulary text
  matching helpers enforce this restriction. A global `brain_measure` without
  an anatomical anchor stays in paper detail; its internal admission status
  must agree with the existing named-region browser views.

The original extraction JSON is immutable. Repaired fields carry rule/source
provenance in normalized findings; unresolved identities and observations retain
an audit or paper-detail disposition. A paper title, background statement or
another item's result cannot supply a missing drug-specific finding. Source
number/unit conflicts and findings absent from the saved extraction require a
separate source/extraction decision; normalization must not invent them.

The 2026-10-26 audit freezes a 480-record diagnostic sample, retains its initial
judgments and explicit corrections, and replays the whole saved corpus. Its
sampling, source checks, code snapshots, tests and three-version count bridges
are under `data/processed/model_runs/luna_v5_20261017/normalization_quality_repair_20261026/`.
This stratified audit diagnoses failure modes; its counts are not an estimated
population error rate. Graph comparisons use the actual UI counting functions.
For this project, open access means usable full text actually recovered and
accessible, consistently across releases.

### Saved-extraction coverage audit

Run the read-only audit on a frozen release and its corresponding normalized
tables before judging count changes or requesting additional extraction:

```bash
python -m pipeline.kg.audit_saved_extraction_coverage \
  --release /path/to/frozen_release \
  --kg /path/to/normalized_tables \
  --out /path/to/new_audit_directory
```

It reconciles registered identifiers, saved task/response/object counts,
extraction profiles, report dispositions and all graph area/type combinations.
Guidelines are counted with their recommendation objects. A completed audit
directory is not overwritten. The output distinguishes a missing or empty
profile from findings captured elsewhere, detail-only findings and normalization
holds; none of these statuses alone establishes a scientific error.

Use saved source fields to diagnose a shared failure mechanism, test that rule
against affected and unaffected cases, and replay the frozen answers into a
separate staging release. Compare actual website memberships as well as table
admission: main-admitted evidence does not necessarily pass every UI filter.
Preserve prior outputs and all numerical/source fields. Missing or incorrect
extracted evidence requires a separate source/extraction decision; normalization
cannot supply it. The all-area repair receipts and comparison for 28 October are
under `data/processed/model_runs/luna_v5_20261017/cross_domain_coverage_repair_20261028/`.


## Safety normalization: current extraction contracts (30 October 2026)

Safety normalization uses the saved item's explicit `safety_event_or_measure`
and `safety_category` together. The category vocabulary is not a closed list of
all possible event names. A concrete event without a canonical event alias may
use its explicitly declared existing category as the overview anchor. The exact
event remains in `safety_event_or_measure`; it must not become a new prose-valued
overview node or borrow an unrelated organ system from treatment/monitoring text.
Missing, unrecognized or paragraph-valued event/category pairs retain their
existing detail-only treatment. Current review/meta relationship contracts do
not necessarily supply the primary schema's safety-category field.

`safety_event_or_measure`, `safety_category`, `severity`, `seriousness`,
`frequency_or_rate` and `discontinuation_or_withdrawal` are preserved as separate
normalized finding fields. These are literal reported values, not inferred
rates, diagnoses or event-specific allocations from a grouped estimate. Known
event aliases keep their specific anchors. Electrolyte/fluid balance is a
neutral anchor for sodium/osmolality findings and explicit electrolyte terms; a
change or discussed risk must not become a confirmed hyponatraemia diagnosis.

Drug/enzyme names alone (paroxetine, moclobemide, MAOIs, CYP2D6) no longer define
an interaction-risk endpoint. Prefer the actual focal event and declared
category. Existing source/actor attribution, null-result and review contracts
remain independent. Reporting-quality audits, safety perceptions, forecasts and
proposed monitoring practices are retained in detail rather than treated as
observed adverse events. CYP activity alone does not establish organ toxicity;
actual cytotoxicity, cell-death, viability and organ-injury measurements must
retain their existing eligible paths. Pretreatment-phase events cannot be
attributed to the main trial drug merely because it names the trial.

A neutral exposure wrapper may resolve to an existing registered identity only
when the entire remaining label is a registered alias. Preserve the full exact
exposure, and do not reduce lists, pooled named-drug estimates, unknown analogues
or policy/indication phrases to a parent drug. Explicit pooled psychedelic-class
results can use the existing broad class node, never separate member-drug
estimates. These changes belong to the normal conversion/normalization
components, with regression controls in `tests/test_safety_schema_alignment.py`;
no additional model-review or screening stage is involved.

Current primary class-level observations retain their reported unit: an
explicitly measured psychedelic-use class can use the existing broad class
node without resolving a molecule or copying its estimate to example drugs.
This does not admit contradictory class definitions, absent administration,
unknown named analogues or explicitly joint nonpsychedelic exposures. Narrow
administration grammar (route, formulation, dose and neutral setting) may resolve
only the entire remaining registered alias, never a familiar substring.

Safety family names round-trip as controlled labels; exact event aliases and
current typed grouped-event fields can use those families without a prose-length
identity gate. Generic words ending in “safety” do not establish overall
tolerability. A measured cognitive psychotomimetic construct cannot become
clinical psychosis merely because its result summary omits the construct name;
actual psychotic episodes and serious/persistent outcomes retain the Safety
path. Unqualified "psychedelic effects/manifestations" no longer implies a
challenging or adverse effect: an increased neural measurement must not create
a worsened-Safety projection from that generic phrase. Explicitly adverse or
distressing effects retain their existing Safety category.
See `tests/test_safety_remaining_patterns.py` for positive and negative
controls.

An explicitly therapeutic-benefit/recommendation review unit without a Safety
role does not become an adverse event because it says "greater" effectiveness
or "higher" recovery. Missing domain tags alone are not an exclusion: explicit
uropathy, damage, cell death, direct symptom worsening and mixed benefit/harm
are preserved. Uncertain units retain their existing path. Primary source-role
checks also preserve hypothetical avoided emergency
calls and exposure trends without clinical outcomes in detail. An eligible drug
used only as an experimental context does not receive another administered
actor's explicitly reported toxicity. Genuine clinical events, poisoning
outcomes, null adverse-event findings and explicit drug interactions retain
their ordinary paths.


## Target identity alignment (30 October 2026)

`target_identity.py` resolves a complete target field against aliases of one
existing registry identity. Species prefixes, equivalent abbreviations and
receptor name order no longer cause a ligand or ancestor-family substring to
turn a single receptor/transporter into an ambiguous multi-target record.
Every remaining token must be accounted for; unknown subtypes, mutations,
engineered constructs and additional targets cannot silently disappear.
Original target, species, assay, comparator and numerical fields remain attached.

Newly recovered primary identities require an explicit compatible assay before
overview admission. Computational predictions, blocker/behavioral mechanism
experiments and unresolved numbered analogue attribution remain in paper detail.
A null binding result is still eligible. This bounded check applies to newly
recovered phrases; it is not a retrospective validation of every existing target
relationship.

After complete supported target lists have been expanded, a still-unresolved
primary target can retain one literal detail finding when the saved item has its
explicit target, target type, assay and finding statement. Its admission reason
is `explicit_target_requires_identity_resolution`. This does not create a
canonical receptor, infer direct binding, split a shared estimate, or admit a
review topic. Existing subject/reference and source-scope gates still run first.

The same-input before/after builds, saved-row fixtures, scientific-field checks,
UI membership comparison and remaining-gap inventory are under
`data/processed/model_runs/luna_v5_20261017/target_identity_alignment_20261030/`.
These isolated snapshots exclude concurrent safety edits. They are diagnostic
staging artifacts; the active release and raw extraction files are unchanged.


## Molecular readout identity alignment (30 October 2026)

`molecular_readout_identity.py` preserves a complete primary molecular readout
when multiple registry hits refer to its measured substrate, mediator, receptor
subunit, phosphosite or ratio components. Recovery requires the saved specific
marker, controlled molecular category, assay field and finding statement. It
runs only after ordinary matching and complete-list expansion have failed with
`entity_combo_not_graphable`, preserving previously resolved findings.

The literal readout and all numerical/source fields remain one observation.
Supported single measurements continue through the existing subject and source
admission gates. Bundled outcomes, unresolved measurement identities and
computational results stay in paper detail. No shared estimate is assigned to
individual panel members, and no molecular identity is inferred from a result
summary. Missing typed fields and review relationships retain their audit path.

The isolated comparison against the accepted Target pass is saved under
`data/processed/model_runs/luna_v5_20261017/molecular_readout_alignment_20261030/`.
It contains saved-source fixtures, the exact code patch, source-field invariants,
UI membership counts and the remaining-gap inventory. Concurrent Safety changes
are excluded from that measured delta. This repair makes no model calls and does
not promote or publish a graph release.


## Brain readout and anatomical identity alignment (30 October 2026)

`brain_readout_identity.py` recovers still-held primary Brain observations after
ordinary matching and existing list/connectivity projections have run. A saved
readout, assay and finding statement can retain one literal `brain_measure`
detail finding when the assay explicitly identifies a neural measurement. The
assay check uses the saved method alone; it does not infer a modality from result
prose or promote the readout to a canonical region or measurement family.
Mixed measurements stay together, with original anatomy and numerical/source
fields intact. Behavioral, biochemical and manipulation-only methods do not
qualify merely because they concern the brain.

Complete child–parent region phrases resolve only through exact existing aliases
and their declared ancestor chain. Inline abbreviations must resolve to the
same registered region. Unsupported subdivisions, peer lists and wrong parents
cannot collapse to a familiar substring. Recovered computational or explicitly
joint-exposure observations retain detail admission when an anatomical match
would otherwise imply an observed individual-drug effect.

The same-input replay and searchable source audit are saved under
`data/processed/model_runs/luna_v5_20261017/brain_readout_alignment_20261030/`.
Its baseline is the accepted Molecular pass; concurrent Safety changes are
excluded from the measured delta. Combined tests cover the current shared
Safety, Target and Molecular implementation. The repair makes no model calls
and does not promote or publish a graph release.


## Explicit PK observation alignment (31 October 2026)

`pk_observation_identity.py` preserves explicit primary PK observations after
object matching fails. Eligibility is captured from saved relationship, object,
method and finding fields before metadata inference. Unresolved metabolites,
enzyme panels and metabolic pathways remain single paper-detail observations;
no registry identity or component-specific result is inferred.

An explicit exposure/detection relationship with a saved parameter can describe
the same analyte as its subject. It is retained as a PK measurement instead of
being rejected as self-metabolism. `metabolized_to` and other relationships do
not receive this exception; source/object inconsistencies and parent-name
collapses remain available in the normalization audit for identity repair.

Generic entity expansion sometimes leaves multiple clones pointing to the same
unchanged PK object. Recovery restores the original unsplit fields and emits
that source observation once, consuming the redundant slots without changing
the ordinal IDs of already represented findings. The complete numerical result
and source context remain attached to the observation.

The same-input replay, source comparison, patch and searchable report are under
`data/processed/model_runs/luna_v5_20261017/pk_observation_alignment_20261031/`.
The isolated delta follows the accepted Brain pass; combined tests include the
current shared Safety, Target, Molecular and Brain code. This repair makes no
model calls and does not publish or promote a graph release.


## Explicit treatment-context observation alignment (31 October 2026)

`intervention_observation_identity.py` preserves complete treatment-context
observations after legacy topic matching fails. An 80-character display-label
limit previously dropped long source descriptions even when a treatment category
was recognized. The redundant downstream 120-character check has been removed.

Primary recovery requires a saved context component, component type, study design,
relationship to outcome or safety, and finding statement. Eligibility is captured
before metadata inference. Review recovery is narrower: only long descriptions
with an explicit coverage role, evidence locator and recognized treatment category
qualify. Missing fields, short unclassified review topics, synthesis rows and
explicit dose/route/metadata exclusions retain their existing audit behavior.

Recovered observations are paper-detail evidence, with the full saved description
and result intact. They receive no inferred parent component and are not split
into component-specific effects. Source role and study design remain available
to distinguish package outcomes, qualitative accounts, modeled protocols and
review recommendations. Existing finding IDs and overview admission are stable.

The same-input replay, source comparison, patch and searchable report are under
`data/processed/model_runs/luna_v5_20261017/intervention_context_alignment_20261031/`.
The isolated delta follows the accepted PK pass; combined tests include the
current shared Safety, Target, Molecular, Brain and PK changes. This repair makes
no model calls and does not publish or promote a graph release.


## Explicit clinical measurement alignment (31 October 2026)

`clinical_observation_identity.py` separates retention of a reported clinical
endpoint from resolution of the condition identity. A still-held primary row
may become a paper-detail `reported_measurement` when the original clinical
schema contains an endpoint, outcome measure, study design and finding statement.
The population or condition wording is retained in its native field; it is not
used to manufacture a diagnosis. The relation is `reports_measurement`, distinct
from a condition edge and from `reports_outcome_scale`.

Eligibility is captured before metadata inference. Native condition, population
and endpoint fields participate in the source signature, and derived endpoint
rows cannot qualify as new native observations. When the configured source has
a legacy clinical-endpoint projection, observations already served by that path
do not receive a duplicate fallback. Multiple fallback slots for one eligible
source are consumed once without changing the ordinal IDs of existing findings.

The fallback is limited to failed condition identity, broad condition labels,
and population labels. Missing source fields, review and synthesis contracts,
family-history and disease-model exclusions, exposure identity, and paper scope
retain their existing boundaries. Complete statistics, timepoints, populations,
source roles and evidence locators stay attached to the measurement.

The same-input replay, source comparison, patch and searchable report are under
`data/processed/model_runs/luna_v5_20261017/clinical_endpoint_alignment_20261031/`.
The isolated delta follows the accepted treatment-context pass. Combined tests
include the current shared Safety, Target, Molecular, Brain, PK and treatment-
context changes. This repair makes no model calls or deployment changes.

## Real-world observation and estimate alignment (31 October 2026)

`real_world_observation_identity.py` separates a public-health observation's
subject from a drug identity. A native primary row held only because its subject
is unmapped may be retained when it explicitly supplies the predictor/exposure,
measure, topic, study design and finding. Eligibility is captured before metadata
inference; split fields cannot borrow the original observation's eligibility.

The exact policy, demographic contrast or sampled panel remains one
`exposure_context` in paper detail. Scope requires an allowed registry/class
identity in the same measure or finding. Titles, separate population fields,
causal caveats and named reference models cannot supply scope. Out-of-scope-only
results, missing fields, secondary contracts, and chemical identity modifiers
retain their existing holds. Actual null results can qualify. This fallback is
limited to `compound_unmapped`; other subject and paper-scope exclusions retain
their behavior.

The recovery does not create atomic overview subjects or substance-use-context
projections. Its scope-label list is internal provenance, not a list of drugs
receiving the pooled estimate. Native findings, estimates, denominators, periods
and evidence locators remain intact. Existing public-health topic normalization
continues to determine the research area.

The browser export now includes the existing scientific fields
`exposure_or_policy`, `estimate_value`, `estimate_unit`, `association_or_trend`,
`time_window` and `setting`. These let the existing paper-detail card show actual
estimates and sampling context instead of only a generic statistic label such
as “descriptive percentages.” Internal normalization notes and raw extraction
JSON remain outside the browser contract. Older tables may omit these fields.

The same-input replay, comparison, tested source snapshots and searchable report
are under `data/processed/model_runs/luna_v5_20261017/real_world_observation_alignment_20261031/`.
The isolated baseline follows the accepted Clinical pass; combined tests include
the shared Safety and other domain repairs. No model calls or deployment changes
are made by this repair.

## Cognitive and behavioral observation alignment (31 October 2026)

`cognitive_observation_identity.py` retains complete native primary observations
at two failed-identity boundaries. Eligibility is captured before metadata
inference and includes the original exposure, construct, task/measure, study
design and finding. Source signatures prevent inferred or split fields from
borrowing another observation's eligibility.

A broad or long construct label can be retained in paper detail when the source
explicitly declares a cognition or behavior family and supplies the complete
measurement contract. The original graph construct label is kept when present;
otherwise the full source construct is retained. This does not manufacture a
more specific construct or promote qualitative reports to observed copulatory
behavior. Neural-only records without the cognitive/behavioral contract retain
their existing boundary.

A failed comparison/regimen subject can be retained as one `exposure_context`
when an allowed atomic drug is the actual leading exposure and the same finding
corroborates it. Only administration/dose descriptors may precede that drug.
This repairs ketamine/ECT comparisons and anesthetic regimens, and an explicit
MDMA interaction result, without changing the scope of an out-of-scope focal
treatment or using a background drug-model mention as the subject. These rows
receive no atomic overview or use-context projections; their complete regimen,
comparators, estimates and evidence locators remain attached.

The export and existing paper-detail card now carry `construct_or_behavior`,
`task_or_measure`, `behavioral_context` and `statistic_or_value`. The reported
value is separate from the narrative `effect_size`/effect description. The
export can obtain these optional scientific fields from saved raw rows, so old
tables need no new columns. Other source fields and internal browser exclusions
are unchanged. Missing values produce no invented assertions or empty lines.

The same-input replay, source comparisons, tested code snapshots and report are
under `data/processed/model_runs/luna_v5_20261017/cognitive_observation_alignment_20261031/`.
The isolated baseline follows the accepted Real-world pass; combined checks
include the shared Safety changes. This repair makes no model calls or deployment
changes.


## Subjective experience observation alignment (31 October 2026)

Native primary subjective findings can contain several explicit constructs in
one reported observation. `subjective_composite_label` retains the complete
source label when at least two distinct controlled constructs are named with
explicit separators. The existing regex priority must not turn positive and
negative affect into positive affect alone. Synonyms of one construct, scale
names, narrative mentions, legacy rows and split endpoints do not qualify.
Safety and other domain boundaries run before this rule. Joint findings remain
one paper-detail observation; their result is not copied onto separate
component-effect edges.

A bounded subject repair accepts an exact registered compound name and an
agreeing parenthetical synonym before an inert comparator. This handles the
native DMT-versus-placebo records rejected because saline was treated as the
subject. Conflicting synonyms, analogues, background-use descriptions, active
drug comparisons and secondary literature retain their existing handling. The
original exposure and comparator wording remain in the source record.

The browser export and paper-detail card preserve `subjective_construct`,
`instrument_or_measure`, `setting_or_context`, `relationship_to_outcome`, and
the already exported `statistic_or_value`. The exact reported value remains
separate from the narrative effect description. Missing fields add no assertions;
zero values are retained. These optional fields can be loaded from saved raw
rows without changing normalized table schemas.

The same-input replay and comparison report are under
`data/processed/model_runs/luna_v5_20261017/subjective_observation_alignment_20261031/`.
The isolated baseline follows the accepted Cognition/behavior repair. Combined
validation includes the shared Safety changes. No extraction calls or deployment
changes are part of this repair.

### Native guideline and consensus recommendations

`recommendation_consensus_v1` items with an explicit secondary source, positive scope and extractability flags, and a stated subject, topic, and recommendation use `recommendation_topic` / `has_recommendation`. The literal topic and full statement, rationale, strength, position, population, and locator are preserved. Topics such as eligibility or monitoring are not normalized into patient diagnoses. Recommendations remain secondary evidence in paper detail and the secondary literature library; they do not contribute observed clinical or Safety effects to research-area overviews. Subject scope checks still apply.

Both saved routed rows and newly converted recommendations use this contract. The diagnostic replay in `data/processed/model_runs/luna_v5_20261017/recommendation_alignment_20261031` records recovered items, corrected existing items, retained scope holds, and export/UI checks. It does not change extraction inputs, publication pointers, or deployed assets.

### Review treatment-context coverage without a controlled topic

Paper-centered v2 review relationships may name complete contexts that do not match the controlled treatment-context vocabulary. An in-scope secondary relationship with an exact `intervention_context` anchor, an explicit treatment-context domain label, a statement, and a locator is retained literally in paper detail after `intervention_context_topic_unmapped`. This does not infer an independent component effect or a controlled parent topic. Comparator/population roles, missing source anchors, paper-scope failures, and metadata exclusions retain their existing handling. The accepted legacy long-label repair keeps its behavior.

The browser export preserves the original reviewed context, full summary, and source limitations. Diagnostic replay and verification are recorded under `data/processed/model_runs/luna_v5_20261017/review_context_alignment_20261031`; no extraction rerun or publication-pointer change is needed for this repair.

### Safety endpoint follow-up (31 October 2026)

`pipeline/kg/safety_observation_identity.py` supplies aliases for explicit Safety
event fields, including hyphenated blood-pressure endpoints, serotonin toxicity,
hearing loss and bounded dependence labels. These aliases do not scan a clinical
indication or another domain's contextual prose. Neutral gastrointestinal,
skin/hypersensitivity, ocular, hematologic, intracranial-pressure and bone
families retain measurements without diagnosing toxicity from a numeric change.
As elsewhere, an intact grouped observation keeps its source statistics; the
normalizer does not manufacture separate event-specific rates.

A predicted or modeled Safety endpoint remains in paper detail even if its name
matches a known organ-system category. Observed regression outcomes and observed
values exceeding predictions are not forecasts. This boundary records
`predicted_safety_not_observed_event` and leaves source wording intact. It does
not delete computational evidence. Unrecognized multi-clause event labels also
remain intact; the old first-semicolon truncation is removed.

Tests: `tests/test_safety_followup_alignment.py`, alongside the two existing
Safety suites. The same-input replay, changed-observation packets, UI checks and
remaining-gap census are under
`data/processed/model_runs/luna_v5_20261017/safety_followup_alignment_20261031/`.

The fully spelled-out primary exposure “Magnesium–ibogaine therapy (MISTIC)”
also survives an incorrect `atomic_compound` type. Only the complete saved
regimen with an event, result and source locator is eligible for this fallback,
and only after ordinary matching returns `compound_unmapped`. It remains
`combined_safety_regimen_requires_attribution` in paper detail, with no overview
projection to ibogaine. Bare acronyms and extra/uncertain components do not pass.

### Target identity and assay follow-up

`target_identity.py` also recognizes singular/plural receptor and channel names,
equivalent voltage-gated/voltage-operated wording, sodium-channel notation,
and receptor-associated ion-channel or binding-site descriptions. Every other
token must still be explained by one identity. Unknown subtypes, mutants,
subunits, and mixed targets cannot be dropped to obtain a canonical match.
Species-prefixed VMAT1 and VMAT2 retain their separate identities.

New curated receptor/transporter entries declare
`identity_match_policy: complete_target_field` and cite their nomenclature
sources. Unlike permissive legacy aliases, these entries must account for the
whole target field before admission is considered. A new primary identity is
subject to the same assay check as recovered target phrases. The assay grammar
includes direct functional and electrophysiological measurements, not just
descriptions containing the word binding. Null binding/affinity results remain
eligible; blocker/knockout experiments alone do not become direct assays.

Explicitly computational primary Target observations stay in paper detail
regardless of whether the target matched an exact name or a longer phrase.
This uses the observation's structured system/design category; mentioning
docking elsewhere in a mixed-method paper does not downgrade a measured assay.
This is not an exhaustive retrospective validation of all legacy direct-target
admissions.

Historical PCP binding-site aliases no longer imply NMDA receptor identity.
Those named sites survive literally in detail with reason
`target_site_requires_identity_resolution`, including qualified review
relationships. Explicit NMDA and nicotinic receptor descriptions keep their
ordinary identity-resolution paths. The original target, assay, species,
statistics, and source locator remain attached to each observation.

Tests and the full same-input replay are recorded under
`data/processed/model_runs/luna_v5_20261017/target_followup_alignment_20261031/`,
including the deployed-membership loss census and remaining extraction gaps.


The 31 October Target follow-up also checks explicit isotopic/substitution qualifiers
against the normalized subject before overview admission. Deuterated drugs,
amino/nitro PCP derivatives, and a ketamine stereoisomer mixture must not inherit
a parent or single-isomer result merely through a contained drug name. These
observations remain in paper detail with their original source fields. Target
identity recovery does not promote receptor binding-site availability to a direct
drug-binding assay. An unresolved historical binding-site component cannot authorize
splitting an intact receptor-plus-site observation.

### Controlled vocabulary expansion (31 October 2026)

Normalization vocabulary changes belong in `data/curated/entity_registry.json`
and `schema/kg_node_vocabularies.json`. Chemical aliases must identify the same
registered substance; they do not admit an unknown analogue, split a pooled
result or change screening scope. New target entries use `complete_target_field`
resolution and retain the existing assay-role checks. Alpha1/alpha2/beta receptor
families and the CYP3A enzyme family remain distinct from their named members.

Node entries can declare `whole_field_aliases` for particular reviewed aliases,
or `whole_field_only: true` for a complete entry. Such terms require the complete
normalized field: substring hits and dropped parenthetical qualifiers cannot
resolve them. Existing unrestricted aliases retain their earlier behavior.
This permits literal constructs such as convergent thinking and motor learning
without equating them to adjacent constructs such as creativity or coordination.
Vocabulary registration alone does not add an overview view or change its filters.

Exact Safety event synonyms remain in `safety_observation_identity.py`. All-cause
discontinuation stays distinct from adverse-event discontinuation; endpoint
recognition does not assert causality, severity, direction or measured rather
than predicted evidence. Original event wording and source values survive.

The bounded registry changes, same-input replay, changed-observation packets and
regression results are recorded under
`data/processed/model_runs/luna_v5_20261017/normalization_vocabulary_expansion_20261031/`.
No additional model, review stage or paper-specific override is involved.

Chemical-alias regression checks must include substituted and numbered derivatives,
and lists that separately name both a substituted drug and its parent. Recognizing
`2-Br-LSD` must not add an LSD subject merely from its suffix; a separately named
LSD exposure remains distinct. Compact modified names such as `DM-nor-MXE` must
not acquire methoxetamine's identity from the contained abbreviation.
