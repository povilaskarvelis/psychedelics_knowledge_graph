# Paper-centered review extraction: asynchronous 250-paper production batch

## Outcome

The Gemini Batch API job completed with 250 responses. Of these, 249 parsed
successfully and matched the production schema. One full-text response was
invalid JSON because the model emitted a very long malformed Unicode escape.
It was not repaired or retried and remains available for the later failed-item
retry workflow.

The 249 successful papers produced 976 relationships:

- 137 full-text papers produced 616 relationships, mean 4.50 per paper;
- 112 abstract-only papers produced 360 relationships, mean 3.21 per paper;
- 572 relationships were marked paper-defining;
- 383 were marked major-supporting;
- 21 were marked secondary context;
- 951 requested main-graph admission.

There were no schema-invalid parsed bundles. Total model use was 2,173,877
prompt tokens and 638,053 output tokens.

## Direct paper review

No evaluator model was used. Fifteen papers were read directly using the
available abstract and, for full-text papers, the objective, section structure,
discussion, and conclusion. The sample deliberately included full-text and
abstract-only papers, clean and automatically flagged outputs, different
scientific domains, and papers with broad or potentially peripheral relevance.

Manual assessment:

- 11 good: the extracted relationships represented the paper's purpose,
  principal conclusions, and important qualifications;
- 3 partial: the main content was captured but one relationship was too broad,
  too prominent, or outside the psychedelic focus;
- 1 poor: an MDMA subgroup result was promoted as paper-defining even though
  the review's objective concerned social decision-making across many
  psychiatric populations.

Strong examples included the reviews of ketamine and esketamine for suicidal
thoughts, ketamine-related cystitis, psychedelic-therapy adverse-event
monitoring, psychedelic ego dissolution, MDMA mitochondrial toxicity, the
claustrum and Salvia divinorum, modified informed consent, and ibogaine
toxicity. In these papers, the extraction preserved negative or mixed results,
time boundaries, evidence limitations, and distinctions between compounds.

The main residual content problem appears in broadly scoped reviews where an
in-scope compound is only one example. For example:

- the Ultimatum Game review was about psychiatric populations generally, but
  its MDMA subgroup was presented as paper-defining;
- the suicide-prevention review correctly extracted ketamine, but also
  extracted lithium, CBT, and DBT because they were central to the paper rather
  than to the psychedelic KG;
- the electronic-cigarette review correctly represented its overall illicit
  drug focus, but much of that focus was cannabis, nicotine, synthetic
  cannabinoids, and other non-psychedelic substances.

This is primarily an admission/focus issue rather than unsupported extraction.
The relationships are usually supported by the source; the problem is deciding
which paper-level relationships belong in a psychedelic KG when the review is
only partly relevant.

## Automatic consistency checks

After correcting the abstract prompt's omitted instruction for the redundant
`source_item_ids` field, 103 of 249 papers had at least one substantive
consistency warning:

- 108 relationship/aspect importance mismatches;
- 17 paper-defining relationships without a paper-level importance basis;
- 16 major aspects covered by a noncentral relationship;
- 16 major aspects without a relationship of matching importance;
- 6 central relationships not assigned to the main graph;
- 2 noncentral relationships assigned to the main graph;
- 1 central relationship without a linked major aspect.

Most warnings are bookkeeping disagreements between `paper_defining` and
`major_supporting`. Both levels are admitted to the main graph, so these do not
usually mean that a relationship was lost. They are more common for full-text
reviews because those bundles contain more aspects and relationships.

## KG replacement

The production rebuild removed all 1,027 legacy domain-routed review evidence
rows and added the 976 paper-centered relationship rows. No legacy
`review_coverage_item` remains in the replacement input or normalized review
findings.

After normalization:

- 542 review findings from 211 papers entered normalized KG tables;
- 520 are admitted to the main graph;
- 22 are retained as paper detail;
- 538 projected rows are retained in the normalization audit rather than being
  forced into graph nodes;
- all 249 successfully extracted papers occur in either normalized findings,
  the normalization audit, or both;
- 38 papers occur only in the audit because none of their projected
  subject-object pairs could be normalized safely;
- the active review bootstrap contains 173 aggregated graph edges and the
  review detail bootstrap contains 542 rows.

The active primary-study and meta-analysis bootstraps were not changed. The
active review graph and detail data now point only to the paper-centered
production build.

## Assessment

The one-pass paper-centered architecture is working well enough for production
use. The main relationships are usually accurate and substantially better
aligned with whole-paper purpose than the old domain-routed review outputs.

The next improvement should not add another model pass. Before the next large
batch, the prompt or admission rules should more explicitly demote
compound-specific results when the paper's stated objective is substantially
broader and the compound is only one example or subgroup. Normalization already
protects the visible graph from many non-psychedelic subjects, but it cannot
detect every source-supported yet paper-peripheral psychedelic relationship.

## Artifacts

- Extraction run: `data/processed/extraction/review_relationship_runs/review_relationships_v2_main_20260712/`
- Conversion report: `data/processed/extraction/routed_runs/review_relationships_v2_main_20260712/review_relationship_conversion_report.json`
- Normalized KG: `data/processed/kg_routed_runs/review_relationships_v2_main_20260712/`
- Public payload: `data/processed/graph_payload_runs/review_relationships_v2_main_20260712/`
