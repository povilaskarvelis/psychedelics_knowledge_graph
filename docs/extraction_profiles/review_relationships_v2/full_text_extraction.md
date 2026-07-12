# Full-Text Review Relationship Extraction

## Task

Read the supplied full-text review and produce the final concise set of
source-supported relationships for a knowledge graph of psychedelic research.

First determine the review's overall purpose and main contribution. Then
extract the relationships that communicate:

1. what this review is mainly about;
2. its principal conclusions or contribution;
3. the important qualifications needed to interpret those conclusions.

Prioritize relationships that define this review. Retain other substantially
discussed relationships as paper detail. Keep background facts and illustrative examples from replacing the review's main contribution.

The review may concern classic psychedelics, related psychoactive compounds such as MDMA or ketamine, psychedelic-assisted interventions, their effects and mechanisms, or the methods and development of the research field.

A relationship is a complete proposition about how two or more entities are
connected. Relevant entities may include compounds, compound classes,
interventions, biological targets, molecular processes, brain systems,
experiences, behaviors, clinical outcomes, conditions, adverse effects,
populations, treatment contexts, methods, or patterns in the research
literature.

Extract relationships connecting a psychedelic compound, compound class, or intervention with another entity when that reflects the review. For a
bibliometric, methodological, policy, or research-agenda review, extract
relationships about the psychedelic research field, a method, a framework, or
a research need when those relationships express the main contribution.

## Input

You receive paper metadata followed by the full available article text. Base
the output only on this material.

Use the title, abstract, stated objective, main synthesis, discussion, and
conclusion to understand the paper. Use section structure, tables, figures, and repeated coverage as additional evidence.

If the supplied text is incomplete, extract only relationships that it
supports and record the limitation in `warnings`.

## Describe the paper before extracting relationships

Populate `paper_frame` with:

- `review_contribution_type`: the kind of contribution the review makes;
- `objective_and_scope`: what the review set out to examine, synthesize,
  explain, map, or propose;
- `review_design`: the review method or approach described by the paper;
- `primary_subjects`: the compounds, classes, interventions, populations,
  frameworks, or research topics that define the paper's purpose;
- `supporting_examples_or_background`: named items used mainly to motivate,
  explain, compare, or illustrate the main subject;
- `populations_or_systems`: the human populations, experimental systems, or research settings to which the review's conclusions apply;
- `major_aspects`: the distinct parts of the objective and principal
  conclusions that must be represented.

Give every major aspect a unique `aspect_id` and one importance value:

- `paper_defining`: directly expresses the paper's objective, organizing
  purpose, principal conclusion, or main contribution;
- `major_supporting`: necessary to understand, complete, or materially qualify
  a paper-defining aspect.

Judge importance relative to this paper. A relationship can be scientifically
interesting or discussed at length without defining the paper.

Evidence used mainly as background, motivation, comparison, or illustration is not a major aspect unless the review itself makes it part of the objective or
principal synthesis.

## Domain-specific considerations

A review may cover one or several of the areas below. Apply the relevant
instructions based on the paper's objective and content. Do not require the
paper to cover areas that are not part of its purpose.

- **Clinical outcomes:** Preserve the compound or intervention, condition,
  population, comparator, outcome, and strength of evidence when these change the review's conclusion. Keep an explicitly mixed or insufficient clinical conclusion rather than replacing it with a positive study example.

- **Safety and tolerability:** Preserve important adverse effects, serious
  risks, contraindications, interactions, vulnerable populations, dose or
  setting dependencies, and uncertainty when the review treats them as
  distinct conclusions.

- **Pharmacokinetics and exposure:** Preserve dose, route, timing, absorption, distribution, metabolism, active metabolites, elimination,
  exposure-response relationships, and drug interactions when they are
  important to the paper.

- **Molecular targets and receptor pharmacology:** Identify the compound,
  target, type of action, relevant biological system, and functional
  consequence. Distinguish direct target evidence from inferred or proposed
  mechanisms.

- **Molecular and cellular pathways:** Preserve the biological system,
  pathway, cellular process, downstream readout, and evidence system when these
  distinctions affect the conclusion.

- **Brain systems and neurophysiology:** Preserve the relevant region, circuit,
  network, or physiological measure; the measurement method; the direction of
  change; and whether the result is acute or persistent when these details are
  material to the synthesis.

- **Cognitive, behavioral, and subjective effects:** Preserve the construct,
  behavior, or experience; how it was assessed; its context; and whether it is
  an acute effect, longer-term change, predictor, mediator, or correlate when
  the review distinguishes these roles.

- **Treatment and delivery context:** Preserve psychotherapy, preparation,
  integration, setting, therapeutic support, co-interventions, and treatment
  timing when the review treats them as part of the intervention or as
  modifiers of its effects.

- **Real-world and public-health research:** Distinguish patterns of use,
  prevalence, motivations, reported benefits, harms, populations, settings,
  access, regulation, and policy relationships when they form separate parts
  of the synthesis.

- **Research methods and research landscape:** Represent study-design
  problems, measurement issues, publication or funding patterns, topic
  clusters, proposed frameworks, evidence gaps, and research priorities as
  relationships about the research field. A research theme does not by itself
  establish that the scientific relationship named by the theme is true.

## Extract the relationships

Extract at least one relationship that states the paper-level answer for every
major aspect.

Also extract relationships discussed substantially outside the major aspects
when they would be useful as paper detail. Assign `paper_prominence` as follows:

- `paper_defining`: represents the objective or a principal conclusion;
- `major_supporting`: completes or materially qualifies a defining
  relationship;
- `secondary_context`: substantially discussed but not necessary to represent
  the paper's main contribution;
- `peripheral`: incidental material worth retaining only as minor paper detail.

Use the following `relationship_kind` values:

- `review_synthesis`: the review reaches a synthesis-level conclusion;
- `reviewed_relationship`: the review substantially covers a relationship but
  does not provide a clear synthesis answer;
- `methodological_contribution`: the paper proposes or evaluates a method,
  model, or framework;
- `research_landscape`: the paper describes publication, funding, policy, or
  other field-level patterns;
- `evidence_gap`: missing or weak evidence is itself an important conclusion.

An explicitly mixed, negative, null, or insufficient conclusion remains a
`review_synthesis`. Use `evidence_gap` when the absence or weakness of evidence
is itself a separate substantive conclusion.

## Decide when to separate or combine information

Write each relationship as one coherent proposition.

Keep information separate whenever combining it would hide a meaningful
difference in:

- the entities involved;
- the type or direction of the relationship;
- certainty or strength of evidence;
- context or scope;
- the paper's conclusion.

Depending on the paper, meaningful differences may involve compounds,
populations, experimental systems, doses, routes, treatment components,
biological targets, outcomes, time periods, research methods, or conflicting
bodies of evidence. These are examples, not a checklist that every review must
contain.

Combine information only when the paper treats it as one relationship and the
combined statement preserves its meaning. When several participants form one
intervention or jointly determine an effect, represent the complete package or
interaction rather than breaking it into misleading independent relationships.

When a review contains a small number of named compounds or treatments and
reports meaningfully different conclusions for them, retain the named
relationships. A broad class summary may organize them, but do not use it to
replace those differences.

## Relationship wording and graph use

Write every `relationship_statement` as a complete, source-supported
proposition rather than a topic label.

Match the wording to the strength of the review. Preserve language indicating
association, possibility, preliminary evidence, mixed findings, inconsistency,
uncertainty, a hypothesis, or a proposal. Do not turn an association,
hypothesis, research theme, or proposed framework into an established effect.

For each relationship:

- list every entity needed to understand the proposition in `anchors`;
- set `source_item_ids` to a list containing the relationship's own `item_id`;
- record why it is important in `centrality_basis`;
- provide concise `evidence_locators` from the supplied paper;
- record qualifications specific to the relationship in `limitations`;
- distinguish the relevant evidence system in `evidence_stratum`;
- assign `domain_labels` only after determining the relationship;
- choose the `graph_form` that preserves the proposition.

Set `graph_eligibility` to:

- `main_graph` for `paper_defining` and `major_supporting` relationships that
  can be stated faithfully;
- `paper_detail_only` for `secondary_context` and `peripheral` relationships;
- `needs_full_text` only when the supplied text cannot support a complete
  proposition;
- `not_graph_coverage` only when the material cannot be represented as a
  meaningful relationship.

Use `combination` when several participants form one intervention package and
`interaction` when one participant changes another's effect. Use `class`,
`context`, or `paper_topic` when a simple two-entity relationship would lose
important meaning.

Write `bundle_summary` using only the defining relationships present in the
output. Set `full_text_priority` to `low` when the supplied full text supports a
coherent final bundle. Use `medium` or `high` only when missing or incomplete
source material prevents faithful representation.

## Final check

Before returning the output, verify that:

1. every major aspect is covered by a relationship with matching importance;
2. every paper-defining or major-supporting relationship covers at least one
   major aspect;
3. the main-graph relationships collectively represent the paper's objective
   and principal conclusions;
4. necessary qualifications and mixed or insufficient conclusions have not
   been dropped;
5. background examples have not displaced the paper's main contribution;
6. every relationship is supported by the supplied text and contains all
   entities needed to understand it;
7. the bundle summary describes relationships actually present in the output.

## Output

Return exactly one JSON object matching the supplied schema. Return JSON only.
