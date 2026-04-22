# Psychedelics Knowledge Graph

A provenance-aware literature pipeline and web interface for exploring
structured claims about psychedelics, mechanisms, and mental health outcomes.

[Live GUI](https://povilaskarvelis.github.io/psychedelics_knowledge_graph/ui) |
[Pipeline Guide](pipeline/README.md) |
[Evidence Policy](docs/evidence_policy.md)

![Interface screenshot](ui/assets/gui-screenshot.png)

## Overview

This repository builds a local literature corpus, screens papers by relevance
and evidence type, extracts structured claims, validates them, and publishes the
result as a graph plus export files.

The current focus is psychedelics. The workflow can be adapted to other
scientific domains by changing the vocabularies, schemas, and search seeds.

## Workflow

### Literature Search

Discovery scripts query multiple literature APIs, generate DOI-context queues,
and build a local paper library with titles, abstracts, access metadata, and
PDFs when available.

At the conceptual level:

- search is broad enough to support recall across OpenAlex, Semantic Scholar,
  PubMed/PMC, Crossref, and OA metadata sources
- recall can be audited against benchmark DOI manifests before downstream work
- metadata sync happens before triage; PDF download happens after triage
- retrieval provenance is retained in discovery reports and ledgers

Technical note: search and sync live in `pipeline/ingest/` and write to
`data/processed/paper_library_*.json` plus local PDFs under `data/raw/papers/`.

### Sorting Papers

Retrieved papers are classified by relevance and paper type. Triage works at
the `(DOI, compound, target/disorder)` context level so one paper can support
multiple graph edges without accidental DOI-only collapse.

Current paper types include:

- primary results
- review or meta-analysis
- protocol
- conference or poster abstract
- other

Only primary results papers are admitted to the main curated claim set. Weaker
material is blocked or retained separately in exploratory files so it stays
visible without inflating the core graph.

Technical note: the current implementation is mostly deterministic. It uses
normalized titles, abstracts, metadata, protected benchmark/curated contexts,
and synthesized context rescue to assign relevance, `paper_type`,
`source_type`, and evidence quality labels.

### Claim Extraction

The pipeline seeds one claim stub per DOI-context and fills structured fields
from abstracts first, then PDFs when full-text evidence is needed.

- mechanistic claims capture compound-target assay evidence
- disorder claims capture compound-disorder outcome evidence
- disorder claims include a lightweight `result_direction` label:
  `positive`, `null`, `negative`, `mixed`, `unclear`
- each row keeps a provenance locator back to text, table, figure, or abstract
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

The GUI defaults to a stricter primary-results-only view and surfaces paper
type and result direction directly in the interface.

## Repository Layout

- `pipeline/ingest/`: discovery, paper sync, DOI seeding
- `pipeline/review/`: triage and autofill
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
python pipeline/review/triage_paper_library.py --dataset disorder
python pipeline/ingest/sync_paper_library.py --dataset disorder --doi-file data/raw/doi_queue.disorder.triage_relevant.txt
python pipeline/ingest/seed_from_dois.py --dataset disorder --doi-file data/raw/doi_queue.disorder.triage_relevant.txt --replace
python pipeline/review/autofill_stubs_from_abstracts.py --dataset disorder --mark-ready --apply
python pipeline/review/autofill_disorder_from_pdfs.py --dataset disorder --mark-ready --apply
python pipeline/review/curation_queue.py --dataset disorder
python pipeline/extract/promote_ready_stubs.py --dataset disorder --apply
python pipeline/validate/validate_claims.py
python pipeline/publish/export_graph_payload.py
```

For the operational walkthrough, recall gates, provider settings, PDF runtime
setup, and larger search runs, see [pipeline/README.md](pipeline/README.md).
