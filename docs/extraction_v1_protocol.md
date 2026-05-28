# Extraction V1 Protocol

This protocol defines the first full knowledge-graph extraction pass. The goal
is to replace the legacy heuristic/autofill path with one model-assisted pass
that performs relevance routing and extracts stable, plot-useful evidence rows.

## Goal

For each candidate paper, the extraction model should decide whether the paper
contains useful evidence for the psychedelics knowledge graph. If it does, the
model should extract essential claim fields with evidence anchors. If it does
not, the model should return a small exclusion record.

The first version is intentionally conservative. It should capture the fields
needed for the current graph and near-term interactive plots, while avoiding
large result-table extraction that can be added later.

## Scope Guard

Extraction v1 should prioritize recall without turning the graph into a broad
neuropharmacology graph. A candidate is relevant only when the supplied input
shows that the studied or reviewed compound/class is an in-scope psychedelic or
closely adjacent agent.

Treat the following as in scope when explicitly supported by the supplied text:

- classic serotonergic psychedelics and analogs such as LSD,
  psilocybin/psilocin, DMT, 5-MeO-DMT, mescaline, DOI, DOB, and DOM
- entactogens such as MDMA or MDA
- ketamine, esketamine, arketamine, and reported metabolites
- ibogaine or noribogaine
- salvinorin A and clearly identified salvinorin analogs
- explicit class-level psychedelic, hallucinogen, entactogen, dissociative
  psychedelic, or classic psychedelic evidence

Do not treat related receptors, pathways, disorders, or clinical areas as
sufficient scope by themselves. Papers about NMDA receptors, serotonin
receptors, monoamine transporters, glutamate, kappa opioid receptors,
plasticity, depression, PTSD, pain, or addiction are not automatically in scope
unless an in-scope compound/class is also central to the original evidence or
secondary-literature scope.

Do not extract primary claims when the only in-scope compound mention is an
anesthetic/sedative context, assay reagent, cited background statement, or
comparison rather than the studied intervention, ligand, exposure, or
mechanism. Broad psychopharmacology reviews should be excluded or routed to
context only unless the supplied text shows substantive psychedelic coverage.

## Inputs

Inputs may be either:

- `full_text`: a full-text evidence packet built from converted PDFs
- `abstract`: an abstract-only candidate record for papers without available
  full text or for optional calibration examples

Both input types should preserve deterministic metadata from the paper library.
The model should not re-extract DOI, title, year, journal, authors, or basic
publication metadata unless it needs to flag a discrepancy.

## One-Pass Output

Each paper returns one JSON object matching
`schema/extraction_v1.schema.json`.

If the paper is not relevant, return:

- `paper_assessment.relevance = not_relevant`
- `paper_assessment.route = exclude`
- `paper_assessment.exclusion_reason`
- no claim rows
- no coverage mentions

If the paper is secondary literature, return:

- `paper_assessment.relevance = relevant` when the review is in scope
- `paper_assessment.route = secondary_literature`
- `paper_assessment.has_original_results = false`
- `paper_assessment.has_extractable_claims = false`
- no claim rows
- one or more coverage mentions when the review scope identifies in-scope
  compounds, targets, disorders, or compound-entity pairs

If the paper is relevant or uncertain, return:

- paper-level source assessment
- one or more essential claim rows when extractable
- evidence location, locator, exact supporting quote, confidence, and
  human-review flag

For primary-evidence papers, v1 keeps `coverage_mentions` empty. Primary
papers contribute plot-ready graph relationships through `claims`; coverage
mentions are reserved for secondary/context papers.

## Paper Assessment Fields

The paper assessment is a sanity-check and routing layer, not the main
extraction target.

Extract or verify:

- relevance: `relevant`, `not_relevant`, or `uncertain`
- route: `primary_evidence`, `secondary_literature`, `context_only`,
  `exclude`, or `human_review`
- source family, source type, paper type
- study design
- system: clinical, preclinical, in vitro, in vivo, ex vivo, observational,
  mixed, unknown, or not applicable
- whether the paper has original results
- whether the paper has extractable KG claims
- metadata discrepancy flags
- country/region, trial registry IDs, funding, conflicts of interest, and
  risk-of-bias notes only when explicit

## Claim Fields

Every claim row must be anchored to explicit supplied evidence. Use
`not_reported` for missing details. The model must not use JSON `null`;
post-processing normalizes accidental nulls to empty strings, but clean model
outputs should use schema-valid strings.

Shared essentials:

- claim type: `compound_target`, `compound_disorder`, or
  `secondary_literature_context`
- compound
- target or disorder, depending on claim type
- because the v1 schema uses a fixed row shape, fill the non-applicable target
  or disorder slot with `not_applicable`
- raw endpoint fields:
  - `raw_entity_label`: the exact endpoint/entity phrase the paper result is
    about
  - `entity_role`: therapeutic indication, molecular target, outcome measure,
    physiological measure, safety/adverse event, biomarker, gene/variant,
    population/context, or related role
  - `clinical_context_condition`: the broader condition or population context
    when distinct from the raw endpoint
  - `graph_entity_label` and `graph_entity_type`: the candidate main-graph
    endpoint, or `not_applicable`/`none` when there is no clean endpoint
  - `graph_include_candidate`: true only when the claim looks suitable for the
    clean graph before deterministic normalization
  - `graph_exclusion_reason`: why the claim should remain an expanded/raw
    evidence signal when `graph_include_candidate` is false
- endpoint roles such as physiological measure, safety/adverse event,
  functional outcome, patient-reported outcome, population/context,
  gene/variant, brain region/circuit, assay readout, or compound/class must
  use `graph_include_candidate = false`. Mechanistic biomarker/readout and
  pathway/process endpoints may be graph candidates only when they are clean
  compound-linked mechanistic findings.
- support: `supported`, `uncertain`, or `not_supported`
- study design and system, if claim-specific
- evidence location, locator, exact quote, confidence, and review flag

Coverage mention essentials:

- coverage type: reviews, summarizes, meta-analyzes, discusses, protocol for,
  commentary on, guideline for, or mentions
- relationship domain: compound-target, compound-disorder, compound only,
  target only, disorder only, general topic, or not applicable
- compound when explicit, otherwise `not_applicable`
- entity type and entity when explicit, otherwise `not_applicable`
- evidence location, locator, exact quote, confidence, and review flag

Mechanistic essentials:

- target or other mechanistic graph endpoint
- assay type or assay family
- affinity/function type such as Ki, Kd, IC50, EC50, EC90, Other, or
  not_reported, using these canonical spellings exactly
- value and unit only if clearly reported
- species, model, tissue, cell system, or route when explicit
- action type when explicit, such as agonist, antagonist, inhibitor, modulator
- result direction is always `not_applicable` for mechanistic claims
- do not treat genotype, allele, transcriptome, brain region, physiological
  readout, or broad assay signal as a clean graph endpoint. Keep the raw phrase
  in `raw_entity_label`, classify it with `entity_role`, and set
  `graph_include_candidate = false` unless a direct target, target
  family/system, pathway/process, or molecular readout relationship is
  supported.

Clinical/disorder essentials:

- distinguish conditions, symptoms/problems, safety signals, and scales.
- use `therapeutic_indication` for diagnosed conditions or explicit indications;
  use `symptom_or_problem` for measured clinical problems that are not clearly
  diagnoses; use `safety_or_adverse_event` for harms/tolerability/physiology.
- do not promote vague labels such as depression, anxiety, pain, social anxiety,
  mental health, wellbeing, or therapeutic potential into conditions unless the
  supplied text explicitly frames them as diagnoses, enrolled conditions, or
  treated indications.
- do not put raw endpoints such as heart rate, blood pressure, nausea, patient
  satisfaction, opioid consumption, biomarkers, personality traits, or
  population/context labels in the `disorder` slot.
- outcome type/domain
- result direction: positive, null, negative, mixed, or unclear. This is the
  therapeutic or functional interpretation for the disorder/indication, not the
  raw numeric direction of the measurement.
- outcome measure if obvious
- sample size total if reported
- population
- intervention or exposure
- comparator
- dose, route, session count or duration when explicit
- central timepoint when clear
- adverse-event summary when explicit
- when a paper reports a safety, physiological, biomarker, functional,
  patient-reported, or process outcome without a clean therapeutic indication,
  set `disorder = not_applicable`, keep the endpoint in `raw_entity_label` and
  `outcome_measure`, set the appropriate `entity_role`, and set
  `graph_include_candidate = false`
- perioperative anesthesia, procedural sedation, surgical satisfaction,
  hemodynamic stability, respiratory parameters, opioid consumption, and
  anesthetic adjuvant outcomes should not become clean indication endpoints.
  Keep them as expanded evidence signals or route the paper away from primary
  graph extraction when no psychedelic-relevant therapeutic/mechanistic claim
  is present.

Interpret `result_direction` as:

- `positive`: beneficial therapeutic signal, including reduced symptoms,
  reduced pathological behavior, reduced relapse/reinstatement/craving/pain,
  increased response/remission, or improved functioning
- `null`: no meaningful therapeutic or functional effect
- `negative`: worsening, harm, increased symptoms/pathology, increased
  relapse/reinstatement/craving/pain, or poorer functioning
- `mixed`: both beneficial and unfavorable findings are present
- `unclear`: evidence does not support a therapeutic interpretation

Do not create standalone disorder claims only for safety/adverse-event absence
or presence unless safety/tolerability is the central outcome. Prefer storing
that information in `adverse_events` on the relevant therapeutic claim.

## Secondary Literature Rules

For v1, secondary literature is classified and mined only for coverage
mentions, not claim rows.
Systematic reviews, meta-analyses, narrative reviews, scoping reviews,
commentaries, protocols, and guidelines can be useful for corpus accounting and
future evidence synthesis, but they should not create compound-target or
compound-disorder graph edges.

Planned synthesis extension: meta-analyses should not be treated like generic
review coverage once we explicitly support evidence-synthesis results. They can
produce separate synthesis-result records focused on the meta-analytic estimate
or conclusion, with outcome measure, comparator, direction, effect size,
confidence interval, p-value, included-study count, and participant count when
reported. Those records should remain distinct from primary-study claims and
from narrative review coverage.

For the current v1 schema, do not extract claims from:

- review summaries of individual primary studies
- meta-analytic aggregate statements
- cited background claims
- guideline or consensus recommendations

Instead, set the paper-level route and source labels and extract lightweight
coverage mentions for the discussed compounds, targets, disorders, indications,
or compound-entity pairs. Use exact quotes that support the paper type or
review scope. If a paper is mostly secondary literature but also reports new
original results, route to `human_review` instead of extracting claims
automatically.

## V1 Non-Goals

Do not extract large result tables in v1. In particular, do not try to enumerate
every p value, confidence interval, effect size, raw arm mean, response count,
or timepoint. Those belong in a later result-level extraction table.

For v1, capture enough to support:

- graph inclusion/exclusion
- primary versus secondary views
- secondary/context coverage overlays
- study-design/system filters
- compound-target and compound-disorder networks
- result-direction views
- sample-size and population summaries
- basic outcome-measure and adverse-event summaries

## Abstract-Only Rules

For abstract-only inputs:

- set `access_level = abstract_only`
- only use title, abstract, and deterministic metadata
- do not report table or figure locators
- mark absent details as `not_reported`
- route ambiguous cases to `human_review`
- keep confidence lower when the abstract does not provide direct evidence

## Full-Text Rules

For full-text inputs:

- set `access_level = full_text_seen`
- prefer Results, tables, figures, Methods, and abstract in that order for
  evidence anchors
- preserve packet chunk IDs or table IDs in `evidence_locator` when available
- use exact quotes copied from supplied chunks/tables
- flag rather than resolve contradictory or ambiguous findings

## Quality Gates

Rows should be blocked or routed to human review when:

- relevance is uncertain
- the supporting quote is missing or not exact
- compound/entity support is indirect
- source labels are inconsistent, such as review plus primary-study labels
- numeric values lack a unit or look inferred
- abstract-only input is used for detailed full-text-only fields

## Projection Safeguards And Manual Corrections

Generated extraction outputs, projected CSV/JSON files, KG tables, and graph
payloads should not be edited by hand. They are build artifacts and will be
overwritten.

Prefer deterministic projection or normalization safeguards for repeatable
error classes:

- review, systematic-review, scoping-review, meta-analysis, guideline, or
  commentary records leaking into primary evidence
- duplicated or mismatched full-text artifacts attached to the wrong DOI
- publisher artifacts such as peer-review reports, author responses, decisions,
  corrections, errata, or retractions
- known alias, endpoint-role, or graph-candidate normalization misses

Use curated manual overrides only for paper-specific factual adjudications that
cannot be safely generalized. Overrides should live in a versioned curated file,
not in generated outputs, and each override should record:

- DOI and dataset
- field or routing decision being overridden
- model/generated value and curated value
- reason for the override
- short evidence note or quote
- curator and date
- whether the override excludes a record, changes primary/secondary routing, or
  changes a normalized entity

Projection should surface manual overrides in reports and provenance fields, for
example with `manual_override_applied`, `override_id`, and `override_reason`, so
manual curation remains visible in the KG rather than silently changing history.

## Pilot

Build a deterministic pilot input file before scaling:

```bash
python pipeline/extract/build_extraction_v1_pilot.py --dataset all --per-bucket 10
```

The pilot should include full-text relevant, full-text uncertain,
abstract-only relevant, and abstract-only uncertain records where available.
Records marked irrelevant by prior screening are excluded from Gemini
extraction by default. Use `--include-irrelevant-controls` only for deliberate
calibration or negative-control runs. Records are selected with a stable hash
inside each dataset/bucket so repeated pilot builds are deterministic without
always taking the earliest DOI/title rows.

For normal Gemini 2.5 Flash scaling, prefer `--thinking-budget 0` unless a
calibration batch shows quality loss. Omit the flag, or pass
`--thinking-budget -1`, for dynamic thinking on difficult retry or audit runs.

After the pilot, manually QA:

- relevance/exclusion decisions
- source-family and paper-type routing
- claim row correctness
- exact quote verification
- missing-field restraint
- abstract-only sparsity

Only after that should the same contract be used for larger extraction runs.
