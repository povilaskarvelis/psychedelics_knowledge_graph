# Extraction Profile Matrix

Extraction is selected by three inputs:

- `domain_route`: what kind of information we want.
- `paper_type`: how the evidence is framed.
- `text_depth`: whether extraction sees article text or only the abstract.

`article_text` means the supplied article text may be the full body or selected
sections, chunks, tables, figures, or supplement text. It should not be treated
as a promise that the complete paper was supplied.

## Primary Studies

Primary studies extract original empirical results. The base prompt is selected
by paper type and text depth; domain scope notes define the evidence target; the
domain schema defines the output fields.

| Domain | Paper Type | Article Text | Abstract Only |
| --- | --- | --- | --- |
| any primary domain | primary_study | `docs/extraction_profiles/paper_type/primary_article_text.md` + scope notes + domain schema | `docs/extraction_profiles/paper_type/primary_abstract_only.md` + scope notes + domain schema |

## Secondary And Review Papers

These are not de-emphasized; they are separate paper-type profiles.

| Domain | Paper Type | Article Text | Abstract Only |
| --- | --- | --- | --- |
| any selected domain | meta_analysis | `docs/extraction_profiles/paper_type/meta_analysis_article_text.md` + scope notes + `schema/extraction_profiles/meta_analysis/<domain>.schema.json` | `docs/extraction_profiles/paper_type/meta_analysis_abstract_only.md` + scope notes + the same domain schema |
| any selected domain | structured_or_narrative_review | `docs/extraction_profiles/paper_type/review_article_text.md` + scope notes + `schema/extraction_profiles/review/<domain>.schema.json` | `docs/extraction_profiles/paper_type/review_abstract_only.md` + scope notes + the same domain schema |

## No-Extraction Routes

`guideline_consensus`, `context_only_or_skip`, and `no_extraction` are explicit
non-extraction profiles for now. They stay visible in routing/accounting but do
not get model extraction prompts.
