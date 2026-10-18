# Gemini and GPT-6 Luna screening and extraction comparison

**Luna was substantially cheaper and my complete review of screening disagreements favors it more often overall. Gemini excludes fewer papers that I judge relevant.** These are single-AI-assessor content judgments; neither the screening nor extraction comparisons have independent human ground truth.

A subsequent [Luna-only screening-prompt comparison](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/docs/evaluation/luna_screening_prompt_comparison_2026-10-16.md), updated 17 October, now compares five prompts across 755 paper inputs. V5 scores **115/133, 93/110, 183/199 and 181/199** on the two challenge sets and two random samples respectively. Against V4 it improves three rows and declines on the first challenge set. On the newest random sample, missed relevant papers stay **12 → 12**, while unnecessary inclusions fall **10 → 6**, raising agreement with the frozen source judgments from **88.9% to 91.0%**. It recovers all three clear misses targeted by the final clarification. The latest round made **1,655 Luna calls**, zero Gemini calls, and cost approximately **$0.35**. These remain single-assistant source judgments, not independent human gold; this round adds no extraction result or production change.

**Original model comparison after reviewing every disagreement**

| My assessment of wrong decisions within disagreements | Original Luna | Original Gemini | Clarified Luna | Clarified Gemini |
|---|---:|---:|---:|---:|
| Relevant paper excluded | 14 | 1 | 3 | 0 |
| Out-of-scope paper included | 2 | 33 | 2 | 17 |
| **Total wrong decisions** | **16** | **34** | **5** | **17** |

I preferred **Luna on 34/50 original-prompt disagreements (68%) and 17/22 clarified-prompt disagreements (77%)**. Across 58 unique disputed papers, removing the 14 repeated across prompt versions, I preferred Luna on **40** and Gemini on **18**. Restricting the comparison to my high-confidence judgments still favors Luna **26–7** and **12–2**, respectively. The remaining 19 unique papers are explicit scope-boundary judgments; they are included in the headline counts with confidence recorded.

This review adds 31 previously unlabeled disputed papers and reverses my earlier inclusion of the Amsterdam dance-event paper. The [complete case-by-case assessment](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/docs/evaluation/screening_disagreements_adjudication_2026-10-16.md) records every decision and rationale. The percentages measure which model I favor among disagreements, not corpus-wide accuracy or recall. Agreements were not re-audited here; no new provider calls were made. Original reference labels and outputs are preserved.

**How correctness was assessed — clarification added after review**

| Measure | Reference or measurement | What it establishes |
|---|---|---|
| Screening relevance | This Codex assistant read source material and assigned reference labels: 80 new judgments plus 24 earlier assistant judgments, made before inspecting the corresponding new paired predictions. Historical Gemini decisions were used to select sampling strata, not as correctness labels. Ten ambiguous or defective cases were excluded, leaving 94 scored records. | Agreement with the assistant's interpretation of eligibility. This is not independently validated recall; sampling from Gemini decisions also limits representativeness. |
| Extraction adequacy | This same assistant compared A/B outputs with supplied source material and earlier source-derived review references. Provider names were concealed, but prior exposure and recognizable styles made blinding imperfect. No independent human assessment was performed, and earlier files named “manual gold” do not establish human provenance. | Exploratory assessor ratings. Source support, numerical attribution and omissions can be inspected case by case, but the pass/fail thresholds and scope judgments are not independent ground truth. |
| Cost, latency and schema validity | Saved provider usage, request timings and programmatic validation against the specified schema. | Direct operational measurements for these inputs and settings. Cost is calculated from metered tokens and the stated rates, rather than reconciled invoices. |

**The content-score differences below must not be presented as established accuracy gains or expected percentage-point improvements.** In particular, the four remaining Luna screening exclusions after clarification concern debatable scope/centrality boundaries. Calling them definite errors requires a project eligibility decision and independent adjudication. A frozen reference set reviewed by domain-qualified humans, with disagreements resolved and outputs assessed without provider identities, is needed to estimate semantic performance reliably. No additional model calls were made for this clarification; the original outputs and judgments are preserved.

Completed 360 matched tasks: 240 screenings and 40 each of primary, review and meta-analysis extraction. Each model received the same frozen paper, instructions and scientific schema. Each extraction family contained 20 full texts and 20 abstracts; primary extraction covered all ten domains. A separate scope-clarification experiment repeated 104 screenings on both models. **This round cost $2.92**, including a superseded preflight response, with 928 paired responses saved and no missing new usage records.

**Cost comparison**

| Task | Luna per 1,000 tasks | Gemini per 1,000 tasks | Gemini cost divided by Luna cost | Cost reduction |
|---|---:|---:|---:|---:|
| Screening | $0.21 | $2.23 | **10.9×** | 91% |
| Primary extraction | $1.24 | $6.17 | **5.0×** | 80% |
| Review extraction | $2.69 | $11.87 | **4.4×** | 77% |
| Meta-analysis extraction | $7.52 | $23.80 | **3.2×** | 68% |

These scale the measured standard API costs of the original matched sample, including reasoning, cache reads, cache writes and long-context pricing. They assume the same task mix and cache behavior; a primary task extracts one domain, so one paper can require several tasks. At standard uncached input rates without cache reads/writes, the observed screening token counts imply **4.8×** savings; the larger measured 10.9× advantage includes caching.

Published standard rates per million ordinary-context tokens are **$0.10 input / $0.50 output for Luna**, versus **$0.50 / $3.00 for Gemini 3 Flash Preview**: five times lower input rates and six times lower output rates. Both offer batch discounts. Luna charges a cache-write premium and higher rates above 272,000 input tokens. [OpenAI pricing](https://developers.openai.com/api/docs/pricing), [Google pricing](https://ai.google.dev/gemini-api/docs/pricing).

The unusually long Cochrane full text cost $0.158 with Luna and $0.348 with Gemini. Excluding it, the remaining 39 meta-analysis tasks cost $0.143 versus $0.604: **4.2×** lower with Luna.

**Earlier screening audit retained for provenance**

The earlier audit labeled 42 records relevant and 52 irrelevant. Eight ambiguous chemistry/assay cases and two source-identity cases were reported separately. The complete disagreement review above supersedes the use of those earlier labels for the disputed cases; the historical figures below have not been selectively recomputed. “Recall” below is relative to the earlier assistant labels, not independent human ground truth.

| Matched prompt | Luna relevant papers retained | Gemini relevant papers retained | Luna irrelevant papers included | Gemini irrelevant papers included |
|---|---:|---:|---:|---:|
| Current production wording | **32/42 — 76.2% recall** | **41/42 — 97.6% recall** | 2/52 | 12/52 |
| Same scope clarification added to both | **38/42 — 90.5% recall** | **42/42 — 100% recall** | 4/52 | 16/52 |

The original wording let Luna interpret MDMA toxicology and ketamine-analogue surveillance as outside “psychedelic-related” evidence. Explicitly including entactogens, dissociatives and their preclinical/nonmedical evidence increased Luna's agreement with the assistant's positive labels by six records overall, while increasing inclusions among assistant-labeled negatives. Four reference inclusions were still excluded, involving polysubstance findings and policy/legal or event-level public-health evidence. **These disagreements raise a screening concern, but do not establish Luna's true recall or prove that its exclusions are wrong.**

A replay in which Gemini reassessed every Luna exclusion retained all 42 assistant-labeled relevant records, but included 18 assistant-labeled irrelevant ones. Its estimated cost was 33% below Gemini alone on those 104 records, or 25% lower using standard uncached input rates. This is a projection from saved outputs; conditional deployment and its cache behavior were not tested, and the replay does not independently validate those relevance labels.

**Follow-up reading of screening disagreements**

The user requested concrete adjudications of selected disagreements. I re-read the exact title/abstract inputs and both models' saved decisions against the frozen screening instructions, and checked the published abstracts. The judgments below are my reasoned assessment. These are selected cases, not a new representative validation sample. Decisions refer to the clarified prompt except for the explicitly identified original-prompt MDMA case.

| Paper | Luna | Gemini | Follow-up judgment and reason |
|---|---|---|---|
| [Amphetamine-induced acute liver failure](https://pubmed.ncbi.nlm.nih.gov/34434429/) | Exclude | Include | **Luna is more correct; high confidence.** The reported case follows amphetamine ingestion. MDMA appears in introductory context, with no reported MDMA exposure in the case abstract. The prompt explicitly excludes background mentions; it does not put all amphetamines in scope. |
| [Emergency-service demand at the Amsterdam Dance Event](https://pubmed.ncbi.nlm.nih.gov/36312590/) | Exclude | Include | **I favor Luna under the written centrality rule; moderate confidence. This reverses my original reference inclusion.** MDMA appears in the background, while the supplied results concern recreational-drug complaints overall and provide no MDMA-specific result. A full-text review might find eligible substance-specific results, but the models did not receive that text. The recall-preserving ambiguity instruction makes inclusion defensible, rather than a clear error. |
| [Multiple DSM-5 substance use disorders in US adults](https://pmc.ncbi.nlm.nih.gov/articles/PMC5898189/) | Exclude | Include | **I favor Gemini; moderate-to-high confidence.** The abstract reports a specific hallucinogen-use-disorder co-occurrence estimate, not just a mention in a drug list. That is original, relevant epidemiological evidence despite the broader question. The prompt's centrality wording should distinguish a substantive measured outcome from a peripheral mention. |
| [Swiss youth substance-use trajectories by sexual attraction](https://pmc.ncbi.nlm.nih.gov/articles/PMC12853546/) | Exclude | Include | **I favor Gemini; moderate-to-high confidence.** The results explicitly compare past-year ecstasy and hallucinogen use between groups at ages 20 and 24. These substances are measured outcomes. Luna's rationale dismisses actual results as merely list items. The indexed record used the repository DOI 10.5167/uzh-284462; the published article has DOI 10.1136/bmjph-2025-003583. |
| [Psilocybin treatment and medical malpractice risk](https://pmc.ncbi.nlm.nih.gov/articles/PMC12358238/) | Exclude | Include | **I lean toward Gemini for this broad knowledge graph; moderate confidence.** Psilocybin policy, access, training and implementation are the central topic, and policy and implementation are explicitly in the domain definitions. Luna says malpractice law is outside the domains, which overlooks that connection. However, the non-primary-publication rule can support exclusion if this legal analysis is treated as commentary without qualifying synthesis; the present instructions leave that boundary unresolved. |
| [MDMA-mediated mitochondrial dysfunction in rat liver](https://pmc.ncbi.nlm.nih.gov/articles/PMC2590641/) — original prompt | Exclude | Include | **Gemini is correct under the intended project scope; high confidence.** This directly studies MDMA toxicology and molecular effects. Luna's original rationale excluded it as recreational-stimulant toxicology. After the shared scope clarification, both models included it. |

The distinction exposed by these examples is **a substantive substance-specific result versus a background mention**, alongside eligibility of substantive policy analysis. The Amsterdam reconsideration is preserved here without overwriting the frozen reference file or selectively recalculating the original aggregate scores. It should not be described as an established Luna false negative.

**Extraction ratings by the assistant**

“Adequate content” requires the main eligible findings and qualifications, with no material unsupported claim, wrong numerical attribution or unsafe combination of distinct estimates. Schema validity is measured separately.

| Source-audited content | Luna rated adequate | Gemini rated adequate | Difference in assessor ratings |
|---|---:|---:|---:|
| Primary extraction | **6/8 — 75%** | **2/8 — 25%** | +50 percentage points |
| Review extraction | **19/20 — 95%** | **7/20 — 35%** | +60 points |
| Meta-analysis extraction | **16/20 — 80%** | **8/20 — 40%** | +40 points |

These are exploratory judgments by one Codex source assessor, with provider labels concealed during assessment but imperfect blinding from prior exposure and recognizable styles. The samples include earlier challenge cases; two upstream primary scope/route problems were excluded from the eight eligible primary cases. **These differences describe this audit, not predicted corpus-wide accuracy. Each model ran once per case; repeatability and independent human validation remain unmeasured.**

| Requirement | Observations from the assistant's audit | Remaining limitation |
|---|---|---|
| Primary findings | Better endpoint denominators and separation of measured effects from inferred mechanisms or treatment components. | Only eight eligible papers received detailed source assessment. Luna still omitted a cognitive-rescue finding and extracted an unrelated methamphetamine result. |
| Review coverage | The assessor rated Luna more complete on PK/PD, human/animal, safety, future-research and sustained-effect coverage, with clearer attribution of proposals and preliminary findings. This supports prioritizing independent review of Luna for this task. | Both models still underrepresented broader implications in the ERP review; adequacy thresholds require independent validation. |
| Quantitative synthesis | More cautious handling of unavailable numbers, ambiguous signs and source inconsistencies. Gemini returned pooled/CI values unsupported by the supplied text in the mindfulness and psychotherapy-protocol papers; Luna left them unavailable. | The supplied text may omit numerical figure content. Luna still packed separate comparisons into numeric fields in several papers. Source-present numbers alone do not establish correct attribution. |
| Machine-readable output | Screening, primary and review schemas passed for every task in both arms. Meta-analysis schemas passed **39/40 Luna versus 35/40 Gemini**. | Both used an invalid synthesis-type label once. Gemini also omitted required fields and returned one object wrapped in an array. |

For meta-analyses, normalized contiguous source matching found **456/489 supporting snippets with Luna (93.3%) versus 181/242 with Gemini (74.8%)**. This checks provenance rather than completeness or claim truth; PDF encoding also causes mismatches.

Median API times were **9.8 versus 5.6 seconds** for primary extraction, **28.0 versus 10.6** for reviews, and **32.5 versus 10.7** for meta-analyses. Luna's cost advantage came with **1.8–3.0× longer extraction latency** in this configuration. Original-prompt screening medians were 3.3 versus 4.3 seconds; the clarification experiment reversed that ordering.

**What this adds to previous testing**

| Earlier evidence | What this round newly establishes |
|---|---|
| May screening comparisons on 28 and 70 papers measured costs and model agreement. | Matched provider costs plus disagreements against assistant source-read labels; true recall and false inclusions still require independent adjudication. |
| June extraction pilot validated 298 Gemini outputs. | Direct model comparison across ten primary domains and three extraction families, with source quality separated from formatting. |
| July review experiments reached 77/100 good representations for the Gemini one-pass workflow versus 75/100 previously. | Current identical inputs/prompts favor Luna in the assistant's 20-paper ratings; neither those ratings nor earlier “manual” file names establish independent human ground truth. The earlier result compared workflows and used different cohorts/versions. |
| July meta-analysis pilot traced 241/247 point estimates and 475/599 supporting snippets to source text. | Same-paper provider comparison exposes unsupported Gemini numbers and persistent numeric-structuring problems in both models. |
| The initial Luna-only pilot completed 130 cases. | A reliable fresh Gemini baseline, larger sample, measured latency, and the screening scope problem. Reviewing the earlier incident also corrected its description: **120 Gemini responses were lost by logging; ten meta-analysis requests were HTTP 400 rejections**, rather than 130 returned responses. |

**Implementation and reproducibility**

The reusable [evaluation runner](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/pipeline/validate/model_head_to_head.py) saves and syncs raw responses before reading text or usage, treats optional null token counts as zero, stops on unknown billing, reserves concurrent spending and recovers locally without repeating paid requests. **44 regression checks pass.** All 928 paired responses were successfully reprocessed without API calls.

Gemini used `gemini-3-flash-preview`, temperature 0 and thinking budget 0; Luna used `gpt-6-luna` with low reasoning. Provider-specific strict-schema translation was normalized before canonical validation. Meta-analyses used the working production approach on both models: identical schema instructions inside the prompt and JSON output, avoiding Gemini’s rejected native-schema request. No production model, screening prompt or graph data was changed.

Historical test sources are linked in the [earlier assessment](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/docs/evaluation/model_selection_2026-10-16.md). The [saved evidence directory](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/evaluation/model_head_to_head_20261016) contains frozen inputs, protocols, raw responses, usage, source judgments, per-case assessments, cost calculations and integrity hashes. The $2.92 covers this new round; the earlier lost Gemini usage remains unreconciled.
