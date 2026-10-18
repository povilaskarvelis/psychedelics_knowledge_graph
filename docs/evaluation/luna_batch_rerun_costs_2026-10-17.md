# GPT-6 Luna batch cost for repeating screening and extraction

17 October 2026

**Recommended scope: preserve deterministic publication-type, language and usable-text exclusions, while letting Luna reassess topical rejections. This sends about 137,300 records to Luna for $37 in Batch screening costs. With the same retained extraction volume, screening plus extraction is approximately $67–80; budget about $100 including a 25% allowance.** These are model API costs in USD, assuming low reasoning and the tested prompts.

The narrower existing workflow remains $44–56, and sending every candidate remains $103–116. The comparison below distinguishes these choices.

| Stage | Papers | Model calls | Estimated Batch cost |
|---|---:|---:|---:|
| V4 screening after current deterministic prescreen | 49,713 | 49,713 | $13.33 |
| Primary-study evidence | 17,632 | 35,571 | $21.22 |
| Reviews and systematic reviews | 5,397 | 5,397 | $7.67 |
| Meta-analyses | 346 | 346 | $1.32 |
| Guidelines and consensus | 71 | 71 | $0.10 |
| **Total** | **23,446 retained for extraction** | **91,098** | **$43.64** |

There are **17,632 retained primary papers but 35,571 primary extraction calls** because evidence is extracted separately for each assigned domain. Reviews and meta-analyses each use one paper-level call. The current retained extraction table contains 41,385 calls in total, of which 19,491 use available full text and 21,894 use abstracts. Paper types partition the retained papers; each paper is counted once in the retained total.

The screening table contains about 23,800 distinct papers; this projection uses the **23,446 currently retained papers in the extraction-route table**. The estimate holds that final volume and type/domain mix constant when switching models. Screening also supplies the domain and paper-type labels, so there is no extra classification call in this calculation.

**Preserve cleanup and relax topical screening**

| Screening option | Records sent to Luna | Estimated Batch screening cost |
|---|---:|---:|
| Keep the complete current deterministic prescreen | 49,713 | $13.33 |
| Keep cleanup and usable-text rules; reopen topical rejections | 137,256 | $36.79 |
| Send every candidate record | 271,620 | $72.81 |

The middle option adds **87,543 records** with usable abstracts currently marked `exclude_obvious_irrelevant`. It preserves existing exclusions for preprints/unpublished records, theses/dissertations and other non-evidence artifacts, non-paper containers, non-English material, and unusable abstracts. It costs **$23.47 more** than the current prescreen-selected screening workload. Counts come from the saved first-matching prescreen outcomes; no production gate has been changed.

At the same retained-paper volume, the middle option totals **$67.11** with today's abstract/full-text extraction mix or **$79.49** with full text throughout. A 25% allowance gives roughly **$84–99**. The number and type of papers Luna newly retains remain an assumption in this extraction projection.

**Batch pricing and measured usage**

Official GPT-6 Luna Batch rates are **$0.05 per million input tokens and $0.25 per million output tokens** for inputs up to 272,000 tokens. Longer inputs cost **$0.10 input and $0.375 output per million**. [OpenAI pricing](https://developers.openai.com/api/docs/pricing). Batch provides a 50% discount relative to synchronous processing. [Official Batch guide](https://developers.openai.com/api/docs/guides/batch).

The calculation applies those Batch rates directly to saved metered input/output usage, including reasoning tokens. It assumes no cache-read savings and does not halve an already discounted rate. It uses the 200-paper V4 random screening run and 40 Luna calls for each extraction family, split into 20 abstract and 20 full-text inputs per family. The production route counts weight the actual abstract/full-text mix rather than blindly using the benchmark's 50/50 mix. Long-context pricing is retained for the unusually large Cochrane input in the meta-analysis sample.

The estimated uncached Batch rates per 1,000 tasks are:

| Task | Abstract | Full text |
|---|---:|---:|
| V4 screening | $0.268 | — |
| Primary extraction per domain | $0.366 | $0.864 |
| Review extraction per paper | $0.998 | $1.822 |
| Meta-analysis extraction per paper | $1.129 | $5.824 |

Guidelines use review-call usage as a proxy because a dedicated Luna guideline benchmark was not run; their projected spend is only about $0.10. Weighting primary costs by the corpus's domain distribution instead of averaging the ten benchmark domains changes the total from **$43.64 to $44.52**. Those domain-level means have just two examples per text depth, so they are a sensitivity check.

**Effect of the retained paper count**

| Papers retained after screening | Existing 49,713-paper model screen plus extraction | All 271,620 candidates screened plus extraction |
|---|---:|---:|
| 15,000 | $32.72 | $92.21 |
| 20,000 | $39.19 | $98.67 |
| 23,446 | $43.64 | $103.13 |
| 30,000 | $52.12 | $111.60 |

With the current type/domain/text mix, **each additional 1,000 retained papers adds about $1.29** in extraction costs. If all extraction inputs were full text, it adds about **$1.82 per 1,000 retained papers**. Thus the final inclusion count matters linearly, but a several-thousand-paper difference changes the estimate by only a few dollars at these rates.

For all-full-text extraction at the current retained volume, extraction rises from **$30.32 to $42.69**. Adding screening gives **$56.02** for the current prescreen-selected workload or **$115.51** for every candidate. This extrapolates the measured full-text usage; it does not assume those full texts are currently available.

**Budget scope**

The 25% allowance is a budgeting assumption for retries, cache-write premiums and longer outputs, rather than a measured retry rate or a guaranteed ceiling. The token samples are small and were selected for model evaluation, so actual corpus-wide output lengths can differ. The estimate covers one screening pass and one extraction pass per applicable route, with deterministic parsing/validation afterward. A second independent model review would add its own calls. Paid article access, external OCR/retrieval fees, implementation work, human review, taxes and account-specific adjustments are outside model token spend.

No screening or extraction batch was submitted to produce this estimate. Current production data and models remain unchanged.

[Reproducible calculation and source counts](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/luna_batch_cost_projection_20261017/projection.json) · [Official pricing snapshot](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/luna_batch_cost_projection_20261017/pricing_snapshot.txt). The saved calculation includes token averages, routes by domain and text depth, assumptions and input-table hashes.
