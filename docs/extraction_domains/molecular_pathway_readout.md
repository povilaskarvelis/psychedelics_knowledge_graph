Focus on molecular pathway or readout evidence: cellular or molecular pathways,
signaling cascades, plasticity markers, gene/protein expression, inflammation,
neurochemistry, hormones, and molecular readouts, including biomarkers when the
paper frames them that way.

Prioritize:

- pathway/process or molecular readout
- clean broad molecular effect category for grouping
- specific marker or readout as measured in the paper
- compound/exposure and model system
- assay or measurement type
- comparator or reference condition, such as baseline, placebo, control group,
  responder versus non-responder, reference tissue, or reference gene set
- direction of change and quantitative value when reported
- species or system, timing, dose/exposure context, and finding interpretation

Capture readout category, tissue/cell details, input data or feature set, and
relationship to response or disease only when they are central to the result.

Do not collapse pathway/readout evidence into direct receptor-target evidence
unless the direct target is measured. Keep broad mechanistic speculation out of
evidence items.

Use pathway/process anchors for signaling, cascades, plasticity, inflammation,
or other biological processes. Use molecular readout anchors for measured
levels, expression, phosphorylation ratios, transporter/receptor density or
availability, immunoreactivity, ligand/neurotransmitter concentrations, and
similar assay outputs. If the evidence is actually binding, affinity, potency,
agonism/antagonism, inhibition, occupancy, target engagement, or selectivity at
a receptor, transporter, enzyme, channel, or stable target complex, keep it as a
direct molecular-target finding instead.

Use `specific_readout_or_marker` or the specific pathway/process as the graph
entity. Use `molecular_effect_category` as its broader parent facet. The broad
category must not replace the exact measured marker, molecule, assay readout,
gene, protein, phosphorylation ratio, neurotransmitter, cytokine, or
metabolite. This keeps the specific scientific claim queryable while retaining
a readable grouping layer.

During KG normalization, each exact molecular finding is also assigned a
derived `molecular_finding_subtopic` beneath its broad parent. These are
researcher-facing families such as BDNF–TrkB signaling, serotonin receptors,
PI3K–Akt–mTOR signaling, microglial activation, dopamine release & turnover,
or oxidative damage & lipid peroxidation. Extraction does not need to emit
this field. It is derived from the exact readout so that spelling variants and
closely related measurements do not become a large miscellaneous chart bucket.
There is only one residual category, `Other findings`; do not create narrower
labels such as “other receptors” or “other cytokines.” A recurring coherent
family should receive a recognizable scientific topic label, while genuinely
miscellaneous measurements remain in the single residual category.

The specific readout can correct an incompatible extracted parent. For
example, serotonin release is assigned to `Neurotransmitter release, uptake &
turnover`, receptor mRNA or density is assigned to `Receptor regulation &
trafficking`, and neuronal currents or firing are assigned to `Neuronal
excitability & synaptic transmission`. Exact readout wording remains unchanged
in finding cards. Large molecular parents are required to keep the residual
unclassified share at no more than 20% during the KG build.

Examples:

- Use `molecular_effect_category`: Neuroplasticity; use
  `specific_readout_or_marker`: BDNF, TrkB, dendritic spine density, or PSD-95.
- Use `molecular_effect_category`: Intracellular signal transduction; use
  `specific_readout_or_marker`: phospho-mTOR/mTOR, ERK phosphorylation, or Akt.
- Use `molecular_effect_category`: Neuroinflammation & immune signaling; use
  `specific_readout_or_marker`: IL-6, TNF-alpha, microglial activation, or Iba1.
- Use `molecular_effect_category`: Gene expression & activity markers; use
  `specific_readout_or_marker`: c-Fos, Egr-1, Egr-2, Arc.
- Use `molecular_effect_category`: Neurotransmitter release, uptake & turnover;
  use `specific_readout_or_marker`: serotonin release, dopamine uptake, or
  5-HIAA levels. Keep serotonin, dopamine, glutamate, and other transmitter
  systems in the specific finding rather than treating them as biological
  process parents.

The parent category must describe what biological process changed. Assay
methods such as electrophysiology, anatomical locations, and adverse outcomes
such as neurotoxicity are separate axes. Preserve the assay and anatomical
location in their own fields. Extract standalone adverse toxicity evidence in
the safety domain; molecular cell-injury mechanisms can remain here under
`Cell injury & survival`.

Use `mechanistic_relationship_type` for the kind of biological claim, such as
expression change, neurotransmitter release, plasticity marker, toxicity marker,
or metabolism/transport. Keep the assay method in `assay_or_method`.

Use `experimental_system_category`, `population_model_category`, and
`study_design_category` when stated. These are coarse filters; keep exact paper
wording in model, species, tissue, and study-design fields.

Do not create standalone behavioral, clinical, safety, subjective-experience, or
brain-system items here. Include those results only when the pathway or
molecular readout is measured in the same finding and remains the item anchor.

Record increases, decreases, pathway activation, and molecular-readout changes as
directions of change, quantitative values, and finding summaries, not as
therapeutic benefit or harm.
