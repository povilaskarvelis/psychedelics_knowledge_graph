Focus on molecular pathway or readout evidence: cellular or molecular pathways,
signaling cascades, plasticity markers, gene/protein expression, inflammation,
neurochemistry, hormones, and molecular readouts, including biomarkers when the
paper frames them that way.

Prioritize:

- pathway/process or molecular readout
- clean molecular effect category for the graph
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

Use `molecular_effect_category` for the graph-facing category and
`specific_readout_or_marker` for the exact measured marker, molecule, assay
readout, gene, protein, phosphorylation ratio, neurotransmitter, cytokine, or
metabolite. This separation keeps the graph readable while preserving the
specific finding.

Examples:

- Use `molecular_effect_category`: Neuroplasticity; use
  `specific_readout_or_marker`: BDNF, TrkB, dendritic spine density, or PSD-95.
- Use `molecular_effect_category`: Intracellular signaling; use
  `specific_readout_or_marker`: phospho-mTOR/mTOR, ERK phosphorylation, or Akt.
- Use `molecular_effect_category`: Inflammation; use
  `specific_readout_or_marker`: IL-6, TNF-alpha, microglial activation, or Iba1.
- Use `molecular_effect_category`: Immediate early gene activation; use
  `specific_readout_or_marker`: c-Fos, Egr-1, Egr-2, Arc.

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
