# Final prompt-only review validation on 50 new papers

Date: 2026-07-11

## Test

The validation set contains 50 reviews that do not appear in the development
set: 29 with full text and 21 with abstract only. The extraction structure was
unchanged: two calls for full text and one for abstract only. No repair,
correction, routing, or evaluator calls were used.

Before examining the extraction results, the supplied paper objectives,
abstracts, discussions, and conclusions were read and summarized in
`manual_gold_summary.csv`.

## Prompt changes tested

The prompts were revised to:

- describe bibliometric themes as patterns in the literature rather than proof
  of the underlying scientific relationship;
- check every separately stated objective dimension;
- retain named treatments when a small evidence set reports distinct results;
- allow an abstract-visible descriptive relationship into the graph when it
  can be stated faithfully without a directional result.

No schema fields or model steps were added.

## Run result

- 50/50 papers completed successfully.
- 79 model calls, no retries, and no correction calls.
- 793,084 total tokens: 585,655 prompt and 207,429 output.
- 201 relationships were produced; 185 were marked central and 184 entered the
  isolated main-graph projection.
- 590/590 anchors were preserved.
- All 50 papers had at least one main relationship.
- The active graph was not changed.

## Manual result

| Source | Good | Partial | Poor |
|---|---:|---:|---:|
| Full text, n=29 | 20 | 9 | 0 |
| Abstract only, n=21 | 13 | 8 | 0 |
| Overall | 33 | 17 | 0 |

Separate judgments were:

- relationship capture: 38 good / 12 partial;
- paper-level importance: 44 good / 6 partial;
- relationship wording and graph representation: 40 good / 10 partial.

The result is weaker than the 40 good / 10 partial development result. The
development result therefore overstated how well the prompt generalized.

## What generalized

- The bibliometric ketamine/enantiomer paper correctly represented publication
  growth and research clusters as literature patterns.
- Complex combinations were structurally preserved, including psilocybin plus
  mindfulness and the four-component DXM regimen.
- Broad safety, mechanism, population, and evidence-strength qualifications
  were usually retained.
- No paper became empty and no relationship anchors were discarded.

## What did not generalize

1. Broad reviews still sometimes lose one or more explicit scope dimensions,
   especially pharmacokinetics, historical scope, long-term outcomes, or
   evidence limitations.
2. Methodological and hypothesis papers can still be written as if their
   proposed mechanism or treatment has already been established.
3. Bibliometric wording improved but did not become reliable: one MDMA
   literature analysis still promoted clinical efficacy as a main scientific
   relationship.
4. Weak evidence can lose its qualification. This affected herbal withdrawal
   evidence, the untested four-drug regimen, a proposed ketamine-psychotherapy
   strategy, and ketamine in palliative care.
5. Eighteen papers produced at least one internal consistency warning between
   the paper-frame aspects and the final relationship importance. The content
   was often usable, but the cross-referenced aspect IDs are not reliably
   followed by the model.

## Decision

The paper-first architecture remains substantially better than the old routed
graph path, but this final prompt should not yet replace the current review
pipeline without another design change. Adding more instructions to the same
prompt is unlikely to solve the remaining failures. The next revision should
simplify the contract again by removing the cross-referenced aspect IDs and
making the model produce the final main relationships directly, with an
explicit `evidence_status` field that distinguishes established synthesis,
preliminary evidence, hypothesis, and research gap.
