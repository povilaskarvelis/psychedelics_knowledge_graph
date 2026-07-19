# API and agent access

The project provides two read-only machine interfaces:

- REST with an OpenAPI schema;
- Model Context Protocol (MCP) for AI agents.

Public entry points:

- `https://psychedelicskg.com/api/`
- `https://psychedelicskg.com/api/agent-guide.md`
- `https://psychedelics-kg-api.onrender.com`
- `https://psychedelics-kg-api.onrender.com/mcp`

## Public data contract

The API is deliberately narrower than the internal knowledge graph. It exposes:

- `papers`: publication metadata plus controlled broad type and subtype;
- `concepts`: standardized labels, aliases, categories, and hierarchy;
- `authors`: OpenAlex/ORCID-backed identities, name variants, and paper counts;
- `paper_authors`: links between papers and ORCID/OpenAlex author identities;
- `relationships`: deduplicated paper-level concept relationships.

It does not expose granular findings, effect or statistical fields, source
quotes, result direction, confidence, extraction warnings, human-review state,
or other internal curation detail.

Bulk database and table releases are intentionally disabled while the public
data contract is still being reviewed. See [Public data policy](public_data_policy.md).

Public author records require an OpenAlex or ORCID identity. ORCID is canonical
when available, including when it links multiple OpenAlex profiles. Profiles
without an ORCID remain separate unless a reviewed correction explicitly links
them. Name-only rows are kept out of the public catalogue rather than merged
without external evidence. The export fails if fewer than 95% of authorship
rows have a structured, non-conflicting identity. Profiles carrying conflicting
ORCID evidence are excluded from the public catalogue.

## Release and update lifecycle

Public catalogue artifacts are versioned under:

```text
data/processed/query_api_runs/<run_id>/
  manifest.json
  schema.json
  public_api.duckdb
```

`public_api.duckdb` is an unpublished runtime artifact used by the API service,
not a public data release. The build does not create downloadable Parquet copies.

After adding papers or rebuilding the graph, run the normal routed release
command:

```bash
ACTIVATE_DEFAULT=1 bash scripts/build_routed_kg_payload.sh <new-run-id>
```

The build creates the internal graph, refreshes authorship, creates and validates
the public catalogue, builds the website payloads, and then updates the current
release pointer. The public export fails when keys are null or duplicated, joins
are broken, fields are undocumented, paper classification conflicts within one
paper, the generated tables do not match the manifest, or structured author
coverage falls below 95%.

When the evidence itself is unchanged and only author resolution, the public
schema, API behavior, or browser payload changed, run:

```bash
bash scripts/refresh_public_release.sh
```

The refresh gives the graph and API one shared public release ID, validates and
uploads both releases, and switches each R2 pointer only after its immutable
files pass checksum verification. Data-only updates do not require a Git or
Netlify deployment.

Pagination cursors contain the release ID. A cursor from an older release is
rejected so results from two versions are not accidentally combined.

## Local service

Install dependencies:

```bash
python3 -m pip install -r services/query_api/requirements.txt
```

Build a catalogue for an existing run when needed:

```bash
python3 pipeline/publish/export_query_api.py \
  --kg-dir data/processed/kg_routed_runs/<run-id> \
  --out-dir data/processed/query_api_runs/<run-id> \
  --run-id <run-id>
```

Start REST and remote MCP together:

```bash
python3 -m services.query_api
```

Local endpoints:

- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/openapi.json`
- `http://127.0.0.1:8000/api/v1`
- `http://127.0.0.1:8000/mcp`

Example paper query:

```bash
curl -sS http://127.0.0.1:8000/api/v1/papers/query \
  -H 'Content-Type: application/json' \
  -d '{
    "filters": {
      "paper_types": ["primary_study"],
      "concept_ids": ["compound:psilocybin"],
      "domains": ["clinical_outcome"],
      "year_from": 2018
    },
    "limit": 25
  }'
```

Use `/api/v1/facets` to discover valid controlled values and
`/api/v1/concepts/search` or `/api/v1/authors/search` to resolve IDs.

## MCP tools

The local stdio server is available with:

```bash
python3 -m services.query_api.stdio
```

Both MCP transports expose:

- `get_release_info`
- `list_available_filters`
- `search_concepts`
- `get_concept`
- `search_authors`
- `get_author_papers`
- `search_papers`
- `get_paper`
- `find_relationships`

## Bulk data policy

The REST service has no bulk-download routes. `/api/v1/schema` documents tables,
fields, keys, and limitations used by the query service, but does not return the
underlying records. A future downloadable release requires a separately reviewed
field allowlist, complete documentation, integrity checks, licensing review,
versioning, checksums, release notes, and manual approval.

## Deployment

Production stores generated browser and API data in Cloudflare R2 rather than
Git or the container image. See [R2 deployment](r2_deployment.md) for the setup
and release checklist.

Build the image from the repository root:

```bash
docker build -f services/query_api/Dockerfile -t psychedelics-kg-api .
```

The code-only service starts immediately and loads its unpublished query database
from a private R2 bucket in the background. The public browser payload lives in a
different R2 bucket. Apply public rate limits at the hosting layer. The API is
read-only and does not require user authorization; authentication must be added
before any private or write operation is introduced.
