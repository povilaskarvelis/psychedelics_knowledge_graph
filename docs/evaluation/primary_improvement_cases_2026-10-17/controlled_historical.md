# Controlled Gemini and Luna comparison 40 papers

Each paper lists all tested arms, source-grounded material errors, scope issues, and the reviewed graph transformations. Counts are items with at least one material error, not numbers of individual mistakes. Core errors concern the shared domain fields; new-field errors concern the eight candidate fields. Coverage uses common central finding groups and essential qualifications. These are Codex judgments, not human gold-standard labels.

Graph notes include confirmed mistakes, uncertainties, vocabulary gaps and intentional detail-only policy; the note type is shown so these are not mistaken for one error category. Graph counts in the main report deduplicate actual finding IDs. The source packets and raw comparison outputs are linked below.

## H01 The effects of low dose ketamine on sensory gating, neuroendocrine secretion and behavior in healthy human subjects

[Paper DOI](https://doi.org/10.1007/s002130050620) · [Supplied source](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/controlled_historical/papers/H01/source.txt>) · [All extraction outputs](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/comparison_packets/controlled_historical/H01.json>)

Source depth: abstract only. Domains: brain system.

| Arm | Items | Core material errors | New field errors | Scope items | Central coverage |
|---|---:|---:|---:|---:|---|
| Luna current | 2 | 0 | 0 | 0 | 1/1 full; 0 partial; 0 missing |
| Luna revised instructions | 2 | 0 | 0 | 0 | 1/1 full; 0 partial; 0 missing |
| Luna revised instructions + schema | 2 | 0 | 0 | 0 | 1/1 full; 0 partial; 0 missing |
| Gemini controlled saved | 2 | 1 | 0 | 0 | 1/1 full; 0 partial; 0 missing |

**Extraction findings**

- **Gemini controlled saved — core**, item(s) 2: PPI is assigned EEG modality, conflating startle-response assessment with the separate P50 ERP assay.

**Graph findings and limitations**

- **Luna current / Luna revised instructions / Luna revised instructions + schema / Gemini controlled saved — mapping coverage gap:** Source-supported finding lacks graph vocabulary match. Explicit valid result survives raw output only.

**Source or interpretation qualifications**

- RCT design is supported by publication-type metadata and is not counted unsupported.

## H02 Ketamine ameliorates post-traumatic social avoidance by erasing the traumatic memory encoded in VTA-innervated BLA engram cells.

[Paper DOI](https://doi.org/10.1016/j.neuron.2024.06.026) · [Supplied source](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/controlled_historical/papers/H02/source.txt>) · [All extraction outputs](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/comparison_packets/controlled_historical/H02.json>)

Source depth: abstract only. Domains: brain system.

| Arm | Items | Core material errors | New field errors | Scope items | Central coverage |
|---|---:|---:|---:|---:|---|
| Luna current | 2 | 0 | 0 | 0 | 2/2 full; 0 partial; 0 missing |
| Luna revised instructions | 3 | 0 | 0 | 0 | 2/2 full; 0 partial; 0 missing |
| Luna revised instructions + schema | 3 | 0 | 0 | 0 | 2/2 full; 0 partial; 0 missing |
| Gemini controlled saved | 2 | 0 | 0 | 0 | 1/2 full; 1 partial; 0 missing |

**Extraction findings**

No confirmed material source or typed-field error identified in these reviewed outputs; omissions and graph behavior are assessed separately.

**Graph findings and limitations**

- **Luna revised instructions / Luna revised instructions + schema — mapping coverage gap:** Source-supported finding lacks graph vocabulary match. Explicit valid result survives raw output only.

**Source or interpretation qualifications**

- Standalone RNA pathway item under brain-system route is a cross-domain boundary; correct scientific content, not counted false. Structured mixed result_pattern lacks direction evidence; diagnostic ambiguity, not a definite false central result.

## H03 LSD Revisited: A Ten-Year Follow-up of Medical LSD Use

[Paper DOI](https://doi.org/10.1001/archpsyc.1971.01750070037005) · [Supplied source](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/controlled_historical/papers/H03/source.txt>) · [All extraction outputs](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/comparison_packets/controlled_historical/H03.json>)

Source depth: abstract only. Domains: clinical outcome.

| Arm | Items | Core material errors | New field errors | Scope items | Central coverage |
|---|---:|---:|---:|---:|---|
| Luna current | 0 | 0 | 0 | 0 | Not scored |
| Luna revised instructions | 0 | 0 | 0 | 0 | Not scored |
| Luna revised instructions + schema | 0 | 0 | 0 | 0 | Not scored |
| Gemini controlled saved | 2 | 0 | 0 | 2 | Not scored |

**Extraction findings**

- **Gemini controlled saved — scope**, item(s) 1, 2: Personality/use patterns are extracted as clinical outcomes although no treated clinical problem is reported.

**Graph findings and limitations**

No specific graph error or mapping limitation recorded for this paper in the completed lineage review.

## H04 Neuropsychological and mood effects of ketamine in electroconvulsive therapy: a randomised controlled trial.

[Paper DOI](https://doi.org/10.1016/j.jad.2012.04.032) · [Supplied source](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/controlled_historical/papers/H04/source.txt>) · [All extraction outputs](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/comparison_packets/controlled_historical/H04.json>)

Source depth: abstract only. Domains: clinical outcome.

| Arm | Items | Core material errors | New field errors | Scope items | Central coverage |
|---|---:|---:|---:|---:|---|
| Luna current | 1 | 0 | 0 | 0 | 1/2 full; 0 partial; 1 missing |
| Luna revised instructions | 2 | 0 | 0 | 0 | 2/2 full; 0 partial; 0 missing |
| Luna revised instructions + schema | 2 | 0 | 0 | 0 | 1/2 full; 0 partial; 1 missing |
| Gemini controlled saved | 3 | 0 | 0 | 0 | 2/2 full; 0 partial; 0 missing |

**Extraction findings**

No confirmed material source or typed-field error identified in these reviewed outputs; omissions and graph behavior are assessed separately.

**Graph findings and limitations**

- **Luna current / Luna revised instructions — policy exclusion:** Depressed patient/MDE broad-condition exclusion; do not prefer unsupportedMDD specificity merely because graph accepts it.

**Source or interpretation qualifications**

- MDD narrower than depressed-patient source and IV route are specificity concerns, not strict verified errors; metadata includes both MDD and bipolar disorder.
- Structured arm still omits clinical cognitive-protection null. Increase result_pattern on depression improvement is direction-vocabulary ambiguity rather than definite reversed symptom effect.

## H05 Lack of rapid antidepressant effects of Kir4.1 channel inhibitors in a chronic social defeat stress model: Comparison with (R)-ketamine

[Paper DOI](https://doi.org/10.1016/j.pbb.2018.11.010) · [Supplied source](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/controlled_historical/papers/H05/source.txt>) · [All extraction outputs](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/comparison_packets/controlled_historical/H05.json>)

Source depth: abstract only. Domains: cognitive behavioral.

| Arm | Items | Core material errors | New field errors | Scope items | Central coverage |
|---|---:|---:|---:|---:|---|
| Luna current | 3 | 0 | 0 | 0 | 1/1 full; 0 partial; 0 missing |
| Luna revised instructions | 5 | 0 | 0 | 0 | 1/1 full; 0 partial; 0 missing |
| Luna revised instructions + schema | 5 | 0 | 0 | 0 | 1/1 full; 0 partial; 0 missing |
| Gemini controlled saved | 2 | 0 | 0 | 0 | 0/1 full; 1 partial; 0 missing |

**Extraction findings**

No confirmed material source or typed-field error identified in these reviewed outputs; omissions and graph behavior are assessed separately.

**Graph findings and limitations**

No specific graph error or mapping limitation recorded for this paper in the completed lineage review.

**Source or interpretation qualifications**

- Standalone quinacrine/sertraline controls:4 rows per candidate,2 baseline. Comparator-context versus out-of-scope expansion remains ambiguous under current contract; excluded from strict error totals.

## H06 Chronic administration of ketamine induces cognitive deterioration by restraining synaptic signaling

[Paper DOI](https://doi.org/10.1038/s41380-020-0793-6) · [Supplied source](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/controlled_historical/papers/H06/source.txt>) · [All extraction outputs](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/comparison_packets/controlled_historical/H06.json>)

Source depth: abstract only. Domains: cognitive behavioral.

| Arm | Items | Core material errors | New field errors | Scope items | Central coverage |
|---|---:|---:|---:|---:|---|
| Luna current | 1 | 0 | 0 | 0 | 1/2 full; 0 partial; 1 missing |
| Luna revised instructions | 2 | 0 | 0 | 0 | 2/2 full; 0 partial; 0 missing |
| Luna revised instructions + schema | 2 | 0 | 0 | 0 | 2/2 full; 0 partial; 0 missing |
| Gemini controlled saved | 1 | 1 | 0 | 0 | 1/2 full; 1 partial; 0 missing |

**Extraction findings**

- **Gemini controlled saved — core**, item(s) 1: The cognitive item is assigned day28 post-treatment, but that persistence sentence concerns receptor/synaptic proteins and LTP, not cognition.

**Graph findings and limitations**

No specific graph error or mapping limitation recorded for this paper in the completed lineage review.

## H07 MDMA/Ecstasy use among young people in Ohio: perceived risk and barriers to intervention.

[Paper DOI](https://doi.org/10.1080/02791072.2004.10399728) · [Supplied source](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/controlled_historical/papers/H07/source.txt>) · [All extraction outputs](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/comparison_packets/controlled_historical/H07.json>)

Source depth: abstract only. Domains: intervention context.

| Arm | Items | Core material errors | New field errors | Scope items | Central coverage |
|---|---:|---:|---:|---:|---|
| Luna current | 2 | 0 | 0 | 0 | 2/2 full; 0 partial; 0 missing |
| Luna revised instructions | 2 | 0 | 0 | 0 | 2/2 full; 0 partial; 0 missing |
| Luna revised instructions + schema | 2 | 0 | 0 | 0 | 2/2 full; 0 partial; 0 missing |
| Gemini controlled saved | 2 | 1 | 0 | 0 | 2/2 full; 0 partial; 0 missing |

**Extraction findings**

- **Gemini controlled saved — core**, item(s) 1: Naturalistic friendship-group use and a proposed peer intervention are typed as delivered group therapy.

**Graph findings and limitations**

- **Gemini controlled saved — wrong graph record context:** Raw group_therapy falsely types naturalistic friendship-group use; node peer/social-network is otherwise source-related.
- **Luna current / Luna revised instructions / Luna revised instructions + schema / Gemini controlled saved — mapping coverage gap:** Source-supported finding lacks graph vocabulary match. Explicit valid result survives raw output only.

**Source or interpretation qualifications**

- Proposed peer intervention remains explicitly proposed in both summaries; do not count it as measured efficacy.
- Peer-based intervention remains explicitly proposed, not measured efficacy. Proposed-author observation role lacks clean enum.

## H08 Self-experimentations with psychedelics among mental health professionals: LSD in the former Czechoslovakia.

[Paper DOI](https://doi.org/10.1080/02791072.2013.873158) · [Supplied source](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/controlled_historical/papers/H08/source.txt>) · [All extraction outputs](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/comparison_packets/controlled_historical/H08.json>)

Source depth: abstract only. Domains: intervention context.

| Arm | Items | Core material errors | New field errors | Scope items | Central coverage |
|---|---:|---:|---:|---:|---|
| Luna current | 1 | 0 | 0 | 0 | 1/1 full; 0 partial; 0 missing |
| Luna revised instructions | 1 | 0 | 0 | 0 | 1/1 full; 0 partial; 0 missing |
| Luna revised instructions + schema | 1 | 0 | 0 | 0 | 1/1 full; 0 partial; 0 missing |
| Gemini controlled saved | 2 | 0 | 0 | 0 | 1/1 full; 0 partial; 0 missing |

**Extraction findings**

No confirmed material source or typed-field error identified in these reviewed outputs; omissions and graph behavior are assessed separately.

**Graph findings and limitations**

- **Luna current / Luna revised instructions + schema — mapping coverage gap:** Source-supported finding lacks graph vocabulary match. Explicit valid result survives raw output only.

**Source or interpretation qualifications**

- Individual delivery is incompletely evidenced, but not counted as a definite false claim.

## H09 Degeneration of purkinje cells in parasagittal zones of the cerebellar vermis after treatment with ibogaine or harmaline

[Paper DOI](https://doi.org/10.1016/0306-4522(93)90500-f) · [Supplied source](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/controlled_historical/papers/H09/source.txt>) · [All extraction outputs](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/comparison_packets/controlled_historical/H09.json>)

Source depth: abstract only. Domains: molecular pathway readout.

| Arm | Items | Core material errors | New field errors | Scope items | Central coverage |
|---|---:|---:|---:|---:|---|
| Luna current | 2 | 0 | 0 | 0 | 2/2 full; 0 partial; 0 missing |
| Luna revised instructions | 2 | 0 | 0 | 0 | 2/2 full; 0 partial; 0 missing |
| Luna revised instructions + schema | 2 | 0 | 0 | 0 | 2/2 full; 0 partial; 0 missing |
| Gemini controlled saved | 3 | 0 | 0 | 0 | 2/2 full; 0 partial; 0 missing |

**Extraction findings**

No confirmed material source or typed-field error identified in these reviewed outputs; omissions and graph behavior are assessed separately.

**Graph findings and limitations**

No specific graph error or mapping limitation recorded for this paper in the completed lineage review.

**Source or interpretation qualifications**

- Sprague-Dawley rat strain in Gemini is supported by MeSH metadata, not hallucination.

## H10 Biosynthesis of Salvinorin A: Overexpression and Biochemical Characterization of Carboxy Methyltransferase from EST of Salvia divinorum Glands

[Paper DOI](https://doi.org/10.1055/s-2009-1216489) · [Supplied source](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/controlled_historical/papers/H10/source.txt>) · [All extraction outputs](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/comparison_packets/controlled_historical/H10.json>)

Source depth: abstract only. Domains: molecular pathway readout.

| Arm | Items | Core material errors | New field errors | Scope items | Central coverage |
|---|---:|---:|---:|---:|---|
| Luna current | 1 | 0 | 0 | 0 | 2/2 full; 0 partial; 0 missing |
| Luna revised instructions | 2 | 0 | 0 | 0 | 2/2 full; 0 partial; 0 missing |
| Luna revised instructions + schema | 2 | 0 | 1 | 0 | 2/2 full; 0 partial; 0 missing |
| Gemini controlled saved | 1 | 0 | 0 | 0 | 2/2 full; 0 partial; 0 missing |

**Extraction findings**

- **Luna revised instructions + schema — new fields**, item(s) 2: result_pattern=no_detected_difference with methylating substrates as comparator, although test substrates were not methylated and comparator substrates were methylated. Prose retains the correct contrast.

**Graph findings and limitations**

No specific graph error or mapping limitation recorded for this paper in the completed lineage review.

**Source or interpretation qualifications**

- Gemini says radiolabeled substrates in addition to14C-SAM; source only identifies labeled SAM. This assay-detail specificity is uncertain/minor.
- Structured null catalytic row has no_detected_difference against positive substrates; prose is correct. Count typed-field contradiction separately.

## H11 Cellular mechanisms of serotonin 5-HT2A receptor-mediated cGMP formation: the essential role of glutamate

[Paper DOI](https://doi.org/10.1016/j.brainres.2004.01.014) · [Supplied source](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/controlled_historical/papers/H11/source.txt>) · [All extraction outputs](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/comparison_packets/controlled_historical/H11.json>)

Source depth: abstract only. Domains: molecular target.

| Arm | Items | Core material errors | New field errors | Scope items | Central coverage |
|---|---:|---:|---:|---:|---|
| Luna current | 2 | 0 | 0 | 0 | 2/4 full; 1 partial; 1 missing |
| Luna revised instructions | 3 | 0 | 0 | 0 | 3/4 full; 0 partial; 1 missing |
| Luna revised instructions + schema | 3 | 0 | 0 | 0 | 4/4 full; 0 partial; 0 missing |
| Gemini controlled saved | 2 | 0 | 0 | 0 | 1/4 full; 2 partial; 1 missing |

**Extraction findings**

No confirmed material source or typed-field error identified in these reviewed outputs; omissions and graph behavior are assessed separately.

**Graph findings and limitations**

- **Luna current — wrong graph object:** Co-application increases cGMP; normalizer invents NMDA receptor levels and changes relation to biomarker readout. No receptor abundance measured.
- **Luna revised instructions + schema — wrong primary evidence inclusion:** 5HT2C background agonist identity promoted into original measured mechanistic-target relations; source experiment addresses5HT2A/cGMP/NMDA dependence.

**Source or interpretation qualifications**

- Structured target labels include5HT2C from background agonist identity; direct2C evidence absent. Flag target specificity for graph review, not certain new scientific claim in prose.

## H12 Suppressive effect of mitragynine on the 5-methoxy-N,N-dimethyltryptamine-induced head-twitch response in mice.

[Paper DOI](https://doi.org/10.1016/s0091-3057(96)00314-0) · [Supplied source](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/controlled_historical/papers/H12/source.txt>) · [All extraction outputs](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/comparison_packets/controlled_historical/H12.json>)

Source depth: abstract only. Domains: molecular target.

| Arm | Items | Core material errors | New field errors | Scope items | Central coverage |
|---|---:|---:|---:|---:|---|
| Luna current | 0 | 0 | 0 | 0 | Not scored |
| Luna revised instructions | 0 | 0 | 0 | 0 | Not scored |
| Luna revised instructions + schema | 0 | 0 | 0 | 0 | Not scored |
| Gemini controlled saved | 2 | 0 | 0 | 0 | Not scored |

**Extraction findings**

No confirmed material source or typed-field error identified in these reviewed outputs; omissions and graph behavior are assessed separately.

**Graph findings and limitations**

No specific graph error or mapping limitation recorded for this paper in the completed lineage review.

**Source or interpretation qualifications**

- Abstention versus indirect behavioral target dependence is a scope boundary under the direct-target contract; no definite missed-target count.

## H13 The identification of a chlorinated MDMA.

[Paper DOI](https://doi.org/10.1093/jat/29.5.353) · [Supplied source](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/controlled_historical/papers/H13/source.txt>) · [All extraction outputs](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/comparison_packets/controlled_historical/H13.json>)

Source depth: abstract only. Domains: pharmacokinetics exposure.

| Arm | Items | Core material errors | New field errors | Scope items | Central coverage |
|---|---:|---:|---:|---:|---|
| Luna current | 1 | 0 | 0 | 0 | 1/1 full; 0 partial; 0 missing |
| Luna revised instructions | 1 | 0 | 0 | 0 | 1/1 full; 0 partial; 0 missing |
| Luna revised instructions + schema | 1 | 0 | 0 | 0 | 1/1 full; 0 partial; 0 missing |
| Gemini controlled saved | 1 | 1 | 0 | 0 | 0/1 full; 1 partial; 0 missing |

**Extraction findings**

- **Gemini controlled saved — core**, item(s) 1: The unidentified chlorinated MDMA derivative is typed as an MDMA metabolite and assigned MDMA as the parent analyte, without biotransformation evidence.

**Graph findings and limitations**

- **Luna current / Luna revised instructions / Luna revised instructions + schema — wrong graph subject:** Chlorinated MDMA derivative mapped to atomic MDMA overview. Candidate full derivative labels preserved in details but overview still parentMDMA.
- **Gemini controlled saved — wrong graph subject:** Gemini raw labels unidentified chlorinated derivative as MDMA metabolite; MDMA parent identity propagates into graph.

## H14 Deaths associated with MDMA in the period 2000-2019.

[Paper DOI](https://doi.org/10.4045/tidsskr.21.0547) · [Supplied source](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/controlled_historical/papers/H14/source.txt>) · [All extraction outputs](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/comparison_packets/controlled_historical/H14.json>)

Source depth: abstract only. Domains: pharmacokinetics exposure.

| Arm | Items | Core material errors | New field errors | Scope items | Central coverage |
|---|---:|---:|---:|---:|---|
| Luna current | 2 | 0 | 0 | 0 | 2/2 full; 0 partial; 0 missing |
| Luna revised instructions | 2 | 0 | 0 | 0 | 2/2 full; 0 partial; 0 missing |
| Luna revised instructions + schema | 2 | 0 | 0 | 0 | 2/2 full; 0 partial; 0 missing |
| Gemini controlled saved | 2 | 0 | 0 | 0 | 2/2 full; 0 partial; 0 missing |

**Extraction findings**

No confirmed material source or typed-field error identified in these reviewed outputs; omissions and graph behavior are assessed separately.

**Graph findings and limitations**

No specific graph error or mapping limitation recorded for this paper in the completed lineage review.

**Source or interpretation qualifications**

- Gemini142sample is study total, not demonstrably period-specific; ambiguity noted, not counted false.

## H15 Use of hallucinogenic drugs on campus

[Paper DOI](https://doi.org/10.1001/jama.204.12.1021) · [Supplied source](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/controlled_historical/papers/H15/source.txt>) · [All extraction outputs](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/comparison_packets/controlled_historical/H15.json>)

Source depth: abstract only. Domains: real world public health.

| Arm | Items | Core material errors | New field errors | Scope items | Central coverage |
|---|---:|---:|---:|---:|---|
| Luna current | 4 | 0 | 0 | 1 | 2/2 full; 0 partial; 0 missing |
| Luna revised instructions | 5 | 0 | 0 | 1 | 2/2 full; 0 partial; 0 missing |
| Luna revised instructions + schema | 5 | 0 | 0 | 1 | 2/2 full; 0 partial; 0 missing |
| Gemini controlled saved | 3 | 0 | 0 | 0 | 1/2 full; 1 partial; 0 missing |

**Extraction findings**

- **Luna current — scope**, item(s) 2: Standalone marijuana use-pattern result is outside the psychedelic comparison.
- **Luna revised instructions — scope**, item(s) 2: Standalone marijuana campus-use result is outside the psychedelic observation.
- **Luna revised instructions + schema — scope**, item(s) 2: Standalone marijuana campus-use result is outside the psychedelic observation.

**Graph findings and limitations**

- **Luna revised instructions — mapping coverage gap:** Campus is valid measured predictor, but missing compound in exposure anchor loses LSD overview despite correct raw summary. Extraction/graph contract mismatch.

**Source or interpretation qualifications**

- Standalone marijuana campus comparison persists. Instruction exposure_or_policy foregrounds campus rather than drug, which can impede subject normalization despite correct summary.

## H16 Nationwide assessment of illicit drug consumption patterns in South Korea using wastewater-based epidemiology during the COVID-19 pandemic (2020-2022).

[Paper DOI](https://doi.org/10.1016/j.jhazmat.2024.135090) · [Supplied source](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/controlled_historical/papers/H16/source.txt>) · [All extraction outputs](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/comparison_packets/controlled_historical/H16.json>)

Source depth: abstract only. Domains: real world public health.

| Arm | Items | Core material errors | New field errors | Scope items | Central coverage |
|---|---:|---:|---:|---:|---|
| Luna current | 3 | 0 | 0 | 1 | 2/3 full; 1 partial; 0 missing |
| Luna revised instructions | 5 | 0 | 0 | 0 | 3/3 full; 0 partial; 0 missing |
| Luna revised instructions + schema | 5 | 0 | 0 | 0 | 3/3 full; 0 partial; 0 missing |
| Gemini controlled saved | 2 | 2 | 0 | 0 | 1/3 full; 2 partial; 0 missing |

**Extraction findings**

- **Luna current — scope**, item(s) 1: Standalone methamphetamine consumption trend is outside the psychedelic comparison.
- **Gemini controlled saved — core**, item(s) 1: The source gives positive correlations for offenders/clubs but does not give the direction of income correlations; item1 asserts positive income correlation.
- **Gemini controlled saved — core**, item(s) 2: Ketamine association_or_trend is increase although the source reports detection and an income association, not a rising ketamine consumption trend.

**Graph findings and limitations**

No specific graph error or mapping limitation recorded for this paper in the completed lineage review.

## H17 Effects of d-lysergic acid diethylamide and its brom derivative on cardiovascular responses to serotonin and on arterial pressure.

[Paper DOI](https://doi.org/10.1016/s0022-3565(25)11841-7) · [Supplied source](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/controlled_historical/papers/H17/source.txt>) · [All extraction outputs](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/comparison_packets/controlled_historical/H17.json>)

Source depth: abstract only. Domains: safety tolerability.

| Arm | Items | Core material errors | New field errors | Scope items | Central coverage |
|---|---:|---:|---:|---:|---|
| Luna current | 3 | 1 | 0 | 0 | 3/3 full; 0 partial; 0 missing |
| Luna revised instructions | 5 | 0 | 0 | 0 | 3/3 full; 0 partial; 0 missing |
| Luna revised instructions + schema | 5 | 0 | 0 | 0 | 2/3 full; 0 partial; 1 missing |
| Gemini controlled saved | 3 | 1 | 0 | 0 | 2/3 full; 1 partial; 0 missing |

**Extraction findings**

- **Luna current — core**, item(s) 1: Mixed rat and cat results are typed rat_model; this loses the second species in controlled filtering.
- **Gemini controlled saved — core**, item(s) 1: Quick-injection regimen is taken from the BOL experiment and assigned to the LSD row.

**Graph findings and limitations**

No specific graph error or mapping limitation recorded for this paper in the completed lineage review.

**Source or interpretation qualifications**

- LSD quick injection is a supplied-source attribution error, not a claim about what the inaccessible full experiment actually did.
- Structured omits sympathetic-inactivation modifiers.

## H18 The effects of ecstasy (MDMA) on rat liver bioenergetics.

[Paper DOI](https://doi.org/10.1111/j.1553-2712.2004.tb00735.x) · [Supplied source](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/controlled_historical/papers/H18/source.txt>) · [All extraction outputs](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/comparison_packets/controlled_historical/H18.json>)

Source depth: abstract only. Domains: safety tolerability.

| Arm | Items | Core material errors | New field errors | Scope items | Central coverage |
|---|---:|---:|---:|---:|---|
| Luna current | 2 | 0 | 0 | 0 | 3/3 full; 0 partial; 0 missing |
| Luna revised instructions | 3 | 0 | 0 | 0 | 3/3 full; 0 partial; 0 missing |
| Luna revised instructions + schema | 3 | 0 | 0 | 0 | 3/3 full; 0 partial; 0 missing |
| Gemini controlled saved | 2 | 1 | 0 | 0 | 2/3 full; 1 partial; 0 missing |

**Extraction findings**

- **Gemini controlled saved — core**, item(s) 1: Combined positive isolated-mitochondria and null cell findings are typed no_detected_effect despite a reported 5mM uncoupling effect; 1/24h timing belongs only to cells.

**Graph findings and limitations**

- **Luna current / Luna revised instructions / Luna revised instructions + schema — wrong graph object:** Mitochondrial respiration in rat liver maps to Respiratory safety, falsely suggesting lung/breathing safety.

**Source or interpretation qualifications**

- Assay preparation, time and dose are correctly separated in both candidates.

## H19 Effects of a subanaesthetic concentration of nitrous oxide on memory and subjective experience: Influence of assessment procedures and types of stimuli

[Paper DOI](https://doi.org/10.1002/hup.470030405) · [Supplied source](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/controlled_historical/papers/H19/source.txt>) · [All extraction outputs](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/comparison_packets/controlled_historical/H19.json>)

Source depth: abstract only. Domains: subjective experience.

| Arm | Items | Core material errors | New field errors | Scope items | Central coverage |
|---|---:|---:|---:|---:|---|
| Luna current | 1 | 0 | 0 | 0 | Not scored |
| Luna revised instructions | 2 | 0 | 0 | 0 | Not scored |
| Luna revised instructions + schema | 1 | 0 | 0 | 0 | Not scored |
| Gemini controlled saved | 2 | 0 | 0 | 0 | Not scored |

**Extraction findings**

- **Gemini controlled saved — conditional**, item(s) 2: The unspecified other mood effects are typed Positive affect even though their valence is not stated. This is conditional scientific review; compound eligibility remains unscored.

**Graph findings and limitations**

No specific graph error or mapping limitation recorded for this paper in the completed lineage review.

**Source or interpretation qualifications**

- Eligibility of nitrous oxide is unscored. Positive-affect categorization issue is separately conditional.

## H20 Memory and mood during the night and in the morning after repeated evening doses of MDMA

[Paper DOI](https://doi.org/10.1177/0269881107083990) · [Supplied source](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/controlled_historical/papers/H20/source.txt>) · [All extraction outputs](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/comparison_packets/controlled_historical/H20.json>)

Source depth: abstract only. Domains: subjective experience.

| Arm | Items | Core material errors | New field errors | Scope items | Central coverage |
|---|---:|---:|---:|---:|---|
| Luna current | 1 | 0 | 0 | 0 | 1/1 full; 0 partial; 0 missing |
| Luna revised instructions | 1 | 0 | 0 | 0 | 1/1 full; 0 partial; 0 missing |
| Luna revised instructions + schema | 1 | 0 | 1 | 0 | 1/1 full; 0 partial; 0 missing |
| Gemini controlled saved | 1 | 0 | 0 | 0 | 1/1 full; 0 partial; 0 missing |

**Extraction findings**

- **Luna revised instructions + schema — new fields**, item(s) 1: comparison_basis=between_groups despite an explicitly within-person crossover.

**Graph findings and limitations**

No specific graph error or mapping limitation recorded for this paper in the completed lineage review.

**Source or interpretation qualifications**

- Luna Positive affect anchor captures a true subset but underrepresents anxiety/confusion in graph categorization; full summary retains both, so not a strict incorrect factual item.
- Structured between_groups contradicts explicitly within-person crossover. Assessment_timepoint redundantly lists baseline and four clock times; baseline is6:30pm, not an extra fifth visit. Minor formatting ambiguity. Mixed positive/negative mood remains one Positive affect graph anchor in both arms.

## H21 Vulnerability to psychotogenic effects of ketamine is associated with elevated D2/3-receptor availability

[Paper DOI](https://doi.org/10.1017/s1461145712000764) · [Supplied source](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/controlled_historical/papers/H21/source.txt>) · [All extraction outputs](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/comparison_packets/controlled_historical/H21.json>)

Source depth: article text. Domains: brain system.

| Arm | Items | Core material errors | New field errors | Scope items | Central coverage |
|---|---:|---:|---:|---:|---|
| Luna current | 3 | 0 | 0 | 0 | 3/4 full; 0 partial; 1 missing |
| Luna revised instructions | 5 | 0 | 0 | 0 | 4/4 full; 0 partial; 0 missing |
| Luna revised instructions + schema | 3 | 0 | 0 | 0 | 4/4 full; 0 partial; 0 missing |
| Gemini controlled saved | 4 | 0 | 0 | 0 | 3/4 full; 1 partial; 0 missing |

**Extraction findings**

No confirmed material source or typed-field error identified in these reviewed outputs; omissions and graph behavior are assessed separately.

**Graph findings and limitations**

- **Luna current / Luna revised instructions / Luna revised instructions + schema / Gemini controlled saved — public context loss:** Region/readout anchor varies by phrasing; public brain_region field not exported for biomarker route, and canonical Receptor occupancy does not preserve D2/3 availability distinction. Narrative retains many region details; not total raw loss or a direct false occupancy claim.

**Source or interpretation qualifications**

- within_subject_baseline used for a separate placebo scan; no within_subject_conditions enum exists. Prose identifies correct comparator, so not counted as wrong. Multi-region biomarker anchors require graph-coverage checking.

## H22 A mouse model of <i>GRIN2D</i> developmental and epileptic encephalopathy recapitulates the human disease

[Paper DOI](https://doi.org/10.1093/brain/awaf149) · [Supplied source](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/controlled_historical/papers/H22/source.txt>) · [All extraction outputs](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/comparison_packets/controlled_historical/H22.json>)

Source depth: article text. Domains: brain system.

| Arm | Items | Core material errors | New field errors | Scope items | Central coverage |
|---|---:|---:|---:|---:|---|
| Luna current | 5 | 0 | 0 | 0 | 3/3 full; 0 partial; 0 missing |
| Luna revised instructions | 11 | 0 | 0 | 0 | 3/3 full; 0 partial; 0 missing |
| Luna revised instructions + schema | 12 | 0 | 0 | 0 | 3/3 full; 0 partial; 0 missing |
| Gemini controlled saved | 4 | 0 | 0 | 0 | 3/3 full; 0 partial; 0 missing |

**Extraction findings**

No confirmed material source or typed-field error identified in these reviewed outputs; omissions and graph behavior are assessed separately.

**Graph findings and limitations**

- **Luna revised instructions / Luna revised instructions + schema — wrong graph object:** Electrophysiology/seizure readout receives appended genotype and molecular fallback despite measured ECoG endpoint. Sequential magnesium→ketamine exposure also collapses to atomic Ketamine; narrative preserves sequence.

**Source or interpretation qualifications**

- Standalone genotype phenotypes and nonpsychedelic comparison-drug arms exceed narrow focal extraction, but were generated within the same experiment. Scope expansion recorded separately from scientific falsehood; no strict error count. [[1, 2, 4, 5]]
- Standalone genotype phenotypes and nonpsychedelic comparison-drug arms exceed narrow focal extraction, but were generated within the same experiment. Scope expansion recorded separately from scientific falsehood; no strict error count. [[1, 2, 3, 4, 9, 10, 11]]
- Items1/2 analysis_unit=animals while slice-cell recordings and n are described; no explicit animal denominator assertion, so not counted as strict denominator error.
- Item12 result_pattern=increase summarizes delta power while median frequency decreases; coarse multi-result summary, source prose correctly binds both.
- Standalone genotype phenotypes and nonpsychedelic comparison-drug arms exceed narrow focal extraction, but were generated within the same experiment. Scope expansion recorded separately from scientific falsehood; no strict error count. [[1, 2, 3, 4, 5, 10, 11, 12]]

## H23 Prospective associations of psychedelic treatment for co-occurring alcohol misuse and posttraumatic stress symptoms among United States Special Operations Forces Veterans.

[Paper DOI](https://doi.org/10.1080/08995605.2022.2156200) · [Supplied source](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/controlled_historical/papers/H23/source.txt>) · [All extraction outputs](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/comparison_packets/controlled_historical/H23.json>)

Source depth: article text. Domains: clinical outcome.

| Arm | Items | Core material errors | New field errors | Scope items | Central coverage |
|---|---:|---:|---:|---:|---|
| Luna current | 2 | 0 | 0 | 0 | 2/4 full; 0 partial; 2 missing |
| Luna revised instructions | 5 | 0 | 0 | 0 | 4/4 full; 0 partial; 0 missing |
| Luna revised instructions + schema | 3 | 0 | 0 | 0 | 2/4 full; 1 partial; 1 missing |
| Gemini controlled saved | 3 | 1 | 0 | 0 | 3/4 full; 0 partial; 1 missing |

**Extraction findings**

- **Luna current — minor**, item(s) 1, 2: Dose/regimen says 5-MeO-DMT follows ibogaine the next day. Source describes ibogaine on day1, integration the next day, and5-MeO-DMT on the final day of a3-day program. This compresses the intervening integration day.
- **Luna revised instructions — minor**, item(s) 1, 2, 3, 4, 5: Dose/regimen says 5-MeO-DMT follows ibogaine the next day. Source describes ibogaine on day1, integration the next day, and5-MeO-DMT on the final day of a3-day program. This compresses the intervening integration day.
- **Luna revised instructions + schema — minor**, item(s) 1, 2, 3: Dose/regimen says 5-MeO-DMT follows ibogaine the next day. Source describes ibogaine on day1, integration the next day, and5-MeO-DMT on the final day of a3-day program. This compresses the intervening integration day.
- **Gemini controlled saved — core**, item(s) 1: condition_or_indication=Alcohol use disorder implies diagnosis; eligibility was AUDIT-C screening for risky use, not established AUD diagnosis.

**Graph findings and limitations**

- **Luna current / Luna revised instructions / Luna revised instructions + schema — vocabulary gap:** Alcohol misuse/posttraumatic stress symptoms/cognitive symptoms unmapped; conservative source labels are rejected while Gemini diagnostic overstatement yields main graph. This is a known vocabulary/admission gap, not proof labels should be forced into diagnosed disorders.

**Source or interpretation qualifications**

- Item2 condition_or_indication remains Alcohol misuse while measured endpoint is PTSD symptoms; cohort criterion and outcome role are overloaded. Narrative faithful.
- Source text reverses responder group counts relative to Table3 and gives d=-3.26 where table shows t=-3.26,d=-.98. Do not score faithful source copying as hallucination. Structured notes table counts and separates t/d; instructions warns counts but repeats prose d.
- PTSD sample_size45 differs from Table2 n19, but source denominators are internally inconsistent; retained as uncertainty rather than certain extractor error. PTSD condition label also may overstate diagnosis; not independently counted.

## H24 Comparison of the Antianhedonic Effects of Repeated-dose Intravenous Ketamine in Older and Younger Adults with Major Depressive Episode.

[Paper DOI](https://doi.org/10.2174/1570159x23666240923112548) · [Supplied source](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/controlled_historical/papers/H24/source.txt>) · [All extraction outputs](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/comparison_packets/controlled_historical/H24.json>)

Source depth: article text. Domains: clinical outcome.

| Arm | Items | Core material errors | New field errors | Scope items | Central coverage |
|---|---:|---:|---:|---:|---|
| Luna current | 4 | 0 | 0 | 0 | 2/3 full; 0 partial; 1 missing |
| Luna revised instructions | 4 | 0 | 0 | 0 | 3/3 full; 0 partial; 0 missing |
| Luna revised instructions + schema | 5 | 0 | 0 | 0 | 3/3 full; 0 partial; 0 missing |
| Gemini controlled saved | 3 | 3 | 0 | 0 | 2/3 full; 0 partial; 1 missing |

**Extraction findings**

- **Gemini controlled saved — core**, item(s) 1, 2, 3: condition_or_indication=Major depressive disorder excludes the32bipolar participants pooled in the reported MDE results. Population prose recognizes unipolar/bipolar in item1, but canonical condition remains MDD for all3.

**Graph findings and limitations**

- **Luna current / Luna revised instructions / Luna revised instructions + schema — wrong graph object:** Mixed unipolar/bipolar major depressive episode cohort becomes Bipolar depression only through unambiguous_condition_context. Raw outcome estimates pool diagnoses; source103MDD/32bipolar. Public narrative preserves pooled context, canonical graph label does not.

## H25 Acute neuropsychological effects of MDMA and ethanol (co-)administration in healthy volunteers

[Paper DOI](https://doi.org/10.1007/s00213-007-1056-9) · [Supplied source](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/controlled_historical/papers/H25/source.txt>) · [All extraction outputs](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/comparison_packets/controlled_historical/H25.json>)

Source depth: article text. Domains: cognitive behavioral.

| Arm | Items | Core material errors | New field errors | Scope items | Central coverage |
|---|---:|---:|---:|---:|---|
| Luna current | 6 | 0 | 0 | 0 | 2/3 full; 1 partial; 0 missing |
| Luna revised instructions | 8 | 0 | 0 | 0 | 3/3 full; 0 partial; 0 missing |
| Luna revised instructions + schema | 10 | 0 | 6 | 0 | 3/3 full; 0 partial; 0 missing |
| Gemini controlled saved | 4 | 0 | 0 | 0 | 1/3 full; 2 partial; 0 missing |

**Extraction findings**

- **Luna revised instructions + schema — new fields**, item(s) 1, 2, 3, 4, 5, 6: New comparison_basis=between_groups labels drug-present/absent contrasts from a four-way within-participant crossover as between groups. Narrative correctly says factorial/crossover; typed field contradicts the design.
- **Luna revised instructions + schema — minor**, item(s) 10: behavioral_context says recognition20minutes after delayed recall; source places recognition after the delayed recall trial and20minutes after presentation. assessment_timepoint correctly says20minutes after presentation, leaving an internal timing contradiction.
- **Luna revised instructions + schema — new fields**, item(s) 1, 2, 3, 4, 5, 6: between_groups despite repeated within-participant factorial drug conditions; other would avoid false specificity.

**Graph findings and limitations**

No specific graph error or mapping limitation recorded for this paper in the completed lineage review.

**Source or interpretation qualifications**

- Ethanol-only factorial observations can be valid comparator context. Do not count their extraction as wrong science or automatic scope violation; isolated role presentation remains a concern.
- All4items state approx110min postdose. Specific test timetable is referenced but absent from supplied packet; this precision is not verifiable here, not a proven error in full published paper.

## H26 Both ketamine and NBQX attenuate alcohol drinking in male Wistar rats

[Paper DOI](https://doi.org/10.1016/j.neulet.2017.12.055) · [Supplied source](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/controlled_historical/papers/H26/source.txt>) · [All extraction outputs](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/comparison_packets/controlled_historical/H26.json>)

Source depth: article text. Domains: cognitive behavioral.

| Arm | Items | Core material errors | New field errors | Scope items | Central coverage |
|---|---:|---:|---:|---:|---|
| Luna current | 5 | 0 | 0 | 0 | 2/3 full; 1 partial; 0 missing |
| Luna revised instructions | 7 | 0 | 0 | 0 | 2/3 full; 1 partial; 0 missing |
| Luna revised instructions + schema | 8 | 0 | 0 | 0 | 3/3 full; 0 partial; 0 missing |
| Gemini controlled saved | 4 | 0 | 0 | 0 | 2/3 full; 1 partial; 0 missing |

**Extraction findings**

No confirmed material source or typed-field error identified in these reviewed outputs; omissions and graph behavior are assessed separately.

**Graph findings and limitations**

- **Gemini controlled saved — wrong graph object:** Reward processing/sucrose preference and stress-coping/FST become Alcohol use disorder condition nodes from alcohol-withdrawal context; explicit measured constructs are lost canonically.

**Source or interpretation qualifications**

- NBQX-only effects are comparator/context observations within a ketamine experiment; separate policy question, not counted as wrong science. Alcohol-withdrawal behavioral changes preserve null drug effects.
- Graph construct Drug seeking is broader than directly measured home-cage alcohol consumption; no operant seeking was tested. Treat as vocabulary/interpretation concern rather than definite numeric or exposure error.

## H27 Moderating factors in psilocybin-assisted treatment affecting mood and personality: A naturalistic, open-label investigation.

[Paper DOI](https://doi.org/10.1007/s00213-024-06733-3) · [Supplied source](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/controlled_historical/papers/H27/source.txt>) · [All extraction outputs](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/comparison_packets/controlled_historical/H27.json>)

Source depth: article text. Domains: intervention context.

| Arm | Items | Core material errors | New field errors | Scope items | Central coverage |
|---|---:|---:|---:|---:|---|
| Luna current | 2 | 0 | 0 | 0 | 2/4 full; 0 partial; 2 missing |
| Luna revised instructions | 7 | 0 | 0 | 0 | 4/4 full; 0 partial; 0 missing |
| Luna revised instructions + schema | 4 | 0 | 0 | 0 | 4/4 full; 0 partial; 0 missing |
| Gemini controlled saved | 4 | 2 | 0 | 0 | 1/4 full; 2 partial; 1 missing |

**Extraction findings**

- **Gemini controlled saved — core**, item(s) 2: context_component=facilitator role and component_type=therapeutic alliance bind surrender/emotional-experience moderator statistics to an untested facilitator/alliance effect. Narrative identifies actual subjective predictors.
- **Gemini controlled saved — core**, item(s) 4: Discussion speculation about supportive environment is encoded as an empirically identified sensory-environment factor increasing emotional safety; EBI mean71 and surrender82.4 are descriptive subjective scores, not an isolated environment effect. EBI n23 also not the stated83.

**Graph findings and limitations**

- **Luna current / Luna revised instructions / Luna revised instructions + schema — wrong design metadata:** Human exploratory moderation analyses become preclinical despite human participant narrative. No animal experiment.
- **Luna revised instructions / Luna revised instructions + schema — wrong graph parent:** Self-rated emotional/surrender experience becomes Facilitator role parent because facilitator mentioned in delivery context; measured predictor is participant experience, not facilitator.

**Source or interpretation qualifications**

- Whole-package association is retained with explicit component-not-isolated qualification. Subjective predictors under intervention_context are legitimate context associations but overlap subjective-experience routing.
- Item6 faithfully copies malformed source F( ,13.9) rather than using not_reported; formatting/contract issue, not invented value.

## H28 Compreensão de Sentidos Atribuídos à Ayahuasca: Percursos Terapêuticos do Uso Ritualístico

[Paper DOI](https://doi.org/10.18065/2020v26n2.4) · [Supplied source](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/controlled_historical/papers/H28/source.txt>) · [All extraction outputs](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/comparison_packets/controlled_historical/H28.json>)

Source depth: article text. Domains: intervention context.

| Arm | Items | Core material errors | New field errors | Scope items | Central coverage |
|---|---:|---:|---:|---:|---|
| Luna current | 2 | 0 | 0 | 0 | 2/3 full; 0 partial; 1 missing |
| Luna revised instructions | 1 | 0 | 0 | 0 | 3/3 full; 0 partial; 0 missing |
| Luna revised instructions + schema | 2 | 0 | 0 | 0 | 2/3 full; 1 partial; 0 missing |
| Gemini controlled saved | 3 | 1 | 0 | 0 | 1/3 full; 1 partial; 1 missing |

**Extraction findings**

- **Gemini controlled saved — core**, item(s) 3: component_type=facilitator role substitutes a human facilitator construct for Arthur’s personal narrative of self-forgiveness and ritual experience; no facilitator outcome was measured. One-year follow-up is also unsupported: this is a life-history interview, with attendance stopping after about a year.

**Graph findings and limitations**

No specific graph error or mapping limitation recorded for this paper in the completed lineage review.

## H29 NMDA receptor blockade at rest triggers rapid behavioural antidepressant responses.

[Paper DOI](https://doi.org/10.1038/nature10130) · [Supplied source](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/controlled_historical/papers/H29/source.txt>) · [All extraction outputs](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/comparison_packets/controlled_historical/H29.json>)

Source depth: article text. Domains: molecular pathway readout.

| Arm | Items | Core material errors | New field errors | Scope items | Central coverage |
|---|---:|---:|---:|---:|---|
| Luna current | 7 | 0 | 0 | 0 | 3/4 full; 1 partial; 0 missing |
| Luna revised instructions | 10 | 1 | 0 | 0 | 4/4 full; 0 partial; 0 missing |
| Luna revised instructions + schema | 7 | 0 | 0 | 0 | 3/4 full; 0 partial; 1 missing |
| Gemini controlled saved | 5 | 0 | 0 | 0 | 2/4 full; 2 partial; 0 missing |

**Extraction findings**

- **Luna revised instructions — core**, item(s) 10: Compound anchor is Rottlerin (5 mg/kg), but the TrkB-autophosphorylation result belongs to NMDAR-antagonist treatment. The same item narrative admits the correct treatment class.

**Graph findings and limitations**

- **Luna revised instructions — wrong graph subject:** Wrong raw Rottlerin anchor survives as detail-only TrkB finding; correct source treatment is NMDAR antagonist.
- **Luna revised instructions / Luna revised instructions + schema — exposure role ambiguity:** Alternative ketamine/MK801 conditions preserved as treatment_regimen with atomic Ketamine overview; rich raw retains MK801 and noncoadministration. Missing explicit alternative-arm role in canonical subject, not automatically false ketamine result.

## H30 Evaluation of Biased and Balanced Salvinorin A Analogs in Preclinical Models of Pain

[Paper DOI](https://doi.org/10.3389/fnins.2020.00765) · [Supplied source](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/controlled_historical/papers/H30/source.txt>) · [All extraction outputs](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/comparison_packets/controlled_historical/H30.json>)

Source depth: article text. Domains: molecular pathway readout.

| Arm | Items | Core material errors | New field errors | Scope items | Central coverage |
|---|---:|---:|---:|---:|---|
| Luna current | 4 | 0 | 0 | 0 | 3/3 full; 0 partial; 0 missing |
| Luna revised instructions | 6 | 0 | 0 | 0 | 3/3 full; 0 partial; 0 missing |
| Luna revised instructions + schema | 3 | 0 | 0 | 0 | 3/3 full; 0 partial; 0 missing |
| Gemini controlled saved | 4 | 0 | 0 | 0 | 2/3 full; 1 partial; 0 missing |

**Extraction findings**

No confirmed material source or typed-field error identified in these reviewed outputs; omissions and graph behavior are assessed separately.

**Graph findings and limitations**

No specific graph error or mapping limitation recorded for this paper in the completed lineage review.

**Source or interpretation qualifications**

- cAMP is a functional accumulation assay; Gemini expression_change is an imprecise old mechanistic label, not counted as a strict false molecular measurement. Gemini dose 0.001–1000 nM is absent from supplied text/caption; original figure axes were not available in input, so this is unsupported precision rather than verified false concentration range.

## H31 Differential Modulation of Remifentanil-induced Analgesia and Postinfusion Hyperalgesia by S -Ketamine and Clonidine in Humans

[Paper DOI](https://doi.org/10.1097/00000542-200307000-00025) · [Supplied source](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/controlled_historical/papers/H31/source.txt>) · [All extraction outputs](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/comparison_packets/controlled_historical/H31.json>)

Source depth: article text. Domains: molecular target.

| Arm | Items | Core material errors | New field errors | Scope items | Central coverage |
|---|---:|---:|---:|---:|---|
| Luna current | 0 | 0 | 0 | 0 | Not scored |
| Luna revised instructions | 0 | 0 | 0 | 0 | Not scored |
| Luna revised instructions + schema | 0 | 0 | 0 | 0 | Not scored |
| Gemini controlled saved | 3 | 0 | 0 | 0 | Not scored |

**Extraction findings**

No confirmed material source or typed-field error identified in these reviewed outputs; omissions and graph behavior are assessed separately.

**Graph findings and limitations**

No specific graph error or mapping limitation recorded for this paper in the completed lineage review.

**Source or interpretation qualifications**

- Target-route scope ambiguity: pain phenotype modulation using known antagonists is mechanistic inference without target-level readout. All Luna empty outputs and Gemini nonempty outputs are excluded from scope/coverage correctness scoring, consistently with root adjudication. Gemini ketamine peak plasma100ng/mL drops source qualifier calculated; this modeled/observed precision is not counted as a false number. Known agonist/antagonist identities are not false merely because not measured here.

## H32 5-HT 2A Receptors Stimulate ACTH, Corticosterone, Oxytocin, Renin, and Prolactin Release and Activate Hypothalamic CRF and Oxytocin-Expressing Cells

[Paper DOI](https://doi.org/10.1523/jneurosci.21-10-03572.2001) · [Supplied source](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/controlled_historical/papers/H32/source.txt>) · [All extraction outputs](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/comparison_packets/controlled_historical/H32.json>)

Source depth: article text. Domains: molecular target.

| Arm | Items | Core material errors | New field errors | Scope items | Central coverage |
|---|---:|---:|---:|---:|---|
| Luna current | 2 | 0 | 0 | 0 | Not scored |
| Luna revised instructions | 2 | 0 | 0 | 0 | Not scored |
| Luna revised instructions + schema | 2 | 0 | 0 | 0 | Not scored |
| Gemini controlled saved | 3 | 0 | 0 | 0 | Not scored |

**Extraction findings**

- **Luna revised instructions + schema — conditional**, item(s) 1: System states MDL administered1hour before DOI; source administered MDL1hour before killing and DOI15min before killing, so actual pretreatment45min. Conditional on target-route eligibility.

**Graph findings and limitations**

No specific graph error or mapping limitation recorded for this paper in the completed lineage review.

**Source or interpretation qualifications**

- Conditional target-route evidence: selective antagonist perturbation with endocrine/Fos endpoints supports receptor mediation, but no direct receptor assay. Coverage not scored across arms due scope sensitivity; measured hormone/Fos results remain source-supported.

## H33 Simultaneous quantitation of ketamine, norketamine and dehydronorketamine in human milk using a novel ultra high-performance liquid chromatography-mass spectrometry (UPLC-MS/MS) assay

[Paper DOI](https://doi.org/10.1016/j.jpba.2023.115502) · [Supplied source](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/controlled_historical/papers/H33/source.txt>) · [All extraction outputs](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/comparison_packets/controlled_historical/H33.json>)

Source depth: article text. Domains: pharmacokinetics exposure.

| Arm | Items | Core material errors | New field errors | Scope items | Central coverage |
|---|---:|---:|---:|---:|---|
| Luna current | 3 | 0 | 0 | 0 | 1/2 full; 0 partial; 1 missing |
| Luna revised instructions | 4 | 0 | 0 | 0 | 2/2 full; 0 partial; 0 missing |
| Luna revised instructions + schema | 2 | 0 | 0 | 0 | 2/2 full; 0 partial; 0 missing |
| Gemini controlled saved | 3 | 0 | 0 | 0 | 1/2 full; 0 partial; 1 missing |

**Extraction findings**

No confirmed material source or typed-field error identified in these reviewed outputs; omissions and graph behavior are assessed separately.

**Graph findings and limitations**

No specific graph error or mapping limitation recorded for this paper in the completed lineage review.

**Source or interpretation qualifications**

- metabolized_to and N-demethylation encode known metabolite relationships beyond measured milk detection. Biological identities are not false; this is evidence-role ambiguity rather than measured metabolic pathway proof. Source abstract negative-ionization versus methods positive-ionization conflict must not count as a model error; instructions follows methods.

## H34 Detection of ketamine in the oral fluid of drivers in northeastern France during the years 2020-2023.

[Paper DOI](https://doi.org/10.1111/fcp.13060) · [Supplied source](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/controlled_historical/papers/H34/source.txt>) · [All extraction outputs](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/comparison_packets/controlled_historical/H34.json>)

Source depth: article text. Domains: pharmacokinetics exposure.

| Arm | Items | Core material errors | New field errors | Scope items | Central coverage |
|---|---:|---:|---:|---:|---|
| Luna current | 2 | 0 | 0 | 0 | 3/3 full; 0 partial; 0 missing |
| Luna revised instructions | 4 | 1 | 0 | 0 | 3/3 full; 0 partial; 0 missing |
| Luna revised instructions + schema | 2 | 0 | 0 | 0 | 2/3 full; 1 partial; 0 missing |
| Gemini controlled saved | 3 | 0 | 0 | 0 | 2/3 full; 1 partial; 0 missing |

**Extraction findings**

- **Luna revised instructions — core**, item(s) 3: PK typed fields encode Norketamine metabolized_to Norketamine (self-metabolism), while narrative correctly describes norketamine detection after ketamine.

**Graph findings and limitations**

- **Luna revised instructions — wrong graph relation:** Raw Norketamine metabolized_to Norketamine is internally wrong; normalizer emits Norketamine metabolized_to Concentration (self-reference fallback changes object but preserves invalid relation).

**Source or interpretation qualifications**

- Source abstract gives821 for norketamine-positive subgroup but results gives1385;821 is overall. Outputs following Results are supported. exposure_altered_by wording for observational association is a coarse relation; narrative in new arms explicitly noncausal. Norketamine metabolite identity itself is not false.

## H35 Examining Attitudes to Psilocybin: Should Candidates for Medical Psilocybin be Required to Pass a Contextual Suitability Test?

[Paper DOI](https://doi.org/10.1177/00221678221110331) · [Supplied source](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/controlled_historical/papers/H35/source.txt>) · [All extraction outputs](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/comparison_packets/controlled_historical/H35.json>)

Source depth: article text. Domains: real world public health.

| Arm | Items | Core material errors | New field errors | Scope items | Central coverage |
|---|---:|---:|---:|---:|---|
| Luna current | 2 | 0 | 0 | 0 | 2/3 full; 0 partial; 1 missing |
| Luna revised instructions | 3 | 0 | 0 | 0 | 3/3 full; 0 partial; 0 missing |
| Luna revised instructions + schema | 3 | 0 | 0 | 0 | 2/3 full; 1 partial; 0 missing |
| Gemini controlled saved | 3 | 3 | 0 | 0 | 1/3 full; 2 partial; 0 missing |

**Extraction findings**

- **Gemini controlled saved — core**, item(s) 1, 2, 3: Self-treatment and Recreational/nightlife contexts are assigned to a hypothetical general-population attitudes survey. Those actual use settings were not measured for these associations.

**Graph findings and limitations**

- **Luna revised instructions / Luna revised instructions + schema — lost focal subject:** Personality-predictor exposure correctly names predictor but lacks Psilocybin; normalizer ignores psilocybin explicitly present in outcome/summary and retains non-drug predictor as detail-only compound. Valid psilocybin attitude association unavailable from main graph.

## H36 Long-term intentional Datura use and its consequences

[Paper DOI](https://doi.org/10.4103/psychiatry.indianjpsychiatry_276_18) · [Supplied source](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/controlled_historical/papers/H36/source.txt>) · [All extraction outputs](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/comparison_packets/controlled_historical/H36.json>)

Source depth: article text. Domains: real world public health.

| Arm | Items | Core material errors | New field errors | Scope items | Central coverage |
|---|---:|---:|---:|---:|---|
| Luna current | 2 | 0 | 0 | 0 | Not scored |
| Luna revised instructions | 0 | 0 | 0 | 0 | Not scored |
| Luna revised instructions + schema | 0 | 0 | 0 | 0 | Not scored |
| Gemini controlled saved | 1 | 0 | 0 | 0 | Not scored |

**Extraction findings**

- **Gemini controlled saved — conditional**, item(s) 1: Conditional on scope: Self-treatment assigned despite intentional hallucinogenic/stimulating recreational use; no therapeutic intent stated.

**Graph findings and limitations**

No specific graph error or mapping limitation recorded for this paper in the completed lineage review.

**Source or interpretation qualifications**

- Datura deliriant boundary is not explicitly settled by focal psychedelic scope. Do not score candidate empty responses as correct or baseline/Gemini nonempty as wrong merely from differing scope treatment.

## H37 Four Novel Synthetic Tryptamine Analogs Induce Head-Twitch Responses and Increase 5-HTR2a in the Prefrontal Cortex in Mice.

[Paper DOI](https://doi.org/10.4062/biomolther.2019.049) · [Supplied source](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/controlled_historical/papers/H37/source.txt>) · [All extraction outputs](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/comparison_packets/controlled_historical/H37.json>)

Source depth: article text. Domains: safety tolerability.

| Arm | Items | Core material errors | New field errors | Scope items | Central coverage |
|---|---:|---:|---:|---:|---|
| Luna current | 2 | 0 | 0 | 0 | 2/3 full; 0 partial; 1 missing |
| Luna revised instructions | 2 | 0 | 0 | 0 | 2/3 full; 0 partial; 1 missing |
| Luna revised instructions + schema | 5 | 0 | 0 | 0 | 2/3 full; 0 partial; 1 missing |
| Gemini controlled saved | 3 | 0 | 0 | 0 | 2/3 full; 1 partial; 0 missing |

**Extraction findings**

No confirmed material source or typed-field error identified in these reviewed outputs; omissions and graph behavior are assessed separately.

**Graph findings and limitations**

- **Luna current / Luna revised instructions / Luna revised instructions + schema / Gemini controlled saved — pooled exposure role ambiguity:** Separately tested novel compounds bundled as compound_combination; detail-only due vocabulary. Source narrative clarifies separate arms; not counted as false coadministration assertion.

**Source or interpretation qualifications**

- CPP n10 is the methods starting denominator; caption n7–8 is analyzed denominator. F16.12 is omnibus while p>0.05 refers to test-drug nulls: compact string does not disambiguate. Do not count source-supported starting n or stated test-drug null as invented numbers.

## H38 Potentiation of antidepressant treatment with racemic ketamine in a patient with an episode of severe depression in the course of bipolar disorder (BD) and a positive history of psychotic mania – a case report

[Paper DOI](https://doi.org/10.5114/fpn.2025.159505) · [Supplied source](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/controlled_historical/papers/H38/source.txt>) · [All extraction outputs](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/comparison_packets/controlled_historical/H38.json>)

Source depth: article text. Domains: safety tolerability.

| Arm | Items | Core material errors | New field errors | Scope items | Central coverage |
|---|---:|---:|---:|---:|---|
| Luna current | 1 | 0 | 0 | 0 | 2/2 full; 0 partial; 0 missing |
| Luna revised instructions | 2 | 0 | 0 | 0 | 2/2 full; 0 partial; 0 missing |
| Luna revised instructions + schema | 1 | 0 | 0 | 0 | 2/2 full; 0 partial; 0 missing |
| Gemini controlled saved | 2 | 0 | 0 | 0 | 2/2 full; 0 partial; 0 missing |

**Extraction findings**

No confirmed material source or typed-field error identified in these reviewed outputs; omissions and graph behavior are assessed separately.

**Graph findings and limitations**

No specific graph error or mapping limitation recorded for this paper in the completed lineage review.

**Source or interpretation qualifications**

- result_direction positive on adverse derealisation is ambiguous between detected occurrence and favorable outcome; narrative accurate. New arms negative with observed_adverse_event/descriptive makes interpretation clearer. Not counted strict scientific falsehood.

## H39 5-methoxy- N,N -dimethyltryptamine (5-MeO-DMT) used in a naturalistic group setting is associated with unintended improvements in depression and anxiety

[Paper DOI](https://doi.org/10.1080/00952990.2018.1545024) · [Supplied source](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/controlled_historical/papers/H39/source.txt>) · [All extraction outputs](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/comparison_packets/controlled_historical/H39.json>)

Source depth: article text. Domains: subjective experience.

| Arm | Items | Core material errors | New field errors | Scope items | Central coverage |
|---|---:|---:|---:|---:|---|
| Luna current | 3 | 0 | 0 | 0 | 3/3 full; 0 partial; 0 missing |
| Luna revised instructions | 3 | 0 | 0 | 0 | 3/3 full; 0 partial; 0 missing |
| Luna revised instructions + schema | 4 | 0 | 0 | 0 | 3/3 full; 0 partial; 0 missing |
| Gemini controlled saved | 4 | 0 | 0 | 0 | 1/3 full; 2 partial; 0 missing |

**Extraction findings**

No confirmed material source or typed-field error identified in these reviewed outputs; omissions and graph behavior are assessed separately.

**Graph findings and limitations**

- **Luna current / Luna revised instructions / Luna revised instructions + schema — partial construct projection:** One item bundles personal meaning, spiritual significance and wellbeing. Only one canonical construct appears (Personal significance except instructions Spiritual significance); other supported constructs remain narrative and are absent from corresponding canonical retrieval.

## H40 Beyond the San Pedro Cactus: Ancient Nasca Shamanism in Polychrome Ceramics

[Paper DOI](https://doi.org/10.23870/marlas.405) · [Supplied source](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/controlled_historical/papers/H40/source.txt>) · [All extraction outputs](</Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/primary_improvement_20261017/comparison_packets/controlled_historical/H40.json>)

Source depth: article text. Domains: subjective experience.

| Arm | Items | Core material errors | New field errors | Scope items | Central coverage |
|---|---:|---:|---:|---:|---|
| Luna current | 0 | 0 | 0 | 0 | Not scored |
| Luna revised instructions | 1 | 0 | 0 | 0 | Not scored |
| Luna revised instructions + schema | 1 | 0 | 0 | 0 | Not scored |
| Gemini controlled saved | 3 | 0 | 0 | 0 | Not scored |

**Extraction findings**

- **Gemini controlled saved — conditional**, item(s) 1, 2, 3: Conditional on route scope: ancient iconography is labeled human_participants with acute administered San Pedro exposure, although evidence consists of artifacts and analogies rather than studied participants or confirmed ingestion. Item3 imports cited modern visionary reports as ancient Nasca finding.

**Graph findings and limitations**

No specific graph error or mapping limitation recorded for this paper in the completed lineage review.

**Source or interpretation qualifications**

- Art-historical original visual interpretation versus primary subjective experience is an unsettled route boundary. Do not score empty/nonempty correctness. New candidates explicitly preserve no administered exposure/no direct participants.
