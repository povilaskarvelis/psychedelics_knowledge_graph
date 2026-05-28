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
