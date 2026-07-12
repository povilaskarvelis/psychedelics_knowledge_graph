# Abstract-Only Review Relationship Extraction

## Task

Read the supplied title and abstract and extract a concise set of
source-supported relationships for a knowledge graph of psychedelic research.

First determine the review's overall purpose and main contribution. Then
extract the relationships that communicate:

1. what this review is mainly about;
2. the principal conclusions or contribution stated in the abstract;
3. the important qualifications needed to interpret those conclusions.

Prioritize relationships that define this review. Retain other substantially
discussed relationships as paper detail. Keep background facts and illustrative
examples from replacing the review's main contribution.

Treat the supplied review as relevant to psychedelic research. It may concern
classic psychedelics, related psychoactive compounds such as MDMA or ketamine,
psychedelic-assisted interventions, their effects and mechanisms, or the
methods and development of the research field.

A relationship is a complete proposition about how two or more entities are
connected. Relevant entities may include compounds, compound classes,
interventions, biological targets, molecular processes, brain systems,
experiences, behaviors, clinical outcomes, conditions, adverse effects,
populations, treatment contexts, methods, or patterns in the research
literature.

Extract relationships connecting a psychedelic compound, compound class, or
intervention with another entity when that reflects the abstract. For a
bibliometric, methodological, policy, or research-agenda review, extract
relationships about the psychedelic research field, a method, a framework, or
a research need when those relationships express the main contribution.

## Input and evidence boundary

You receive paper metadata, the title, and the abstract. Treat the source as
`abstract_only` and base every relationship on information visible in this
input.

Use the title and the abstract's stated objective, methods, results, and
conclusion to determine what is central. Use metadata only as supporting
context.

Do not reconstruct results that may exist in the full article but are absent
from the abstract. When the abstract identifies an important relationship but
does not report its direction or conclusion, preserve the visible scope
conservatively or mark the relationship as requiring full text.

## Describe the review before extracting relationships

Populate `paper_frame` with:

- `review_contribution_type`: the kind of contribution described in the
  abstract;
- `objective_and_scope`: what the review set out to examine, synthesize,
  explain, map, or propose;
- `review_design`: the review method or approach stated in the abstract;
- `primary_subjects`: the compounds, classes, interventions, populations,
  frameworks, or research topics that define the review's purpose;
- `supporting_examples_or_background`: named items used mainly to motivate,
  explain, compare, or illustrate the main subject;
- `populations_or_systems`: the human populations, experimental systems, or
  research settings to which the abstract-visible conclusions apply;
- `major_aspects`: the distinct parts of the objective and principal
  conclusions that must be represented.

Give every major aspect a unique `aspect_id` and one importance value:

- `paper_defining`: directly expresses the objective, organizing purpose,
  principal conclusion, or main contribution;
- `major_supporting`: necessary to understand, complete, or materially qualify
  a paper-defining aspect.

Judge importance relative to this review. A relationship can be scientifically
interesting or visible in the abstract without defining the review.

Evidence used mainly as background, motivation, comparison, or illustration is
not a major aspect unless the objective or conclusion makes it part of the main
contribution.

## Domain-specific considerations

The abstract may cover one or several of the areas below. Apply the relevant
instructions based on its stated objective and content. Do not require areas
that are not part of its purpose.

- **Clinical outcomes:** Preserve the compound or intervention, condition,
  population, comparator, outcome, and strength of evidence when the abstract
  states them and they change the conclusion. Keep an explicitly mixed or
  insufficient conclusion rather than replacing it with a positive result.

- **Safety and tolerability:** Preserve important adverse effects, serious
  risks, contraindications, interactions, vulnerable populations, dose or
  setting dependencies, and uncertainty when the abstract states them as
  distinct conclusions.

- **Pharmacokinetics and exposure:** Preserve dose, route, timing, absorption,
  distribution, metabolism, active metabolites, elimination,
  exposure-response relationships, and drug interactions when they are
  important to the abstract-visible contribution.

- **Molecular targets and receptor pharmacology:** Identify the compound,
  target, type of action, relevant biological system, and functional
  consequence when stated. Distinguish direct target evidence from inferred or
  proposed mechanisms.

- **Molecular and cellular pathways:** Preserve the biological system,
  pathway, cellular process, downstream readout, and evidence system when the
  abstract makes these distinctions material to the conclusion.

- **Brain systems and neurophysiology:** Preserve the relevant region, circuit,
  network, or physiological measure; the measurement method; the direction of
  change; and whether the result is acute or persistent when stated and
  important.

- **Cognitive, behavioral, and subjective effects:** Preserve the construct,
  behavior, or experience; how it was assessed; its context; and whether it is
  an acute effect, longer-term change, predictor, mediator, or correlate when
  the abstract distinguishes these roles. Treat transient psychotomimetic effects
  as cognitive or behavioral effects. Treat induced, exacerbated, or persistent
  psychosis as a safety relationship.

- **Treatment and delivery context:** Preserve psychotherapy, preparation,
  integration, setting, therapeutic support, co-interventions, and treatment
  timing when the abstract treats them as part of the intervention or as
  modifiers of its effects.

- **Real-world and public-health research:** Distinguish patterns of use,
  prevalence, motivations, reported benefits, harms, populations, settings,
  access, regulation, and policy relationships when they form separate parts
  of the abstract-visible synthesis.

- **Research methods and research landscape:** Represent study-design
  problems, measurement issues, publication or funding patterns, topic
  clusters, proposed frameworks, evidence gaps, and research priorities as
  relationships about the research field. A research theme does not by itself
  establish that the scientific relationship named by the theme is true.

## Extract the relationships

Extract at least one relationship representing every major aspect.

When the abstract reports a conclusion, state that conclusion using the
appropriate relationship kind. When it identifies a central topic but does not
report an answer, use `reviewed_relationship` and describe only the visible
scope.

Assign `paper_prominence` as follows:

- `paper_defining`: represents the objective or a principal conclusion;
- `major_supporting`: completes or materially qualifies a defining
  relationship;
- `secondary_context`: represents other substantive abstract-visible content;
- `peripheral`: represents an incidental detail worth retaining only as minor
  paper detail.

Use the following `relationship_kind` values:

- `review_synthesis`: the abstract reports a synthesis-level conclusion;
- `reviewed_relationship`: the abstract identifies a substantially covered
  relationship without reporting a clear synthesis answer;
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
- the abstract's conclusion.

Depending on the abstract, meaningful differences may involve compounds,
populations, experimental systems, doses, routes, treatment components,
biological targets, outcomes, time periods, research methods, or conflicting
bodies of evidence. These are examples, not a checklist that the abstract must
contain.

Combine information only when the abstract treats it as one relationship and
the combined statement preserves its meaning. When several participants form
one intervention or jointly determine an effect, represent the complete
package or interaction rather than breaking it into misleading independent
relationships.

When the abstract describes a small number of named compounds or treatments
and reports meaningfully different conclusions for them, retain the named
relationships. A broad class summary may organize them, but do not use it to
replace those differences.

## Relationship wording and graph use

Write every `relationship_statement` as a complete, source-supported
proposition rather than a topic label.

Match the wording to the strength of the abstract. Preserve language indicating
association, possibility, preliminary evidence, mixed findings, inconsistency,
uncertainty, a hypothesis, or a proposal. Do not turn an association,
hypothesis, research theme, or proposed framework into an established effect.

For each relationship:

- list every entity needed to understand the proposition in `anchors`;
- set `source_item_ids` to a list containing the relationship's own `item_id`;
- record why it is important in `centrality_basis`;
- use the title or abstract as the `evidence_locators`;
- record abstract-visible qualifications in `limitations`;
- distinguish the visible evidence system in `evidence_stratum`;
- assign `domain_labels` only after determining the relationship;
- choose the `graph_form` that preserves the proposition.

Set `graph_eligibility` to `main_graph` for `paper_defining` and
`major_supporting` relationships that can be stated faithfully from the title
and abstract. Set it to `paper_detail_only` for `secondary_context` and
`peripheral` relationships.

Use `needs_full_text` only when the title and abstract do not support a complete
proposition without guessing. When the abstract clearly states that the review
covers a relationship but gives no direction or effect, use
`reviewed_relationship`, `direction_or_tone: descriptive_only`, and
`main_graph` if that scope defines or materially supports the review.

Use `combination` when several participants form one intervention package and
`interaction` when one participant changes another's effect. Use `class`,
`context`, or `paper_topic` when a simple two-entity relationship would lose
important meaning.

Set `full_text_priority` to:

- `high` when a major aspect cannot be represented faithfully from the
  abstract;
- `medium` when full text would materially improve an otherwise coherent
  bundle;
- `low` when the title and abstract support a coherent conservative
  representation.

Write `bundle_summary` using only the defining relationships present in the
output and keep it within the strength and scope of the abstract.

## Final check

Before returning the output, verify that:

1. every major aspect is covered by a relationship with matching importance;
2. every paper-defining or major-supporting relationship covers at least one
   major aspect;
3. the defining relationships collectively represent the stated objective and
   principal abstract-visible conclusions;
4. necessary qualifications and mixed or insufficient conclusions have not
   been dropped;
5. background examples have not displaced the main contribution;
6. every statement is supported by the supplied title and abstract;
7. no relationship depends on information assumed to be present only in the
   full article.

## Output

Return exactly one JSON object matching the supplied schema. Return JSON only.
