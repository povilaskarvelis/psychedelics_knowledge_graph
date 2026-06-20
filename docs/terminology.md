# Terminology

This project uses evidence-synthesis terminology in public-facing text and the
new table-based pipeline. Older files and schemas may still use `claim` for
compatibility with the first-generation graph.

| Concept | Preferred Term | Human-Facing Term | Notes |
| --- | --- | --- | --- |
| Database/API hit from a search provider | `retrieved_record` | search result | A PubMed, OpenAlex, Crossref, or other provider record before screening. |
| DOI-level article, preprint, or report | `source_report` or `paper` | paper | A report is not always the same as a study; one study can have multiple reports. |
| DOI plus compound/entity routing unit | `candidate_context` | candidate evidence | A lead found by search, queue, or prior artifact. |
| Screened relevant DOI-context | `screened_context` | screened evidence | A context supported by title/abstract review but not necessarily extracted yet. |
| Structured extracted row | `evidence_record` | finding | The canonical unit of extracted evidence. Each record should represent one interpretable study finding with provenance. |
| Graph-ready relationship | `evidence_edge` | evidence-supported relationship | A derived graph view over one or more evidence records between normalized entities. |
| Older extracted row/file language | `claim` | finding | Legacy term used by current schemas, file names, payloads, and some scripts. |

## Routed Extraction Terms

Use these terms for the table-based extraction pipeline.

| Concept | Preferred Term | Notes |
| --- | --- | --- |
| DOI-level routing row | extraction route | A paper can have more than one route when it should be extracted for more than one evidence domain. |
| Single model job | extraction task | One paper plus one paper type, evidence domain, text availability, prompt, and schema. Track this by `task_id`/`route_id`, not DOI alone. |
| Paper category | paper type | Primary study, meta-analysis, systematic review, narrative review, guideline, or other routed source type. |
| Evidence topic | evidence domain | Clinical outcome, safety/tolerability, molecular target, pathway, brain system, cognitive/behavioral, subjective experience, pharmacokinetics/exposure, intervention context, or public-health/real-world evidence. |
| Available text level | text availability | Either abstract-only or article text. Article text can be selected sections, not necessarily the whole paper. |
| Text extracted from PDFs/XML | extracted text | The source text produced before model extraction. |
| Selected text sent to the model | article text input | The article sections/tables/figures/references chosen for an article-text extraction task. |
| Rule for choosing article text | section selection strategy | For example: primary study, meta-analysis, or review. |
| Model instructions | extraction prompt | The instructions for the model for a specific paper type, evidence domain, and text availability. |
| Expected JSON output | extraction schema | The JSON structure the model must return. |
| Route retained but not sent to a model | terminal no-model route | Useful for audit/accounting, not a KG extraction task. |

Older code and JSON files may still use `packet` for article text input and
`packet_profile` for section selection strategy. Treat those names as
compatibility fields, not preferred terminology for new docs or commands.

## Practical Rule

Use `evidence_record` in new table names and backend documentation. Use
`finding` in the interface and reader-facing prose.

An evidence record should be as atomic as practical: one compound or
intervention linked to one target, system, task, clinical outcome, symptom, or
safety event in one study context. It can still carry rich fields such as study
design, sample size, outcome measure, timepoint, result direction, evidence
locator, source excerpt, extraction confidence, funding, conflicts of interest,
and risk-of-bias notes.

Graph edges can be derived later by grouping evidence records by normalized
compound, entity, and relation type.
