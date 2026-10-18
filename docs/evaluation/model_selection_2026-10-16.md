# Screening and evidence extraction model assessment

> Superseded for model choice by the [completed matched comparison](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/docs/evaluation/gemini_luna_head_to_head_2026-10-16.md). The assessment below records the earlier exploratory pilot.

16 October 2026

GPT-6 Luna is a credible, substantially cheaper candidate for this project. The new pilot demonstrates that it can execute all four task families and recover useful details missing from some earlier Gemini outputs. It does **not** establish that Luna is more accurate than Gemini, and it exposes enough remaining extraction problems to rule out an immediate wholesale replacement. Keep the current production models while preparing a controlled comparison, prioritizing screening and review extraction.

## Current models and requirements

The active routing table contains 23,819 distinct papers and records `gemini-3-flash-preview` throughout. The batch queue also explicitly selects that model. Primary, review and meta-analysis extraction use Gemini 3 Flash Preview. The `.env` screening fallback still names `gemini-2.5-flash`; treating that fallback as the production baseline would misdescribe the current system. The intended OpenAI candidate is **GPT-6 Luna**, model ID `gpt-6-luna`.

The project needs recall-oriented binary screening, evidence-domain and report-type routing, source-bound extraction, faithful numbers and uncertainty, and separation of primary findings from review conclusions. Reviews must preserve the paper's organizing purpose and treatment combinations. Meta-analyses must keep distinct outcomes/comparisons and their estimates separate. Abstract-only calls must not reconstruct full-text results. Structured-output validity is necessary but does not establish these qualities. These requirements come from the [screening prompt](../screening/title_abstract_screening.md) and the production extraction prompts and schemas.

Luna supports structured outputs, text and image input, Responses API and batch processing. Its documented input limit is 922,000 tokens. The frozen tasks fit: the largest observed input was 597,118 tokens. Native OpenAI strict output requires an adapter for optional fields; this pilot represented absence as null on the wire and restored omission before validation against the project schema. Existing production runners remain Gemini-specific. [OpenAI model specifications](https://developers.openai.com/api/docs/models/gpt-6-luna).

## Previous testing and what it established

| Previous test | Recorded findings | What it establishes |
| --- | --- | --- |
| May 2026 screening pilot, 28 papers: Gemini 2.5 Flash, Gemini 3.1 Flash Lite, GPT-5.4 nano | All three completed 28/28. Historical estimated standard costs were $0.0205, $0.0143 and $0.0129. Exact domain-set agreement was 71.4% for the Gemini pair and 42.9% between nano and either Gemini. | Cost, operational feasibility and disagreement; agreement is not adjudicated classification accuracy. [Stored comparison](../../data/processed/corpus/paper_domain_routing_model_comparison_pilot_summary.json). |
| Expanded screening audit, 70 papers: Gemini 3.1 Flash Lite, Gemini 3 Flash Preview, Gemini 3.5 Flash | All completed 70/70. Exact domain-set agreement ranged from 62.9% to 71.4%. The stored historical standard costs were approximately $0.040, $0.079 and $0.244. | Different models produce materially different routing and costs. The summary does not establish which decisions are correct. [Three-model audit](../../data/processed/corpus/paper_domain_routing_gemini_three_model_audit70_summary.json). |
| June 2026 routed extraction pilot | Gemini 3 Flash Preview validated 298/298 mixed primary/review/meta-analysis tasks. In a separate five-task retry experiment, 3/5 completed; retrying the two failures with thinking disabled completed 2/2. | Extraction feasibility and a small operational observation about thinking/truncation, not a controlled model-quality ranking. [298-task report](../../data/processed/extraction/route_extraction_pilot_gemini3_20260627_report.json), [retry report](../../data/processed/extraction/route_extraction_3flash_retry_thinking0_report.json). |
| July review extraction development and validation | The original 50-paper routed baseline had 13 good, 17 partial and 20 poor paper representations. Paper-centered extraction initially reached 35 good/15 partial/0 poor. Later prompts reached 42 good on the development cohort but only 33 good on the second 50. A simplified contract regressed to 26 good on that second cohort. | Prompt and architecture changes strongly affect quality and can overfit familiar papers. These are Gemini workflow experiments, not provider comparisons. [Initial redesign](review_relationships_v2_eval50_results.md), [development versus validation](review_relationships_v2_old50_prompt_final_comparison.md), [contract regression](review_relationships_v2_validation50_direct_contract_results.md). |
| July one-pass review comparison, 100 papers | One-pass extraction produced 77 good/23 partial versus 75/25 for prior two-pass versions, using 100 rather than 158 calls and 24.6% fewer tokens. The exact candidate was subsequently promoted. | A real existing efficiency improvement. It also retained the known problem of assigning too many relationships to the main graph. [One-pass assessment](review_relationships_v2_context_first_onepass_100_results.md). |
| July production review batch, 250 papers | 249/250 parsed. Direct reading of 15 papers rated 11 good, 3 partial and 1 poor; broad-topic scope leakage remained. | Larger-scale reliability and evidence that source-supported content can still be inappropriate for this graph. [Production assessment](review_relationships_v2_async250_20260712_results.md). |
| July meta-analysis pilot, 100 papers, evenly split by source depth | 100/100 parsed; 338 synthesis results. Point-estimate tracing matched 241/247 values, but only 475/599 excerpts matched contiguous source text. The converter accepted 322/338 results and held unsafe outputs. | Stronger task-specific evidence than parse rates alone. It already identified unsupported/reconstructed numbers, combined estimates, statistical-direction errors and quote problems. [Pilot assessment](meta_analysis_v2_pilot_100_assessment.md). |

The historical costs above are the amounts recorded at the time, not current price quotes. The review reports describe source-read “manual” assessments; they do not document an independently recruited human adjudication panel. No retrieved selection summary proves that Gemini is the most accurate available model. Earlier tests nevertheless provide valuable failure cases and substantial workflow evidence that should be retained.

## New tests in this round

The frozen exploratory pilot used `gpt-6-luna` with low reasoning effort:

- 100 screening records: 40 historically included, 40 historically excluded and 20 curated exclusion challenges;
- 10 primary-study tasks, one from each evidence domain;
- 10 reviews enriched for previously difficult cases;
- 10 meta-analyses, including two historical numerical regression cases.

Each extraction family contained five article-text and five abstract-only inputs. Current prompts and schemas, complete supplied evidence, selection seed, input hashes, raw outputs and usage are saved in the [evaluation folder](../../data/processed/evaluation/model_comparison_20261016/). Reference annotations were kept out of model requests. The review sample reuses previously studied papers and is not an unseen validation cohort. Screening judgments below were written after reading the supplied sources and before inspecting candidate classification outputs, with historical sampling strata visible.

| New Luna test | Completed and schema-valid | Metered token cost estimate | Median response time |
| --- | --- | --- | --- |
| Screening | 100/100 | $0.0209 | 3.8 seconds |
| Primary extraction | 10/10 | $0.0148 | 16.1 seconds |
| Review extraction | 10/10 | $0.0260 | 35.6 seconds |
| Meta-analysis extraction | 10/10 | $0.1860 | 39.6 seconds |
| Total | 130/130 | $0.2477 | — |

These are standard API token-cost estimates using returned usage, including reasoning, cache reads/writes and the long-context surcharge. They exclude any taxes or account-specific adjustments. One very long Cochrane input accounted for about $0.1544, illustrating why ordinary-paper averages should not be extrapolated to every review. Response times are one-run observations with four concurrent requests, not a controlled latency comparison.

**Comparison limitation and test incident.** The Gemini calibration attempted 130 calls. Later inspection established that 120 returned responses were lost when this evaluation harness added an integer token count to a null unused-thinking count; ten meta-analysis requests were HTTP 400 rejections of the native schema. These were instrumentation and request-format problems, not 130 model-quality failures. The logger is corrected, the failed records are isolated, and no further API calls were made after the problem was identified. Gemini spend is unknown, so the $0.2477 above is Luna's metered cost, not the total experiment bill; the intended $2 ceiling cannot be verified. The incident and original ledger are preserved in [run_incident.json](../../data/processed/evaluation/model_comparison_20261016/run_incident.json).

## What the new testing revealed

**Luna can execute the real contracts at low cost.** All 130 responses validated, including the long document. Primary and review outputs passed the current automatic semantic checks. This is new evidence about this candidate, rather than an inference from general benchmarks. It does not imply semantic correctness.

**Screening was permissive in the source-read sample.** Of 24 inspected records, 22 had a defensible input-level judgment: Luna retained all 9 relevant examples, excluded 10 of 13 out-of-scope examples, and retained 3 out-of-scope examples. Those three concerned rave-tourism sociology and two analytical detection methods. The latter expose ambiguity between the prompt's methodological `general_topic` allowance and curated exclusions. Seven of the 100 outputs also retained domain tags despite an exclusion decision, contrary to the prompt. Two inspected records were deliberately unscored: one pairs a smoking-cessation title with an unrelated psychedelic abstract, and another requires source-format evidence unavailable to the model. A non-English review is content-relevant under this prompt even though language eligibility excludes it elsewhere. These distinctions prevent stage-policy and metadata defects from being miscounted as model errors. The sample is small and convenience-selected; nine retained relevant examples do not establish corpus recall.

**Some earlier review omissions were recovered.** Luna preserved pharmacokinetic scope in the broad psilocybin review, enantiomer/metabolite differences and safer-derivative priorities in the ketamine scoping review, and publication growth/US-MAPS leadership as literature patterns in the MDMA bibliometric review. These address specific weaknesses recorded previously. Broader clinical implications remain underrepresented in the ERP review. Nine of ten review source fingerprints matched the archived task sources, but one source changed and the current prompts contain later revisions. These examples demonstrate what the current Luna workflow can capture; they cannot attribute improvement to the model alone.

**The difficult extraction failures have not disappeared.** Source checks of the five abstract-only meta-analyses found the principal reported estimates and null qualifications preserved without added numerical estimates in the inspected results. All five full-text meta-analyses triggered at least one automatic flag. One substantive error puts two psilocybin estimates under different placebo references, 0.88 and 0.31, into a single estimate field as “0.88 to 0.31.” A primary public-health output also includes a methamphetamine-only finding outside the intended evidence focus. These confirm previously known failure classes on a new provider; they are not newly discovered classes of error.

**Some QA flags need interpretation.** Fourteen meta-analysis excerpt flags include repairs of damaged PDF characters, which violate the verbatim-quote contract without necessarily inventing a result. Fifteen empty-object flags concern optional fields after the strict-schema adapter restores omissions. A supposed significance contradiction in the ayahuasca review is a false positive: the treatment effect is non-significant while heterogeneity is significant, which is logically consistent. These are newly documented reasons to separate source quality, provider adaptation and validator behavior from scientific extraction errors. [Source-check findings](../../data/processed/evaluation/model_comparison_20261016/source_check_findings.json).

## Current price comparison

USD per million text tokens, standard processing:

| Model | Input | Output including reasoning |
| --- | --- | --- |
| GPT-6 Luna, up to 272,000 input tokens | $0.10 | $0.50 |
| GPT-6 Luna, above 272,000 input tokens | $0.20 | $0.75 |
| Gemini 3 Flash Preview, current production baseline | $0.50 | $3.00 |
| Gemini 2.5 Flash, configured fallback | $0.30 | $2.50 |

For ordinary inputs, Luna's rates are five times lower for input and six times lower for output than Gemini 3 Flash Preview. Both offer batch discounts; comparing Luna batch with Gemini standard would overstate savings. Actual savings depend on tokenization, output length, reasoning and caching. The long Cochrane case narrows Luna's rate advantage and incurred a cache-write premium. [OpenAI pricing](https://developers.openai.com/api/docs/pricing), [Google pricing](https://ai.google.dev/gemini-api/docs/pricing).

For illustration, 10,000 screenings at an assumed 3,500 input and 250 output tokens each, without caching, would cost about $4.75 with Luna versus $25 with Gemini 3 Flash Preview. This is a pricing calculation with identical assumed token counts, not measured Gemini expenditure or a quality-adjusted saving. A little additional manual review can outweigh that screening saving.

## Recommended decision

Prioritize Luna as a candidate for screening and review extraction; retain Gemini in production until an interpretable comparison supports switching. This round establishes functional fit, low metered Luna cost and promising source fidelity on selected cases. It does not establish greater general capability or a quality-adjusted cost advantage over Gemini.

The next comparison should freeze identical evidence and prompt versions, validate provider adapters before spending, and use blind source-based judgments. Include independently adjudicated screening exclusions and relevant papers, all primary domains, difficult reviews and quantitative full-text cases. To support a conditional 99% screening sensitivity claim with zero observed misses, roughly 300 independently adjudicated relevant examples would be needed for a one-sided 95% binomial lower bound; this still depends on representative sampling. Keep the smaller challenge set for regression testing. For extraction, compare critical omissions, unsupported assertions, evidence-strength inflation, exact statistics and source provenance, and report cost per accepted correct output alongside token cost.

The earlier calibration spend remains partly unmetered. The subsequently authorized matched comparison uses a separate durable response ledger and is documented in the superseding report; its metered cost does not reconcile these earlier missing charges.
