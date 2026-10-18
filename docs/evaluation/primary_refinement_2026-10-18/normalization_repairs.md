# Normalization repairs before the paired extraction comparison

This stage changes deterministic normalization only. All replayed model outputs and prompts are unchanged. Nothing has been published and no model calls were made for this stage. The replay includes the 96-paper Luna baseline and its two previous variants, the controlled 40-paper four-arm comparison, the earlier fresh 48-paper four-arm comparison, and saved archival Gemini outputs. The archive contains 542 item instances including old extra domains; its matched-current-domain subset is reported separately (85 papers, 167 tasks, 491 items).

## Changes and evidence

| Mechanism | Repair | Source-audit examples / limits |
|---|---|---|
| Chemical identity | Preserve unregistered derivatives exactly in paper details instead of inheriting a parent drug. Normalize 5OMeDMT and racemic ketamine separately from enantiomers. | MLD-41, ETH-LAD, 1T-LSD, chlorinated MDMA, Oxo-LSD; P47 5OMeDMT and P84 racemate. The broad Hallucinogens analytical panel keeps its legitimate class link. An unregistered chemical is not assigned a newly invented registry entry. |
| Receptor identity | Receptor subtype/family text outranks a parenthetical ligand synonym, including subtype-not-specified qualifiers. A downstream reporter in the result narrative does not turn the receptor itself into an abundance assay. | P10 generic 5-HT receptor and H11 NMDA/cGMP. Functional-perturbation eligibility remains a separate scope question. |
| Scientific marker specificity | Measurement suffixes use the focal marker and tightly attached measurement wording, rather than incidental genotype/activation/expression words elsewhere in the row. | ECoG genotype, PPI genotype, mTOR expression and unrelated BDNF context. Co-labelled cell populations stay intact; c-Fos activity-marker intersections do not become separate positive receptor assays. Other immune/neurogenesis/injury co-label families retain their declared category. |
| Experimental preparation and design | Explicit preparation/unit metadata precedes species words and ancillary study context; species patterns are bounded and case-insensitive. Randomized animals remain preclinical; human “administration” no longer matches “rat.” | Cultured neurons, isolated mitochondria, human/document studies. Generic open-label prose does not establish nonrandom allocation. Raw contradictory explicit fields remain extraction errors rather than being silently corrected from external knowledge. |
| Adjunct sequences | Lithium after ketamine and analogous explicit sequences retain the complete regimen in paper details, without an atomic ketamine-effect projection. | F45 and H22. Treatment package identity is preserved; the current graph cannot faithfully express all roles and sequence structure. |
| Observed event versus policy/documentation | Explicit consent-document, eligibility, washout, and anticipated-concern rows remain accessible in details without the same main safety projection as an observed event. | P03, P14, P65. These are role-distinction repairs; the former literature links were not necessarily explicit false event assertions. Direct participant-reported global harm is preserved (P57). |
| Subjective symptom scales | Acute questionnaire “psychotic symptoms” stays a subjective profile; persistent/serious clinical psychosis remains safety. Pure measurement validation is detail-only; mixed validation plus actual dose/intensity association remains represented. | F47 VESSPA; F48 EDI. Merely mentioning a scale's reliability in the instrument description does not demote an observed association (P29). |
| Focal safety endpoints | Focal temperature, rash, arterial pressure and assay-readout descriptions outrank incidental care or drug names. Radioligand paroxetine is not co-administration. | P31 temperature/assay; P63 rash; H17 arterial-pressure “fall” is not falling behavior. Direct null dropout endpoints are retained. |
| Safety splitting | Do not split a row containing shared negation into affirmative fragments with an inherited overall result direction. | F44: “no significant adverse consequences or dropouts…” retains the complete observation. This can reduce individual endpoint links; it avoids creating an unsupported per-endpoint polarity. |
| Cellular versus respiratory safety | Explicit mitochondrial respiration/oxidative-phosphorylation endpoints become molecular readouts; apnea/breathing endpoints stay safety. | H18. The in-vitro and ex-vivo arms stay distinct. |
| Pooled diagnoses and context parents | Mixed unipolar/bipolar depressive-episode results retain the pooled label in details. Service integration is not post-session integration; emotional/mystical predictors do not inherit facilitator parents. | H24, P03, H27. Surrender still maps to set/setting. Broad-condition scope policy otherwise stays in place. |
| PK relationship inference | A route alone is not a route effect; a placebo comparator is not a co-exposure; a concentration correlation requires an actual response endpoint. Distinct measured metabolites retain their identity. | F15 concentration–subjective-effect association; P13 HMMA/HMA; P61 self exposure. Matrix–matrix and dose–concentration associations remain exposure characterization. Invalid self-metabolism assertions remain rejected/audited. |
| Public-health topic | Annual death counts are not population-use prevalence. A context-of-use proportion among deceased people is not a mortality-rate endpoint. | F43. The denominator context is not allowed to replace the measured topic. |
| Unknown endpoint transport | Preserve explicit unknown cognitive, subjective and safety labels in paper details rather than borrowing a nearby familiar construct or dropping the whole observation. | P21 behavioral change, P75 after-effects, P94 social/drug-use behavior. This improves transport, not necessarily extraction correctness or main-graph coverage. |

## Verification and interpretation

`normalization_verification.json` provides per-arm before/after counts, the exact matched archival subset, input hashes and the zero-mismatch reproduction of the prior saved projection. `normalization_change_review.json` lists every changed item instance and distinguishes anchor/admission changes from metadata-only changes. Raw-item equality is asserted in the replay, and the complete normalized/public/audit lineage is retained in every arm's `item_lineage.json`.

Before modules execute frozen copies of builder, converter, exporters and PK helper. Every imported changed PK function is explicitly rebound to the frozen helper; the old builder also uses the frozen converter bindings. The unchanged registry and vocabulary hashes are recorded. The replay's pre-change outputs reproduce the previous frozen projection, rather than assuming the snapshot worked.

The test suite includes positive and negative scientific controls, not just historical row counts. Independent peer review found several overbroad candidate rules (open-label allocation, PK correlations, co-label categories, pressure “fall,” mortality denominators, validation context and shared negation); these were corrected before freezing the code. The peer ledgers retain the original findings and subsequent reconciliation.

Counts of added findings or removed main links are not accuracy scores. Newly transported rows can expose previously hidden extraction errors. A role ambiguity or conservative detail-only decision is not automatically a corrected scientific falsehood. Some broad links are intentionally reduced when the current fields cannot support a faithful canonical interpretation; the complete scientific text remains in details or the audit record.

Known limitations remain: unregistered derivatives require registry work for atomic overview visibility; combined findings may contain inseparable roles/polarities; invalid self-metabolism records retain valid narrative components only in the raw/audit record; broad category ambiguities and domain eligibility policies remain unchanged; mistaken extraction fields, corrupted source units and missing source results require extraction/source-processing changes. The eight experimental extra fields from the earlier structured arm are retained but do not drive new semantic decisions in this normalization-only comparison.

## Saved-output replay counts

These are finding counts, not unique papers or accuracy estimates. The same paper appears in multiple arms.

| Cohort | Saved arm | Raw items | Findings before → after | Main findings before → after | Represented raw items before → after |
|---|---|---:|---:|---:|---:|
| archival | archived | 542 | 494 → 505 | 418 → 402 | 465 → 476 |
| controlled_historical | baseline | 91 | 80 → 80 | 63 → 57 | 79 → 80 |
| controlled_historical | gemini | 106 | 93 → 94 | 83 → 82 | 93 → 94 |
| controlled_historical | instructions | 133 | 115 → 116 | 86 → 74 | 110 → 113 |
| controlled_historical | structured | 124 | 108 → 111 | 77 → 72 | 103 → 106 |
| existing | baseline | 565 | 490 → 503 | 407 → 395 | 454 → 467 |
| existing | instructions | 675 | 593 → 617 | 480 → 465 | 535 → 557 |
| existing | structured | 647 | 579 → 598 | 464 → 445 | 521 → 539 |
| fresh | baseline | 124 | 106 → 105 | 99 → 88 | 98 → 101 |
| fresh | gemini | 114 | 98 → 102 | 86 → 85 | 87 → 91 |
| fresh | instructions | 150 | 134 → 134 | 104 → 93 | 126 → 130 |
| fresh | structured | 139 | 135 → 131 | 105 → 92 | 114 → 116 |

Across arms: 3,410 unchanged raw item instances; 471 changed projection instances; zero mismatches when reproducing the preceding saved projection. The matched archival subset has 491 items: represented items 428 → 438, findings 457 → 467, main findings 387 → 375. Those extra represented items are not automatically correct extractions. Final validation passed 273 tests and 305 parameter subtests across ten test files. The gate freezes 24 dependencies/configuration/test files.
