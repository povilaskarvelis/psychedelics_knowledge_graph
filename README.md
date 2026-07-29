# Psychedelics Knowledge Graph

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21671975.svg)](https://doi.org/10.5281/zenodo.21671975)

A map of psychedelic research that makes findings easier to explore, audit,
and keep up to date.

[Explore the knowledge graph](https://psychedelicskg.com/) ·
[About](https://psychedelicskg.com/about/) ·
[Methods](https://psychedelicskg.com/methods/) ·
[API](https://psychedelicskg.com/api/) ·
[Pipeline guide](pipeline/README.md) ·
[Release guide](docs/releasing.md) ·
[Evidence policy](docs/evidence_policy.md) ·
[API and agent access](docs/agent_access.md)

![Psychedelics Knowledge Graph interface](ui/assets/gui-screenshot.png)

## About the project

Psychedelic research spans clinical outcomes, molecular mechanisms, brain and
behavioral effects, subjective experience, safety, and real-world use. The
evidence is growing quickly but remains scattered across source reports and
research domains.

Psychedelics Knowledge Graph organizes that literature into structured
findings linked to their source reports. Its public interface helps researchers
move between broad patterns, individual findings, and the underlying studies.

The repository also contains the tools used to discover and screen records,
process selected reports, and add new evidence. It records which reports were
included, how their records were screened, and where each finding came from.
Primary studies, meta-analyses, and reviews are kept separate, and null, mixed,
uncertain, and positive findings are retained rather than collapsed into a
single conclusion.

## What this repository contains

This repository includes the full workflow behind the public graph:

1. Find and deduplicate records while preserving how they were discovered.
2. Enrich and screen records, then route selected reports by evidence domain
   and report type.
3. Retrieve and convert available report text.
4. Extract structured findings and link them back to the source text.
5. Validate and normalize source metadata, entities, findings, and relationships.
6. Build the public graph, finding details, bibliography, and Methods views.

The main data is stored in normalized tables. The browser graph presents a
readable view of that data rather than trying to display everything at once.

For machine use, every release can also produce a narrow public catalogue of
papers, concepts, OpenAlex/ORCID-backed authors, and paper-level relationships. It is
available through a read-only REST/OpenAPI service and MCP tools for AI agents.
Bulk data releases are intentionally withheld until their fields and semantics
have a separate publication review. Granular extraction data remains internal;
see the [API and agent access guide](docs/agent_access.md) and
[public data policy](docs/public_data_policy.md).
Production setup is covered by the [R2 public-data and API deployment checklist](docs/r2_deployment.md).

## Repository map

- `pipeline/` — literature discovery, screening, full-text processing,
  extraction, validation, updates, and publishing
- `schema/` — definitions for extracted fields, graph mappings, and standard
  names
- `data/` — curated inputs plus generated local corpus, graph, and publication
  artifacts; generated production data is released through R2
- `about/`, `methods/`, and `feedback/` — public project pages
- `ui/` — shared static browser assets and interface scripts
- `scripts/` — graph and site build entry points
- `docs/` — scope, search, terminology, evidence, and deployment documentation
- `tests/` — pipeline and interface regression tests

For operational commands and the current end-to-end workflow, see the
[pipeline guide](pipeline/README.md). For a targeted correction to one report or
a DOI list, use the [scoped update workflow](docs/scoped_paper_updates.md).

## Local site preview

Preview local UI changes against the currently published R2 data:

```bash
bash scripts/preview_site.sh public
```

Then open <http://127.0.0.1:8011>.

To review an unpublished candidate release, first build and promote it locally
without setting `PUBLISH_QUERY_API_R2=1`, then run:

```bash
bash scripts/preview_site.sh local
```

The local server opens the explicit `?data-source=local` mode and serves only
the generated graph and Methods artifacts named by the candidate release. It
does not expose the repository, papers, `.env`, or other pipeline data. It also
verifies graph checksums and requires the graph, Methods flow, bibliography, and
inclusion audit to name the same run and release before starting.

The preview mode is mandatory; neither preview command has an implicit data
source. A public-mode server rejects `?data-source=local` instead of loading a
different release.

## Project principles

- Link every public finding back to its source.
- Keep discovery broad while making graph inclusion conservative.
- Separate primary research, meta-analyses, reviews, and non-primary context.
- Treat uncertainty, disagreement, and missing evidence as meaningful results.
- Keep the evidence base reproducible, correctable, and incrementally updatable.

## Licensing and citation

The software is released under the [Apache License 2.0](LICENSE). Project-created
public data is released under [CC0 1.0](DATA_LICENSE.md); third-party reports,
abstracts, figures, tables, and provider data retain their original rights and
terms.

If you use the project or its public API, cite both the software version and the
literature update represented by the graph:

> Karvelis, Povilas. (2026). *Psychedelics Knowledge Graph* (software v1.0.0;
> literature updated 2026-07-15). Zenodo.
> https://doi.org/10.5281/zenodo.21671976

The version-specific DOI identifies the software release, while the literature
date identifies the evidence represented by the graph. The [concept
DOI](https://doi.org/10.5281/zenodo.21671975) always resolves to the project's
latest archived software version.
