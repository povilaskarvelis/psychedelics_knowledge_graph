# Terminology

Public-facing text should describe what readers can see and what the workflow
does. Exact filenames, model names, and run labels belong in technical
instructions, not in the public explanation of the method.

## Reader-facing terms

| Use this term | Meaning |
| --- | --- |
| **search result** | A record returned by a literature source before screening. |
| **paper** | A DOI-level article, preprint, report, or other publication record. A paper is not always the same as a study; one study can have several papers. |
| **initial screening** | Rules-based removal of records that clearly lack usable title or abstract information or clearly fall outside scope. |
| **title and abstract screening** | Review of the title, abstract, and basic metadata to assess relevance, evidence topics, and paper type. |
| **paper type** | The source category, such as primary study, meta-analysis, systematic review, scoping review, narrative review, protocol, or commentary. |
| **evidence topic** | The part of the evidence base discussed by a paper, such as clinical outcomes, safety, molecular targets, brain systems, cognition, subjective experience, pharmacokinetics, intervention context, or real-world use. |
| **article text** | Converted article content used for extraction. This may be selected relevant sections rather than every page. |
| **abstract only** | Evidence extraction limited to the abstract. |
| **finding** | One structured, interpretable result or relationship that remains linked to its source paper. |
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
| `extraction route` | A stored extraction assignment for one paper and evidence topic. A paper can have more than one. In public prose, say **extraction assignment**. |
| `extraction task` | One executable extraction job with a paper type, evidence topic, available text, instructions, and expected output structure. |
| `evidence_record` | The stored representation of a finding. |
| `evidence_edge` | A graph relationship created from a finding. |
| `graph projection` | The rule-based conversion of stored findings into public graph relationships. |
| `staged build` | A versioned graph build that has not changed the active public release. |
| `promotion` | The publication step that makes one checked build public and refreshes the graph, bibliography, Methods data, and site together. In public prose, say **publish a reviewed release**. |

## Practical writing rule

Backend documentation can use `evidence_record`, task IDs, route IDs, schemas,
and run labels where precision requires them. Public text should say **finding**,
**paper**, **evidence topic**, **article text**, and **publish** unless the
technical distinction is itself important to the reader.

A finding should be as focused as practical: one compound, intervention, or
exposure connected to one target, system, task, outcome, symptom, safety event,
or synthesis result in a defined paper context. It can still retain study
design, sample size, outcome measure, time point, direction, source location,
effect estimate, funding, conflicts of interest, and reported risk-of-bias
information.
