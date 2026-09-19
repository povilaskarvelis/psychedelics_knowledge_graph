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
6. Follow `meta.next_cursor` with the same operation and filters until it is null.
   See pagination and error recovery below.

Public author records require an OpenAlex or ORCID identity. ORCID is canonical
when available, so OpenAlex profiles carrying the same ORCID resolve to one
author ID. OpenAlex profiles without an ORCID remain separate unless a reviewed
correction explicitly links them. Unresolved name-only authorship records are
excluded rather than merged speculatively. Profiles with conflicting ORCID
evidence are also excluded.

## Interpretation and search semantics

Relationships are literature-retrieval links, not proof of benefit, harm,
causation, or effectiveness. Counts refer to reports, not independent studies.
Keep primary studies, reviews, and meta-analyses separate when describing coverage.
Missing metadata remains unknown; missing relationships do not establish that
no relevant research exists. Catalogue records can have no public relationships
or no broad paper classification.

Author arrays include only resolved public identities and may omit credited
authors. Do not assume they are complete author lists for citations.

- Values within a filter list use **OR**; separate filter fields use **AND**.
- `concept_ids` matches **any** listed concept at either endpoint. Listing a
  compound and condition here does not require a relationship between them.
- Use `subject_ids` and `object_ids` together to search a compound–outcome pair.
  All relationship filters in a paper search must match the **same relationship**.
- Paper `query` searches title, DOI, journal, and credited author names. It does
  not search abstracts or evidence quotations.
- Unknown fields in REST query bodies, including nested filters, and unknown MCP
  arguments are rejected. Use the published schemas and facets; do not invent
  fields such as `graph_view`. Controlled values that do not match the catalogue
  can still return zero results; this does not establish absence of research.

## Pagination and error recovery

Cursors are bound to the data release, operation, filters, and ordering. Keep the
same filters when continuing; page size may change. Reordering or repeating list
values is harmless. Changing string values, filters, or operations requires
starting again without a cursor. REST paper search and MCP `search_papers` share
an operation; author-paper retrieval is a separate operation.

Old cursors issued before query binding are rejected. On REST `400 invalid_query`
for an obsolete/mismatched cursor or `409 release_changed`, discard the cursor
and restart the search. Discard partial pages from the previous release rather
than merging releases. REST `422` identifies invalid request fields; correct the
request before retrying. MCP exposes corresponding tool errors with recovery
instructions. For `503` loading responses, honor `Retry-After` when supplied.

`get_paper` returns at most `relationship_limit` relationships (default 50,
maximum 100). If `relationships_truncated` is true, use `find_relationships` (or
REST `/relationships/query`) with `paper_ids: [data.paper_id]`, starting without a
cursor, then follow its `meta.next_cursor`. That search includes the relationships
already returned by `get_paper`; do not append both lists without deduplicating.

## MCP tools

- `get_release_info`: current version, record counts, scope, and limitations.
- `list_available_filters`: paper types, subtypes, domains, relationship types,
  relationship-scoped endpoint kinds, and website category presets.
- `search_concepts`: resolve labels and aliases to concept IDs. `concept_kinds`
  and `domains` match observed public relationships rather than only the
  concept record's legacy singular metadata.
- `get_concept`: retrieve one concept, its hierarchy, and paper count.
- `search_authors`: resolve a preferred name or known variant to an ORCID/OpenAlex author ID.
- `get_author_papers`: retrieve papers across all types linked to that author.
- `search_papers`: filter papers by metadata, author, concept, domain,
  relationship type, subject/object ID or contextual kind, or year.
- `get_paper`: retrieve one paper, credited authors, and public relationships.
- `find_relationships`: filter deduplicated paper-level concept relationships.

Website categories are documented by `list_available_filters.graph_views` as
convenience presets. API clients can reproduce a website category using those
atomic filters, combine them with narrower filters, or ignore the presets and
query the relationship fields directly. Presets define category membership; they
do not reproduce the overview's parent grouping, subject projections, or display
thresholds.

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

Find primary papers linking psilocybin to major depressive disorder
(resolve IDs with concept search before constructing a query):

```bash
curl -sS \
  "https://psychedelics-kg-api.onrender.com/api/v1/papers/query" \
  -H "Content-Type: application/json" \
  -d '{
    "filters": {
      "subject_ids": ["compound:psilocybin"],
      "object_ids": ["clinical_entity:major_depressive_disorder"],
      "paper_types": ["primary_study"]
    },
    "limit": 25
  }'
```

The equivalent MCP call is `search_papers` with these three filter arguments at
the top level (no `filters` wrapper), plus `limit`.

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
