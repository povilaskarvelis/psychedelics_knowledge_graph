# Psychedelics Knowledge Graph

A provenance-aware literature pipeline and web interface for exploring
structured claims about psychedelics, mechanisms, and mental health outcomes.

[Live GUI](https://povilaskarvelis.github.io/psychedelics_knowledge_graph/ui) |
[Pipeline Guide](pipeline/README.md) |
[Search Seed Strategy](docs/search_seed_strategy.md) |
[Search Completeness](docs/search_completeness.md) |
[Evidence Policy](docs/evidence_policy.md)

![Interface screenshot](ui/assets/gui-screenshot.png)

## Overview

This repository builds a local literature corpus, screens papers by relevance
and evidence type, extracts structured claims, validates them, and publishes the
result as a graph plus export files.

The current focus is psychedelics. The workflow can be adapted to other
scientific domains by changing the vocabularies, schemas, and search seeds.

## Knowledge Graph Architecture

The project is intended to build a real, provenance-aware knowledge graph, not
only a visual network diagram. The visual graph is a digestible view over a
larger graph-shaped data model.

The KG has several layers:

- `Paper` records capture literature metadata, discovery provenance, screening
  status, PDF/full-text availability, publication type, and study context.
- `Claim` records capture extracted scientific assertions from papers, with
  evidence locators, source family, paper type, study design, result direction,
  assay/outcome fields, confidence, and validation status.
- Canonical entity nodes represent compounds, clinical indications, mechanistic
  targets, papers, and evidence records using stable identifiers.
- Semantic edges aggregate evidence into relationships such as
  `compound -> indication` and `compound -> target`.
- View payloads turn the canonical KG into readable interfaces, including the
  main graph, the Methods literature landscape, paper flow, and gap views.

This separation matters. The canonical KG can grow as more papers and claims are
screened, extracted, corrected, or updated. The UI does not need to display
every node and edge directly; it can summarize important KG components without
losing the underlying provenance.

During the transition to the full pipeline, exploratory KG views can be built
from paper libraries, screening outputs, converted full texts, and existing
curated claims. Once full-text LLM extraction is complete, the same projection
can be rebuilt with up-to-date paper records and extracted claims.

## Workflow

### Literature Search

Discovery scripts query multiple literature APIs, generate DOI-context queues,
and build a local paper library with titles, abstracts, access metadata, and
PDFs when available.

At the conceptual level:

- search is broad enough to support retrieval across OpenAlex, Semantic Scholar,
  PubMed/PMC, Crossref, and OA metadata sources
- retrieval can be checked against a known relevant study set before downstream work
- metadata sync happens before abstract screening; PDF download happens after
  abstract screening
- retrieval provenance is retained in discovery reports and ledgers

Technical note: search and sync live in `pipeline/ingest/` and write to
`data/processed/paper_library_*.json` plus local PDFs under `data/raw/papers/`.

### Screening Papers

Retrieved papers now move through abstract screening before PDF acquisition.
The old rule-based triage remains available for legacy audits, but it is not
the default gate for the live graph. Abstract screening works at the
`(DOI, compound, target/disorder)` context level so one paper can support
multiple graph edges without accidental DOI-only collapse.

Current paper types include:

- primary results
- review or meta-analysis
- protocol
- conference or poster abstract
- other

Only primary results papers are admitted to the default primary-evidence graph.
Reviews, systematic reviews, and meta-analyses are retained as secondary
literature and can be included with the secondary-source view/checkmark.
Protocols, conference abstracts, commentary, and corrections are retained as
non-primary context where possible without inflating primary-evidence counts.

Technical note: the current default path is non-destructive. It uses a
deterministic no-signal pre-screen, then local LLM abstract screening for
relevance and quote-supported contexts only. Full-text eligibility assessment,
source-family labeling, evidence-strength labeling, and data extraction happen
later from PDFs or abstract-only fallback evidence.

### Claim Extraction

The pipeline seeds one claim stub per DOI-context and fills structured fields
from abstracts first, then PDFs when full-text evidence is needed. The full-text
LLM step is best described as full-text evidence assessment plus data
extraction; use `adjudication` only for the final conflict-resolution decision
when model/rule/curator outputs disagree.

- mechanistic claims capture compound-target assay evidence
- disorder claims capture compound-disorder outcome evidence
- disorder claims include a lightweight `result_direction` label:
  `positive`, `null`, `negative`, `mixed`, `unclear`
- each row keeps a provenance locator back to text, table, figure, or abstract
- bibliographic and synthesis fields include journal, publication type, trial
  registry IDs, sample size, comparator/intervention details, outcomes, effect
  sizes, adverse events, funding, conflicts of interest, and risk-of-bias notes
- PDF-heavy extraction scripts auto-run inside the `psychkg-pdf` conda
  environment when it exists

The current extraction approach is schema-driven and conservative. The output is
meant to be auditable and easy to improve over time.

### Validation and Outputs

Curated rows are checked against JSON schemas and evidence-policy rules before
publication.

Main outputs:

- browser interface in `ui/`
- curated claim files in `data/curated/`
- exploratory claim files for weak or demoted evidence
- graph export payloads in `data/processed/graph_payload_*.json`
- canonical KG projection files in `data/kg/` when
  `python pipeline/kg/build_kg.py` is run locally
- the GUI defaults to primary evidence and has a `Secondary sources` checkbox
  for reviews, systematic reviews, and meta-analyses

The GUI defaults to a stricter primary-results-only view and surfaces paper
type and result direction directly in the interface.

## Repository Layout

- `pipeline/ingest/`: discovery, paper sync, DOI seeding
- `pipeline/review/`: abstract screening, legacy triage audit, and autofill
- `pipeline/extract/`: promotion into curated claims
- `pipeline/validate/`: validation, cleanup, and audit helpers
- `pipeline/publish/`: export
- `schema/`: claim schemas and normalization rules
- `ui/`: browser interface
- `data/curated/`: main and exploratory claim sets
- `data/processed/`: paper libraries, reports, stubs, and export payloads

## Quick Start

Requirements:

- Python 3.10+ for the core pipeline
- optional `psychkg-pdf` conda environment for PDF-heavy extraction
- local credentials in `pipeline/config.local.yaml` for API keys/emails

Minimal current flow for one dataset after credentials are configured:

```bash
python pipeline/ingest/run_extensive_search.py --dataset disorder --provider hybrid --discover-only
python pipeline/ingest/sync_paper_library.py --dataset disorder --skip-download
python pipeline/review/run_local_llm_abstract_screening.py --dataset disorder --deterministic-prescreen --deterministic-prescreen-only --only-with-abstract --only-undownloaded
python pipeline/review/run_local_llm_abstract_screening.py --dataset disorder --doi-file data/raw/doi_queue.disorder.deterministic_prescreen_retained.txt --model qwen3:14b --only-with-abstract --continue-on-error --timeout-sec 0 --resume-from-checkpoint --num-ctx 4096
python pipeline/ingest/sync_paper_library.py --dataset disorder --doi-file data/raw/doi_queue.disorder.llm_fulltext_candidates.txt
python pipeline/ingest/seed_from_dois.py --dataset disorder --doi-file data/raw/doi_queue.disorder.llm_relevant.txt --replace
python pipeline/review/autofill_stubs_from_abstracts.py --dataset disorder --mark-ready --apply
python pipeline/review/autofill_disorder_from_pdfs.py --dataset disorder --mark-ready --apply
python pipeline/review/curation_queue.py --dataset disorder
python pipeline/extract/promote_ready_stubs.py --dataset disorder --apply
python pipeline/validate/validate_claims.py
python pipeline/publish/export_graph_payload.py
```

For the operational walkthrough, search completeness checks, provider settings,
PDF runtime setup, and larger search runs, see [pipeline/README.md](pipeline/README.md).
