# Luna screening comparison: five prompts, four datasets

Updated 17 October 2026. **On the fresh random sample, V5 gets 181/199 decisions correct (91.0%), versus 177/199 (88.9%) for V4. Missed relevant papers: 12 → 12; unnecessary inclusions: 10 → 6.**

**Recommendation: freeze V5 as the screening candidate and end this prompt-tuning round.** It recovers all three targeted clear misses and improves both random rows under the frozen labels, while losing two correct decisions on Challenge 1. The fresh-sample gain is modest and does **not** improve overall relevant-paper retention. The secondary label sensitivity below also shows that V5 does not beat V4 under every reasonable scope interpretation.

| Source-assessed set | V1 original | V2 umbrella | V3 ordered | V4 focused | **V5 final** |
|---|---:|---:|---:|---:|---:|
| Challenge 1 | 111/133 · 83.5% | 116/133 · 87.2% | 113/133 · 85.0% | 117/133 · 88.0% | 115/133 · 86.5% |
| Challenge 2 | 70/110 · 63.6% | 70/110 · 63.6% | 80/110 · 72.7% | 85/110 · 77.3% | 93/110 · 84.5% |
| Random 1 (previous round) | 163/199 · 81.9% | 163/199 · 81.9% | 173/199 · 86.9% | 182/199 · 91.5% | 183/199 · 92.0% |
| **Random 2 (NEW)** | 164/199 · 82.4% | 168/199 · 84.4% | 176/199 · 88.4% | 177/199 · 88.9% | 181/199 · 91.0% |

All five prompts use **GPT-6 Luna, low reasoning**, identical source content, metadata and output schemas. The previous V1–V4 results and reference labels are reused exactly. This round adds V5 on all 555 previous papers and all five prompts on 200 fresh papers. Only assessed, usable records enter the scores. **Correctness means agreement with my frozen source judgments, not independently validated human accuracy.**

**Errors: missed relevant / unnecessary inclusion. Lower is better.** The relevant/irrelevant denominators are 48/85, 52/58, 66/133 and 63/136 respectively.

| Source-assessed set | V1 original | V2 umbrella | V3 ordered | V4 focused | **V5 final** |
|---|---:|---:|---:|---:|---:|
| Challenge 1 | 15 / 7 | 6 / 11 | 4 / 16 | 3 / 13 | 2 / 16 |
| Challenge 2 | 32 / 8 | 28 / 12 | 13 / 17 | 13 / 12 | 5 / 12 |
| Random 1 (previous round) | 31 / 5 | 27 / 9 | 10 / 16 | 9 / 8 | 8 / 8 |
| **Random 2 (NEW)** | 26 / 9 | 21 / 10 | 14 / 9 | 12 / 10 | 12 / 6 |

**What this final revision adds**

| Scope point | V4 | V5 clarification |
|---|---|---|
| Eligible compound families | Broad “related psychedelic compounds” umbrella | Explicit established psychedelic tryptamines and phenethylamines/amphetamines, including MMDA; related entactogens MDA/MDEA. Structural similarity alone remains insufficient. |
| Class-level and secondary results | A substantive drug- or class-specific finding can qualify | Explicitly accept reported hallucinogen/psychedelic class findings without named molecules, including secondary associations, predictors, correlates, use patterns and null results. |

V5 is 2,201 words versus V4's 2,085. Ketamine anesthesia/pain exclusions, review centrality, scholarly-analysis eligibility and the reagent/comparator distinction were not revised. The changes do not automatically include all stimulants, every pooled drug category, or every paper that mentions a psychedelic.

| V5 versus V4 | Errors fixed | New errors | Net correct decisions |
|---|---:|---:|---:|
| Challenge 1 | 4 | 6 | -2 |
| Challenge 2 | 12 | 4 | +8 |
| Random 1 (previous round) | 5 | 4 | +1 |
| **Random 2 (NEW)** | 11 | 7 | +4 |

On the genuinely new sample, V5 fixes **11** V4 errors and introduces **7**, for **+4** correct decisions overall. This is the additional evidence beyond the earlier V4 round; the other three rows are now exposed regression sets. Do not pool their scores into a population-wide accuracy estimate. The fresh paired exact McNemar test gives **p=0.481**; it is exploratory and does not account for assessor uncertainty.

| Fresh random sample | V4 | V5 |
|---|---:|---:|
| Relevant papers retained | 51/63 · 81.0% | 51/63 · 81.0% |
| Unnecessary inclusions | 10/136 | 6/136 |
| Included papers judged relevant | 83.6% | 89.5% |
| High-confidence decisions correct | 158/166 · 95.2% | 162/166 · 97.6% |
| High-confidence relevant papers missed | 2/40 | 0/40 |
| Repeat decisions unchanged | 18/20 | 20/20 |

V5 retains **51/63 relevant fresh papers (81.0%)**, the same total as V4, through a different mix of inclusions. It fixes four missed relevant papers but introduces four others. All 12 remaining missed relevant papers have moderate-confidence reference labels: they concern nonpsychiatric or anesthesia-adjacent ketamine research, comparator use, review centrality, and a sparse hallucinogen-use estimate. They remain in the primary denominator. V5's four high-confidence errors are unnecessary inclusions: a pooled hard-drug result, generic 5-HT2A ligand research, and two excluded anesthesia/sedation safety contexts. This identifies remaining review needs without proposing a sixth prompt.

The fresh V5 sampling-only 95% Wilson intervals are **86.2–94.2%** for accuracy and **69.6–88.8%** for relevant-paper retention. High-confidence results supplement the full scores; excluding borderline scope cases does not estimate full-workload accuracy. [Every V4→V5 change and both reasons](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/luna_screening_prompts_v5_20261017/v4_v5_changes.md) and [all fresh V5 disagreements, with source text](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/luna_screening_prompts_v5_20261017/v5_fresh_errors.md) are available for inspection.

**High-confidence subset, kept separate from the primary scores**

| Source-assessed set | V1 original | V2 umbrella | V3 ordered | V4 focused | **V5 final** |
|---|---:|---:|---:|---:|---:|
| Challenge 1 | 98/108 · 90.7% | 103/108 · 95.4% | 99/108 · 91.7% | 105/108 · 97.2% | 103/108 · 95.4% |
| Challenge 2 | 53/76 · 69.7% | 54/76 · 71.1% | 65/76 · 85.5% | 68/76 · 89.5% | 71/76 · 93.4% |
| Random 1 (previous round) | 146/161 · 90.7% | 145/161 · 90.1% | 153/161 · 95.0% | 158/161 · 98.1% | 161/161 · 100.0% |
| **Random 2 (NEW)** | 152/166 · 91.6% | 154/166 · 92.8% | 160/166 · 96.4% | 158/166 · 95.2% | 162/166 · 97.6% |

Challenge 1 also has a small decline among high-confidence judgments, from 105/108 to 103/108. The regressions are not confined to ambiguous references. On Random 1, V5 agrees with all 161 high-confidence judgments, recovering the three clear relevant-paper misses.

**What happened to the nine previously reviewed V4 misses**

| Previously reviewed V4 miss | V5 decision | Prior review category |
|---|---|---|
| [The Identification, Metabolism and Toxicity of an Unknown Component Found in a New Clande…](https://doi.org/10.3408/jafst.15.75) | Exclude | Scope / threshold |
| [Scoring Ecstasy: MDMA, Consumerism and Spirituality in the Early Fiction of Irvine Welsh](https://doi.org/10.1080/14797580305357) | Exclude | Defensible exclusion |
| [Simultaneous quantitative determination of amphetamines, ketamine, opiates and metabolite…](https://doi.org/10.1002/rcm.3409) | Include | Defensible exclusion |
| [Recent Use of Synthetic Cannabinoids, Synthetic Opioids, and Other Psychoactive Drug Grou…](https://doi.org/10.1080/02791072.2020.1754534) | Include | Clear miss |
| [Sexual risk behavior associated with co-administration of methamphetamine and other drugs…](https://doi.org/10.1080/10550490802544466) | Exclude | Scope / threshold |
| [Women who abuse prescription opioids: Findings from the Addiction Severity Index-Multimed…](https://doi.org/10.1016/j.drugalcdep.2009.03.014) | Include | Clear miss |
| [Not All Cases of Visual Snows are Benign: Mimics of Visual Snow Syndrome.](https://doi.org/10.2147/ndt.s338111) | Exclude | Scope / threshold |
| [Effects of midazolam, pentobarbital and ketamine on the mRNA expression of ion channels i…](https://doi.org/10.1186/1471-2253-13-32) | Exclude | Scope / threshold |
| [Evidence for the Biogenic Formation of Amphetamine Derivatives from Components of Nutmeg](https://doi.org/10.1159/000136402) | Include | Clear miss |

**All three strong misses are now included:** the two hallucinogen/opioid association studies and the myristicin-to-MMDA metabolism study. V5 also includes the disputed hair-assay paper, while excluding the other five. That last inclusion helps the original frozen score but does not agree with my dated preference to exclude assay-validation-only work.

The primary Random 1 row still uses its original 66 include / 133 exclude labels. The preceding review already preferred excluding two of those references: literary criticism and assay-validation-only research. A prespecified secondary calculation applies those two changes consistently to **all five prompts**: **V1 163/199 (81.9%); V2 163/199 (81.9%); V3 171/199 (85.9%); V4 184/199 (92.5%); V5 183/199 (92.0%)**. This sensitivity result does not replace the primary table or count as new evidence. The exact older reasons and dated reassessments remain in the [nine-paper review](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/luna_screening_prompts_v4_20261016/posthoc_20261017/nine_exclusions_review.json).

**Fresh sample and reference method**

The two challenge rows were assembled around difficult prior cases. Challenge 2 originally contained 75 fresh historical-Gemini/Luna disagreements and 40 agreement controls; 72 and 38 respectively had usable references. Historical Gemini decisions selected cases, not correctness labels. Random 1 was the previous uniform workload test. All three rows are now exposed to prompt development. Their history is preserved in the previous-report snapshot.

The new production prescreen frame contains 49,713 records. After excluding all known previous evaluation DOI/title identities, the earlier 400-paper nomination pool, known aliases and duplicate normalized titles, 37,519 unseen records remained. A uniform seeded sample of 200 was selected without using any inclusion/exclusion prediction, disagreement filter, topic quota or abstract-length filter. It estimates this unseen prescreen-retained workload, not all retrieved literature.

V5 was fixed before I read these papers. I then read all 200 source-only records and froze 63 include, 136 exclude and one unscorable judgment before any new API inference. There are 166 high-confidence and 33 moderate-confidence usable judgments. One mismatched/corrupt source record is removed equally for all prompts, giving 199. No labels or prompt text were changed after predictions. The assessor and prompt designer are the same Codex assistant; this is not independent human gold, and some boundary judgments remain contestable. The earlier Challenge 1/2 rows score 133/240 and 110/115 records; previously unassessed papers are not silently counted as correct.

The design separates typical and edge cases, freezes references before predictions and checks variability, following [official evaluation guidance](https://developers.openai.com/api/docs/guides/evaluation-best-practices). The single-assessor limitation remains material.

**Operating cost and repeatability**

This round completed **1,655 new Luna calls**: 1,555 first responses and 100 repeats, at an estimated metered-token cost of **$0.349573**. There were **zero new Gemini calls**. The complete comparison now contains 755 unique paper inputs × five prompts = 3,775 first responses, with older responses reused.

| New random sample: observed operating cost | V4 | V5 |
|---|---:|---:|
| Metered-token estimate per 1,000 screenings | $0.215 | $0.209 |
| Uncached equivalent per 1,000 screenings | $0.538 | $0.548 |
| Median response time | 3.01 seconds | 2.95 seconds |
| Raw exclusions carrying domain tags | 7/200 | 8/200 |

Actual cost depends on caching; the uncached equivalent uses standard token rates with the same observed token volumes. These figures are estimates from provider usage, not reconciled invoices. Timings describe this run. The existing normalizer removes excluded-paper domain tags without changing screening decisions. Domain and paper-type semantic correctness were not independently assessed.

On 20 fresh papers repeated once per prompt, decisions agree **V1 19/20; V2 20/20; V3 17/20; V4 18/20; V5 20/20**. Primary scores use first responses only; this small repeat sample describes variability without establishing a general stability ranking.

All 1,655 new responses have saved raw outputs, complete usage and valid scientific-schema results. Offline replay added no requests and preserved every raw response and result. Source content and both schemas match across all five prompts for all 755 papers. Thirty relevant regression tests pass. Production settings and corpus were not changed by this evaluation. **This is a screening experiment; it adds no extraction-performance result.**

**Evidence and previous work**

- [Exact V5 prompt](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/luna_screening_prompts_v5_20261017/prompts/v5_class_scope.txt), with V1–V4 in the same folder.
- [All 200 new source judgments and five decisions](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/luna_screening_prompts_v5_20261017/random_case_audit.md), [frozen labels](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/luna_screening_prompts_v5_20261017/random_judgments.json), [timestamp and hashes](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/luna_screening_prompts_v5_20261017/random_reference_freeze.json).
- [Frozen protocol](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/luna_screening_prompts_v5_20261017/protocol.json), [full numerical results](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/luna_screening_prompts_v5_20261017/analysis.json), [integrity checks](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/luna_screening_prompts_v5_20261017/integrity.json), [raw-response hashes](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/luna_screening_prompts_v5_20261017/raw_response_hashes.json).
- [Previous four-prompt report snapshot](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/luna_screening_prompts_v5_20261017/previous_report_snapshot.md), preserving all earlier findings and the nine-paper posthoc note.
- [Original Gemini/Luna model and extraction comparison](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/docs/evaluation/gemini_luna_head_to_head_2026-10-16.md).
