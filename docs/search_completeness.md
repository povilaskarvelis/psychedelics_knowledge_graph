# Checking Search Completeness

No literature search can prove that it found every relevant paper. This project
therefore keeps a reviewed set of known relevant studies and uses it to test
whether the search is retrieving papers that should reasonably be found.

The canonical file is `data/raw/benchmark_manifest.json`. The filename is kept
for compatibility with older code. In documentation and public-facing text,
call it the **known relevant study set** or **search completeness set**.

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

The current paper corpus then tracks these studies through initial screening,
title and abstract screening, source-text preparation, evidence extraction, and
graph representation. Those later stages answer different questions. A paper
can be successfully found but later excluded, retained only as background, or
kept out of the graph because no finding can be represented reliably.

The older `pipeline/ingest/recall_audit.py` command still reports several legacy
queue and paper-library stages for reproducibility. Do not describe those legacy
stage names as the current end-to-end workflow. For a current release, compare
the known DOI set with the corpus tables and the active graph release as well as
the discovery report.

## Adding studies to the set

Add a study only after it has been judged relevant and its source is known.
Acceptable sources include prior systematic or narrative reviews, reference
lists, citation searching, trial records, expert searching, or automated
discovery followed by review.

Keep enough information to explain the decision, including the source,
selection method, review status, related review DOI where relevant, rationale,
and the study's role in the completeness set. The manifest's machine-readable
field names remain part of the audit trail; they do not need to appear in
reader-facing Methods text.

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
