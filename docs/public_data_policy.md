# Public data policy

The public interfaces are intentionally narrower than the internal knowledge
graph. A field or table is not public merely because the pipeline can generate
it.

## Current access

- The REST API and MCP server provide scoped, read-only queries over reviewed
  catalogue fields for papers, concepts, externally identified authors, and
  paper-level relationships.
- The browser receives only the allowlisted fields required to render the
  interactive graph, filters, summaries, evidence cards, Methods flow, and
  bibliography. The release also retains the generated graph-inclusion audit
  used to verify those public Methods statuses.
- Bulk database and table downloads are not published.
- `/api/v1/schema` documents the query contract but does not return data rows.

Anything sent to a web browser is publicly retrievable. Browser-field controls
therefore live in the exporter, not only in page links or documentation. New
extraction columns remain private unless they are deliberately added to the
browser allowlist and reviewed.

The API's DuckDB file is a service runtime artifact. It is stored in a private
R2 bucket with no custom domain or public `r2.dev` address. It is not a data
release.

## Publication gate for future bulk releases

A downloadable dataset may be introduced only after all of the following are
complete:

1. An explicit table and field allowlist defines the release.
2. Stable identifiers, uniqueness, required values, and foreign keys pass
   automated checks.
3. Every field has documented meaning, grain, limitations, provenance, and
   licensing status.
4. Ambiguous or provisional categories are resolved, excluded, or clearly
   versioned as such.
5. The release has a version, date, checksums, release notes, citation guidance,
   and a retained schema.
6. A human reviewer approves the exact generated artifact.

When these conditions are met, downloads should be presented openly as a
versioned data release. Hiding a public download behind an undocumented API URL
is not an access-control mechanism.

## Automated safeguards

The release pipeline fails when the public field contract contains forbidden
internal fields or duplicate entries. The public R2 pointer is switched only
after all required graph and Methods files are present and checksum-verified.
The query build emits only the private DuckDB runtime and its schema; it does
not emit Parquet download tables. The private API synchronizer rejects any
runtime manifest containing files other than the database and schema.
