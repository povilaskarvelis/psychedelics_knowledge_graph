Focus on pharmacokinetics and exposure evidence: PK, exposure-response linked
to measured exposure, plasma/serum/blood levels, metabolism, metabolites,
bioavailability, clearance, half-life, Cmax, AUC, Tmax, or PK/PD findings.

Prioritize the PK story: what happens to the compound, what exposure species is
measured, what modifies exposure, where the compound goes, how it is cleared,
and whether exposure is linked to effects. The main graph object should be a
specific PK-relevant object, not merely the metric used to measure it.

For each item, set `pk_relationship_type`, `pk_graph_object_kind`, and
`pk_graph_object_label` around the most informative relationship:

- active exposure species or metabolite: psilocybin -> psilocin, ibogaine ->
  noribogaine, ketamine -> norketamine
- metabolic enzyme, transporter, or pathway: DMT -> MAO-A, MDMA -> CYP2D6,
  ketamine -> N-demethylation
- route, formulation, or bioavailability object when route/formulation changes
  exposure: oral bioavailability, intranasal delivery, dissolution profile
- distribution or tissue compartment when the finding is about where the drug
  goes: brain exposure, CSF exposure, tissue distribution
- elimination object when the finding is about clearance, half-life, urinary
  recovery, or excretion
- modifier or interaction when co-medication, genotype, inhibitor, inducer, or
  condition changes exposure
- exposure-linked effect when concentration, dose, or exposure is linked to a
  subjective, clinical, physiological, receptor-occupancy, or behavioral effect
- detection/monitoring only when the paper is about forensic, hair,
  wastewater, biological monitoring, or analytical exposure detection

Use `pk_or_exposure_parameter` for a true exposure metric or parameter, such as
Cmax, AUC, Tmax, half-life, clearance, bioavailability, concentration, volume
of distribution, metabolic ratio, or Km. Do not make that metric the main `pk_graph_object_label`
when a more meaningful object is available.

EC50, IC50, ED50, receptor occupancy, and ordinary dose-response findings are
pharmacodynamic rather than pharmacokinetic. Route them to molecular target or
molecular pathway/readout unless the paper explicitly relates the effect to a
measured concentration or exposure, in which case capture an
`exposure_linked_to_effect` relationship and keep the pharmacodynamic metric as
edge metadata.

Also capture:

- the compatibility graph anchor kind: PK/exposure parameter,
  compound/analyte/metabolite, metabolic enzyme or transporter, or
  metabolic/transport pathway
- analyte, metabolite, and matrix
- concentration, exposure metric, or model parameter
- dose, route, sampling window, and participant/system context
- comparator or reference condition, such as dose level, route, enantiomer,
  co-administered medication, responder group, baseline, or placebo
- metabolic enzyme, transporter, or delivery pathway when reported; do not
  collapse these into a generic PK-parameter label when they are the actual
  target-side anchor
- exposure-response or drug-interaction interpretation

Capture dose standardization, equivalence, co-exposures, modifiers, and model
method only when they are central to the exposure finding.

Do not extract a result merely because a dose is reported as trial context. The
paper must measure or synthesize exposure, metabolism, or exposure-linked response evidence.

Do not create standalone clinical outcome, safety, subjective-experience,
brain-system, cognitive/behavioral, target, or pathway items here unless the
reported finding is directly about pharmacokinetics, exposure, metabolism,
exposure-response or drug interaction.
