# Checking Search Completeness

No literature search can prove that it found every relevant paper. This project
therefore keeps a reviewed set of known relevant studies and uses it to test
whether the search is retrieving papers that should reasonably be found.

This reviewed collection is called the **known relevant study set**. It is a
quality check for the search, not the source of papers included in the graph.

## What this check does

- **Improves the search vocabulary.** Known studies can reveal missing compound,
  target, condition, outcome, or study-design terms.
- **Tests retrieval.** After a search, the check asks whether the known studies
  were found and records which source, query, and search run found them.
- **Supports citation searching.** Relevant reviews and primary studies can seed
  bounded reference and citation searches.
- **Protects known records.** Known relevant papers are kept from silently
  disappearing when a provider limits the number of returned results.
- **Explains misses.** A missing study should lead to a search revision or a
  documented explanation about scope, indexing, or identifier quality.

The project tracks these studies through screening, preparation of available
article text, evidence extraction, and publication. Those stages answer
different questions. A paper can be found successfully but later excluded,
kept only as background, or left out of the graph because no relationship can
be represented reliably.

## Adding studies to the set

Add a study only after it has been judged relevant and its source is known.
Acceptable sources include prior systematic or narrative reviews, reference
lists, citation searching, trial records, expert searching, or automated
discovery followed by review.

Keep enough information to explain the decision, including the source,
selection method, review status, related review DOI where relevant, rationale,
and the study's role in the completeness set.

## Interpreting a miss

A missed known relevant study is not automatically a pipeline failure. It
should lead to one of three outcomes:

- revise the search with better synonyms, source coverage, citation searching,
  or source-specific query variants;
- document that the study falls outside the current scope; or
- document that the selected sources cannot retrieve it reliably, for example
  because it lacks usable indexing or identifier metadata.

Coverage of this set is a transparent quality check, not an estimate of total
recall and not a rule for inclusion in the graph.
