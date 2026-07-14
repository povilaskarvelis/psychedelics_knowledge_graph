# Terminology

Public-facing text should describe what readers can see and what the workflow
does. Exact filenames, model names, and run labels belong in technical
instructions, not in the public explanation of the method.

## Reader-facing terms

| Use this term | Meaning |
| --- | --- |
| **record** | A title, abstract, citation, or other indexed search entry returned by a literature source. Records are the unit used during discovery and screening. |
| **report** | A document that supplies information about a study, such as a journal article, preprint, conference abstract, registry entry, dissertation, or government report. A report may or may not have a DOI. |
| **study** | The underlying investigation. One study can have several reports, and one report can describe more than one study. |
| **paper** | Use only for a source that is actually a paper, or when referring to a legacy technical name such as `candidate_papers.parquet` or `paper_id`. Do not use **paper** as the public umbrella term for all records or reports. |
| **initial screening** | Rules-based removal of records that clearly lack usable title or abstract information or clearly fall outside scope. |
| **title and abstract screening** | Review of a record's title, abstract, and basic metadata to assess relevance, evidence topics, and report type. |
| **report type** | The source category, such as a primary-study report, meta-analysis, systematic review, scoping review, narrative review, protocol, or commentary. The internal field remains `paper_type`. |
| **evidence topic** | The part of the evidence base discussed by a report, such as clinical outcomes, safety, molecular targets, brain systems, cognition, subjective experience, pharmacokinetics, intervention context, or real-world use. |
| **article text** | Converted article content used for extraction. This may be selected relevant sections rather than every page. |
| **abstract only** | Evidence extraction limited to the abstract. |
| **finding** | One structured, interpretable result or relationship that remains linked to its source report. |
| **evidence-supported relationship** | A graph relationship supported by one or more findings. |
| **graph** | The public view of relationships that are clearly supported and can be represented accurately. |
| **release** | A reviewed update to the graph, bibliography, and Methods information published together. |

Use **finding** rather than **claim** in the interface and reader-facing prose.

## Technical workflow terms

The repository uses the following terms in operational documentation and code:

| Technical term | Meaning |
| --- | --- |
| `retrieved_record` | A source-specific search result before DOI-level deduplication. |
| `candidate_context` | A DOI plus the compound, topic, or search context in which it was found. |
| `extraction route` | A stored extraction assignment for one report and evidence topic. A report can have more than one. In public prose, say **extraction assignment**. |
| `extraction task` | One executable extraction job with an internal paper type, evidence topic, available text, instructions, and expected output structure. |
| `evidence_record` | The stored representation of a finding. |
| `evidence_edge` | A graph relationship created from a finding. |
| `graph projection` | The rule-based conversion of stored findings into public graph relationships. |
| `staged build` | A versioned graph build that has not changed the active public release. |
| `promotion` | The publication step that makes one checked build public and refreshes the graph, bibliography, Methods data, and site together. In public prose, say **publish a reviewed release**. |

## Practical writing rule

Backend documentation can use `evidence_record`, task IDs, route IDs, schemas,
and run labels where precision requires them. Public text should say **finding**,
**record**, **report**, **study**, **evidence topic**, **article text**, and
**publish** according to the distinctions above. Stable internal identifiers
that contain `paper` do not need to be renamed.

A finding should be as focused as practical: one compound, intervention, or
exposure connected to one target, system, task, outcome, symptom, safety event,
or synthesis result in a defined report context. It can still retain study
design, sample size, outcome measure, time point, direction, source location,
effect estimate, funding, conflicts of interest, and reported risk-of-bias
information.

These distinctions follow [PRISMA 2020](https://www.bmj.com/content/372/bmj.n71):
records are indexed search entries, reports are documents, and studies are the
underlying investigations.
