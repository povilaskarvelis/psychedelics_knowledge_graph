# Evidence and Provenance Policy

This policy explains what a finding in the Psychedelics Knowledge Graph means,
what information should accompany it, and what the graph does not claim.

## Core principles

1. Every public finding should remain traceable to a source paper.
2. Primary studies, meta-analyses, and other reviews remain separate evidence
   types. Review statements are not presented as primary-study results.
3. Article-text and abstract-only findings remain distinguishable.
4. Null, mixed, negative, uncertain, and positive findings are retained rather
   than collapsed into a single conclusion.
5. A structured extraction is not automatically admitted to the overview
   graph. It must also pass validation and normalization checks.

## Information kept with a finding

When the source provides it, a finding should preserve:

- the source paper's DOI or other identifier, title, authors, year, journal,
  publication type, and study design;
- whether the extraction used article text or only an abstract;
- a source location such as the abstract, results text, a table, a figure, or a
  supplement, plus a more specific locator when available;
- the compound or exposure, the related entity or outcome, the evidence topic,
  and the reported direction of the finding where that concept applies;
- study context such as population, sample size, intervention, comparator,
  dose, route, follow-up time, outcome measure, effect estimate, uncertainty,
  and adverse events when reported; and
- reported funding, conflicts of interest, risk-of-bias assessments, and
  certainty assessments when available.

These fields will be incomplete when the paper does not report them or when
only an abstract is available. Missing fields should remain missing rather than
being inferred as facts.

## Evidence types

- **Primary study:** original empirical research, including trials,
  observational studies, case reports, and preclinical studies. Study design is
  shown so these sources are not treated as interchangeable.
- **Meta-analysis:** a quantitative synthesis. Pooled estimates, uncertainty,
  heterogeneity, included-study counts, subgroups, and network-analysis details
  are preserved when reported.
- **Review:** a systematic, scoping, umbrella, narrative, or literature review.
  The graph represents the review's major relationships and coverage without
  treating them as newly observed primary results.
- **Non-primary context:** protocols, conference abstracts, commentary,
  corrections, and similar records can remain in the paper corpus for
  auditability, but they do not enter the standard primary-study, meta-analysis,
  or review graph views unless a specific reviewed use is added.

## Article text and abstracts

`article_text` means that extraction used converted article content. Depending
on the paper type, this can be a selected set of relevant sections rather than
every page of the paper. `abstract_only` means that the extraction was limited
to the abstract. Abstract-only findings must not imply access to details that
were not present in that abstract.

Older schemas and compatibility files may use `full_text_seen` or
`secondary_summary`. These are not the preferred labels for the current public
workflow.

## Validation and graph representation

Before publication, extracted records are checked for the expected structure,
source support, and internally consistent fields. Compounds and related
entities are then matched to controlled names where possible.

A finding can remain available in paper details and search without becoming a
node in the visual overview. Common reasons include:

- the compound or related entity cannot be normalized safely;
- the text describes a class, context, or multi-part relationship that would be
  misleading if flattened into a simple edge;
- the finding is marked for further review;
- the support comes only from background or introductory text; or
- a primary-study or review node is supported by only one source paper and does
  not meet the overview's two-paper display rule.

Meta-analysis findings are shown in their own view and are not subject to that
two-paper display rule because each paper is itself a synthesis. The visual
overview is therefore a deliberately smaller view of the underlying normalized
findings, not the full evidence store.

## Direction, certainty, and risk of bias

For clinical and functional findings, `result_direction` records the reported
interpretation: `positive`, `null`, `negative`, `mixed`, or `unclear`. It is not
simply the mathematical sign of a score. For example, a lower symptom score can
be positive when lower values mean improvement.

The project does not currently assign a universal certainty grade or formal
risk-of-bias judgment to every finding. Source-reported certainty and
risk-of-bias information can be retained as context. Legacy fields such as
`evidence_level` and provisional fields such as `evidence_strength` must not be
presented as project-wide GRADE, Cochrane, or clinical-recommendation ratings,
and they do not override the provenance and validation checks above.

## Corrections and updates

Corrections should be made at the paper, source-text, screening, or extraction
layer rather than by editing a public graph edge directly. Updating a selected
paper replaces all of that paper's previous extraction and evidence rows, or
removes them when the paper is no longer eligible. A reviewed release then
rebuilds the graph, bibliography, Methods counts, and public site together.

Legacy files may still use the word `claim`. In current reader-facing text, use
**finding**. See [`terminology.md`](terminology.md) for the preferred terms.
