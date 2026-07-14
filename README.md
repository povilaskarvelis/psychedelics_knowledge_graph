# Psychedelics Knowledge Graph

A map of psychedelic research that makes findings easier to explore, audit,
and keep up to date.

[Explore the knowledge graph](https://psychedelicskg.com/) ·
[Methods](https://psychedelicskg.com/ui/methods.html) ·
[Pipeline guide](pipeline/README.md) ·
[Evidence policy](docs/evidence_policy.md)

![Psychedelics Knowledge Graph interface](ui/assets/gui-screenshot.png)

## About the project

Psychedelic research spans clinical outcomes, molecular mechanisms, brain and
behavioral effects, subjective experience, safety, and real-world use. The
evidence is growing quickly but remains scattered across source reports and
research domains.

The Psychedelics Knowledge Graph organizes that literature into structured
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

## Repository map

- `pipeline/` — literature discovery, screening, full-text processing,
  extraction, validation, updates, and publishing
- `schema/` — definitions for extracted fields, graph mappings, and standard
  names
- `data/` — curated inputs, processed corpus tables, graph tables, and public
  payloads
- `ui/` — the static browser interface and Methods page
- `scripts/` — graph and site build entry points
- `docs/` — scope, search, terminology, evidence, and deployment documentation
- `tests/` — pipeline and interface regression tests

For operational commands and the current end-to-end workflow, see the
[pipeline guide](pipeline/README.md). For a targeted correction to one report or
a DOI list, use the [scoped update workflow](docs/scoped_paper_updates.md).

## Local site preview

Build the curated static site and serve the same `dist/` output used for
deployment:

```bash
bash scripts/build_site.sh
python3 -m http.server 8011 --bind 127.0.0.1 --directory dist
```

Then open <http://127.0.0.1:8011>.

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

If you use the project or its public data exports, please cite it using
[`CITATION.cff`](CITATION.cff).
