# Brain, Circuit, Network, and Cognitive-Behavioral Search Strategy

This document defines the brain-system, circuit, network, neurophysiology, and
cognitive-behavioral search domain for the psychedelics knowledge graph. It is
part of the same first-build literature strategy as the molecular-target,
molecular-pathway, clinical-evidence, and clinical endpoint searches. DOI
rows pass through the same DOI gate, metadata enrichment, abstract screening, PDF
retrieval, full-text conversion, extraction, normalization, KG table, and
graph-payload pipeline.

## Scoping Check

A small PubMed and OpenAlex scoping pass on 2026-05-26 was used to calibrate
the vocabulary before freezing the strategy. The goal was not to select papers,
but to check which terms retrieve known systems-neuroscience psychedelic
literature.

The scoping queries supported five high-yield discovery families:

- human neuroimaging and connectivity: fMRI, resting-state, functional
  connectivity, default mode network, salience network, frontoparietal network,
  thalamic connectivity, and whole-brain desynchronization
- brain regions and circuits: prefrontal cortex, medial prefrontal cortex,
  anterior/posterior cingulate, hippocampus, amygdala, thalamus, claustrum,
  striatum, nucleus accumbens, dorsal raphe, cortical-subcortical,
  thalamo-cortical, cortico-striatal, and hippocampal-prefrontal circuits
- PET and receptor-occupancy imaging: PET, positron emission tomography,
  receptor occupancy, radioligand, FDG, glucose metabolism, 5-HT2A occupancy,
  and tracer names when known
- EEG, MEG, and neurophysiology: EEG, MEG, electroencephalography,
  magnetoencephalography, neural oscillations, gamma/theta/alpha power,
  signal diversity, entropy, Lempel-Ziv complexity, event-related potentials,
  local field potentials, electrophysiology, calcium imaging, and fiber
  photometry
- cognitive and behavioral task domains: cognitive flexibility, reversal
  learning, extinction learning, fear conditioning, reward learning, social
  cognition, emotional processing, attention, impulsivity, prepulse inhibition,
  and translational behavioral assays

Example scoping hits included human psilocybin fMRI work, ayahuasca default
mode network connectivity work, LSD multimodal neuroimaging work, psilocybin
5-HT2A occupancy work, DMT EEG-fMRI work, and preclinical region/circuit papers
on ketamine and psychedelic-like compounds. These examples are search-quality
anchors, not inclusion decisions.

## Query Design

This domain keeps the same three-concept Boolean structure used by the main
search protocol:

```text
(compound or drug-class terms)
AND (brain/circuit/network/task terms)
AND (evidence-context or modality terms)
```

Terms inside each concept block are joined with OR. PubMed terms are searched
in Title/Abstract fields. OpenAlex uses the works search endpoint, preferably
with title-and-abstract search when running direct pair files. No date or
language restriction is applied during discovery.

The implementation currently routes this domain through the existing dataset
flag, but its entity kinds are kept distinct from molecular targets:

- `brain_region_or_network`: anatomical regions, named circuits, and
  functional networks
- `cognitive_behavioral_task`: task domains and experimental behavioral
  paradigms
- modality terms such as fMRI, PET, EEG, MEG, and calcium imaging are evidence
  context terms, not graph entities by default

## Compound Block

The compound block should reuse the canonical compound registry and include
class-level terms for recall:

- `psychedelic`, `psychedelics`, `classic psychedelic`,
  `serotonergic psychedelic`, `hallucinogen`, `psychoplastogen`
- `psilocybin`, `psilocin`, `LSD`, `lysergic acid diethylamide`, `DMT`,
  `N,N-dimethyltryptamine`, `5-MeO-DMT`, `mescaline`, `ayahuasca`
- `MDMA`, `MDA`, `entactogen`, `empathogen`
- `ketamine`, `esketamine`, `arketamine`, `dissociative`
- `ibogaine`, `noribogaine`, `salvinorin A`, `DOI`, and other configured
  registry compounds

Ambiguous acronyms such as `DMT`, `DOI`, and `MDA` should keep the existing
acronym safeguards during screening and DOI-context auditing.

## Brain Region Terms

Initial high-confidence region vocabulary:

- cortical: `prefrontal cortex`, `medial prefrontal cortex`, `mPFC`,
  `orbitofrontal cortex`, `anterior cingulate cortex`, `posterior cingulate
  cortex`, `cingulate cortex`, `visual cortex`, `somatosensory cortex`,
  `insula`
- limbic and memory: `hippocampus`, `ventral hippocampus`, `dorsal
  hippocampus`, `amygdala`, `basolateral amygdala`, `central amygdala`
- striatal/reward: `striatum`, `ventral striatum`, `dorsal striatum`,
  `nucleus accumbens`, `caudate`, `putamen`
- thalamic and subcortical: `thalamus`, `mediodorsal thalamus`,
  `reticular thalamus`, `claustrum`, `habenula`, `lateral habenula`
- brainstem and neuromodulatory: `dorsal raphe nucleus`, `raphe nucleus`,
  `ventral tegmental area`, `locus coeruleus`, `periaqueductal gray`

These terms should seed both grouped query modules and direct compound-region
pairs. Exact graph normalization can later map aliases such as `mPFC` to a
canonical region label.

## Network and Circuit Terms

Initial high-confidence network/circuit vocabulary:

- functional networks: `default mode network`, `DMN`, `salience network`,
  `frontoparietal network`, `central executive network`, `limbic network`,
  `visual network`, `sensorimotor network`
- connectivity and whole-brain terms: `functional connectivity`, `effective
  connectivity`, `resting-state connectivity`, `dynamic functional
  connectivity`, `global brain connectivity`, `connectome`, `network
  modularity`, `network integrity`, `desynchronization`, `desynchronisation`
- named circuits: `thalamo-cortical`, `thalamocortical`,
  `cortico-striatal`, `corticostriatal`, `cortical-subcortical`,
  `fronto-limbic`, `corticolimbic`, `hippocampal-prefrontal`,
  `amygdala-prefrontal`, `mesolimbic`, `reward circuit`

Search logic should avoid false positives from `network meta-analysis` by
requiring a brain, imaging, connectivity, circuit, or named-network term when
the word `network` is used.

## Modality and Evidence-Context Terms

Use these as the third Boolean block for grouped modules:

- imaging: `fMRI`, `functional MRI`, `BOLD`, `resting-state`, `resting state`,
  `neuroimaging`, `functional connectivity`, `effective connectivity`,
  `dynamic connectivity`, `connectivity`, `connectome`
- PET/metabolism: `PET`, `positron emission tomography`, `receptor occupancy`,
  `occupancy`, `radioligand`, `FDG`, `glucose metabolism`, `cerebral blood
  flow`, `arterial spin labeling`, `CBF`
- EEG/MEG: `EEG`, `MEG`, `electroencephalography`,
  `magnetoencephalography`, `neural oscillations`, `oscillatory`,
  `event-related potential`, `ERP`, `mismatch negativity`, `gamma`, `theta`,
  `alpha`, `signal diversity`, `entropy`, `Lempel-Ziv`
- preclinical physiology: `electrophysiology`, `local field potential`,
  `single-unit`, `multi-unit`, `calcium imaging`, `fiber photometry`,
  `optogenetic`, `chemogenetic`, `c-Fos`, `immediate early gene`,
  `neuronal activation`

## Cognitive and Behavioral Task Terms

Initial high-confidence task-domain vocabulary:

- cognitive control and flexibility: `cognitive flexibility`, `reversal
  learning`, `probabilistic reversal learning`, `set shifting`,
  `attentional set shifting`, `Wisconsin Card Sorting`, `go/no-go`,
  `stop-signal`, `delay discounting`
- fear, threat, and extinction: `fear conditioning`, `fear extinction`,
  `extinction learning`, `threat processing`, `startle`, `prepulse
  inhibition`, `conditioned freezing`
- reward and motivation: `reward learning`, `reinforcement learning`,
  `social reward learning`, `monetary incentive delay`, `sucrose preference`,
  `conditioned place preference`, `self-administration`, `drug seeking`,
  `relapse`
- emotion and social cognition: `emotional processing`, `emotion recognition`,
  `facial emotion recognition`, `social cognition`, `empathy`, `theory of
  mind`, `social behavior`, `social interaction`
- attention and memory: `attention`, `continuous performance task`,
  `working memory`, `novel object recognition`, `spatial memory`
- translational stress/antidepressant-like assays: `forced swim test`,
  `tail suspension test`, `learned helplessness`, `chronic social defeat`,
  `open field`, `elevated plus maze`

Clinical symptom scales and broad treatment outcomes should not enter this
domain solely because they measure functioning. They belong in the clinical
evidence domain unless the paper explicitly uses a cognitive, affective,
behavioral, or neurobiological task paradigm.

## Grouped Search Modules

The grouped modules use the standard broad cap. Dense-topic modules can run
deeper, matching the existing cap pattern.

| Module ID | Type | Entity block | Evidence block |
|---|---|---|---|
| `systems_neuroimaging_connectivity` | primary | named networks, connectivity, connectome, cortical-subcortical circuit terms | fMRI, BOLD, resting-state, functional/effective/dynamic connectivity, neuroimaging |
| `brain_regions_circuits` | primary | region vocabulary plus named circuits | brain region, circuit, activation, c-Fos, neuronal activity, connectivity, projection |
| `pet_receptor_occupancy_metabolism` | primary | 5-HT2A, receptor occupancy, thalamus/cortex where useful | PET, positron emission tomography, radioligand, occupancy, FDG, glucose metabolism, cerebral blood flow |
| `eeg_meg_neurophysiology` | primary | brain, cortex, network, neural dynamics | EEG, MEG, oscillations, signal diversity, entropy, ERP, electrophysiology |
| `cognitive_affective_tasks` | primary | cognitive flexibility, reversal learning, fear/extinction, reward learning, emotional processing, social cognition, attention, impulsivity, prepulse inhibition | task, behavior, behavioural, performance, learning, conditioning, response, paradigm |
| `translational_behavioral_assays` | primary | preclinical behavioral assays, social defeat, forced swim, sucrose preference, conditioned place preference, self-administration | mouse, mice, rat, rodent, animal model, behavioral assay, in vivo |

Dense topic modules:

| Module ID | Type | Query focus |
|---|---|---|
| `psilocybin_default_mode_connectivity` | dense_topic | psilocybin/psilocin AND default mode network/resting-state/functional connectivity/fMRI |
| `lsd_thalamocortical_connectivity` | dense_topic | LSD AND thalamus/thalamocortical/global brain connectivity/fMRI |
| `dmt_eeg_fmri_dynamics` | dense_topic | DMT/5-MeO-DMT AND EEG/fMRI/neural dynamics/signal diversity |
| `ayahuasca_default_mode_connectivity` | dense_topic | ayahuasca/DMT AND default mode network/functional connectivity/neuroimaging |
| `psilocybin_pet_5ht2a_occupancy` | dense_topic | psilocybin/psilocin AND PET/radioligand/5-HT2A receptor occupancy |
| `mdma_social_reward_cognition` | dense_topic | MDMA/MDA AND social reward/social cognition/empathy/emotion recognition |
| `ketamine_prefrontal_hippocampal_circuitry` | dense_topic | ketamine/esketamine/arketamine AND prefrontal/hippocampal/amygdala/striatal circuitry |
| `psychedelic_fear_extinction_flexibility` | dense_topic | classic psychedelics/ketamine/MDMA AND fear extinction/cognitive flexibility/reversal learning |

## Direct Pair Search Layer

After the grouped modules, generate direct pair seeds from the compound
registry crossed with two new systems-level registries:

- `allowed_brain_regions_and_networks`
- `allowed_cognitive_behavioral_tasks`

Direct pair templates should be entity-kind aware:

For brain regions/networks:

```text
{compound} {entity} functional connectivity neuroimaging
{compound} {entity} fMRI BOLD activation
{compound} {entity} PET receptor occupancy
{compound} {entity} EEG MEG neural oscillations
{compound} {entity} neuronal activity c-Fos
{compound} {entity} circuit behavior
```

For cognitive-behavioral tasks:

```text
{compound} {entity} cognitive task
{compound} {entity} behavioral task
{compound} {entity} learning conditioning
{compound} {entity} performance paradigm
{compound} {entity} rodent behavior
```

The pair layer is a recall audit and gap-filling mechanism. Retrieved records
still require abstract screening and extraction before they become graph
evidence.

## Screening Rules To Add Later

The abstract-screening scope for this domain should be updated so a paper is
retained when the title/abstract supports:

- an in-scope compound or explicit in-scope psychedelic/entactogen/dissociative
  class, and
- a brain region, brain network, named circuit, neuroimaging/PET/EEG/MEG/
  neurophysiology modality, or cognitive/behavioral task domain.

Preserve high recall:

- mark as `uncertain` rather than irrelevant when the abstract clearly names a
  compound plus brain/task terms but the relationship is underspecified
- keep animal, ex vivo, electrophysiology, imaging, and healthy-volunteer
  studies; these are core brain-system and cognitive-behavioral evidence
- exclude clinical efficacy papers with no brain, circuit, network,
  neurophysiology, or task outcome signal from this domain, even if
  they remain relevant to the clinical evidence domain
- avoid treating broad parent systems such as `serotonergic system` as direct
  evidence for a brain network unless the paper directly studies that network

## Extraction Rules To Add Later

The extraction prompt and schema should promote direct systems-level evidence
into graph candidates when the paper directly studies a compound relationship
with:

- a brain region or anatomical circuit
- a functional network or connectivity measure
- a cognitive or behavioral task domain

The graph fields should distinguish:

- `raw_entity_label`: the exact reported region, network, circuit, task, or
  modality-linked endpoint
- `entity_role`: `brain_region_or_circuit` or a new
  `cognitive_behavioral_task` role
- `graph_entity_type`: `brain_region_or_network` or
  `cognitive_behavioral_task`
- `graph_include_candidate`: true only for directly studied regions, networks,
  circuits, or task domains, not for broad interpretations inferred by the
  extractor

This keeps molecular targets, brain systems, and cognitive-behavioral tasks as
different evidence scales inside one coherent KG.

## Implementation Notes

The first code pass should:

1. add systems-level module constants to
   `pipeline/ingest/build_boolean_search_modules.py`
2. add systems-level allowlists to `pipeline/config.example.yaml`
3. update direct-pair generation so direct searches can target molecular
   targets, brain/network entities, and cognitive-behavioral tasks without
   collapsing their entity kinds
4. update screening scope text and deterministic entity-term safeguards
5. update extraction schema, prompt, projection, normalization, KG tables, and
   UI only after the discovery vocabulary is accepted

Run labels should describe the stream, for example
`systems_neuroscience_2026_05`, while public methods text should describe it as
the brain/circuit/network and cognitive-behavioral search layer.
