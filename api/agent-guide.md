# Psychedelics Knowledge Graph: API guide for agents

The public, read-only API provides a curated catalogue of papers, standardized
concepts, OpenAlex/ORCID-backed authors, and deduplicated paper-level relationships.
Granular extracted findings, statistics, source quotes, result direction, and
internal curation data are intentionally excluded.

## Service addresses

- Human documentation: https://psychedelicskg.com/api/
- REST base URL: https://psychedelics-kg-api.onrender.com/api/v1
- OpenAPI schema: https://psychedelics-kg-api.onrender.com/openapi.json
- Interactive API reference: https://psychedelics-kg-api.onrender.com/docs
- Remote MCP server: https://psychedelics-kg-api.onrender.com/mcp
- Data version and counts: https://psychedelics-kg-api.onrender.com/api/v1/meta
- Database structure: https://psychedelics-kg-api.onrender.com/api/v1/schema

No API key is required.

## Recommended workflow

1. Call `get_release_info` and retain the release ID.
2. Call `list_available_filters` instead of guessing controlled values.
3. Resolve labels and aliases with `search_concepts` when filtering by topic.
4. Resolve preferred names or known variants with `search_authors` when filtering by author.
5. Use `search_papers` for literature retrieval and `find_relationships` for
   graph relationships.
6. Follow `next_cursor` until it is null when complete pagination is required.

Public author records require an OpenAlex or ORCID identity. ORCID is canonical
when available, so OpenAlex profiles carrying the same ORCID resolve to one
author ID. OpenAlex profiles without an ORCID remain separate unless a reviewed
correction explicitly links them. Unresolved name-only authorship records are
excluded rather than merged speculatively. Profiles with conflicting ORCID
evidence are also excluded.

## MCP tools

- `get_release_info`: current version, record counts, scope, and limitations.
- `list_available_filters`: paper types, subtypes, domains, relationship types,
  relationship-scoped endpoint kinds, and reproducible website-view presets.
- `search_concepts`: resolve labels and aliases to concept IDs. `concept_kinds`
  and `domains` match observed public relationships rather than only the
  concept record's legacy singular metadata.
- `get_concept`: retrieve one concept, its hierarchy, and paper count.
- `search_authors`: resolve a preferred name or known variant to an ORCID/OpenAlex author ID.
- `get_author_papers`: retrieve papers across all types linked to that author.
- `search_papers`: filter papers by metadata, author, concept, domain,
  relationship type, relationship-scoped subject/object kind, or year.
- `get_paper`: retrieve one paper, credited authors, and public relationships.
- `find_relationships`: filter deduplicated paper-level concept relationships.

Website categories are documented by `list_available_filters.graph_views` as
convenience presets. API clients can reproduce a website category using those
atomic filters, combine them with narrower filters, or ignore the presets and
query the relationship fields directly.

## REST examples

Discover valid filters:

```bash
curl -sS \
  "https://psychedelics-kg-api.onrender.com/api/v1/facets"
```

Resolve a concept:

```bash
curl -sS \
  "https://psychedelics-kg-api.onrender.com/api/v1/concepts/search?q=psilocybin&limit=5"
```

Find primary papers in a domain that involve that concept:

```bash
curl -sS \
  "https://psychedelics-kg-api.onrender.com/api/v1/papers/query" \
  -H "Content-Type: application/json" \
  -d '{
    "filters": {
      "concept_ids": ["compound:psilocybin"],
      "paper_types": ["primary_study"],
      "domains": ["clinical_outcome"]
    },
    "limit": 25
  }'
```

Find relationships where NMDA receptor is used specifically as a target:

```bash
curl -sS \
  "https://psychedelics-kg-api.onrender.com/api/v1/relationships/query" \
  -H "Content-Type: application/json" \
  -d '{
    "filters": {
      "object_ids": ["mechanistic_entity:nmda_receptor"],
      "object_kinds": ["target"]
    },
    "limit": 25
  }'
```

Find an author, then retrieve all papers linked to that identity:

```bash
curl -sS \
  "https://psychedelics-kg-api.onrender.com/api/v1/authors/search?q=carhart-harris"

curl -sS \
  "https://psychedelics-kg-api.onrender.com/api/v1/authors/AUTHOR_ID/papers"
```

## Access policy

Bulk database and table downloads are not currently published. Use the scoped
REST or MCP operations above. The `/api/v1/schema` endpoint documents the query
contract; it is not a bulk dataset. Record the release ID before combining
paginated results from separate sessions.

## Availability

The public API currently runs on a free preview instance. It may sleep after a
period without traffic. The first request after sleeping can take about one
minute while the service reloads and verifies its database from object storage.
