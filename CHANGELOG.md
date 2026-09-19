# Changelog

Notable changes to Psychedelics Knowledge Graph are recorded here. Releases use
[Semantic Versioning](https://semver.org/).

## Unreleased

- Reject unsupported REST query-body fields and MCP arguments instead of silently
  ignoring them. Clients with extra fields must correct their requests.
- Add subject/object ID filters to paper search for matching a compound–outcome
  pair on the same relationship.
- Bind pagination cursors to the operation and filters as well as the release.
  Previously issued cursors must be discarded and pagination restarted.
- Clarify agent guidance on relationship interpretation, OR/AND filtering,
  incomplete author lists, and truncated relationship results.

## [2.0.0] - 2026-09-18

- Added a dedicated Analyze workspace that presents the graph through
  interactive charts and summaries across compounds, research areas, authors,
  journals, and changes over time, with paths back to the underlying studies.
- Updated the evidence base through September 15, 2026, representing 21,735
  papers: 16,731 primary studies, 4,672 reviews, and 332 meta-analyses.
- Improved author identity resolution using reviewed OpenAlex and ORCID
  information, reducing fragmented and incorrectly merged author records.

## [1.0.0] - 2026-07-29

Initial release.

[2.0.0]: https://github.com/povilaskarvelis/psychedelics_knowledge_graph/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/povilaskarvelis/psychedelics_knowledge_graph/releases/tag/v1.0.0
