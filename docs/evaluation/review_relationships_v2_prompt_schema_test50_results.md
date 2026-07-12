# Review relationship prompt/schema-only test: 50-paper result

Date: 2026-07-11

## Test constraint

The paper-first architecture was held constant. Full-text reviews used one
discovery call followed by one reconciliation call; abstract-only reviews used
one call. The test added no repair, correction, evaluator, or routing calls.
Only the extraction prompts and their structured output schemas changed.

## What changed

The prior experimental contract represented paper scope through overlapping
question, facet, scope-unit, central-requirement, and item-ID structures. The
new contract uses one `paper_frame`, one list of `major_aspects`, and the
relationships that cover those aspects. It also:

- defines all project-specific terms inside each self-contained prompt;
- explicitly tells the reconciliation call that the discovery JSON is the
  output of the first call;
- requires every major aspect to be represented by a complete relationship;
- distinguishes evidence used to motivate a paper from its main contribution;
- requires all participants in a proposition to appear as anchors;
- preserves evidence strata, combinations, interactions, uncertainty, and
  research-landscape relationships;
- assigns domains after relationships are identified.

## Run result

- 50/50 papers completed successfully.
- 29 full-text and 21 abstract-only reviews.
- 79 model calls and no retries or correction calls.
- 890,380 total tokens: 681,631 prompt and 208,749 output tokens.
- 198 relationships, of which 175 were marked central and 174 entered the
  isolated main-graph projection.
- 628/628 anchors were preserved.
- The active KG was not modified.

Compared with the initial paper-first run, total tokens increased from 856,298
to 890,380 (+4.0%). Total relationships fell from 205 to 198, while central
relationships remained at 175 and main-graph relationships increased from 162
to 174.

## Direct manual assessment

Every revised bundle was compared with the previously read paper-level gold
relationships and, where the comparison was ambiguous, with the supplied
abstract or full-text objective, discussion, and conclusion. No evaluator model
was used.

| Assessment | Initial paper-first | Prompt/schema test |
|---|---:|---:|
| Good overall paper representation | 35 | 40 |
| Partial | 15 | 10 |
| Poor | 0 | 0 |

Separate dimensions for the new run were:

- relationship capture: 45 good / 5 partial;
- paper-level importance: 45 good / 5 partial;
- relationship, anchor, and graph-form fidelity: 42 good / 8 partial.

Seven initially partial papers improved to good: the self-awareness review,
NIH funding review, glutamatergic strategy review, NMDA-model review,
MDMA-assisted EX/RP review, broad TRD-management review, and
ketamine-lamotrigine review.

Two initially good papers regressed to partial:

1. The clinical-pharmacology abstract retained safety, dosing, and interaction
   coverage but marked it as needing full text, preventing main-graph admission.
2. The military/veteran systematic review was compressed into a correct class
   summary but lost important named psychedelic-treatment relationships from
   its small evidence set.

## Remaining prompt/schema problems

The ten partial papers fall into four actionable groups:

1. **Motivating evidence still promoted too highly.** Methodological and
   bibliometric papers sometimes turn background clinical evidence or keyword
   clusters into central substantive relationships.
2. **Broad objectives still lose one dimension.** Pharmacokinetics, biological
   and social disparity pathways, or an agenda component can remain
   underrepresented.
3. **Compression can remove named relationships.** A correct class summary can
   hide important named interventions when the evidence set is small and those
   interventions are explicitly synthesized.
4. **Abstract scope can be graph-excluded unnecessarily.** A clearly stated
   reviewed relationship may be useful main-graph coverage even when the
   abstract does not provide a directional result.

The prompt/schema revision is therefore an improvement, but it should receive
one more prompt-only refinement addressing these four rules and then be tested
on a disjoint review set. Repeating development on the same 50 would overfit the
known examples.
