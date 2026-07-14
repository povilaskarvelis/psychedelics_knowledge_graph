# Evidence and Provenance Policy

This policy explains what a finding in the Psychedelics Knowledge Graph means,
what information should accompany it, and what the graph does not claim.

## Core principles

1. Every public finding should remain traceable to a source paper.
2. Primary studies, meta-analyses, and other reviews remain separate evidence
   types. Review statements are not presented as primary-study results.
3. Article-text and abstract-only findings remain distinguishable.
4. Positive, negative, mixed, unclear, and no-detected-effect findings are
   retained rather than collapsed into a single conclusion.
5. Information is added to the graph only when it is supported by the source
   and can be represented accurately.

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

**Article text** means that extraction used converted article content. Depending
on the paper type, this can be a selected set of relevant sections rather than
every page of the paper. **Abstract only** means that extraction was limited to
the abstract. Abstract-only findings must not imply access to details that were
not present in that abstract.

## Validation and graph representation

Before publication, extracted information is checked against the source paper,
and names for compounds, conditions, outcomes, and other topics are made
consistent. A paper can appear in the bibliography without adding a
relationship to the graph. This happens when the source does not support a
clear relationship, the relationship would be misleading if simplified, or it
still needs review. Primary-study and review relationships also need support
from at least two papers before they appear in the overview. Meta-analyses are
shown separately because each paper already combines results from multiple
studies.

The graph is therefore a selected view of relationships that can be shown
clearly. A missing relationship does not show that no relevant research exists.

## Direction, certainty, and risk of bias

Where a direction is meaningful, the graph preserves the paper's reported
interpretation: positive, negative, mixed, unclear, or no detected effect. This
is not simply the mathematical sign of a score. For example, a lower symptom
score can be positive when lower values mean improvement.

The project does not currently assign a universal certainty grade or formal
risk-of-bias judgment to every finding. When a paper reports certainty or
risk-of-bias information, it can be shown as part of that paper's information,
but it is not a project-wide GRADE, Cochrane, or clinical-recommendation rating.

## Corrections and updates

Corrections are made from the source paper forward rather than by editing a
published relationship directly. When a paper is updated, its previous
findings are replaced or removed. A reviewed release then updates the graph,
bibliography, Methods counts, and public site together.

See [`terminology.md`](terminology.md) for the terms used throughout the
project.
