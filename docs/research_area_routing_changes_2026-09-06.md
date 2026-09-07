# Research-area routing changes — 6 September 2026

Implemented a conservative hybrid: deterministic routing boundaries, a
persistent adjudication pass, explicit holds for unsupported indication
projections, and advisory ambiguity flags for later review. There are no new
model/API calls and no changes to extraction schemas. The saved audit is used
as a precise semantic-review input; it is not a new classifier or a collection
of hard-coded extraction exceptions.

## Automatic behavior

- Negated psychosis in a population label no longer makes a clinical response
  a psychosis-risk finding. When an explicit extracted endpoint says depression
  severity or suicidality, that endpoint supplies the projection. Otherwise the
  population anchor is held for review rather than expanded into new diagnosis
  links.
- Psychosis requiring hospitalization is retained in Safety even when the text
  mentions a psychotomimetic scale/model. Negated persistence, such as “no
  persistent psychosis,” does not override an explicitly transient effect.
- Narrow explicit adverse-event endpoints and unambiguous no-manic-switch
  statements route to Safety. Ordinary treatment failure, worsening depression,
  and mixed benefit/safety statements are not generically moved to Safety.
- The explicit Parkinson’s-precipitation finding routes to the existing
  neurotoxicity safety bucket. The statement's tentative wording is unchanged.
  The two retraction-context records are flagged, not recast as positive harm.
- Ketamine-associated uropathy is not admitted as a ketamine treatment
  indication. Those condition projections remain in paper detail and the
  review queue. No rule guesses whether the eventual destination should be
  Safety, management by another intervention, or a different context.

## What is flagged

Checks cover clinical/safety ambiguity, exposure-related harm, other treatments
or withdrawal/cessation, disease models, diagnosis-versus-measured-endpoint
confusion, policy/preferences, exposure-group comparisons, therapeutic results
in Safety, and exact statements projected into both clinical and safety views.
Schizophrenia condition rows deliberately receive a broad role-review flag,
since this cohort contains both genuine therapeutic research and challenge or
risk research. A flag is not an error verdict.

The queue includes normalization failures as well as normalized findings. An
unmapped patient-description anchor therefore remains available for review.
Flags do not alter graph admission; the explicit boundaries above can.

## Full-corpus staging result

The versioned build `research_area_routing_20260906` completed successfully with
97,132 normalized findings. The full comparison reproduces the scoped audit
result: 15 changed/suppressed projections, 38 held, and 156 remaining flagged.

The review queue contains **5,405 row-level review records**, not 5,405
reports:

| Record type | Count |
|---|---:|
| Normalized findings currently admitted to the graph | 2,430 |
| Normalized findings already held in paper detail | 727 |
| Normalization-audit records | 2,248 |

The earlier figure of about **2,400** referred to the **2,430 flagged finding
rows that were still admitted to the main graph**. The other 727 flagged finding
rows were already held in paper detail, and the remaining 2,248 records are
normalization-audit rows with no normalized finding ID. Those three groups sum
to 5,405. A single DOI can produce many finding rows, so these are not report
counts; the full queue covers 2,750 distinct DOIs.

These are candidate review records, not 5,405 confirmed errors. The first group
is the natural starting point for reviewing visible graph content. The full
queue is available as both Parquet and CSV under
`data/processed/kg_routed_runs/research_area_routing_20260906/`.
The input/output identity checks confirm that every flagged normalized finding
has a matching queue record and is still labeled as deterministically classified.

The candidate is not promoted, and public graph payloads were not regenerated.
The active release pointer remains `full_corpus_normalization_patch_qa_20260724`.

## First adjudication pass

Every one of the 5,405 queue records now has a persistent adjudication in the
versioned overlay
`data/processed/kg_routed_runs/research_area_routing_20260906_adjudicated/`.
The overlay records the evidence fingerprint, decision, action, rationale,
review date, and reviewer policy version. It makes 624 conservative
corrections and leaves 2,533 finding records unresolved for a later source-level
decision. The remaining 2,248 records are normalization-audit records; they
are reviewed as unresolved because there is no normalized graph subject to
correct safely.

Of the corrected records, 525 finding rows have their graph edges held in
paper detail. The other 99 already have a deterministic replacement
projection (for example a safety or psychotomimetic projection), so the
adjudication marks the replacement without deleting its edge. The overlay
does not silently change unresolved rows or promote itself to the active
release.

As a regression check, none of the 209 previously audited exact old
condition/safety projections remains as a `main_graph` projection in the staged
overlay; each is either held or represented by the corrected deterministic
replacement.

The materialization command is:

```bash
python pipeline/validate/apply_research_area_adjudications.py \
  --candidate-dir data/processed/kg_routed_runs/research_area_routing_20260906 \
  --out-dir data/processed/kg_routed_runs/research_area_routing_20260906_adjudicated \
  --audit docs/evaluation/research_area_audit_2026-09-06/high_confidence_findings.csv \
  --reviewed-at 2026-09-06
```

The corrected findings and edges are staged in the overlay's Parquet tables;
`research_area_adjudications.parquet` and its CSV companion provide the full
decision ledger, while `research_area_review_queue_adjudicated.parquet` is the
queue with decisions joined back to each record.

## Second semantic pass

The second pass reviews the unresolved rows that were still admitted to the
main graph after the first pass. It uses the saved support statement, current
research-area domain, and normalized graph-entity kind; it makes no model or
API calls and does not alter the extraction schema. Exact repeated statements
share one decision through a deterministic statement/projection key, and that
decision is propagated to every repeated finding row.

The second pass reviewed **2,032 main-graph finding rows** representing **1,927
unique statement/projection groups**:

| Second-pass result | Rows |
|---|---:|
| Confirmed at the current area | 1,517 |
| Corrected and current edge held | 513 |
| Unresolved for source-level context review | 2 |

The 513 corrections include safety entities projected into the clinical area,
therapeutic text projected into Safety, model/comparison statements, measured
endpoints attached to condition rows, and policy or contextual statements.
Every corrected second-pass row has its current evidence edge removed from the
staged graph; no confirmed second-pass row is missing an evidence edge. The two
remaining rows are deliberately unresolved because their saved statements do
not establish a specific endpoint: one is a review-level statement about
psychedelic research in terminal cancer, and one is a diathesis-stress model
statement about psychiatric reactions to MDMA.

Across both passes, the 5,405-row adjudication ledger now contains 1,137
corrected findings, 1,517 confirmed findings, 503 unresolved findings, and
2,248 unresolved normalization-audit records. Of the 503 unresolved findings,
501 were already in paper detail after the first pass and therefore were not
reopened in the main-graph semantic pass; the remaining two are the contextual
rows described above. The final second-pass overlay contains 96,181 evidence
edges and 97,132 findings. It is staged only; the active release pointer and
public graph payloads remain unchanged.

Run the second pass with:

```bash
python pipeline/validate/apply_research_area_second_pass.py \
  --first-pass-dir data/processed/kg_routed_runs/research_area_routing_20260906_adjudicated \
  --out-dir data/processed/kg_routed_runs/research_area_routing_20260906_second_pass \
  --reviewed-at 2026-09-06
```

The second-pass decision table is available as
`research_area_second_pass_decisions.parquet`/`.csv`; the combined ledger and
joined queue are in the same versioned output directory.

## Release QA and promotion

Before promotion, every one of the 513 proposed second-pass corrections was
reviewed against the saved evidence statement and the graph view contract. A
deterministic, hash-stable sample of 200 confirmations was also reviewed: 140
condition/outcome rows, 49 safety rows, all six cognitive/behavioral rows, and
all five real-world/public-health rows. The two remaining contextual cases were
resolved from their source records.

This QA found that the second pass had over-applied several domain-mismatch
rules. The public graph selects Conditions, Safety, and the other research
areas from `entity_kind`; extraction `domain` is provenance and does not by
itself select the visible view. QA therefore restored 273 valid edges, retained
240 of the proposed removals, found 24 additional wrong projections in the
confirmation sample, and held both source-reviewed contextual rows. The final
2,032-row main-graph scope has 1,766 confirmed and 266 corrected findings, with
no unresolved rows. All corrected rows are absent from `evidence_edges`; all
confirmed rows have an edge.

The final ledger is in
`data/processed/kg_routed_runs/research_area_routing_20260906_release_candidate/`:

- `research_area_release_qa.parquet`/`.csv` records the 715 reviewed QA rows,
  the prior decision, final decision, rationale, reviewer, and whether the row
  was in the confirmation sample.
- `research_area_final_decisions.parquet`/`.csv` records the final status for
  all 2,032 second-pass rows.
- `release_qa_manifest.json` records review counts and edge-integrity checks.
- `data/curated/research_area_release_qa_overrides.json` is the reviewed,
  replayable override registry.

The reviewed candidate was promoted as
`research_area_routing_20260906_release_candidate` with release ID
`research_area_routing_20260906_release_candidate:831a39b0160546258bcfc82130e51916`.
Both active pointers, the public query artifact, the Methods outputs, and the
static site now refer to that release. In the promoted browser payload, the
chronic-MDMA/early-onset-Parkinson finding appears once in the Safety detail
view and zero times in the Conditions detail view.

Run the release-QA overlay with:

```bash
python pipeline/validate/apply_research_area_release_qa.py \
  --second-pass-dir data/processed/kg_routed_runs/research_area_routing_20260906_second_pass \
  --out-dir data/processed/kg_routed_runs/research_area_routing_20260906_release_candidate \
  --overrides data/curated/research_area_release_qa_overrides.json \
  --run-id research_area_routing_20260906_release_candidate
```

The ongoing deterministic pass is now version v3. It uses `entity_kind` as the
graph-area contract, retains null and negative therapeutic findings as clinical
evidence, and holds model-only or context-only statements without treating a
domain mismatch as an error by itself. Deterministic output remains a proposal:
release candidates must review every proposed correction, a stable stratified
sample of confirmations, and every unresolved main-graph row before promotion.

## Provenance and review status

Every normalized finding records the pre-boundary source classification,
routing version, available rule actions, classification origin, review status,
review reasons, and a source-evidence fingerprint. Existing normalization and
admission reasons remain available too.

The candidate builder still records deterministic classification. The
adjudicated overlays add `agent_reviewed` provenance to rows explicitly
confirmed or corrected by the review passes. Adjudication statuses are
`confirmed_current`, `corrected`, and `unresolved`; unresolved means the row
was reviewed and deliberately left unchanged, not that it was silently
accepted. Every decision references the finding ID when available plus the
source-evidence fingerprint, rationale, date, and policy version. The
fingerprint detects changed evidence; it is not a unique projection identifier.

Outputs in each new KG build:

- `findings.parquet`: classification and review provenance.
- `research_area_review_queue.parquet`: flagged finding/normalization records,
  evidence text, locators, and reasons.
- `manifest.json` → `research_area_review`: rule version and aggregate counts.

## Validation against the audit

The isolated before/after replay uses the same 909 saved source rows from the
171 audited DOI records, the same current registries and dependencies, and the
pre-change builder saved from Git. This distinguishes effects of this patch
from differences between the July active release and today's code.

**53 of the audited, previously admitted misclassified projections are removed
by this patch:**

- **14 receive corrected placements:** six depression/suicidality endpoints,
  six mania/switch-safety findings, the Parkinson’s-precipitation finding, and
  the psychosis-hospitalization finding.
- **38 ketamine-uropathy projections are held in paper detail for review.**
- **1 unresolved patient-description projection moves to normalization review.**

Relative to the active audit, the complete scoped candidate accounts for all
209 rows: **156 remain at their audited placement and are flagged**, **38 are
held in paper detail**, and **15 have another projection in place of the audited
one**. Fourteen receive the corrected placements described above; the unresolved
population-based finding retains an existing therapeutic endpoint projection
while its unmappable original anchor is queued for normalization review.
These are normalized rows, not independent experiments.

The scoped candidate contains 1,074 normalized findings, with 372 flagged
finding records. Its normalization failures are also included in the queue.
This is an enriched problem cohort; its flag rate is not an estimate for the
full corpus.

The focused research-area suite passes 28 tests. The full suite has 1,134
passing tests with 367 parameterized subtests; two unrelated existing site/UI
tests remain red because of pre-existing favicon and responsive-CSS
expectations. Regression controls include baseline negation with new psychosis,
transient effects with no persistent psychosis, ordinary nonresponse/worsening,
null safety results, postmortem PK measurements, prevention of new comorbidity
projections, and second-pass area-mismatch decisions.

Artifacts are under `docs/evaluation/research_area_routing_2026-09-06/`:

- `isolated_patch_changes.json`: source and baseline-code hashes plus every
  changed projection key in the scoped replay.
- `scoped/audit_comparison.csv` and JSON: per-audited-row dispositions.
- `pytest.txt`: focused validation output.
- `full/audit_comparison.csv`: per-audited-row results for the full staging build.
- `full_build_summary.json`: full-corpus counts and review-queue breakdown.
- `adjudication_summary.json`: counts and integrity summary for the persistent
  adjudication overlay.
- `second_pass_summary.json`: second-pass scope, decision counts, combined
  ledger counts, and edge-integrity checks.

The initial routing and adjudication artifacts remain immutable staging inputs.
The reviewed release candidate described above is the promoted graph. The 501
remaining unresolved finding records were already held in paper detail before
the main-graph pass; they do not create visible graph edges and remain available
for later source-level cleanup.

To reproduce the isolated before/after replay, use the baseline revision stored
in `isolated_patch_changes.json` and a new, empty work directory:

```bash
python pipeline/validate/replay_research_area_audit.py \
  --baseline-ref BASELINE_GIT_REVISION \
  --evidence data/processed/extraction/routed_runs/full_corpus_normalization_patch_qa_20260724/routed_evidence_rows.json \
  --audit docs/evaluation/research_area_audit_2026-09-06/high_confidence_findings.csv \
  --work-dir data/processed/kg_routed_runs/research_area_audit_replay_new \
  --report-dir docs/evaluation/research_area_routing_replay_new
```
