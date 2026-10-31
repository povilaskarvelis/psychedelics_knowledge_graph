# Framing, presentation and scientific rigor: assessment, 31 October 2026

## Basis

I read the public pages (home, About, Methods, API) in the repository and on the
live site, the README, `CITATION.cff`, the pipeline README, the evidence policy,
the terminology guide, the agent guide, the draft field protocol
(`protocols/SPEC.md`), the screening and extraction evaluation reports dated
16–25 October 2026, and the assessment of 5 September 2026. I inspected the live
interface (Explore, Analyze and finding cards) and queried the tables behind the
active release (`living_update_20260917_author_identity_reviewed`) and the
canonical candidate table. No other file was changed.

The 5 September assessment covered extraction accuracy, normalization, the
report–study distinction, selection mechanisms and architecture. This assessment
concerns how the project describes itself, which claims its methods support, and
how to state its value now and as its accuracy improves. Earlier findings are
repeated only where they affect those questions or are still visible on the live
site.

## Summary

1. **What the graph is.** It carries out three stages of a systematic review
   (searching, screening and data extraction) for the whole field, and repeats
   them at each update. It does not carry out risk-of-bias assessment, weighting
   and pooling of results, or certainty assessment, which are the stages that
   produce conclusions about effects. The established term for this kind of
   product is an **evidence map**. "Living evidence map" is accurate. "Evidence
   synthesis" is not accurate as a description of what the graph does.
2. **"Summarizing" is also imprecise.** The graph writes a one-sentence summary
   of each extracted finding, but it does not summarize what the literature on a
   topic shows. At the level of a topic it counts papers by their
   characteristics.
3. **The value can be stated without the word synthesis.** The graph does the
   search, screening and extraction work that every review in the field
   repeats; it keeps that work current; it lists existing reviews and
   meta-analyses separately; and, with one display that the existing data
   already supports, it can show how many primary studies have been published
   since the latest meta-analysis on each topic. As its accuracy is validated
   against human reviewers, the same records can support reviewer-verified data
   extraction and regularly updated meta-analyses for defined questions.
4. **The public copy is less precise than the internal documents.** The agent
   guide states: "Relationships are literature-retrieval links, not proof of
   benefit, harm, causation, or effectiveness. Counts refer to reports, not
   independent studies." The evaluation reports are equally careful. The About
   page, in contrast, says the graph synthesizes knowledge, presents reviews and
   meta-analyses as a deficient predecessor, and uses promotional phrases ("a
   new way", "the emerging era of agentic science").
5. **Five statements on the site are inaccurate now.** (a) The Methods page names
   GPT-6 Luna for screening and extraction and does not say which models
   produced the published release; according to the routing table and the
   extraction runners, that release was built with Gemini 3 Flash Preview. (b) "Checked … for support in the source publication" describes
   automated schema and identity checks. (c) Counts labelled "studies" are
   counts of papers. (d) The "Open access" figure reflects whether the pipeline
   used full text. (e) Two dose errors found on 5 September are still displayed
   ("10g LSD"; dried-mushroom weights shown as grams of psilocybin).
6. **Several displays can be read as synthesis.** One arrow symbol connects
   compounds to treatment outcomes, adverse outcomes and correlates alike; line
   width encodes the number of papers without a legend; empty cells are called
   gaps; the "Synthesis coverage" chart counts narrative reviews as syntheses;
   finding cards show the parent trial's design ("RCT") for secondary
   correlational analyses.
7. **Better models will not fix the design limits.** The reference labels in all
   current audits were produced with model assistance; the search uses two
   databases and excludes non-English papers and records without a 50-word
   abstract; counts are of papers, not studies; there is no appraisal stage;
   there is no release-time retraction check; about half of represented papers
   were extracted from abstracts only. These are design decisions or limits of
   source access, and they determine which claims the graph can make.
8. **Most valuable next steps.** Version the Methods page by release; apply the
   wording changes in section 3; build a small human-adjudicated benchmark;
   measure relative recall against the included-study lists of published
   meta-analyses; publish a validation statement with each release; add a
   display of primary papers published since the latest meta-analysis.

## 1. What the graph does, in the terms of evidence synthesis

### 1.1 Stages

| Stage | In a systematic review | In the graph now | Status |
|---|---|---|---|
| Question and protocol | A defined question (PICO); protocol registered in advance | A field-level scope; versioned search strategy and screening instructions; no registered protocol | Partial |
| Search | Several bibliographic databases, trial registries and grey literature, usually designed with an information specialist | PubMed and OpenAlex; queries logged and reproducible; repeated at each update | Done for the field, with two databases |
| Screening | Two reviewers working independently | Rules, then one language model; decision and reason recorded for every record | Done, automated; accuracy under measurement |
| Data extraction | One reviewer with verification, or two working independently | One language model with domain-specific schemas; source locations recorded | Done, automated; accuracy under measurement |
| Risk-of-bias assessment | A standard tool (RoB 2, ROBINS-I) applied to each study | Study design recorded; meta-analyses' own assessments retained when reported | Not done |
| Synthesis | Meta-analysis, or structured synthesis without meta-analysis (SWiM) | Papers counted by characteristics; pooled results of existing meta-analyses displayed | Not done |
| Certainty assessment | GRADE | None | Not done |
| Reporting | PRISMA 2020 | Record flow in PRISMA format; decision and reason for every record | Done, with more record-level detail than most reviews |
| Updating | For living reviews, a stated search interval | Literature updates at roughly monthly intervals; versioned, citable releases | Done; interval not stated publicly |

The graph therefore performs the stages that identify and describe the evidence,
for an entire field and at a regular interval. It does not perform the stages
that evaluate and combine it. Statements about whether an effect exists, how
large it is and how certain the evidence is come only from the last three
stages. The graph cannot support such statements, and its copy and displays
should not suggest them.

### 1.2 The appropriate category

In evidence-synthesis methods, a product that systematically identifies research
on a broad topic and describes its volume, distribution and characteristics,
without appraising or pooling results, is an **evidence map** (Miake-Lye et al.,
2016). Related forms are the systematic map in environmental science (James et
al., 2016) and the evidence and gap map (White et al., 2020). The Campbell
Collaboration and the Collaboration for Environmental Evidence treat maps as one
type of evidence-synthesis product, so the term places the project within
evidence-synthesis methods without claiming that it combines results.

The graph goes beyond a standard evidence map in one respect: it extracts
individual findings, not only study characteristics. The closest precedent for
that part is Trialstreamer, a living, automatically updated database of trial
reports with machine-extracted PICO elements and sample sizes (Marshall et al.,
2020).

Recommended description: **a living evidence map of psychedelic research, built
from findings that language models extract from each paper**, with the update
interval stated wherever "living" appears.

Terms to avoid until the corresponding methods exist:

- *systematic review*: requires appraisal and synthesis;
- *scoping review*: a review type with its own reporting guideline (PRISMA-ScR);
- *systematic map*: implies standards such as independent double screening of a
  sample of records;
- *comprehensive*: search recall has not been measured;
- *strength of evidence*, *validated*, *evidence-based conclusions*.

### 1.3 Why "summarizing" is also imprecise

The graph writes a one-sentence summary of each extracted finding (the "Finding:"
line on each card). It does not produce summaries of the literature on a topic,
such as "most trials report a reduction in symptoms". At the level of a topic it
counts papers by design, population, comparator, follow-up and similar
characteristics. The accurate verbs are *identify*, *screen*, *extract*,
*standardize*, *link* and *count*. The accurate nouns are *evidence map* for the
product, *reported findings* for the content and *data extraction* for the
process applied to each paper.

### 1.4 Vocabulary

| Use | Avoid | Reason |
|---|---|---|
| evidence map; living evidence map (with the update interval) | evidence synthesis; living synthesis | No appraisal, weighting or pooling |
| records what each paper studied and reported; reported findings | scientific knowledge (for the content); established findings | Extracted findings are statements made by papers |
| papers, or reports (in counts) | studies (in counts) | One study can produce several papers |
| relationships derived from findings; papers that report X in relation to Y | evidence-supported relationships; evidence for X | "Supported" implies an assessment |
| no papers in this release | evidence gap; understudied (unqualified) | Absence from the graph can reflect search, screening, extraction or display rules |
| automated checks for schema, source identity and corrupted characters | validated; checked against the source | Findings are not verified one by one |
| screened by a language model; accuracy measured on N records against model-assisted (or human) reference labels | manual review (for model-assisted review) | The reference standard determines what an accuracy figure means |
| language-model-assisted; AI-assisted | agentic science; a new era; a new way | Promotional |
| supports reviews; shortens the work of a review | replaces or improves on reviews | Reviews answer questions the graph cannot answer |

## 2. How to state the value

### 2.1 What is true now

1. **Breadth in one structure.** 21,735 papers across ten research areas, from
   receptor pharmacology to clinical outcomes and real-world use, are described
   with the same fields. No review covers this range, and no bibliographic
   database records these fields.
2. **Retrieval by study characteristics.** Papers can be filtered by compound,
   population or model, design, comparator type (for example inert versus active
   placebo), follow-up window, administration route and sample size. PubMed
   indexing does not record most of these. This shortens the work of assembling
   the studies relevant to a question.
3. **Record-level transparency.** The decision and reason for every screened
   record are public, and each finding links to the paper and a location in the
   text. Most published reviews report only a flow diagram and a list of studies
   excluded at the full-text stage.
4. **Separation by evidence type.** Primary studies, meta-analyses and reviews are
   kept apart, and null and mixed findings are retained. Pooled results of
   existing meta-analyses are shown where they are reported.
5. **Currency and citability.** The literature date is stated, updates follow a
   regular schedule, and each release has a DOI.
6. **Machine access.** AI agents can retrieve release-identified, source-linked
   records through the API and MCP server instead of relying on a model's
   training data.

### 2.2 The relationship to synthesis

The graph does not produce new syntheses. Its relationship to synthesis has three
parts:

1. It **records existing syntheses**: 332 meta-analyses and 586 systematic
   reviews in the current release, with pooled results, numbers of studies,
   search end dates and the authors' own certainty ratings where reported.
2. It **maps the primary studies** on each topic, with their designs,
   populations and reported results.
3. It can **show where synthesis is missing or out of date**: for each
   compound–condition pair, the end date of the most recent meta-analysis search
   and the number of primary papers published since then. The meta-analysis
   schema already stores `search_end`, so this requires a display, not new
   extraction.

The third part answers the problem stated in the film and on the About page
(reviews take months and quickly become outdated) with something the graph can
measure. It does not require claiming that the graph replaces reviews.

### 2.3 Value as accuracy improves: claim levels

Each level adds specific uses, and each use depends on a published measurement.
This gives a concrete account of future value without describing the future as
the present.

| Level | Required evidence | What can be claimed |
|---|---|---|
| 0 (now) | Documented methods; model-assisted audits | "Evidence map"; "records what papers report"; "helps locate studies"; "extracted by language models; accuracy is being measured" |
| 1 | Human-adjudicated benchmark for screening and extraction, with a fresh holdout; relative recall against the included-study lists of published reviews | "Screening recall X% (95% CI) against human reviewers"; "contains Y% of the studies included in Z recent meta-analyses"; "suitable as an additional search source for systematic reviews" |
| 2 | Study-level identities; links from reviews to their included studies; validated design and reporting fields | "N independent studies (M papers)"; "primary studies published since the latest meta-analysis"; displays stratified by design |
| 3 | Structured effect estimates with measured accuracy; a human verification step | "Reviewer-verified data extraction"; "regularly updated meta-analyses for defined questions". At this level "living synthesis" is accurate for those specific outputs. |

Screening automation is conventionally evaluated at 95% recall (Cohen et al.,
2006), which is a reasonable threshold for the level-1 claim about systematic
review use.

### 2.4 Recommended description

For the About page, a paper abstract or a grant application:

> Psychedelics Knowledge Graph is a living evidence map of psychedelic research.
> It uses language models to search, screen and extract data from the
> literature, the stages that every systematic review repeats, for the whole
> field and at each monthly update. For each included paper it records what was
> studied and what was reported, with a link to the source text. It does not
> assess risk of bias, pool results or rate the certainty of evidence. Its
> displays therefore describe what has been studied and reported, and
> conclusions about effects require a systematic review or meta-analysis.
> Researchers can use it to locate studies, to examine how research is
> distributed across compounds, designs and populations, and to see which topics
> have reviews or meta-analyses. As its accuracy is measured against human
> reviewers, the same records can support reviewer-verified data extraction and
> regularly updated meta-analyses.

"Monthly" should be used only if that interval is kept; otherwise state the
actual interval.

## 3. Page-by-page review with proposed wording

### 3.1 Home page

| Location | Current | Problem | Proposed |
|---|---|---|---|
| Subtitle and meta descriptions ([index.html](../index.html), lines 9–39 and 120) | "A living map of psychedelic research, built to keep scientific knowledge organized, connected, and easily explorable" | "Scientific knowledge" describes the content as established; the second clause names no specific property; no update interval | Subtitle: "A living evidence map of psychedelic research, updated monthly, with each extracted finding linked to its source." Meta: "An evidence map of psychedelic research: what each study examined and reported, extracted by language models and linked to the source text. Updated monthly." |
| Release line | "Literature updated: 2026-09-15" | No information about the next update | Add "Next update: [date]". |

### 3.2 About page

| Location ([about/index.html](../about/index.html)) | Current | Problem | Proposed |
|---|---|---|---|
| Meta descriptions (lines 8, 20, 27) | "…scientific knowledge organization, living evidence synthesis, and access for humans and AI systems." | Claims synthesis | "Why Psychedelics Knowledge Graph exists, what it records, and how researchers and AI systems can use it." |
| Lead (lines 73–75) | "provides a new way to organize, synthesize, and access scientific knowledge, enabled by and optimized for the emerging era of agentic science" | Claims synthesis; promotional | "Psychedelics Knowledge Graph is a living evidence map of psychedelic research. Language models search and screen the literature and extract each paper's findings into a common structure. Researchers can browse the results, and AI agents can query them." |
| Reasons, second and third paragraphs (lines ~92–101) | "Our current evidence synthesis methods, reviews and meta-analyses, … are limited in scope, require substantial expert labor and provide static snapshots…"; "Together, these forms of knowledge storage and synthesis make it difficult…" | Presents reviews as a deficient predecessor; a defined question is a design property of reviews, not a defect | Use the lines already settled for the film: "Findings, methods and context are reported in the text of individual papers, so patterns across studies remain implicit. Reviews and meta-analyses document some of these patterns, but they take months to complete (Borah et al., 2017) and quickly become outdated. A large part of the work in every review goes into the same steps: searching the literature, screening the records and extracting data from each paper." |
| AI paragraph (lines ~103–111) | "Emerging AI tools make it possible to address both of these problems … updated as new evidence appears, audited and corrected, accessed by humans and AI systems, and used to support new analyses and evidence syntheses." | "Address both problems" overstates; "audited and corrected" reads as a description of current practice | "Language models can now carry out these steps for an entire field, record where in each paper an extracted finding comes from, and repeat the process at each update. Because every finding is linked to its source, users can check it, and reported errors are corrected in the next release." |
| Diagram (lines ~115–160) | Current system (publications; reviews and meta-analyses as "Narrowly scoped snapshots of the literature") → agentic workflow → living knowledge graph (Time: "Continuously updated"; Scale; Reuse; Accessibility) | Implies that the graph supersedes reviews; "continuously" is inaccurate | A stage diagram: Search · Screen · Extract, shaded and labelled "done by the graph for the whole field, at each update"; then Appraise · Synthesize · Rate certainty, labelled "done by reviewers for specific questions". Underneath, the users: researchers (browse and filter), reviewers (candidate studies, extracted data, existing reviews per topic), AI agents (API and MCP). Caption: "As automated methods for later stages are validated against human reviewers, the graph can take on more of them, with human verification." The shaded part extends to the right as levels in section 2.3 are reached, which shows future value in the same figure. |
| New paragraph after the diagram | None | The page never states what the graph does not do | "The graph does not assess risk of bias, weight studies, pool results or rate the certainty of evidence. The number of papers or findings on a topic therefore does not indicate whether an effect exists, how large it is or how reliable the evidence is. For these questions, use systematic reviews and meta-analyses, which the graph lists separately for each topic." |
| Applied paragraph | "…identify connections and gaps across the literature…" | "Gaps" unqualified | "…see which compounds, outcomes, designs and populations have few or no papers in the current release…" |
| Work in progress | "errors and omissions are expected" | Accurate but unquantified | Keep, and link to measured error rates once the validation section exists. |
| New section | None | A commercialized field; a single maintainer | Funding and conflicts-of-interest statement. |

### 3.3 Methods page

| Location ([methods/index.html](../methods/index.html)) | Current | Problem | Proposed |
|---|---|---|---|
| Overview (lines ~135–145) and screening and extraction sections (lines 496, 527, 598, 614) | "The current pipeline uses GPT-6 Luna for new title-and-abstract screening and the planned replacement evidence extraction. The published graph continues to represent its last completed release…" | The page names only GPT-6 Luna. According to the routing table and extraction runners, the published release (2.0.0) was screened, classified and extracted with Gemini 3 Flash Preview ([model_selection_2026-10-16.md](evaluation/model_selection_2026-10-16.md)); no public page names Gemini. Methods must describe the release they accompany. | Version the page: "Methods for release 2.0.0 (literature to 15 September 2026)", naming the models and prompt versions used. Move the GPT-6 Luna pipeline, the PCP search and the V5 screening counts to "Changes in the next release". |
| Validate and publish (line ~253) | "Extracted findings are checked for the required fields and for support in the source publication." | The production checks are schema validity, source identity and character integrity. Support for each finding is not checked. | "Automated checks confirm that each output follows the required schema, that the source text belongs to the intended paper, and that no characters are corrupted. Findings are not individually verified by a person before publication. Findings that fail these checks or cannot be mapped to graph entities are held back. Measured error rates are reported under Validation." |
| Screening criteria | Lists the rule-based exclusions | Omits the ketamine anesthesia, sedation and analgesia exclusion in the V5 instructions. That rule will remove ketamine pain studies that release 2.0.0 displays (fibromyalgia, complex regional pain syndrome, neuropathic pain). Users will see these relationships disappear without explanation. | State the complete eligibility criteria, including the ketamine rules, and list scope changes for each release. |
| Compound scope | List of compounds in scope | The graph displays dextromethorphan, nitrous oxide, methoxetamine and norketamine, which are not on the list, and places non-compound subjects (Chemsex, Psychedelic-assisted therapy) and classes (Hallucinogens, Dissociatives) on the same axis | State the rule that admits them, or align the list with the graph; mark classes and contexts as such. |
| New section | None | No public statement of measured accuracy | "Validation": for each stage, the reference set, who labelled it, the measured value with a 95% CI, and the release it applies to. |
| Flow diagram heading (line 773) | "PRISMA flow diagram" | Can be read as a claim that the graph is a PRISMA-compliant systematic review | "Record flow (PRISMA 2020 format)", followed by: "The diagram uses the PRISMA 2020 format to report the flow of records. The graph is not a systematic review, so PRISMA items on risk of bias, synthesis and certainty of evidence do not apply." |
| Limitations (line ~841) | "The graph is intended for research exploration, not as a complete systematic review or as clinical guidance." | "Not a complete systematic review" implies an incomplete one; the main limitations are not listed | Replace with a list: counts are papers, not independent studies; about half of represented papers were extracted from abstracts, which report fewer outcomes than full texts and more often emphasize statistically significant results (Boutron et al., 2010); exclusions (non-English papers, abstracts under 50 words, preprints, conference abstracts, theses, books); no risk-of-bias assessment, pooling or certainty assessment; accuracy so far measured against model-assisted reference labels; retraction status as recorded by publishers at retrieval. End with: "The graph is an evidence map. It is not a systematic review and is not clinical guidance." |

### 3.4 Repository documents

| File | Current | Proposed |
|---|---|---|
| [README.md](../README.md) | Accurate overall; "Link every public finding back to its source" | Add: "It does not assess risk of bias or pool results; see the Methods limitations." |
| [pipeline/README.md](../pipeline/README.md), lines 1 and 6 | "Evidence Synthesis Pipeline"; "validates them against their sources" | "Literature processing and extraction pipeline"; "checks them for schema validity, source identity and character integrity" |
| [docs/evidence_policy.md](evidence_policy.md), line 50 | "Before publication, extracted findings are checked against their source reports" | The same correction as on the Methods page |
| [docs/evidence_policy.md](evidence_policy.md), line 58 | "relationships from primary studies and reviews require support from at least two reports" | "are displayed when at least two papers report them. This is a display rule. Two papers can report the same study, and the rule does not indicate the reliability of the relationship." |
| [docs/terminology.md](terminology.md), lines 21–22 | "supported by one or more findings"; "evidence-supported relationships" | "derived from one or more findings"; "relationships derived from extracted findings" |
| [CITATION.cff](../CITATION.cff), line 21 | keyword "evidence synthesis" | "evidence map"; optionally add "living evidence" and "systematic review automation" |
| [llms.txt](../llms.txt) | "A living map of psychedelic research with links from structured findings back to their source reports…" | Accurate; add the update interval |

### 3.5 Interface labels

| Current | Proposed | Reason |
|---|---|---|
| "All studies 2,060"; author rows "68 studies" | "2,060 papers"; "68 papers" | Counts are of papers |
| "Open access 1,289 · 63% of studies" | "Full text used 1,289 · 63% of papers"; a separate "Open access" filter only if it is derived from licence data | Two different properties |
| Arrow from compound to outcome on cards and edges | A neutral connector, with the relationship type on the card and on hover (treatment outcome, adverse outcome, association, predictor, pharmacokinetic) | One symbol currently covers benefit, harm and correlation. Example: "25I-NBOMe → Suicidal ideation & behavior" (depressive symptoms in patients with HPPD, mapped to "Major depressive disorder") appears in the same view as ketamine treatment trials. |
| Line width without a legend | Legend: "Line width: number of papers. It does not indicate effect size, direction or certainty." | Research volume is easily read as strength of evidence |
| Design badge copied from the parent study | Parent design plus analysis type, for example "RCT · secondary predictor analysis" or "Open-label trial · change from baseline" | The comparison that produced a finding determines what it can show. Example: the card "(2R,6R)-hydroxynorketamine → Major depressive disorder · RCT" reports a correlation between metabolite concentration and response to ketamine. |
| No source-text indication on cards | "Extracted from: abstract" or "Extracted from: full text" | Abstracts differ systematically from full texts |
| "Evidence gap" | "No papers in this release", with a note listing coverage limits | Absence from the graph can reflect search, screening, extraction or display rules |
| "Synthesis coverage: primary volume × meta-analysis and review coverage", with a diagonal guide line ([ui/app.js](../ui/app.js), line 10717) | "Primary studies and reviews by research area"; plot meta-analyses and systematic reviews separately from narrative reviews; remove the diagonal | 3,863 of the 4,672 "reviews" are narrative or unclassified reviews, which are not syntheses; a 1:1 ratio has no methodological meaning; "coverage" implies that the reviews included those studies |
| Funders "National Institute of Mental Health" and "NIMH NIH HHS" listed separately | Merge aliases | Duplicate counts (noted on 5 September; still live) |
| Stored `result_direction` values: positive 13,714; supports 11,478; negative 9,368; no_detected_effect 2,967; mixed 1,195; empty for 55,624 of 99,100 findings | Before any display, separate the direction of change (increase, decrease, no difference) from the statistical result (significant, not significant, not tested) | "Positive" can mean beneficial, increased or statistically significant |

### 3.6 Launch film

The v21 script says "It's time to rethink how scientific knowledge is stored,
synthesized and accessed" and presents patterns, coverage and gaps in Act III.
This is consistent with the evidence-map description provided that no line says
the graph synthesizes evidence. The current script contains no such line.

## 4. Displays that can be read as synthesis

Counting the papers that report a benefit is vote counting. The Cochrane
Handbook advises against vote counting based on statistical significance,
because it ignores effect size, precision and study quality and has low power
(McKenzie and Brennan, Chapter 12; Hedges and Olkin, 1980). The interface does
not show tallies of result direction, and that choice should be kept.

The remaining risks are indirect:

- **Edges and line width.** An edge appears when at least two papers report a
  relationship, and its width grows with the number of papers. Two papers from
  one trial meet the threshold. Without a legend, width is read as strength of
  evidence.
- **One arrow for different relationships.** Treatment outcomes, adverse
  outcomes, associations and predictors share the same symbol.
- **Gap labels.** An empty cell is described as a gap in the literature when it
  can result from the pipeline's coverage.
- **Synthesis coverage.** The chart treats every review as a synthesis and
  implies an expected ratio between reviews and primary studies.
- **Design inheritance.** Findings from secondary, correlational or
  within-group analyses carry the parent study's randomized design.
- **Abstract-only findings.** About half of represented papers (10,547 of
  21,496 in the canonical table) have no converted full text. Findings from
  abstracts carry abstract reporting biases, and cards do not show which source
  was used.

If result direction is displayed in future, an effect direction plot or a
harvest plot, stratified by design and sample size, is the standard form for
presenting results without meta-analysis (Thomson and Thomas, 2013; Ogilvie et
al., 2008; Campbell et al., 2020).

## 5. Scientific rigor: what better models will and will not change

| Issue | Current evidence | Will better models fix it? | Action |
|---|---|---|---|
| Screening errors at the scope boundary | Fresh random sample: 181/199 decisions agree with the reference (91.0%, 95% CI 86.2–94.2); 51/63 relevant papers retained (81.0%, 95% CI 69.6–88.8); 0/40 high-confidence relevant papers missed ([luna_screening_prompt_comparison_2026-10-16.md](evaluation/luna_screening_prompt_comparison_2026-10-16.md)) | Partly. The remaining misses are boundary cases, which depend on how the scope is written as much as on the model | Report recall separately for core and boundary scope; write boundary rules as explicit criteria |
| Extraction attached to the wrong arm, outcome, cohort or time | 21 flagged items in 9 of 96 papers; overall, 31 items in 15 papers with high-confidence incorrect or unsupported fields ([luna_primary_comprehensive_audit_2026-10-17.md](evaluation/luna_primary_comprehensive_audit_2026-10-17.md)) | Largely, but it must be re-measured for each model | Fixed benchmark; deterministic checks that numbers occur in the cited passage; verbatim excerpts stored with findings |
| Omitted principal findings or qualifying contrasts | 14 of 96 papers | Partly | Completeness measured on the benchmark |
| Reference standard produced with model assistance | All current screening and extraction audits | No. As errors become rarer they become harder to detect by inspection, and a model assessor shares failure modes with the extractor | Human-adjudicated benchmark |
| Search sources and filters | Two databases. On 5 September, 86,584 records were excluded for abstract availability, 7,440 for language, and 60,796 records without a DOI awaited resolution | No | Audit exclusions by rule, period and compound; relative recall; consider trial registries |
| Abstract-only extraction | 10,547 of 21,496 represented papers | No; limited by access | Show the source on each finding; pursue text-and-data-mining agreements; stratify displays |
| Counting unit | Papers, not studies; 199 trial registry IDs linked to more than one paper (5 September) | No | Study-level identities from registry IDs |
| No appraisal fields | Design only | Not by itself; the schema must first contain the fields | Add descriptive reporting fields (section 6, item 11) |
| Retraction status | Retracted papers are excluded when their publication type or title marks the retraction at the time metadata is retrieved or refreshed (69 records with retraction-marked titles, none represented). The structured `is_retracted` field is set for 1 of 277,094 candidate records, and there is no release-time check against a retraction database. | No | Check represented DOIs against Crossref's Retraction Watch data and OpenAlex at each release |
| Methods describe a different release | GPT-6 Luna named; release 2.0.0 built with Gemini 3 Flash Preview | No | Version the Methods page |
| Errors carried forward from earlier runs | "10g LSD" and mushroom weights as psilocybin still displayed | No | Release gate applied to all fields, not only new outputs |
| Non-determinism and model retirement | Preview models used; outputs archived | No | State that builds are reproducible from archived outputs; record model and prompt version on each finding |
| Publication bias and selective reporting in the literature | Not addressed | No | State in limitations; list registered trials without published results |

Two consequences follow. First, every model change should be re-measured on a
fixed benchmark. The October prompt comparison shows why: on the fresh sample,
V5 corrected 11 V4 errors and introduced 7 new ones, and inspection alone would
not have shown the new ones. The benchmark is therefore the part of the
validation work that keeps its value as models change. Second, claims about
coverage, independence of evidence and comparability across studies depend on
the design items in the table, and model improvements alone will not make those
claims accurate.

## 6. Recommended changes, in order

**Immediate: make current statements accurate (no new methods needed)**

1. Version the Methods page by release; name the models and prompt versions
   used for release 2.0.0; move next-release content (GPT-6 Luna, V5 screening,
   the PCP search, the ketamine analgesia exclusion) to "Changes in the next
   release".
2. Apply the wording in section 3 to the About page, Methods page, home page,
   terminology guide, evidence policy, pipeline README and `CITATION.cff`.
3. Change the interface labels in section 3.5: papers instead of studies; full
   text used instead of open access; a legend for line width; the source text on
   each card; renamed gap and synthesis-coverage displays.
4. Correct the two dose errors now displayed, and apply the release gate to all
   carried-forward fields.
5. Check retraction status of all represented DOIs at each release.

**Next: measure**

6. **Human-adjudicated benchmark.** Two domain experts label independently;
   disagreements are adjudicated; agreement (Cohen's kappa) is reported before
   adjudication; a fixed holdout is never used for prompt development.
   - Screening: to estimate recall near 0.9 with a 95% CI half-width of about
     0.05 requires about 140 relevant records (1.96² × 0.9 × 0.1 / 0.05² ≈ 138).
     At the 32% relevance rate in the fresh random sample, that is about 450
     records sampled after the rule-based stage. Add a sample of rule-excluded
     records to estimate losses from the abstract and language rules.
   - Extraction: at about 15% of papers with a material error, a 95% CI
     half-width of 0.07 requires about 100 papers
     (1.96² × 0.15 × 0.85 / 0.07² ≈ 100), stratified by research area and
     source text.
7. **Relative recall** (Sampson et al., 2006). Take the included-study lists of
   recent systematic reviews and meta-analyses in scope; the graph already
   contains 332 meta-analyses and 586 systematic reviews. For each list, report
   the share of included studies that the pipeline retrieved, kept after the
   rules, included after model screening, and represented in the graph. This
   gives a stage-by-stage recall estimate against a reference set assembled by
   human reviewers, at low cost. It covers mainly clinical topics; preclinical
   systematic reviews can extend it.
8. **Validation statement with each release.** The graph card in
   `protocols/SPEC.md` section 8 already lists most fields. Add: the claim level
   from section 2.3; relative recall; scope changes since the previous release;
   the date of the retraction check; the interval between literature date and
   release date.
9. **Primary papers since the latest meta-analysis.** For each compound–condition
   pair with a meta-analysis, show the latest `search_end` date and the number of
   primary papers published after it, by design. Label the counts as papers,
   and note that matching is at the level of graph entities and may include
   studies outside the meta-analysis's eligibility criteria. Garner et al.
   (2016) list new studies as a main reason to update a review, so this display
   directly supports decisions about new and updated syntheses.

**Later: extend the data model**

10. Study-level identities from trial registry IDs, as recommended on
    5 September; display counts as "N studies (M papers)" where known.
11. Descriptive reporting fields that reviewers use in appraisal: randomization,
    blinding and any assessment of blinding, comparator type (already present),
    preregistration (already present), attrition, funding source and industry
    involvement, and conflicts of interest. Functional unblinding and expectancy
    are recognized problems in psychedelic trials (Muthukumaraswamy et al.,
    2021), so reported blinding assessment is a useful filter. These are
    descriptions of what papers report; they are not risk-of-bias judgements.
12. Structured effect estimates for clinical results (arms, n, estimate,
    interval), which level 3 requires.
13. Register the field protocol (for example on OSF) and record scope changes as
    dated amendments.

**Governance (low cost)**

14. A funding and conflicts-of-interest statement on the About page.
15. A public log of corrections for each release.
16. Named contributors for the validation work. A validation paper (for example
    in *Research Synthesis Methods* or *Systematic Reviews*) would give the
    project a citable accuracy statement.

Because the aim is for others to build graphs for their own fields, the rules for
what a graph may claim should also be part of the field protocol: each protocol declares
which stages it automates, the graph card reports the claim level reached, and
the site template generates the "does not do" statement and the limitations from
those declarations.

## 7. What to keep

- The public table of selection decisions, with a reason for every record.
- The separation of primary studies, meta-analyses and reviews, and the
  retention of null and mixed findings.
- The absence of result-direction tallies in the interface.
- The interpretation statement in the agent guide, which can serve as the model
  for the human-facing pages.
- Versioned releases with DOIs and checksums, archived model outputs, and builds
  that are reproducible from saved outputs.
- The internal evaluation reports, which report confidence intervals, separate
  development samples from fresh samples, and state the reviewer type.
- Holds for sources whose identity cannot be confirmed.

## Evidence for specific statements

- Models behind release 2.0.0: [model_selection_2026-10-16.md](evaluation/model_selection_2026-10-16.md);
  no public page mentions Gemini.
- Screening figures: [luna_screening_prompt_comparison_2026-10-16.md](evaluation/luna_screening_prompt_comparison_2026-10-16.md).
- Extraction audit: [luna_primary_comprehensive_audit_2026-10-17.md](evaluation/luna_primary_comprehensive_audit_2026-10-17.md).
- Full-text share and retraction flags: `data/processed/corpus/candidate_papers.parquet`
  (`graph_inclusion_status = 'represented'`, `has_converted_full_text`, `is_retracted`).
- Review subtypes and result-direction values:
  `data/processed/kg_routed_runs/living_update_20260917_author_identity_reviewed/findings.parquet`.
- Live-site observations, 31 October 2026: the "25I-NBOMe → Suicidal ideation &
  behavior" and "(2R,6R)-hydroxynorketamine → Major depressive disorder" cards;
  a dose field reading "microdosing (mean 225mg psilocybin or 10g LSD)"; paper
  counts labelled "studies"; duplicate NIMH funder entries.

## References

- Borah R, Brown AW, Capers PL, Kaiser KA. Analysis of the time and workers
  needed to conduct systematic reviews of medical interventions using data from
  the PROSPERO registry. *BMJ Open*. 2017;7:e012545.
- Boutron I, Dutton S, Ravaud P, Altman DG. Reporting and interpretation of
  randomized controlled trials with statistically nonsignificant results for
  primary outcomes. *JAMA*. 2010;303:2058–2064.
- Campbell M, McKenzie JE, Sowden A, et al. Synthesis without meta-analysis
  (SWiM) in systematic reviews: reporting guideline. *BMJ*. 2020;368:l6890.
- Cohen AM, Hersh WR, Peterson K, Yen PY. Reducing workload in systematic review
  preparation using automated citation classification. *JAMIA*.
  2006;13:206–219.
- Elliott JH, Synnot A, Turner T, et al. Living systematic review: 1.
  Introduction—the why, what, when, and how. *J Clin Epidemiol*.
  2017;91:23–30.
- Garner P, Hopewell S, Chandler J, et al. When and how to update systematic
  reviews: consensus and checklist. *BMJ*. 2016;354:i3507.
- Hedges LV, Olkin I. Vote-counting methods in research synthesis. *Psychol
  Bull*. 1980;88:359–369.
- James KL, Randall NP, Haddaway NR. A methodology for systematic mapping in
  environmental sciences. *Environ Evid*. 2016;5:7.
- Marshall IJ, Nye B, Kuiper J, et al. Trialstreamer: a living, automatically
  updated database of clinical trial reports. *JAMIA*. 2020;27:1903–1912.
- McKenzie JE, Brennan SE. Chapter 12: Synthesizing and presenting findings
  using other methods. In: *Cochrane Handbook for Systematic Reviews of
  Interventions*.
- Miake-Lye IM, Hempel S, Shanman R, Shekelle PG. What is an evidence map? A
  systematic review of published evidence maps and their definitions, methods,
  and products. *Syst Rev*. 2016;5:28.
- Muthukumaraswamy SD, Forsyth A, Lumley T. Blinding and expectancy confounds in
  psychedelic randomized controlled trials. *Expert Rev Clin Pharmacol*.
  2021;14:1133–1152.
- Ogilvie D, Fayter D, Petticrew M, et al. The harvest plot: a method for
  synthesising evidence about the differential effects of interventions. *BMC
  Med Res Methodol*. 2008;8:8.
- Sampson M, Zhang L, Morrison A, et al. An alternative to the hand searching
  gold standard: validating methodological search filters using relative
  recall. *BMC Med Res Methodol*. 2006;6:33.
- Thomson HJ, Thomas S. The effect direction plot: visual display of
  non-standardised effects across multiple outcome domains. *Res Synth Methods*.
  2013;4:95–101.
- White H, Albers B, Gaarder M, et al. Guidance for producing a Campbell
  evidence and gap map. *Campbell Syst Rev*. 2020;16:e1125.

Reference details were written from memory and should be checked before they
are cited in a publication.
