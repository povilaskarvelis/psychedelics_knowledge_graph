# Search Completeness Practice

This project maintains a known relevant study set to support a high-sensitivity
literature search strategy. The goal is to follow systematic/scoping-review
search practice: develop broad searches, document exact sources and dates, check
that expected relevant studies are retrieved, and revise or explain misses.

The canonical file is `data/raw/benchmark_manifest.json`. The filename is kept
for compatibility with older pipeline code, but project methods should describe
it as the known relevant study set or search completeness set.

## How The Set Is Used

- Search strategy development: known key studies help reveal missing compound,
  target, disorder, outcome, and study-design terms.
- Completeness checks: after discovery, the audit asks whether known relevant
  DOI records appear in discovered, triage, library, PDF, and curated stages.
- Citation chasing: source reviews and known relevant studies can seed bounded
  reference/citation expansion.
- Protected retention: known relevant DOI-contexts are kept from silently
  falling out of capped queues.

## How To Add Studies

Add studies when they are manually judged relevant and come from one or more
traceable sources: prior systematic or narrative reviews, source-review
reference lists, citation chasing, clinical-trial records, manual expert search,
or automated discovery followed by review.

Each added study should keep enough provenance to explain why it belongs:
`source`, `selection_method`, `review_status`, `source_review_dois`, `rationale`,
and a study role such as `search_development_seed`,
`known_relevant_primary_or_mechanistic_study`,
`known_relevant_follow_up_study`, `known_relevant_mechanistic_structure_study`,
or `known_relevant_mechanistic_pathway_study`.

## How To Interpret Misses

A missed known relevant study is not automatically a pipeline failure. It should
trigger one of three actions:

- Revise the search strategy with better synonyms, source coverage, citation
  chasing, or provider-specific query variants.
- Document that the study is outside the current review scope.
- Document that the study is not retrievable from the selected sources or lacks
  reliable DOI/indexing metadata.

Coverage of the known relevant study set should not be presented as proof that
all relevant literature has been found. It is a transparent completeness and
quality-assurance check for the current search workflow.
