# Psychedelics Knowledge Graph

Provenance-aware literature pipeline and web interface for turning scientific
papers into inspectable claims about psychedelics, mechanisms, and mental
health outcomes.

[Open the live GUI](https://povilaskarvelis.github.io/psychedelics_knowledge_graph/ui) |
[Pipeline guide](pipeline/README.md) |
[Evidence policy](docs/evidence_policy.md)

![Interface screenshot](ui/assets/gui-screenshot.png)

## What This Repository Does

This project turns a messy literature search problem into a structured,
inspectable graph-building workflow.

At a high level it:

- searches for candidate papers
- builds a local paper library with metadata and PDFs when available
- sorts papers by relevance and evidence type
- extracts structured claims with provenance
- validates those claims and publishes them to a browser UI and ORKG-style
  payloads

The current example domain is psychedelics, but the workflow is reusable for
other scientific domains with different vocabularies and schemas.

## Why This Matters for Agentic Science

Agentic science is not just about generating answers. It is about building
systems that can search, decide, extract, and justify those decisions in a way
that a human can inspect.

This repository is a concrete prototype of that idea:

- the pipeline can search and triage literature at scale
- claims keep provenance back to the source paper
- weak evidence can be separated from countable evidence instead of silently
  mixed into the main graph
- the result is visible in a GUI rather than buried in notebooks or prompts

In other words, this is a paper-to-graph workflow designed to support agentic
reasoning over scientific evidence.

## How The Pipeline Works

### 1. Literature Search

The pipeline starts broad. It uses API-based discovery to generate candidate
DOI queues and a local paper library covering titles, abstracts, access
metadata, and PDFs when available.

Conceptually:

- search is optimized for recall first
- a paper can be found before we know whether it is strong evidence
- the paper library becomes the local working set for later triage and
  extraction

Technical note: literature discovery and paper syncing live in
`pipeline/ingest/` and write to `data/processed/paper_library_*.json` plus
local PDFs under `data/raw/papers/`.

### 2. Sorting and Evidence Gating

After retrieval, papers are sorted by relevance and document type. This is a
critical step because not every paper that mentions a topic should count as
main graph evidence.

The pipeline distinguishes between:

- primary results papers
- reviews and meta-analyses
- protocols
- conference or poster abstracts
- other weak or non-countable sources

Only primary results papers are allowed into the main curated claim set. Weaker
rows are retained separately in exploratory files so they are still visible, but
they do not silently inflate the core graph.

Technical note: the current implementation is mostly deterministic and
rule-based. It uses paper metadata, normalized title and abstract text, and
cleanup passes to classify `paper_type`, `source_type`, and evidence quality.

### 3. Claim Extraction

Once papers are sorted, the pipeline seeds claim stubs from DOI queues and then
fills structured fields from abstracts and PDFs.

The extracted claims are intentionally simple and inspectable:

- mechanistic claims capture compound-target assay evidence
- disorder claims capture compound-disorder outcome evidence
- disorder rows also include a lightweight `result_direction` label
  (`positive`, `null`, `negative`, `mixed`, `unclear`)
- every row keeps a provenance locator back to text, table, figure, or abstract

Technical note: extraction today is still relatively conservative and
schema-driven. The goal is not to produce fluent summaries, but to create rows
that can be validated, audited, and later improved.

### 4. Validation, Graphing, and Export

Before publication, curated rows are validated against JSON schemas and
evidence-policy checks. The outputs then feed:

- the browser UI in `ui/`
- ORKG-style export payloads in `data/processed/orkg_payload_*.json`

The GUI defaults to a stricter primary-results-only view and surfaces paper
type and result direction so users can see evidence quality directly.

## Data Model At A Glance

- `data/curated/claims.json`: curated mechanistic claims
- `data/curated/disorder_claims.json`: curated disorder claims
- `data/curated/exploratory_*.json`: weak or demoted claims kept outside the
  main evidence set
- `data/processed/paper_library_*.json`: local paper metadata library
- `data/processed/orkg_payload_*.json`: export payloads for downstream graph use

## Minimal Repository Map

- `pipeline/ingest/`: discovery, paper sync, DOI seeding
- `pipeline/review/`: triage and autofill
- `pipeline/extract/`: promotion into curated claims
- `pipeline/validate/`: validation, cleanup, and audit helpers
- `pipeline/publish/`: ORKG export
- `schema/`: claim schemas and normalization rules
- `ui/`: browser interface

## Running The Pipeline

Requirements:

- Python 3.10+
- standard library only

Typical flow for one dataset:

```bash
python pipeline/ingest/discover_literature.py --dataset disorder
python pipeline/ingest/sync_paper_library.py --dataset disorder --skip-download
python pipeline/review/triage_paper_library.py --dataset disorder --apply-to-stubs
python pipeline/review/autofill_stubs_from_abstracts.py --dataset disorder --apply
python pipeline/extract/promote_ready_stubs.py --dataset disorder --apply
python pipeline/publish/export_orkg_payload.py
```

For the full operational walkthrough, see [pipeline/README.md](pipeline/README.md).
