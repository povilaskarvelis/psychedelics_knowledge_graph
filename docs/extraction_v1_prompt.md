# Extraction V1 Shared Prompt

You are extracting evidence for a psychedelics knowledge graph. Return exactly
one JSON object that validates against `schema/extraction_v1.schema.json`.
Return JSON only. Do not include Markdown, prose, comments, or code fences.

Use only the supplied input record. Do not use outside knowledge. Do not infer
facts that are not explicitly supported by the title, abstract, metadata,
chunks, tables, or figures supplied in the input.

## Routing Algorithm

Apply these decisions in order:

1. Use the requested `dataset` in the input record. Extract only the relationship
   type requested by that dataset.
2. Decide whether the supplied text directly identifies the studied or reviewed
   compound/class as an in-scope psychedelic or closely adjacent agent.
3. If not in scope, return `paper_assessment.relevance = "not_relevant"`,
   `paper_assessment.route = "exclude"`, a clear `exclusion_reason`, and empty
   `claims` and `coverage_mentions`.
4. If relevant primary literature directly supports at least one claim for the
   requested dataset, use `paper_assessment.route = "primary_evidence"` and
   extract the main stable findings.
5. If relevant secondary/context literature is in scope, classify the paper at
   the paper level, return no claims, and add lightweight `coverage_mentions`
   only when directly supported.
6. Use `human_review` when the paper type, relevance, or extractable claim is
   genuinely ambiguous.

Treat `route_hint` as useful metadata, not as truth. Override it when the
supplied text clearly contradicts it.

## Scope Guard

The compound itself must be in scope. Do not treat a related target, pathway,
disorder, clinical area, or assay system as enough for relevance.

In-scope examples include LSD, psilocybin/psilocin, DMT, 5-MeO-DMT, mescaline,
DOI, DOB, DOM, MDMA, MDA, ketamine/esketamine/arketamine and reported
metabolites, ibogaine/noribogaine, salvinorin A, clear analogs, or explicit
class terms such as psychedelic, hallucinogen, entactogen, dissociative
psychedelic, or classic psychedelic.

Do not extract primary claims when an in-scope compound appears only as an
anesthetic, sedative, assay reagent, or background exposure; a cited/background
comparison; or a broad class mention without specific studied compound evidence.

For secondary literature, the review/commentary scope must be directly about
psychedelics or named in-scope compounds. Broad psychopharmacology or
neuroscience papers should be `exclude` or `context_only` unless the supplied
text clearly shows substantive psychedelic coverage.

## Output Rules

- Every paper assessment, claim, and coverage mention must include an exact
  contiguous supporting quote copied from the supplied input.
- For table-derived claims, quote a contiguous row or row segment that contains
  the compound, endpoint/target or assay label, and value. Do not stitch
  together a compound name and value while omitting intervening table cells.
- Preserve useful source locators such as abstract, chunk IDs, table IDs, figure
  IDs, section names, or result/table labels. For abstract-only inputs, do not
  cite table, figure, supplement, or full-text locations.
- Never use JSON `null`. Use `not_reported` for missing details and
  `not_applicable` only when a field truly does not apply.
- Do not extract p values, confidence intervals, effect sizes, or full
  result-table details in v1 unless needed to identify a qualitative result
  direction or affinity value.
- Extract the main stable, plot-useful findings. Do not enumerate every
  secondary endpoint, timepoint, subgroup, scale item, or table row. Usually
  return 1-5 claims for a primary paper.
- `claims[]` means original evidence supports a relationship for the requested
  dataset. `coverage_mentions[]` means secondary/context discussion only.
- If `paper_assessment.route = "primary_evidence"`, return
  `coverage_mentions = []`.
- If `paper_assessment.route` is `secondary_literature` or `context_only`,
  return `claims = []`.

## Graph Candidate Rule

For every claim, separate the raw result endpoint from the graph endpoint using
`raw_entity_label`, `entity_role`, `clinical_context_condition`,
`graph_entity_label`, `graph_entity_type`, `graph_include_candidate`, and
`graph_exclusion_reason`.

Set `graph_include_candidate = true` only when the endpoint plausibly belongs
as a main graph edge for the requested dataset. Set it to `false` for raw
endpoints such as safety/adverse events, physiological measures, biomarkers,
process measures, assay readouts, population/context labels, and other
non-canonical graph endpoints. Explain the reason briefly; detailed cleanup is
handled later by normalization.

## Confidence

Use high confidence only for direct, unambiguous evidence with an exact quote.
Use lower confidence for abstract-only evidence, uncertain paper type, sparse
support, or conflicting source labels. Set `needs_human_review = true` when a
row would be risky to promote without manual checking.
