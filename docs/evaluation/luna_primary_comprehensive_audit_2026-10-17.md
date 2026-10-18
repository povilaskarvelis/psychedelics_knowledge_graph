# Expanded audit of Luna primary-study extraction and normalization

17 October 2026. This supersedes the scope and conclusions of the earlier 24-paper diagnostic audit; its original evidence remains available.

**The first audit was too small to support a comprehensive assessment. This round reviews all 96 primary papers in the available Luna evaluation pool, all 208 domain tasks and all 565 extracted items, and follows every item through normalization. The main finding is that correctness depends on three separate problems: binding results to the right experiment, retaining the contrasts that qualify those results, and preserving scientific meaning during normalization. More prompt instructions alone would leave several reproducible failures untouched.**

This is a much broader diagnostic assessment, not a representative accuracy estimate for the full corpus. It provides evidence for targeted repairs and a more explicit observation contract. It does not yet justify replacing all ten domain-specific extraction modules.

## What changed in the investigation

| Assessment | Earlier audit | Expanded audit |
|---|---:|---:|
| Papers inspected against supplied source | 24 | **96**, including 72 additional papers |
| Source depth | 10 abstracts / 14 article texts | **48 abstracts / 48 article texts** |
| Routed tasks / raw items | 51 / 150 | **208 / 565** |
| Conservative count of items with incorrect/unsupported fields | 6 in 5 papers | **31 in 15 papers**; 25 additional items in 10 additional papers |
| Source-first completeness assessment | Selected diagnostic papers | Inventories recorded before output review for all 72 additional papers |
| Normalization investigation | Selected traces and known failure examples | All-item lineage, actual converter/builder/exporter contracts, field transport, admission, identity, browser/API consistency |
| Additional evaluation | Limited diagnostic checks | **20 scientific question tests**, controlled behavioral probes, saved repeats for **16 tasks across 8 papers**, source/PDF checks and existing test-suite comparison |

The 96 are **every available final baseline primary paper from the preceding Luna experiment**, not 96 papers chosen because the new review found problems. However, the original experiment pool was already selected for evaluation; including all of it does not remove that selection bias. The former holdout papers have now been inspected and cannot be described as unseen validation for subsequent fixes.

The earlier six important incorrect/unsupported items in five papers remain. The additional 72 papers contribute **25 further items in 10 papers**. The conservative combined ledger therefore contains **31 items in 15 papers with high-confidence incorrect or unsupported fields**. One is a moderate baseline-quarter error; the other 30 contain important errors. This does **not** mean the other 534 items are entirely correct: items contain many assertions, omissions are a separate axis, and some role/category interpretations remain unresolved.

## How correctness was established

The reference was the paper material actually supplied to extraction, not Gemini's decisions, previous judge scores, model agreement or the output itself. For each additional paper, the assigned reviewer first wrote a source-only inventory of central results, limiting contrasts, design, population and denominators. Only then did the reviewer open all domain outputs. Reviews check identity, quantities, population, comparator, timing, statistical attribution, causal strength, category/prose consistency and omissions across routes.

These are **model-assisted scientific judgments by Codex, with parallel reviewers using the same model**, not independent human expert annotations. I consolidated the findings conservatively, examined consequential examples across reviewers, and retained exact source passages and item identifiers so judgments can be challenged. The inventories are not uniformly atomized enough to support a defensible overall precision/recall score.

“Checked against the papers” also has a specific limit: abstract-only outputs were checked against their abstracts; article outputs against the supplied article packets. I did not pretend that missing full-text information was available to Luna. Where damaged symbols or tables could change the verdict, I inspected original PDF page images. Four additional papers received targeted visual checks, supplementing the two in the first audit. These were specific table/unit checks, not a claim that every page of all 96 original publications was visually reviewed.

The final [validation record](../../data/processed/evaluation/primary_comprehensive_audit_20261017/review_validation.md) confirms all 96 papers, all 565 items exactly once, all 208 task outcomes, all 96 source hashes, and literal matches for 1,354 quoted-evidence occurrences (697 unique paper/quote pairs). This verifies coverage and transcription, not interpretation. The [casebook](../../data/processed/evaluation/primary_comprehensive_audit_20261017/casebook.md) contains the paper-level evidence; the [conservative adjudication ledger](../../data/processed/evaluation/primary_comprehensive_audit_20261017/adjudication.json) defines what is and is not counted. Original reviews remain intact; this ledger and the later PDF adjudication resolve their uncertainties.

Source depth matters: 48 abstract papers contribute 166 items, including five flagged items in four papers; 48 article-text papers contribute 399 items, including 26 flagged items in 11 papers. These differing selected papers and extraction opportunities do not establish that full text causes more errors.

## Ranked extraction failures

Ranking reflects scientific consequence and recurrence, rather than summing incomparable field, item and paper counts. Counts describe this evaluation pool only.

| Priority | Recurring failure | Evidence in the reviewed pool | Why it matters |
|---|---|---|---|
| 1 | Correct-looking facts attached to the wrong outcome, experiment, cohort or time | **21 flagged items across 9 papers** in the conservative ledger | A plausible number is still wrong if it belongs to another table column, arm, assay or endpoint. |
| 1 | Missing principal findings or contrasts that limit an apparently positive result | **14 papers** on the curated priority omission list; additional secondary omissions in the casebook | A set of individually accurate items can still give a distorted account of a paper. This is not an atomic recall denominator. |
| 2 | Incorrect population/system/construct labels despite usable narrative | **4 flagged items across 4 papers** | Structured graph filters can contradict the source even when a reader could recover the truth from prose. |
| 2 | Uncertain source text reconstructed too confidently | **4 wrong numerical uncertainty fields in one paper**, confirmed visually | Source conversion and model reconstruction need separate responsibility and review states. |
| 2 | Domain routing misses an entire relevant result family | **4 concrete papers** with missing routes | Better instructions inside an existing domain call cannot extract a domain that never receives a call. |
| 3 | Over-specific design or underdefined scientific roles | **2 unsupported randomized-design fields in one paper**; broader role concerns kept separate | The system needs to distinguish measured outcomes, predictors, assay readouts, contextual exposures and eligibility policies. |

### Concrete examples newly established

| Paper | Source evidence | What the baseline extraction did | Judgment |
|---|---|---|---|
| **P29 — Ayahuasca context survey**, DOI 10.3389/fphar.2021.623979 | Traditional practices: integration difficulties **B=.03, p=.236**; spiritual significance **B=.04, p=.008** | One domain claimed integration p=.000; another assigned the spiritual-significance coefficient and p-value to integration. Yoga/tai-chi was also misbound. | Three clear erroneous items; null or unrelated associations become apparent adverse-context findings. |
| **P32 — Ketamine/psilocybin immediate-early-gene mapping**, DOI 10.1021/acschemneuro.2c00637 | **Four animals per treatment per imaging experiment**; pooled across methods, four male and four female per drug | All eight brain items report four male plus four female per treatment in each experiment. | Repeated denominator error. Counted as eight affected items, but one underlying paper-level error pattern. Another domain got the sample description right. |
| **P49 — Ketamine and macrophages**, DOI 10.1016/j.ebiom.2019.10.063 | Functional response to LPS includes reduced CD80/HLA-DR and TNF, with distinct IL6/IL10 results | Ten molecular items cover phenotype markers but omit the central functional inflammatory-response experiment. | A substantial completeness failure that output length and schema validity would miss. |
| **P89 — Spine-head JNK**, DOI 10.1523/eneuro.0303-19.2019 | Ketamine pretreatment protects; ketamine given two hours after corticosterone **does not rescue** at the measured time, whereas JNK inhibition does | Retains pretreatment protection and omits the delayed-treatment failure. Also borrows sample counts from other experimental panels. | Missing prevention-versus-rescue distinction, plus two unsupported denominator assignments. |
| **P94 — Survey of people who use methamphetamine**, DOI 10.1016/j.drugalcdep.2025.112699 | Planning/challengingness associations concern mood and substance use; social-functioning improvement is separately descriptive | Applies those predictors to social functioning. | Unsupported transfer of an association between outcomes. |

Other priority omissions include death-anxiety null results (P50), Nrf2-knockdown reversal (P52), market price/purity changes (P55), genotype-selective endocrine results (P64), regional/time specificity (P71), and a second corrected predictive brain cluster (P74). Routing gaps involve behavior in P48, safety in P50 and P64, and PK in P52. The computational result in P73 and analytical-method findings in P93 expose additional scope/coverage questions rather than straightforward failures to obey existing prompts.

There are also strong positive controls: P27 preserves tissue-specific dose responses and nulls; P42 separates learning, retention and swimming speed; P53 retains sex/time/cytokine contrasts; P61 preserves parent/metabolite PK distinctions; P67 correctly distinguishes higher-dose benefit, lower-dose null and later loss of benefit. P81’s missing pulmonary-trauma context remains an important concern, but I excluded its event-level severity attribution from the strict error count: describing case-level intubation under an agitation item is not an explicit statement that agitation caused intubation. P60’s counted category defect is specifically brain tissue classified as a cell model; “in vitro” alone is sometimes used broadly for slice experiments. Appropriate empty outputs were also retained, including a formulation-only paper and tasks without direct target evidence. The evidence does not support indiscriminately making extraction longer.

## Source quality is a separate failure layer

Original-PDF checks materially changed several judgments:

- **P73:** four Ki uncertainty fields were reconstructed incorrectly from concatenated table text: **1040±618 instead of 1040±188; 847±679 instead of 847±79; 124±69 instead of 124±9; 1872±6345 instead of 1872±345 nM**. Central values were correct. Visual inspection confirmed three suspected errors and found a fourth. The apparently conflicting prose unit is actually µM in the PDF; the extraction's restored µM value was correct.
- **P49:** the PDF reports ketamine **0.1, 1 and 10 µM**. The supplied text and two molecular outputs say **mM**, a 1,000-fold discrepancy. Luna included an encoding warning. This is faithful copying of damaged input, not invented drug concentration, but it still yields scientifically wrong values.
- **P89:** missing µ symbols were restored correctly to ketamine10µM and NMDA20µM. The initial source-limited uncertainty is resolved in favor of these values.
- **P48:** the PDF genuinely specifies a **1mM local puff**. A global mM→µM “correction” would introduce an error.

The first audit had already confirmed LSD µg→mg and MDMA µM→mM source corruption in P19/P23. The new examples show both incorrect and correct reconstruction, so neither “trust every extracted unit” nor “automatically repair suspicious units” is defensible. Original images, supplied text and adjudications are linked in [PDF adjudication](../../data/processed/evaluation/primary_comprehensive_audit_20261017/pdf_adjudication.json).

## What the normalization architecture investigation found

I examined the actual ten extraction contracts, converter aliases, compound/entity registries, regex fallbacks, scientific-category rules, admission gates, proposition/conflict identities, browser whitelist, graph presets and query-API projection. This was not inferred from a few final graph screenshots. The current converter reproduces **all 564 saved converted rows exactly**; one of 565 raw items has no conversion/audit trace. The builder matches the saved experiment version. New tests use current code and dictionaries without publishing anything.

Raw items have different legitimate fates: **364 have main-graph findings, 77 detail-only findings, 123 audit-only outcomes and one no converted row**. Splitting yields 467 finding rows. These are representation counts, not accuracy scores: intentional scope exclusions and specificity requirements must not be called errors wholesale.

| Ranked normalization problem | Measured evidence | Practical effect |
|---|---|---|
| Scientific category overridden by incidental prose | P68 EEG finding becomes **Receptor regulation & trafficking** because a null comparison mentions power spectral **density**; source and raw output are correct | Normalization introduces the scientific error. Removing that phrase avoids it; even adding “No receptor assay was performed” can trigger it. |
| Explicit information fails to reach canonical/public fields | **125/125** represented molecular items with meaningful dose lose it from the canonical/public dose field; **34/34** meaningful intervention phases likewise miss canonical/public timing | These facts were already extracted. Some remain in prose/internal JSON. More prompt instructions cannot fix a missing field alias. |
| Observation identity omits distinguishing context | **Four duplicate-identity groups, nine rows, two papers**; tissue/dose and PK matrix/time probes fail | Serum versus urine, or distinct stereoisomer experiments, can share identity. Both rows currently survive; no actual direction-conflict quarantine was observed. |
| Explicit experimental system loses precedence | **Four P66 ex-vivo assays become in-vivo**; P41 simulated human receptor findings acquire system=clinical | Species or protein origin is being mistaken for experimental setting. P41 remains detail-only, so this is not demonstrated false clinical evidence entering the main graph. |
| Entity splitting and matching alter meaning | P69 unit punctuation produces an event fragment “L at peak on ICU day 2)”; P86 plural seizures lose a projection; expanded single-receptor names can be rejected as combinations | Scientific punctuation and harmless naming variants should not change categories or erase recognized entities. Full prose may still survive. |
| Browser and query API disagree about subjects | **25 unique paper–subject–object links** absent from API projection after deduplication, involving 18 findings across six papers | Browser expands plural subjects; API uses the first singular subject. This is a retrieval discrepancy, not proof of a causal treatment effect. |
| Clean marker identity is subordinated to descriptive text | **106/128 represented molecular items** choose a differing legacy readout string over the clean marker | Direction-bearing sentences can become node names. This is a precedence count, not 106 incorrect scientific claims. |

The API deliberately excludes effect estimates and detailed finding provenance; that is an interface choice, not an accidental omission. Similarly, 31 retained findings lack a matching current graph preset, mostly PK. Whether to display them is a product/category decision. The architecture review separates these choices from bugs and records corrected false alarms from isolated-helper tests.

Full stage-by-stage evidence and code locations: [normalization architecture](../../data/processed/evaluation/primary_comprehensive_audit_20261017/architecture.md). Every item's fate and field changes: [normalization census](../../data/processed/evaluation/primary_comprehensive_audit_20261017/normalization_census.json).

## Other ways quality was evaluated

### Scientific question answerability

I used **20 source-answerable questions spanning all ten current graph views**, then checked raw extraction and public finding details, including other routes before declaring an answer absent. Questions test distinctions such as pretreatment/comparator, species, tissue/dose response, study design and statistical baseline. They were selected diagnostically, not randomly, and the public projection was reconstructed locally with current code, not measured against a deployed release.

| Answer quality | Raw extraction | Public finding details |
|---|---:|---:|
| Complete | **15** | **11** |
| Partial | 2 | 3 |
| Conflicting | 1 | 1 |
| Absent | 1 | 4 |
| Incorrect | 1 | 1 |

Four questions answerable from raw extraction deteriorated downstream: a dose-specific depression contrast, circuit rescue, opposed regional glucose effects, and single-receptor findings. One loss follows an intentional broad-condition gate; others expose mapping/identity limitations. Conversely, a rejected treatment-context item did not destroy the basic design answer because another domain preserved it. This cross-route check prevented overcounting losses.

**Complete here includes information recoverable from prose. It does not mean structured filters can answer the question.** For example, P27's tissue/dose contrast remains readable while canonical dose and dedicated tissue fields are missing. See [all 20 questions and judgments](../../data/processed/evaluation/primary_comprehensive_audit_20261017/question_audit.md).

### Repeatability, behavioral tests and negative controls

Saved repeats allow a paired check of **16 identical requests across eight papers**, verified by request hashes. Both runs produce **43 items**, yet six tasks change item counts. P29 acquires additional statistic/direction errors; some findings improve or become separately retrievable, while others disappear. Both runs share a false traditional-practice/integration association and omit the same embryonic harms in P09. Repetition and agreement therefore cannot establish truth. See [paired review](../../data/processed/evaluation/primary_comprehensive_audit_20261017/reviews/repeatability_review.md).

Controlled normalization tests expose **13 behavioral failure families**, including name expansion, explicit exclusion, field transport, marker precedence, observation identity, system precedence, category boundaries, unit punctuation and cross-surface consistency. Expectations were recorded before each probe set. Follow-up probes of newly discovered mechanisms are diagnostic, not unseen validation.

At the same time, **151 existing tests and 291 subtests pass**, as do 2,897 dictionary self-consistency checks and idempotence for all 564 converted rows. These are useful compatibility checks, but they can preserve a consistently wrong interpretation. I corrected several initial test false alarms after tracing the full pipeline; isolated helpers are not always the final behavior. See [probe adjudication](../../data/processed/evaluation/primary_comprehensive_audit_20261017/probe_adjudication.json).

## What this implies for the extraction contract and processing strategy

The graph's categories remain useful targets, but a category alone is insufficient. For each observation, downstream processing needs explicit links among **exposure and its role; comparison/arm; measured outcome or entity; population and experimental system; specimen/location; dose and time; estimate and its denominator; and source locator/uncertainty**. These should not have to be reconstructed repeatedly from one sentence.

Some of that information already exists and is simply ignored downstream. Other distinctions remain implicit: measured event versus eligibility rule; administered drug versus rescue medication; predictor versus outcome; receptor binding versus tracer binding; prevention versus rescue; biological metabolism versus sample preparation. Those are concrete requirements exposed by the audit, not a finished replacement schema.

I recommend this order of work:

1. **Repair deterministic normalization defects independently.** Field transport, explicit-category precedence, identity context, splitting accountability and browser/API consistency have reproducible expected behaviors. They can be verified on saved extractions without paying for or confounding a new model run.
2. **Address source damage and uncertain numerical attribution.** Detect suspicious/conflicting values, preserve locators, and give unresolved values an explicit review state. Do not silently invent table repairs or replace units globally.
3. **Improve experiment/contrast binding and completeness in extraction.** The recurring problem is not lack of prose; it is linking the right number and qualifier to the right observation, and retaining main nulls/limiting contrasts. Test these separately from routing coverage and role/schema changes.
4. **Evaluate a shared observation layer before discarding domain modules.** Shared paper/experiment context plus domain-specific measurements is a plausible direction. This audit establishes requirements, not that this design outperforms the current one. A structural redesign becomes justified if important observations still cannot be represented faithfully after targeted repairs.

The 208 domain calls repeat **2.19 times as much source text as the unique paper sources**. This identifies an efficiency question for shared context or caching, not a measured 2.19-fold cost saving. Output/reasoning cost, caching and any quality loss from combining calls have not been measured here.

## What is new, and what remains unproven

This round adds 72 source reviews, 415 item reviews, 25 high-confidence erroneous/unsupported items, new major omissions, original-PDF adjudication, an all-item normalization census, new category/system/splitting failures, observation-identity collisions, browser/API parity measurement, scientific question testing and repeatability analysis. It also establishes where accurate information survives in prose despite broken structured fields, avoiding an exaggerated claim of total information loss.

The evidence supports **targeted normalization repairs plus stronger observation/contrast handling**, rather than another broad prompt polish. It does not yet establish a replacement prompt's benefit, justify one universal extraction call, or estimate the entire corpus's error rate.

Before full extraction, fixes should face the known regression cases **and a fresh, untouched, stratified sample** covering abstract/article depth, all domains, table-heavy multi-arm work, preclinical systems, observational/context/safety roles and ordinary uncomplicated papers. A probability-sampled component is needed for population estimates; a separate challenge component should stress known failure modes. Have an independent human scientific reviewer adjudicate a subset and disagreements. Freeze the reference inventories before comparing variants. Report factual support, coverage, binding, uncertainty handling, downstream answerability and cost separately.

**No new Luna/Gemini API calls, production extraction/prompt/schema changes, or full extraction rerun were made during this audit.** The work reused saved Luna outputs and current normalization code.
