# Local checkpoint — 1 November 2026

This checkpoint collects the accumulated working-tree changes since
`6284a5710e110b198e7990b0fa0dfb070f47fb1c` (22 October). Some work began before
that merge and remained uncommitted. This is a source/configuration/documentation
checkpoint, not a graph publication. No push or deployment accompanies it.

## Discovery, screening and source eligibility

- Add explicit, contextualized PCP/phencyclidine PubMed and OpenAlex queries,
  targeted discovery support, deduplication/promotion handling and methods
  documentation. Register PCP as an eligible graph compound.
- Keep production title/abstract screening on Luna V5, including the explicit
  PCP addition. Deterministic prescreening handles publication format, language
  and usable abstracts rather than substituting topical rules for Luna.
- Generalize verified source/collection exclusions, protect genuine full
  articles and case reports, and keep source-specific decisions in the curated
  post-retrieval eligibility ledger. Update metadata and DOI alias registries.
- Preserve V6/V6.1 correction prompts and separate screening-audit utilities as
  historical/diagnostic work. Their presence is not adoption of full-text
  screening, a new production model-review step, or replacement of V5 decisions.

## Full text and metadata integrity

- Improve alternate-source resolution, PMC XML retrieval, PDF conversion,
  recovery worklists, manual queues and browser-batch reconciliation.
- Require reconciliation of full-text recovery for the current screening
  generation before extraction preparation. Do not treat abstract-only XML or
  empty JATS/TEI bodies as usable full text.
- Preserve supplementary/non-English/wrong-document evidence without silently
  substituting it for the intended report. Update source identities, exact-PDF
  attestations, access overrides and record-specific eligibility provenance.
- Require native report identity before refreshing metadata from cached PubMed
  identifiers; keep writes scoped and audit skipped conflicts and failures.
- Preserve scientific comparison text through markup cleanup.

## Extraction and batch execution

- Route accepted scholarly analyses through Reviews while retaining their more
  specific publication genres and applying the existing source checks.
- Use authoritative candidate metadata consistently across routes and tasks;
  detect unusable abstract sources and retain explicit source-review holds.
- Strengthen source/contract fingerprints, secondary-task identity, cache
  matching and statistical-result validation. Add reproducible source/routing
  repair and saved-release replay tools.
- Support explicitly authorized concurrent Batch dispatch without the previous
  worst-case reservation serialization, retaining accounting, idempotency and
  duplicate-submission protection.
- Do not wire experimental extraction self-review or recursive coverage checks
  into the production entry point. Saved diagnostic evidence is not an
  automatically adopted extraction plan.

## Normalization and evidence fidelity

- Repair primary, review and meta-analysis conversion, measured endpoints,
  contribution roles and graph admission across clinical, Safety, cognitive,
  subjective, Target, Molecular, Brain, PK, treatment-context and Real-world
  evidence.
- Preserve complete observations in paper detail when a category or atomic
  subject cannot be resolved. Keep recommendations, pooled interventions,
  comparison/control results, indirect mechanisms and predictions distinct from
  individual-drug observed effects.
- Improve target/site, brain anatomy/readout, chemical and subject identity;
  prevent unsupported compound splitting and transfer of another actor's
  findings. Retain null results, statistics, source quotations and limitations.
- Expand controlled vocabularies and verified aliases, with whole-field and
  chemical-derivative protections. Preserve unresolved identities explicitly.
- Add saved-extraction coverage diagnostics and comparison tooling. These
  describe processing locations and gaps, not scientific accuracy scores.

## Authors, export and interface

- Update reviewed author identities, canonical-name handling and byline
  preservation to reduce duplicates without indiscriminately merging namesakes.
- Keep graph/corpus dispositions consistent with represented, detail-only and
  held evidence. Export native observation fields for inspection in paper cards.
- Display richer Safety, cognitive, subjective, recommendation and review-context
  details. Keep recommendations distinct from observed results and preserve the
  concise Reviews toggle.
- Improve mobile controls, graph-label sizing/wrapping and compact layout;
  update matching browser tests and asset versions.

## Documentation and other authored work

- Update pipeline, discovery, extraction, full-text, normalization and publishing
  guides; retain the dated Luna run history, recovery/cost notes, source audits,
  framing assessment and architectural review.
- Include the draft `protocols/` specifications, field configuration, concept
  schemes and migration-analysis tools. They are proposals and are not yet read
  by the production pipeline.
- Include the existing launch-video and living-knowledge-film source projects,
  versioned compositions, scripts, design notes and supporting input assets.
  Video rendering is not validated by the pipeline regression suite.

## Checkpoint boundaries and validation

Generated model-run directories, graph payload builds, downloaded paper libraries,
local credentials, dependency installations and render output remain local under
the repository's ignore policy. Newly ignored paths cover approximately 1.1 GB
of generated audio, the launch-video build directory and temporary paper-audit
renders. Those files are preserved on disk; they are not deleted. Reproducing
video renders requires their local generated media or regenerating it with the
authoring scripts. Public graph pointers are unchanged.

The broad checkpoint check covers every changed/new Python test module under
`tests/` and the changed/new browser tests. It exposed four obsolete expectations:
two excluded an explicitly accepted commentary from source recovery, one assumed
the earlier registry size, and one equated an unresolved historical PCP site
with NMDA. The tests now reflect the already implemented and separately tested
contracts; no production rules were changed for this checkpoint.

Final validation: 1,685 Python tests and 492 subtests passed across 70 changed/new
modules; one existing test was skipped. All 26 changed/new browser tests passed.
The 46-test focused check for the corrected older expectations also passed.
Python parsing, JSON parsing and a credential-pattern scan found no errors or
credential candidates in the staged source set. Diff whitespace checks exclude
the two generated migration CSVs, which intentionally preserve CSV line endings
and literal source snippets. Source/docs trailing whitespace was cleaned.

Scientific correctness and completeness remain bounded by the source assessments;
passing software tests does not establish an overall accuracy advantage over the
deployed graph.
