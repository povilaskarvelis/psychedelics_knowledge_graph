# Primary-study extraction: source audit and graph trace

17 October 2026. **24 papers, 51 saved Luna domain outputs, all 150 extracted items reviewed. No new model calls; no prompt, schema or production changes.**

The audit identifies several focused repairs; it does not establish a need for wholesale redesign. Luna often preserves the scientific narrative and detailed numbers well. The recurring weaknesses are **incorrect structured qualifiers, missing important comparisons, and information that normalization either ignores or reinterprets**. Two original-PDF checks also confirmed serious unit corruption before Luna received the text.

This is a diagnosis of the existing baseline, not a new candidate comparison or proof of readiness for the full rerun. The earlier recommendation to retain the baseline meant that the tested replacements had not demonstrated sufficient benefit; it did not establish that the baseline was free of these problems.

## What was checked and what counts mean

I used saved outputs from the **current baseline primary-study prompts** in the earlier Luna experiment. These are evaluation outputs, not a new production extraction. The sample covers all ten primary extraction domains: 16 papers selected for domain and source-depth coverage independently of earlier scores, plus 8 deliberately chosen diagnostic cases. There are 10 abstract-only and 14 article-text inputs. All routed domain outputs were retained for each paper.

For each paper, the review compared the supplied methods/results, tables and available captions with every extracted item, checked the important findings for omissions, and inspected the actual instructions and schema. A separate trace followed every item through conversion, normalized findings, admission decisions and graph relationships. I divided source reading across three Codex reviewers, reconciled classifications and rechecked the headline examples. This is **source-grounded AI judgment, not independent human gold**; reviewer agreement was not treated as proof.

The authoritative reference was the paper text supplied to Luna, with original PDF images used to resolve two unit discrepancies. We did not treat earlier Gemini decisions, Luna grades or the previous reference inventory as truth. Article packets can omit material or contain conversion errors; this is not an exhaustive audit of every figure in all original PDFs. All 150 items were inspected, but no exhaustive atomic-claim denominator was constructed.

| Source-audit finding | Coverage set: 16 papers, 90 items | Diagnostic set: 8 papers, 60 items | Total |
|---|---:|---:|---:|
| Confirmed incorrect or unsupported important factual fields | 2 papers / 2 items | 3 papers / 4 items | **5 papers / 6 items** |
| Important missing findings or comparisons | 3 papers | 2 papers | **5 papers** |
| Confirmed upstream unit corruption | 0 | 2 papers | **2 papers** |
| Unrelated routed papers extracted instead of abstained | 1 paper / 10 items | 1 paper / 5 items | **2 papers / 15 items** |

Rows overlap. The two unrelated papers are scope controls, leaving 22 in-scope papers and 135 items. The factual-field count excludes ambiguous biological categories, source conflicts, omissions and normalization defects; those are recorded separately. These purposeful samples **do not estimate corpus-wide accuracy**, and 144/150 must not be read as an accuracy score. All reviewed papers now belong to diagnostic/development material for any future revision, even where the earlier experiment called them holdout papers.

## Ranked failures, with concrete evidence

The order below reflects scientific consequence and recurrence, not an estimated population frequency. Paper IDs link to frozen source packets; exact output paths and quotations are in the [casebook](../../data/processed/evaluation/primary_source_audit_20261017/casebook.md).

### 1. Source conversion can silently change quantities by 1,000-fold

**LSD entropy/personality, P19:** the original PDF shows **75 μg**. The supplied text says **75 mg**, and all five extracted items carry that dose. The saved normalized findings retain the erroneous dose. One domain call warned about the source wording; the others did not. This is a verified source-processing error, not a Luna-invented dose. See the [PDF page image](../../data/processed/evaluation/primary_source_audit_20261017/pdf_checks/P19_page1.png).

**MDMA/ethanol rat-slice study, P23:** the original PDF shows MDMA concentrations **0.3 and 3 μM**; the supplied text repeatedly says mM. Six molecular items follow that text. Ethanol's **34.3 mM** is correct, so a global unit substitution would itself introduce errors. See the [original methods image](../../data/processed/evaluation/primary_source_audit_20261017/pdf_checks/P23_page4.png).

These two papers were selected partly because of known source ambiguity. The new result is resolution against the original images and confirmation of propagation, not a claim that two of every 24 papers have this problem.

### 2. Normalization sometimes changes a correctly extracted entity

**Bufotenine becomes partly DMT, P10:** three bufotenine-only items correctly distinguish the compound in extraction, but alias matching adds **DMT** as a graph subject. The paper studies DMT elsewhere; the error is attribution of these particular findings, not the mere existence of a paper–DMT link.

**Receptor becomes ligand, P10:** all seven generic 5-HT receptor items become Serotonin molecular-readout findings. One item explicitly says a mechanism is unlikely to involve serotonin release, yet its normalized label becomes **Serotonin release**. Conversely, two valid **5-HT2A** target items in P05 are rejected because the receptor's expanded name is mistakenly recognized as a combination of 5-HT2A and Serotonin.

These are reproducible downstream defects. Additional extraction prose would not address their cause.

### 3. Correct prose can conceal a wrong structured fact

| Paper | What the source establishes | What extraction gets wrong | Why it matters |
|---|---|---|---|
| **P10**, tryptamine electrophysiology | DMT directly inhibited 54 of 64 neurons excited by 5-HT | Summary attaches 54/64 to the separate antagonism experiment | Correct number, wrong experimental relation |
| **P15**, human ketamine/nicotine | Human participants receiving IV ketamine | One route field says `preclinical_injection` | Misclassifies human evidence; survives normalization |
| **P18**, MDMA stereoisomers | Four female rhesus monkeys | Safety population category says `mouse_model` | Wrong species in a graph-facing filter |
| **P19**, LSD/openness | Reported T = 1.95, p = .03, d = .16 describes change from screening | Comparator field says placebo | Within-person change can appear to be a treatment-versus-placebo effect; currently withheld as unmapped Openness |
| **P22**, cancer/psilocybin follow-up | Abstract states phase 2; does not establish randomization or a control arm | Both clinical items say `phase_2_rct` | Unsupported elevation of the evidence design |

The current schemas already permit a faithful answer in these cases. This is evidence for better adherence and consistency checks, not evidence that new fields are always necessary.

A separate category contains **semantic mismatches requiring a clearer contract**: plasma oxytocin/prolactin concentrations labelled `expression_change`, and retreat safety practices labelled with a negative safety-effect direction although no participant harm was measured. The prose is generally accurate. These are retained as problems without inflating the six-item factual-error count.

### 4. Extraction sometimes omits the result that limits the main story

| Paper | Retained | Missing important finding or qualification |
|---|---|---|
| **P09**, zebrafish toxicity | Low embryonic mortality and larval effects | Embryonic sublethal harms of DCK/2F-DCK, including edema and developmental abnormalities |
| **P11**, ketamine psychotherapy | Symptom changes, remission, follow-up, therapist-group null tests | Reported baseline-severity/improvement association; age and session-count null associations. These are secondary descriptive associations, not established causal moderators; lower priority than the missing P18 experiment. |
| **P16**, MDMA/touch | Increased oxytocin, greater pleasantness, OT–brain association | **No relationship between oxytocin change and touch pleasantness**; a different result from the retained OT–brain correlation |
| **P18**, stereoisomers | Fourteen molecular items, including many null results | Dose-equated S-MDMA 0.85 mg/kg versus racemate 1.7 mg/kg comparison: no detected dopamine difference, p = .492. This does not establish equivalence. |
| **P23**, rat slices | Inhibition of evoked dopamine overflow with the SERT blocker present | Explicit disappearance of that effect without the blocker; retained extraction is correctly restricted, but the complementary test is absent |

This is a selective completeness problem. Luna retained many other null findings accurately; the audit does not establish a universal preference for positive results. Producing more items also does not guarantee preservation of the paper's scientific argument.

### 5. Normalization overlooks information extraction already supplies

Among the **in-scope** normalized molecular-readout items:

- **29/29 items across five papers contain a meaningful extracted dose, but the canonical dose is empty.** The converter's alias list does not include `dose_or_exposure`. The original text remains available; this is structured-field loss, not complete deletion.
- **24/29 items choose the older sentence-shaped readout over the explicit specific marker.** In P18, `Plasma prolactin` becomes a label such as “Plasma prolactin concentration increased relative to session baseline. levels.” A no-change result receives a different node. A stable marker is being mixed with its result.
- **Five grouped brain items across P16/P19 lose part of their entity lists.** One six-entry region list maps only to Cerebellum. Another item loses the focal MT+ region while retaining Calcarine cortex. Some parent-level merging is intentional, but unmatched members currently have no separate failure record.

The current converter reproduced all 150 saved converted rows exactly in a read-only check; the graph builder is byte-identical to the evaluated snapshot. These observations concern the current transformation behavior, not an obsolete implementation. The [normalization report](../../data/processed/evaluation/primary_source_audit_20261017/reviews/normalization_trace.md) contains complete lineage and reproduction details.

### 6. Scientific roles remain implicit at the extraction–graph boundary

Three representative cases illustrate the same problem:

- **P03:** expert concerns about delirium/distress become safety relationships. The graph retains supporting prose, but lacks an explicit distinction between anticipated risk and observed patient events.
- **P14:** organizations' psychosis exclusion policies become a Psychosis risk relationship. The measured quantity is policy prevalence, not psychosis incidence.
- **P24:** findings about a peer integration group project to five named drugs from participants' histories. The analyzed factor is group participation; no five separate drug-specific effects were estimated.

These are **lost role distinctions and projection ambiguities**, not automatically false scientific claims: the existing graph also functions as a literature-retrieval map. Nevertheless, a user or downstream analysis needs those roles to distinguish evidence about a topic from a measured effect. Similar distinctions arise between an assayed metabolite and a separately consumed drug, an experimental control and a focal exposure, or an analytical reagent and an in-vivo metabolic pathway.

## What should be explicit for the existing graph

The current categories are a useful minimum contract, not a ceiling on extracted detail. The audit suggests evaluating the following information directly before deciding whether each gap needs a prompt adjustment, a schema clarification or a normalization repair.

| Current graph views | Information needed without scientific guesswork | Rich detail to retain beyond the graph |
|---|---|---|
| Conditions, Safety | Measured endpoint versus enrolled diagnosis; observed event versus concern/policy; exact comparator and direction | Diagnostic criteria, prevention context, severity, denominators, uncertainty |
| Cognition, Behavior, Subjective effects | Construct versus instrument; drug effect versus predictor/association; task and comparison | Subscales, conditional/null results, scale direction, qualitative experience |
| Brain regions | Separate named entities, region/network/circuit identity, which contrast each result belongs to | Laterality, coordinates, clusters, modality and connectivity pairings |
| Molecular effects, Targets | Stable marker/target identity; ligand versus receptor; measured concentration versus inferred mechanism; assay/system | Tissue, cell type, functional versus binding evidence, doses, stereoisomers |
| Treatment context, Real-world use | Actual intervention or analyzed exposure versus recommendation, reported practice or historical use | Delivery details, participant perspectives, implementation and policy context |
| Across all views | Focal subject, comparator/co-exposure, population, analysis-specific sample, timing, source locator, uncertainty | Complete narrative, original labels, unmapped concepts and additional estimates |

PK findings should remain rich even though the current graph contract has no dedicated PK overview preset. Absence from that preset is not grounds to discard them. Likewise, stable graph categories should not force a measured biomarker to become a mechanistic claim.

The most important streamlining principle is to **capture the scientific relationships explicitly once, then have normalization map identities and categories while preserving those relationships**. This means binding an estimate to its outcome, comparison, population and timepoint—not merely putting more numbers into a long field. It also means using explicit information already present before asking Luna for additional detail. The audit establishes these requirements; it does not yet establish a winning revised schema.

## Strengths, efficiency and what this round newly establishes

The baseline handles substantial complexity correctly: P12 preserves functional channel inhibition without inventing direct binding; P13 distinguishes individual mice from analytical replicates; P15 retains subgroup-dependent results and a nonsignificant trend; P20 distinguishes human observations from simulated subjects and apparent clearance from true systemic clearance. P21 explicitly flags a source conflict rather than silently treating conflicting direction language as certain. These capabilities should be preserved in future comparisons.

The graph trace found **93 raw items with main-graph representation, 24 with detail-only representation and 33 in audit records only**. None disappeared without a finding or audit record. These are processing destinations, not correctness scores. All 15 unrelated control items were kept out of the main graph, and some other exclusions are intentional. Separately, P08's valid delirium-prevention result and P12's Kir4.1 functional target expose usable-vocabulary gaps.

The 51 domain calls repeated **2.15 times** the unique source text of these 24 papers. This is a measured source of processing overhead, not proof that 53% of calls or a comparable fraction of cost can safely be removed. The earlier combined-call experiment lost coverage. A shared paper-level representation might help consistency, but this audit alone does not justify replacing the domain architecture.

Compared with the earlier broad experiment, the new contribution is **150 item-level source reviews, explicit omission inventories, complete extraction-to-graph lineage, original-image resolution of two unit errors, and reproducible identification of ignored fields and unsafe entity matching**. Some diagnostic examples were already suspected; this round establishes their causes and consequences more carefully. It does not claim a new improvement percentage, because no revised system was tested.

My judgment is to retain the overall architecture for now and use this evidence to define focused changes and separate evaluations. Source fidelity, extraction correctness/completeness and normalization fidelity need separate checks. Correct conversion of already-extracted information should not depend on another prompt experiment. Any later extraction revision should be evaluated on these fixed cases **and genuinely unseen papers**, with important omissions and wrong structured qualifiers scored separately from prose quality and graph admission counts.

The full extraction rerun remains on hold. This audit incurred **$0 additional model-API cost**.

## Evidence package

- [All 24 papers and their detailed reviews](../../data/processed/evaluation/primary_source_audit_20261017/casebook.md): source/output links, item verdicts, omitted findings and exact evidence.
- [Frozen sample manifest](../../data/processed/evaluation/primary_source_audit_20261017/manifest.json): strata, selection reasons and source hashes.
- [Adjudicated headline findings and counts](../../data/processed/evaluation/primary_source_audit_20261017/adjudication.json): explicit inclusion/exclusion rules for error counts.
- [Normalization trace](../../data/processed/evaluation/primary_source_audit_20261017/reviews/normalization_trace.json): all 150 item lineages and domain-field inventories.
- [Artifact validation](../../data/processed/evaluation/primary_source_audit_20261017/review_validation.json): coverage, references and source-quote checks.
