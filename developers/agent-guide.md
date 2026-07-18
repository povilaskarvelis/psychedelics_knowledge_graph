# Psychedelics Knowledge Graph: agent access guide

The Psychedelics Knowledge Graph provides public, read-only access to its active
evidence release through REST/OpenAPI, Model Context Protocol (MCP), and bulk
DuckDB or Parquet downloads.

## Service addresses

- Human documentation: https://psychedelicskg.com/developers/
- REST base URL: https://psychedelics-kg-api.onrender.com/api/v1
- OpenAPI schema: https://psychedelics-kg-api.onrender.com/openapi.json
- Interactive API reference: https://psychedelics-kg-api.onrender.com/docs
- Streamable HTTP MCP: https://psychedelics-kg-api.onrender.com/mcp
- Active release metadata: https://psychedelics-kg-api.onrender.com/api/v1/meta
- Public query schema: https://psychedelics-kg-api.onrender.com/api/v1/schema

No API key is required. All operations are read-only.

## Recommended agent workflow

1. Call `get_release_info` or `GET /api/v1/meta` and retain the release ID.
2. Resolve human labels and aliases with `search_entities` or
   `GET /api/v1/entities/search`.
3. Use canonical entity IDs with `find_evidence`, `get_neighborhood`, or the
   corresponding REST endpoints.
4. Keep primary studies, meta-analyses, and reviews separate using
   `literature_source`.
5. Use `study_count`, not finding-row count, when comparing evidence volume.
6. Return DOI, evidence locator, result direction, and release ID when supporting
   an answer.

The default `main_graph` scope returns findings admitted to the overview graph.
Use `all_normalized` to include findings retained as paper detail.

## MCP tools

- `get_release_info`: release metadata and evidence semantics.
- `search_entities`: resolve compounds, conditions, targets, outcomes, and aliases.
- `get_entity`: retrieve one canonical entity and its counts.
- `find_evidence`: filter and paginate normalized public findings.
- `get_finding`: retrieve one finding with public provenance.
- `get_paper`: retrieve a report by canonical ID or DOI.
- `aggregate_evidence`: aggregate distinct studies, findings, and propositions.
- `get_neighborhood`: retrieve a bounded one-hop evidence neighborhood.

## REST example

Resolve an entity:

```bash
curl -sS \
  "https://psychedelics-kg-api.onrender.com/api/v1/entities/search?q=psilocybin&limit=5"
```

Query primary-study evidence:

```bash
curl -sS \
  "https://psychedelics-kg-api.onrender.com/api/v1/findings/query" \
  -H "Content-Type: application/json" \
  -d '{
    "filters": {
      "compound_ids": ["compound:psilocybin"],
      "literature_sources": ["primary"]
    },
    "scope": "all_normalized",
    "detail_level": "summary",
    "limit": 25
  }'
```

## Bulk downloads

- DuckDB: https://psychedelics-kg-api.onrender.com/api/v1/downloads/database
- Schema: https://psychedelics-kg-api.onrender.com/api/v1/downloads/schema
- Findings: https://psychedelics-kg-api.onrender.com/api/v1/downloads/tables/findings
- Evidence edges: https://psychedelics-kg-api.onrender.com/api/v1/downloads/tables/evidence_edges
- Entities: https://psychedelics-kg-api.onrender.com/api/v1/downloads/tables/entities
- Papers: https://psychedelics-kg-api.onrender.com/api/v1/downloads/tables/papers

Downloads resolve to the active immutable release. Check the release metadata and
checksums before combining results from separate sessions.

## Availability

The public API currently runs on a free preview instance. It may sleep after 15
minutes without traffic. The first request after sleeping can take about one
minute while the service reloads and verifies its database from object storage.
