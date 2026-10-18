Classify a scientific paper record by scope, evidence domain, and paper type.

Base the classification on the supplied title and abstract. Use publication
labels, MeSH terms, and keywords only as supporting context; these metadata can
be incomplete or misleading and should not override clear title or abstract
evidence.

Screening scope and eligibility

Decide eligibility before assigning domains or publication type. Apply the
following scope rules to what the record actually studies or synthesizes.
Domain matches do not establish eligibility.

1. Substance scope
"Psychedelic-related" includes classic psychedelics, MDMA and related
entactogens, ketamine/esketamine/arketamine and their analogues,
ibogaine/noribogaine, salvinorin A, and related psychedelic compounds.
This includes established psychedelic tryptamines and psychedelic
phenethylamines/amphetamines such as MMDA, and MDMA-related entactogens such
as MDA and MDEA. These are examples, not an exhaustive compound list. A less
familiar eligible compound is not out of scope merely because it is not named
here. Structural similarity alone does not qualify an otherwise unrelated
stimulant, anticholinergic, or nonpsychedelic compound.
Original preclinical pharmacology, toxicology, and nonmedical-use research
can qualify. A stimulant, dissociative, or nonclassic classification does not
itself exclude these substances; other stimulants and psychoactive drugs are
not automatically in scope.

2. Require a substantive connection to an in-scope substance
For original research, include a substantive result specifically attributable
to an in-scope drug or class: an intervention effect, exposure estimate,
subgroup or co-use association, use-pattern finding, or null result. Mixed-drug
research qualifies when it reports such a drug-specific finding. A drug need
not be the sole intervention or exposure. An original result specifically
reported for a "hallucinogen" or "psychedelic" category counts as a class-specific
finding even if its individual compounds are not listed. A class-specific
association, predictor, correlate, use pattern, or null finding can qualify
when the main study concerns another drug, condition, or social factor;
being a secondary finding does not make it a background mention.

A name in a background, recruitment, treatment, substrate, or assay list does
not establish this connection. Neither does a proposed future application,
possible treatment implication, or inference that a measured receptor, gene,
enzyme, or mechanism might matter for a psychedelic. Establish an actual
drug-specific experiment, exposure result, or substantial synthesis/analysis.
Generic receptor biology, unrelated drug development, and music, meditation,
or consciousness described as psychedelic-like are excluded on their own.

3. Distinguish a drug experiment from a reagent or comparator
An experiment that directly investigates an in-scope drug's own effects,
mechanisms, pharmacokinetics, toxicity, or modification of those effects can
qualify, including healthy volunteers, animal disease models, cells, and
studies of rescue or prevention of drug toxicity. It need not demonstrate a
psychiatric therapeutic benefit. Healthy-volunteer ketamine pharmacokinetics
is eligible when drug exposure is the study question.

Exclude a drug used merely as an assay reagent/radioligand or as a challenge
probe or comparator to characterize another non-psychedelic treatment, when
its own effects are not a substantive research question. The presence of a
control drug or another tested compound does not by itself make a genuine
ketamine or psychedelic experiment peripheral.

4. Ketamine use exclusions depend on the research purpose
Exclude work focused on ketamine-class drugs for anesthesia, procedural or
general sedation, analgesia/pain treatment, or veterinary anesthesia.
The analgesia exclusion applies to chronic and acute pain, including outside
surgery. Safety monitoring within an otherwise excluded anesthesia or pain
study does not establish eligibility.

Include ketamine-class research with a substantive psychiatric, addiction,
psychological-therapy, or otherwise eligible psychedelic-related question.
Psychiatric efficacy, including depression or postpartum depression, can be
studied around surgery or childbirth: the setting and the simultaneous use
of anesthetics do not override a substantive psychiatric endpoint. Conversely,
a pain endpoint does not become psychiatric evidence merely because mood is
mentioned. Assess the actual question and results; an infusion, PK method,
anesthesiology journal, or surgical setting alone is not grounds for exclusion.
Research centered on ketamine's own nonmedical toxicity is eligible under
the drug-experiment rule.

5. Reviews, conceptual work, and policy analysis
For reviews and evidence synthesis, an in-scope substance or class must be a
central question or major synthesis topic. A broad treatment, suicide,
neurobiology, or public-health review does not qualify solely because it
lists or briefly discusses ketamine, MDMA, or a psychedelic. Positive evidence
of substantial psychedelic-specific coverage is needed in a broad review;
do not assume it from a treatment list. A review centered on an eligible drug
can cover several contexts; apply the ketamine purpose rule to its main focus.

Include substantive scholarly conceptual, policy, legal, or implementation
analysis centrally addressing psychedelic evidence, regulation, access,
liability, professional standards, training, or therapy delivery. Participant
data are not required. The substance connection remains mandatory: a general
drug-policy, policing, or mental-health essay with peripheral psychedelic
examples is excluded. Unsupported brief opinion, news, and teaching summaries
do not qualify. Hypothetical vignettes within a substantive analysis do not
make it ineligible. Preserve the actual publication type rather than inventing
a primary study or a formal guideline process to justify inclusion.

6. Publication exclusions and uncertainty
Exclude protocols/registrations without completed results, corrections,
errata, peer-review/decision artifacts, citation/container records, and news
or educational summaries without their own substantive findings or synthesis.
An otherwise non-primary label does not veto actual completed findings,
qualifying synthesis, or substantive policy/legal analysis.

When a title or thin abstract indicates a plausible eligible drug-specific
question and no clear exclusion applies, include to preserve recall. Distinguish
missing detail from clear evidence of peripheral mention or an excluded use.
This uncertainty rule cannot override a clear exclusion. A relevant empirical
result is not peripheral merely because other drugs are also studied.

7. Final decision check
For inclusion, identify in the supplied record the qualifying drug-specific
result or central synthesis/analysis (or the plausible eligible question for
a thin record). For exclusion, check that a clear scope/format exclusion or
absence of a qualifying connection supports it. Keep screening_reason
consistent with that decision: a rationale acknowledging only a peripheral
drug mention cannot justify inclusion through a general domain match.
For excluded records, return empty domain_tags and methodological_validity_tags,
with primary_domain general_topic.

Evidence domain options:
- clinical_outcome: Human clinical indications, symptoms, diagnoses, patient outcomes, functioning, quality of life, remission, response, relapse, or trial efficacy endpoints. Also use for systematic reviews/meta-analyses that synthesize human clinical outcome studies. Do not use for primary animal, cell, or other preclinical disease-model studies just because a human condition is named or translational relevance is discussed. Do not use for healthy-volunteer pharmacology unless clinical symptoms or patient outcomes are a substantive endpoint.
- safety_tolerability: Adverse events, tolerability, abuse liability, toxicity, medical risk, contraindications, physiological safety, discontinuation, or safety monitoring.
- molecular_target: Receptors, transporters, enzymes, ion channels, binding affinity, target engagement, agonism/antagonism, or molecular pharmacology.
- molecular_pathway_readout: Cellular or molecular pathways and readouts, including plasticity, signaling cascades, gene/protein expression, inflammation, neurochemistry, hormones, or other molecular readouts; biomarkers are a subset when the paper frames them that way.
- brain_system: Brain regions, circuits, networks, connectivity, neuroimaging, EEG/MEG, PET, oscillations, neural dynamics, or regional brain physiology.
- cognitive_behavioral: Cognitive tasks, behavioral measures or phenotypes, learning, memory, attention, emotion processing, social behavior, addiction behavior, or animal/behavioral phenotypes. For human clinical studies, do not use for ordinary symptom scales, abstinence, response, remission, or functioning unless cognition or behavior is explicitly measured as a distinct construct.
- subjective_experience: Acute subjective effects, altered states, mystical-type experience, ego dissolution, perceptual effects, phenomenology, experience questionnaires, or psychological insight during/after the drug experience. Do not use merely because consciousness, anesthesia, intoxication, or drug effects are mentioned unless subjective experience is measured or central.
- pharmacokinetics_exposure: Pharmacokinetics, exposure-response linked to measured exposure, plasma/serum/blood levels, concentration-time data, metabolism, metabolites, bioavailability, clearance, half-life, or PK/PD. Use for analytical exposure measurement only when exposure, metabolism, or dose/exposure interpretation is a main study question. Route EC50, IC50, ED50, receptor occupancy, and ordinary dose-response findings to molecular target or molecular pathway/readout unless measured concentration or exposure is part of the relationship. Do not use merely because a clinical dose, bolus, infusion, route, or toxicology screen is described as part of another study.
- intervention_context: Psychotherapy or treatment model, preparation, integration, set and setting, therapist/facilitator role, dosing-session structure, music, psychological support, manualized therapy such as CBT when it is central to the intervention, or implementation of assisted therapy. Do not use for ordinary trial methodology, blinding, comparator choice, washout, follow-up schedule, or the mere fact that a trial administered a drug.
- real_world_public_health: Epidemiology, prevalence, population-level use patterns, nonmedical/recreational use as the study focus, naturalistic or retreat settings, emergency visits, poison-center data, harm reduction, policy, access, or public-health impact. Do not use merely because participants are described as drug users in a mechanistic or clinical study.

Set domain_tags and primary_domain as follows:
- Choose domain_tags for every evidence domain that is substantively supported.
- A supported domain is a study question, analysis target, measured endpoint,
  original result type, or major synthesis topic.
- Multiple domain_tags are allowed, but prefer a compact set that reflects the
  central evidence rather than every term mentioned in the abstract.
- If no specific evidence domain is supported, use primary_domain
  "general_topic" with empty domain_tags only when the title/abstract is still
  broadly relevant to psychedelic evidence, such as a conceptual overview,
  cross-domain synthesis, or methodological context relevant to the domains
  above.
- "general_topic" is not a catch-all for out-of-scope records.
- An empty domain_tags list is not by itself an exclusion signal.

Optional methodological validity modifiers:
- blinding_expectancy_validity: The paper substantively evaluates blinding, masking, functional unblinding, expectancy effects, or how participant/rater expectations affect interpretation of psychedelic evidence.
- comparator_control_validity: The paper substantively evaluates placebo, active-placebo, treatment-as-usual, open-label, antidepressant, psychotherapy, or other comparator/control choices and how they affect interpretation.
- measurement_psychometric_validity: The paper substantively validates, critiques, or compares scales, questionnaires, outcome measures, factor structure, reliability, validity, or psychometric interpretation.
- evidence_quality_bias: The paper substantively evaluates risk of bias, certainty/quality of evidence, heterogeneity, small-study effects, GRADE-style certainty, or other evidence-quality concerns.

Use methodological_validity_tags only when the paper substantively evaluates
whether evidence in a clinical, subjective-experience, intervention-context, or
public-health domain is interpretable or well measured. Ordinary study design
descriptions, general laboratory assay development, analytical chemistry
methods, drug-checking methods, and computational tools do not need
methodological_validity_tags unless they directly evaluate interpretation of
psychedelic evidence.

For methodological papers about blinding, trial design, measurement bias, or
regulatory validity, keep the main domain tied to the evidence being judged,
usually clinical_outcome, subjective_experience, intervention_context, or
real_world_public_health, and add methodological_validity_tags when appropriate.

Set paper_type_group, paper_type, and paper_type_labels as follows:
- primary: original empirical research, including human trials,
  observational studies, case reports/series, animal studies, cell or tissue
  studies, pharmacokinetic studies, surveys, qualitative studies, and records
  that appear empirical but are too thin to classify more specifically. Do not
  use primary for analyses where the data are publications, citations, search
  records, or research-field metadata rather than participants, patients,
  animals, cells, tissues, assays, samples, or real-world exposure/outcome
  records. Use paper_type "primary" and paper_type_labels ["primary"].
- secondary_literature: papers that synthesize or summarize multiple studies,
  bodies of evidence, clinical guidance, expert consensus, or the research
  literature itself. Bibliometric, scientometric, citation-network, and
  research-trend or knowledge-map papers belong here, usually as paper_type
  "review", unless the input supports a more specific review type. Set
  paper_type to the most specific paper type supported by the input:
  meta_analysis, network_meta_analysis, systematic_review, scoping_review,
  umbrella_review, narrative_review, literature_review, review, guideline, or
  consensus_statement. Set paper_type_labels to every supported secondary label
  from that list. For example, a "systematic review and meta-analysis" should
  use paper_type "meta_analysis" and paper_type_labels including both
  "systematic_review" and "meta_analysis".
- non_primary_publication: records that are not usable as original evidence or
  evidence synthesis, such as protocols, trial registrations, commentaries,
  editorials, letters, replies, conference or meeting abstracts, poster
  abstracts, posters, corrections, retractions, author
  responses, dissertations, theses, book chapters, container/citation records,
  or news summaries. Set paper_type to the most specific paper type supported
  by the input: protocol, trial_registration, commentary_editorial,
  correction_retraction, peer_review_artifact,
  thesis_or_dissertation, book_chapter, news_summary, or other_non_primary. Set
  paper_type_labels to every supported non-primary label from that list.

Paper type rules:
- Prefer explicit title and abstract evidence over weak hints.
- If a protocol paper also reports pilot or completed study results, classify
  it as primary rather than protocol.
- If a review also reports a quantitative pooled analysis, classify it as
  meta_analysis or network_meta_analysis.
- Always include paper_type itself in paper_type_labels.
- Do not add the generic "review" label when a more specific review type is
  supported, unless the input itself only supports a generic review label.
- Generic "review" labels can indicate secondary_literature, but do not treat
  "peer review" or peer-review artifacts as evidence synthesis.
- For non_primary_publication records, normally use screening_decision
  "exclude_out_of_scope" unless the title/abstract contains substantive
  original results, evidence synthesis, or substantive scholarly policy/legal analysis eligible under the scope rules.

Set screening_decision from the eligibility rules above:
- include_in_scope: the record meets an empirical, synthesis, policy/legal,
  implementation, or plausible-relevance inclusion rule and no explicit scope
  or publication exclusion applies.
- exclude_out_of_scope: an explicit exclusion applies or the supplied record
  has no substantive or plausibly eligible psychedelic-related evidence.
- For excluded records return empty domain_tags and primary_domain general_topic.
- For eligible records assign only substantively supported domains; general_topic
  with empty domain_tags remains available for eligible broad conceptual context.
- For animal, cell, tissue, in vitro, and ex vivo findings do not assign
  clinical_outcome. Use the measured preclinical domains instead.
- For reviews assign domains only for evidence types substantively synthesized.

Return only compact JSON matching the provided schema.
