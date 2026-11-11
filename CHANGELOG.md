# Changelog

Notable changes to Psychedelics Knowledge Graph are recorded here. Releases use
[Semantic Versioning](https://semver.org/).

## Unreleased

Planned as 3.0.0.

- Screened all records again and extracted all findings again with GPT-6 Luna,
  which replaces Gemini 3 Flash, using revised extraction instructions and
  output schemas.
- Updated the evidence base through November 10, 2026, representing 23,855
  papers: 18,794 primary studies, 4,720 reviews, and 341 meta-analyses.
- Added phencyclidine (PCP) to the compounds in scope, with its literature
  searched from 1800 onward.
- Increased the number of papers whose findings are read from the full text,
  from 10,324 to 11,539. Every full text is checked to belong to the paper it
  is used for, and a preprint's text is no longer used in place of the
  published article.
- Revised how findings are mapped to compounds and research-area concepts.
- Removed retracted papers from the graph and added notices to papers with an
  expression of concern.
- Kept authors who share a name apart, and matched OpenAlex profiles to ORCID
  records when the name and coauthors agree.
- Compute finding IDs from the finding's content, so they stay the same across
  rebuilds; IDs from earlier releases change.
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
