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
| `biomarker_readout` | current | Biomarker, molecular readout, biochemical readout, or ligand/readout measure. |
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

These node kinds are useful for the new routed extraction layer but are not yet
fully wired into the current KG projector:

| Kind | Status | Domain |
| --- | --- | --- |
| `brain_region` | planned | Brain system |
| `brain_network` | planned | Brain system |
| `neural_circuit` | planned | Brain system |
| `cognitive_behavioral_construct` | planned | Cognitive/behavioral |
| `subjective_experience_construct` | planned | Subjective experience |
| `pharmacokinetic_parameter` | planned | Pharmacokinetics/exposure |
| `intervention_component` | planned | Intervention context |
| `public_health_measure` | planned | Real-world/public health |

## Domain Mapping

| Extraction domain | Current/proposed graph node kinds |
| --- | --- |
| `clinical_outcome` | `condition_indication`, `symptom_problem`, `outcome_scale` |
| `safety_tolerability` | `safety_adverse_event` |
| `molecular_target` | `target` |
| `molecular_pathway_readout` | `pathway_process`, `biomarker_readout` |
| `brain_system` | current fallback `system_family` and `biomarker_readout`; planned `brain_region`, `brain_network`, `neural_circuit` |
| `cognitive_behavioral` | planned `cognitive_behavioral_construct` |
| `subjective_experience` | planned `subjective_experience_construct` |
| `pharmacokinetics_exposure` | planned `pharmacokinetic_parameter` |
| `intervention_context` | planned `intervention_component` |
| `real_world_public_health` | planned `public_health_measure` |

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
| `clinical_outcome` | Conditions, symptoms/problems, endpoints, outcome instruments. | Keep `condition_indication`, `symptom_problem`, `outcome_scale`. |
| `safety_tolerability` | Adverse events, tolerability issues, risk windows, severity, monitoring, mitigation. | Keep `safety_adverse_event`; keep severity/rate/context as edge attributes. |
| `molecular_target` | Receptors, transporters, enzymes, channels, genes, proteins, binding/action/selectivity. | Keep `target`. |
| `molecular_pathway_readout` | Signaling pathways, biological processes, biomarkers, tissues, cell/model systems. | Keep `pathway_process` and `biomarker_readout`. |
| `brain_system` | Regions, networks, circuits, connectivity, activation, oscillations, imaging/PET/EEG measures. | Use separate `brain_region`, `brain_network`, and `neural_circuit` anchors; reuse `biomarker_readout` for neural measures when they need graph queries. |
| `cognitive_behavioral` | Cognitive constructs, behavioral constructs, tasks, task domains, animal or human behavioral models. | Keep `cognitive_behavioral_construct`. |
| `subjective_experience` | Mystical-type experience, ego dissolution, insight, challenging experience, valence, scale dimensions. | Keep `subjective_experience_construct`; instruments/subscales are usually attributes unless we want them as `outcome_scale` nodes. |
| `pharmacokinetics_exposure` | PK parameters, analytes, metabolites, route/formulation, matrix, enzymes/transporters, metabolic pathways, exposure-response. | Use `pharmacokinetic_parameter` for true PK/exposure parameters, and mark metabolites/analytes, enzymes/transporters, and metabolic pathways with `compound`, `target`, or `pathway_process` anchor kinds when those are the real target-side anchors. |
| `intervention_context` | Preparation, dosing-session support, integration, psychotherapy model, setting, provider role, fidelity, delivery format, implementation, access/cultural context. | Keep `intervention_component`; use component category and implementation details as edge attributes. |
| `real_world_public_health` | Use patterns, abuse potential, harm reduction, access/equity, policy, service delivery, epidemiology, population risks/benefits. | Keep `public_health_measure`, interpreted broadly enough to include stable public-health topics and measures. |

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
