# API and Agent Access

The project exposes the same promoted evidence release through three machine
interfaces:

- a read-only REST API with an OpenAPI schema;
- a Model Context Protocol (MCP) server for agent clients;
- sanitized DuckDB and Parquet downloads for larger analyses.

The browser remains a static Netlify site. The query service reads the existing
`data/processed/graph_payload_active.json` pointer, so the UI, API, MCP tools,
and downloads identify the same promoted run and release.

## Release and update lifecycle

Public query artifacts are versioned under:

```text
data/processed/query_api_runs/<run_id>/
  manifest.json
  schema.json
  public_api.duckdb
  tables/
    findings.parquet
    evidence_edges.parquet
    entities.parquet
    papers.parquet
    authors.parquet
    paper_authors.parquet
```

Use the normal routed release command after adding papers or extracting new
findings:

```bash
ACTIVATE_DEFAULT=1 bash scripts/build_routed_kg_payload.sh <new-run-id>
```

The command now performs these operations in order:

1. build the normalized KG tables and internal DuckDB database;
2. refresh author identity and authorship tables;
3. build a sanitized public query database and bulk Parquet tables;
4. build the browser graph, dashboard, and detail payloads;
5. validate all artifacts and atomically promote the release.

Promotion fails if the query artifact is absent, belongs to another run, or has
a different finding count from the normalized KG. The service resolves the
active pointer on every request, so no service restart or database migration is
needed after a new artifact is mounted. Pagination cursors include the release
ID and are rejected after a release change, preventing mixed-release result
pages.

Use a new run ID for each published dataset. Rebuilding an already-active run
directory in place is discouraged because immutable run directories make
rollback and reproducibility much simpler.

## Local REST and remote MCP service

Install the service dependencies, if they are not already available:

```bash
python3 -m pip install -r services/query_api/requirements.txt
```

If the active run predates the API implementation, build its query artifact
once:

```bash
python3 pipeline/publish/export_query_api.py \
  --kg-dir data/processed/kg_routed_runs/<run-id> \
  --out-dir data/processed/query_api_runs/<run-id> \
  --run-id <run-id>
```

Start the combined service:

```bash
python3 -m services.query_api
```

The default endpoints are:

- API documentation: `http://127.0.0.1:8000/docs`
- OpenAPI schema: `http://127.0.0.1:8000/openapi.json`
- REST API: `http://127.0.0.1:8000/api/v1`
- Streamable HTTP MCP: `http://127.0.0.1:8000/mcp`

Example evidence query:

```bash
curl -sS http://127.0.0.1:8000/api/v1/findings/query \
  -H 'Content-Type: application/json' \
  -d '{
    "filters": {
      "compounds": ["Psilocybin"],
      "domains": ["clinical_outcome"],
      "literature_sources": ["primary"],
      "year_from": 2018
    },
    "scope": "all_normalized",
    "detail_level": "summary",
    "limit": 25
  }'
```

Resolve names and aliases with `/api/v1/entities/search` before using canonical
entity IDs in repeated queries. The API defaults to `main_graph`; request
`all_normalized` to include findings retained as paper detail.

## Local stdio MCP

Agent clients that launch local MCP processes can use:

```bash
python3 -m services.query_api.stdio
```

The server exposes these read-only tools:

- `get_release_info`
- `search_entities`
- `get_entity`
- `find_evidence`
- `get_finding`
- `get_paper`
- `aggregate_evidence`
- `get_neighborhood`

It also exposes release and public-schema resources. Tool descriptions remind
agents not to merge primary studies, meta-analyses, and reviews, and not to
interpret finding counts as independent study counts.

## Bulk downloads

The REST service streams the active sanitized artifacts at:

- `/api/v1/downloads/database`
- `/api/v1/downloads/schema`
- `/api/v1/downloads/tables/findings`
- `/api/v1/downloads/tables/evidence_edges`
- `/api/v1/downloads/tables/entities`
- `/api/v1/downloads/tables/papers`

Responses include the active release ID and a SHA-256-based ETag. The API never
serves the internal `kg.duckdb`, raw extraction rows, or normalization audit.

## Container deployment

Production uses Cloudflare R2 rather than embedding generated data in Git or in
the container image. Follow the complete one-time and recurring operator
checklist in [R2 query API deployment](r2_deployment.md).

Build the application image from the repository root:

```bash
docker build -f services/query_api/Dockerfile -t psychedelics-kg-api .
```

For an offline or manually mounted container, create a bundle containing only
the active pointer and sanitized active artifact:

```bash
python3 pipeline/publish/build_query_api_bundle.py
```

Run it locally with the bundle mounted read-only:

```bash
docker run --rm -p 8000:8000 \
  -v "$PWD/dist/query-api-bundle/data:/data:ro" \
  -e PKG_DATA_DIR=/data \
  -e PKG_PUBLIC_BASE_URL=https://api.psychedelicskg.com \
  -e PKG_MCP_ALLOWED_HOSTS=api.psychedelicskg.com \
  -e PKG_MCP_ALLOWED_ORIGINS=https://psychedelicskg.com \
  psychedelics-kg-api
```

For production, the R2 publisher uploads a newly generated release only after
guarded promotion succeeds. The code-only container synchronizes the active
database before starting, and bulk downloads redirect directly to R2.
Apply public rate limits at the reverse proxy or container platform. The MCP
SDK keeps DNS-rebinding protection enabled; production host and origin
allowlists must be supplied with the environment variables above.

Optional API browser access is controlled with `PKG_CORS_ORIGINS`, a
comma-separated origin allowlist. The public service is read-only and does not
need user authorization; add OAuth before exposing any private or write
operations.

## Public-data boundary

The exporter uses the same public finding projection as the browser payload and
adds only canonical join identifiers and literature-source classification. It
does not export `raw_row_json`, extraction warnings, human-review flags,
normalization notes, or the normalization audit. Short supporting excerpts
remain third-party material under their original rights and terms; see
`DATA_LICENSE.md`.
