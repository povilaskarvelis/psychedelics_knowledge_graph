# Extraction-To-KG Mapping

Generated: 2026-06-25

The extraction schemas should be designed from the graph backwards. Each
extracted item should either define a graph anchor or describe a graph edge.

The machine-readable mapping is `schema/extraction_to_kg_mapping.json`.

Seed normalization vocabularies for the new node kinds live in
`schema/kg_node_vocabularies.json`. These are not meant to be exhaustive; they
provide canonical labels and aliases for common anchors while pilot extraction
outputs reveal what needs to be added.

## Current Graph Template

The current normalized KG is built around:

- `entities.parquet`: normalized compounds and entities
- `claims.parquet`: rich evidence records
- `evidence_edges.parquet`: graph-oriented compound-to-entity edges

Current graph node kinds:

| Kind | Status | Use |
| --- | --- | --- |
| `compound` | current | Psychedelic compound, active metabolite, prodrug, or class. |
| `condition_indication` | current | Clinical condition, diagnosis, or indication. |
| `symptom_problem` | current | Symptom, symptom cluster, or broad clinical problem. |
| `safety_adverse_event` | current | Safety event, adverse event, complication, tolerability issue, or risk. |
| `outcome_scale` | current | Clinical outcome instrument, scale, or endpoint measure. |
| `target` | current | Receptor, transporter, enzyme, channel, gene, protein, or target complex. |
| `pathway_process` | current | Pathway, signaling process, cellular process, or biological process. |
| `biomarker_readout` | current | Internal compatibility kind for molecular readouts: measured molecular, biochemical, ligand, or assay readouts; true biomarkers are a subset. |
| `system_family` | current | Broad mechanistic system or family. |

Current primary relation types:

| Node kind | Primary relation |
| --- | --- |
| `condition_indication` | `studied_for_condition` |
| `symptom_problem` | `studied_for_symptom` |
| `safety_adverse_event` | `reports_safety_signal` |
| `outcome_scale` | `reports_outcome_scale` |
| `target` | `has_mechanistic_target` |
| `pathway_process` | `has_mechanistic_pathway` |
| `biomarker_readout` | `has_biomarker_readout` |
| `system_family` | `has_mechanistic_system` |

Secondary literature currently uses `discusses_relationship` for graphable
coverage. Meta-analyses and reviews can later get more specific relation types,
but the first mapping should stay compatible with the current graph.

## Planned Extensions

These routed node kinds are wired into the current KG projector:

| Kind | Status | Domain |
| --- | --- | --- |
| `brain_region` | current | Brain regions & networks |
| `brain_network` | current | Brain regions & networks |
| `neural_circuit` | current | Brain regions & networks |
| `cognitive_behavioral_construct` | current | Cognitive/behavioral |
| `subjective_experience_construct` | current | Subjective experience |
| `pharmacokinetic_parameter` | current | Pharmacokinetics/exposure |
| `intervention_component` | current | Treatment context |
| `public_health_measure` | current | Real-world use |

## Domain Mapping

| Extraction domain | Current/proposed graph node kinds |
| --- | --- |
| `clinical_outcome` | `condition_indication`, `symptom_problem`; `outcome_scale` only for explicit instrument-focused findings |
| `safety_tolerability` | `safety_adverse_event` |
| `molecular_target` | `target` |
| `molecular_pathway_readout` | `pathway_process`, `biomarker_readout` compatibility kind for molecular readouts |
| `brain_system` | current fallback `system_family` and `biomarker_readout` compatibility kind for queryable neural readouts; planned `brain_region`, `brain_network`, `neural_circuit` |
| `cognitive_behavioral` | planned `cognitive_behavioral_construct` |
| `subjective_experience` | planned `subjective_experience_construct` |
| `pharmacokinetics_exposure` | `pharmacokinetic_parameter`, plus `compound`, `target`, or `pathway_process` for metabolites, enzymes/transporters, and metabolic pathways |
| `intervention_context` | `intervention_component` with a recognizable researcher-facing topic such as music, integration, facilitator role, therapeutic alliance, group therapy, or a named recurring psychotherapy model |
| `real_world_public_health` | `public_health_measure` |

General fallback routes are not graph-mappable until manually reassigned to
a stable domain and node kind.

## Review Anchor Check

I sampled 7,774 routed review-coverage records from
`data/processed/corpus/paper_extraction_routes.parquet` and wrote a compact
sample to
`data/processed/corpus/audits/review_coverage_anchor_sample_20260625.tsv`.

The current/planned anchor list looks broadly right. The main issue is not that
we need many more broad node kinds; it is that some schemas still combine
things that should later become separate graph anchors.

| Domain | Review papers tend to focus on | Anchor decision |
| --- | --- | --- |
| `clinical_outcome` | Conditions, symptoms/problems, endpoints, outcome instruments. | Keep conditions and symptoms as graph anchors. Keep outcome instruments as metadata/facets unless the instrument itself is the finding. |
| `safety_tolerability` | Adverse events, tolerability issues, risk windows, severity, monitoring, mitigation. | Retain the specific event beneath a stable safety parent; keep seriousness, severity, rate, discontinuation, and context as distinct attributes or summary outcomes. |
| `molecular_target` | Receptors, transporters, enzymes, channels, genes, proteins, binding/action/selectivity. | Keep `target`. |
| `molecular_pathway_readout` | Signaling pathways, biological processes, molecular readouts, tissues, cell/model systems. | Keep `pathway_process` and the `biomarker_readout` compatibility kind for measured readouts. |
| `brain_system` | Regions, networks, circuits, connectivity, activation, oscillations, imaging/PET/EEG measures. | Use separate `brain_region`, `brain_network`, and `neural_circuit` anchors; reuse the molecular-readout-compatible `biomarker_readout` kind for neural measures when they need graph queries. |
| `cognitive_behavioral` | Cognitive constructs, behavioral constructs, tasks, task domains, animal or human behavioral models. | Keep `cognitive_behavioral_construct`. |
| `subjective_experience` | Mystical-type experience, ego dissolution, insight, challenging experience, valence, scale dimensions. | Keep `subjective_experience_construct`; instruments/subscales are usually attributes unless we want them as `outcome_scale` nodes. |
| `pharmacokinetics_exposure` | PK parameters, analytes, metabolites, route/formulation, matrix, enzymes/transporters, metabolic pathways, exposure-response. | Project the extracted PK relationship itself (`metabolized_to`, `metabolized_by`, `distributed_to`, and so on). Use `pharmacokinetic_parameter` only for true exposure parameters; potency and occupancy without measured exposure belong to molecular evidence. |
| `intervention_context` | Preparation, dosing-session support, integration, psychotherapy model, setting, provider role, fidelity, delivery format, implementation, access/cultural context. | Retain exact paper wording in the finding, but aggregate aliases under recognizable topic nodes. Keep well-represented topics separate and place sparse long-tail details in clearly named `Other ...` buckets. Keep dose, route, participant traits, subjective effects, and outcomes as metadata or in their corresponding domains. |
| `real_world_public_health` | Population use, use patterns, motivations, health outcomes, harms, treatment effectiveness, access/equity, implementation, economics, policy, and supply composition. | Keep `public_health_measure` for graph-facing research topics/outcomes; keep use context and data source as separate facets. |

## Schema Design Rule

For each extraction item:

1. Anchor the edge with a compound/intervention/exposure.
2. Anchor the target side with one graphable entity kind.
3. Put methods, statistics, dose, timing, population, comparator, limitations,
   and interpretation on the edge as attributes.
4. For secondary literature, add `coverage_focus` so the graph can distinguish
   main review topics from brief contextual mentions.

This means schemas should prefer stable graph anchors over exhaustive detail.
If a field cannot become either a node anchor or an edge attribute, it should
usually not be required.

## Forward-Compatible Extraction Fields

Primary extraction schemas keep existing required fields, but newer runs may
also emit optional normalized fields that separate graph-facing labels from raw
paper context:

- Clinical outcomes: use `condition_or_indication` for the condition node and
  `population_or_subgroup` for age, subgroup, eligibility, comorbidity, or
  recruitment context. `condition_or_population` remains valid as the legacy
  combined wording.
- Cognition and behavior: use `graph_construct_label` for the graph node,
  `construct_family` for cognition versus behavior, and `raw_task_or_measure`
  for the task, assay, or instrument. Specific constructs remain visible nodes
  and may retain a broader parent family—for example `Verbal memory` under
  `Memory`, `Drug reinstatement` under `Drug seeking`, and `Reversal learning`
  under `Cognitive flexibility`.
- Molecular pathway/readout evidence: use `specific_readout_or_marker` or the
  specific pathway field for the graph node, and retain
  `molecular_effect_category` as its broad parent facet.
- Brain-system evidence: canonical subregions remain distinct graph entities;
  the node vocabulary records their broader anatomical parent rather than
  treating a subregion name as an alias of that parent.
- Real-world use: graph nodes represent the substantive research topic or
  outcome. Use `real_world_use_context` for coexisting context tags such as
  Microdosing, Recreational/nightlife, Self-treatment, Ceremonial/retreat,
  Polysubstance, or Clinical care, and use `data_source_type` for survey,
  poison-center, wastewater, drug-checking, registry, qualitative/interview,
  or observational-cohort source classes.
- Cross-domain context: optional `population_model_category`,
  `study_design_category`, `administration_route`, `dosing_schedule`,
  `session_context`, and `experimental_system_category` fields support cleaner
  UI facets while preserving exact wording in the legacy fields.
