# Psychedelics Knowledge Graph

A provenance-aware literature pipeline and web interface for exploring
structured claims about psychedelics, mechanisms, and mental health outcomes.

[Live GUI](https://povilaskarvelis.github.io/psychedelics_knowledge_graph/ui) |
[Pipeline Guide](pipeline/README.md) |
[Evidence Policy](docs/evidence_policy.md)

![Interface screenshot](ui/assets/gui-screenshot.png)

## Overview

This repository builds a local literature corpus, sorts papers by relevance and
evidence type, extracts structured claims, validates them, and publishes the
result as a graph plus export files.

The current focus is psychedelics. The workflow can be adapted to other
scientific domains by changing the vocabularies, schemas, and search seeds.

## Workflow

### Literature Search

Discovery scripts query literature APIs, generate DOI queues, and build a local
paper library with titles, abstracts, access metadata, and PDFs when available.

At the conceptual level:

- search is broad enough to support recall
- the paper library becomes the working set for later triage and extraction
- retrieval happens before strong evidence judgments are made

Technical note: search and sync live in `pipeline/ingest/` and write to
`data/processed/paper_library_*.json` plus local PDFs under `data/raw/papers/`.

### Sorting Papers

Retrieved papers are classified by relevance and paper type. Current paper
types include:

- primary results
- review or meta-analysis
- protocol
- conference or poster abstract
- other

Only primary results papers are admitted to the main curated claim set. Weaker
material is retained separately in exploratory files so it stays visible
without inflating the core graph.

Technical note: the current implementation is mostly deterministic. It uses
normalized titles, abstracts, metadata, and cleanup passes to assign
`paper_type`, `source_type`, and evidence quality labels.

### Claim Extraction

The pipeline seeds claim stubs from DOI queues and fills structured fields from
abstracts and PDFs.

- mechanistic claims capture compound-target assay evidence
- disorder claims capture compound-disorder outcome evidence
- disorder claims include a lightweight `result_direction` label:
  `positive`, `null`, `negative`, `mixed`, `unclear`
- each row keeps a provenance locator back to text, table, figure, or abstract

The current extraction approach is schema-driven and conservative. The output is
meant to be auditable and easy to improve over time.

### Validation and Outputs

Curated rows are checked against JSON schemas and evidence-policy rules before
publication.

Main outputs:

- browser interface in `ui/`
- curated claim files in `data/curated/`
- exploratory claim files for weak or demoted evidence
- ORKG-style export payloads in `data/processed/orkg_payload_*.json`

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

- Python 3.10+
- standard library only

Example flow for one dataset:

```bash
python pipeline/ingest/discover_literature.py --dataset disorder
python pipeline/ingest/sync_paper_library.py --dataset disorder --skip-download
python pipeline/review/triage_paper_library.py --dataset disorder --apply-to-stubs
python pipeline/review/autofill_stubs_from_abstracts.py --dataset disorder --apply
python pipeline/extract/promote_ready_stubs.py --dataset disorder --apply
python pipeline/publish/export_orkg_payload.py
```

For the operational walkthrough, command variants, and larger search runs, see
[pipeline/README.md](pipeline/README.md).
