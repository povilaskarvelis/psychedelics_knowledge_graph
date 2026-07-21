Classify a scientific paper record by scope, evidence domain, and paper type.

Base the classification on the supplied title and abstract. Use publication
labels, MeSH terms, and keywords only as supporting context; these metadata can
be incomplete or misleading and should not override clear title or abstract
evidence.

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

Special domain rules:
- A record is in scope only when the psychedelic-related substance,
  intervention, exposure, or evidence topic is a central study object or major
  synthesis topic.
- Exclude records where the psychedelic-related topic is only a background
  example, comparison point, assay reagent, radioligand, challenge probe for
  another drug's development, or one item in a broad list.
- For broad clinical, therapeutic, biological, psychiatric, or conceptual
  reviews, include only when psychedelic-related evidence is a central topic of
  the title/abstract. Exclude when a psychedelic-related intervention or state
  is only one example among many treatments, mechanisms, or analogies.
- Exclude papers about non-psychedelic drugs, targets, therapies, cognitive
  systems, music, meditation, language, or consciousness when psychedelic
  evidence is used only as an analogy, motivation, or illustrative example.
- Generic serotonin, monoamine, receptor, neurobiology, psychiatry, biomarker,
  or therapy papers are out of scope unless they are directly centered on
  psychedelic-related evidence.
- Ketamine, esketamine, or arketamine records are out of scope when the focus is
  perioperative/procedural anesthesia, postoperative pain, general sedation,
  analgesia, or veterinary anesthesia rather than psychiatric, addiction,
  psychological-therapy, or psychedelic-related evidence.
- For primary animal, cell, tissue, in vitro, or ex vivo studies, do not assign
  clinical_outcome. Use cognitive_behavioral, brain_system,
  molecular_pathway_readout, safety_tolerability, or pharmacokinetics_exposure
  if those endpoints are actually measured.
- For reviews, assign a domain only if the review substantively synthesizes that
  evidence type, not because a mechanism or outcome is named in passing.
- Exclude protocols, trial registrations, corrections, errata, decision
  letters, peer-review reports, Faculty Opinions/recommendations, replies, and
  citation/container records unless the title/abstract contains substantive
  evidence synthesis or original results. Do not assign domain tags to a
  correction or protocol solely from the study described in its title.
- Use exclude_out_of_scope for records about cannabis, opioids, stimulants,
  alcohol, general psychiatry, general anesthesia, or unrelated neuroscience
  unless the title/abstract centrally links them to psychedelic-related evidence
  covered by the domains above.

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
  original results or evidence synthesis.

Set screening_decision after domain and paper-type assignment:
- include_in_scope: use when the title/abstract substantively supports at least
  one evidence domain, or when primary_domain is "general_topic" for a broadly
  relevant psychedelic evidence paper.
- exclude_out_of_scope: use when the title/abstract does not support any
  evidence domain and does not support in-scope "general_topic" relevance. Also
  use this for records that are only container/citation/issue records or contain
  only a passing/background mention of an in-scope topic.
- When relevance is plausible but the title/abstract is thin or ambiguous,
  use include_in_scope. Exclude only when the available evidence clearly
  establishes that the record is out of scope; this preserves recall without
  creating a third decision state that has no distinct downstream workflow.
- For exclude_out_of_scope, return no domain_tags and primary_domain
  "general_topic".
- For non_primary_publication records that are excluded, return no domain_tags
  and primary_domain "general_topic" even if the title mentions an in-scope
  substance or disorder.

Return only compact JSON matching the provided schema.
