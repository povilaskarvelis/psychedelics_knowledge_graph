# Primary extraction refinement protocol

Frozen before new generation on 18 October 2026. Scope: normalization repairs, unchanged-schema instruction refinement, paired current-Luna comparison. No new Gemini calls, production extraction rerun, or graph publication.

## Independent stages

1. Freeze current normalization code before edits. Repair confirmed normalization-owned scientific errors, retain uncertainty and explicit policy exclusions separately, and test before/after on identical saved extractions. Positive controls must demonstrate that conservative fixes do not simply remove legitimate evidence. Record all changed and dropped item identities, source adjudication, code/config hashes and regression checks. Freeze the verified implementation before paid extraction comparison.
2. Refine the instructions using the existing failure inventory. Preserve the ten current domain schemas and domain assignments. Freeze prompt and schema hashes before output inspection. The candidate uses only current fields. No post-validation edits to the tested candidate.
3. Run BOTH current-production instructions and refined instructions anew on identical sources: existing96 (208 tasks), controlled historical40 (40 tasks), previous fresh48 (48 tasks), and a new64-paper sample (one pre-existing assigned domain per paper). The three old sets are now development sets. New samples must be disjoint from all prior extraction-evaluation papers.
4. Fresh64 selection uses source availability, depth, domain and source complexity only, with recorded deterministic selection. Target32 abstracts/32 article packets and32 ordinary/32 challenging papers. Freeze source-only central findings and essential qualifications before any fresh generation. Preserve eligible, ineligible and unresolved tasks; do not replace difficult cases after seeing output.
5. Interleave paired calls with deterministic order. Same Luna model, reasoning effort, content, native schema and output limit in both arms. Budget ceiling $10 for this experiment, within the existing project API budget. Save exact requests, responses, timestamps, usage, transport errors and charged/unknown attempts. No automatic schema-invalid repair masquerading as a first attempt.

## Scientific judgment

Use the supplied source as evidence. Existing references and earlier judgments are revisable evidence, not ground truth. Record any reference correction separately and apply to both arms. Freeze existing common reference groups before new generation; do not count arm-specific findings with different denominators. Fresh source-only references are separate and frozen. Grouped central findings are not an exhaustive atomic-claim gold standard.

Show reviewers paired outputs under deterministic random X/Y labels, with the arm key stored separately. Review all output items, including assertions outside central references. Every item must receive a brief documented source assessment, with exact case and item identifiers; every confirmed error requires its field, explanation, severity, source locator/short quotation, and responsibility. Use the same criteria for baseline and candidate. Reviewers are Codex agents, not independent human experts; labels conceal arm names but reviewers know the experiment's hypothesis and may recognize earlier papers.

Material errors include unsupported or contradicted substance/outcome identity, result binding, number/unit, population/denominator, comparator, time, experimental preparation, design, causal claim or scientific role. Correct prose does not excuse contradictory typed fields, but do not claim the prose asserted an error it explicitly qualifies. Separate schema mismatch, scope mismatch, source damage, ambiguous eligibility, semantic-category ambiguity and minor wording. An unknown field does not count as false merely because full-text information exists outside the supplied abstract. Conditional eligibility judgments stay outside strict material-error counts.

Coverage uses the same scored source-reference groups for both arms: fully covered, partial, missing, unscorable. Necessary qualifications and central null/limiting results matter. Report group-weighted coverage, paper-mean coverage and papers improved/worse/tied. Count affected items and affected papers; one repeated label error across many rows is not many independent experiments. Never call raw-item error fractions model accuracy when granularity changes.

## Graph judgment

Replay BOTH arms through the same frozen repaired normalizer, retain full per-item lineage including audit-only and detail-only fates, and inspect actual canonical subject/object/relation/admission and scientific metadata. Report wrong canonical links/admissions separately from material errors in evidence-record fields. Separate errors caused by extraction from new errors caused by normalization, plus intentionally excluded evidence, vocabulary gaps and potentially over-specific broad categories.

Report valid evidence lost as well as wrong evidence removed; extra nodes are not proof of improvement. Old archive replay establishes normalization effects independently of model generation. Historical Gemini evidence can be cited as context with its existing provenance caveats, but there are no new Gemini calls in this round.

## Decision rule

Do not promote solely because output is longer, schema-valid or development coverage improves. Recommend the candidate for the full extraction rerun only if fresh results support improved central coverage or fewer material errors without a material regression in source correctness or false graph inclusion, and earlier failure families have positive and negative controls. Report tradeoffs and remaining failures explicitly; no claim of zero corpus-wide error or human gold-standard validation. Production rerun remains a subsequent step after the user receives the results.

## Planned reporting calculations

For each cohort and prompt, report fully covered central groups divided by the common scored groups, partial groups separately, and the mean within-paper full-coverage fraction among papers with scored groups. Affected-paper error proportions include all reviewed papers, including empty and ineligible controls. Pair papers to count coverage improvements, regressions and ties, and material-error wins/losses/ties. Do not pool the fresh sample with development results as if all were independent validation. Fresh depth and ordinary/challenge strata are separate descriptive breakdowns. Any uncertainty interval or significance test added later is exploratory and cannot turn this deliberately balanced sample into a corpus error-rate estimate.
