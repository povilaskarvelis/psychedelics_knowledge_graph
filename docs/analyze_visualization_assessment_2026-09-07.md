# Analyze visualization assessment

Assessment date: 7 September 2026. Trending-topic update: 16 September 2026.

## Recommendation

Keep Explore and Analyze as the two top-level modes. Do not add a third workspace or generic question-preset buttons at the top of Analyze. A small, editorially curated **Trending now** shelf is justified because it serves a different purpose: it gives users a current entry point into cross-cutting themes supported by research activity, public discussion, and the graph. The default Analyze overview already covers the general publication landscape well. The best additions are narrower views that appear after a user selects a trend, research area, topic, compound, author, or journal.

Do not aggregate result direction. The field does not carry a common meaning across clinical benefit, safety, abuse liability, behavioral assays, molecular activity, and public-health associations. Even within a single domain, direction can describe movement on a scale rather than benefit or harm. Its strong positive skew also makes a field-wide chart low-information and vulnerable to publication and extraction bias. Keep direction in individual finding details unless a future analysis defines a domain-specific estimand and harmonizes outcome direction.

The low-hanging opportunity is to improve the representation of **what kind of evidence exists**, not to summarize what all that evidence concludes.

## Trending topics as Analyze shortcuts

Add this within Analyze, not as a new top-level mode. Place a single compact row below the Analyze controls and above the first evidence panel:

The target shelf, after one small curation pass, is:

**Trending now** · Microdosing · Therapy without the trip? · Neuroplasticity · Therapy, setting & expectancy · Ibogaine & addiction · Policy & access

The first implementation can ship the other five themes and add **Therapy without the trip?** once its derived tag has been reviewed.

This should not be a generic set of natural-language questions. Each item is a versioned theme definition that can span several existing graph dimensions. Clicking one applies that theme to the current Analyze workspace, retains the global paper-type, access, and year filters, and recomputes every existing panel. Show the active theme as a removable chip and make it shareable in the URL. Choosing a conventional research area, topic, or entity should clear the theme.

The existing Momentum panel should remain. It measures publication activity inside the corpus. Trending now has a different basis: recent literature growth, public and news attention, regulatory activity, and the ability to retrieve a meaningful subset from the graph. Label the shelf “Topics receiving increased research and public attention,” not “most promising,” “best supported,” or “effective.”

### Initial theme assessment

| Theme | Why it belongs | Current graph support | Recommendation |
| --- | --- | --- | --- |
| Microdosing | Strong public recognition and continuing research growth | Structured dosing schedule and real-world use context; 97 current-release reports under a union of those fields | Ship now |
| Therapy without the trip? | Fast-growing research and public interest in non-hallucinogenic psychoplastogens | 108 reports contain relevant free-text terms, but there is no clean structured theme field | Add a curated derived tag first, then ship |
| Neuroplasticity | The strongest recent publication growth in the topic scan and a central mechanistic question | Curated Neuroplasticity parent with 1,067 reports and detailed subtopics | Ship now |
| Therapy, setting & expectancy | Central to trial interpretation, blinding, psychological support, and service design | Existing intervention-context concepts retrieve 484 reports under a conservative definition | Ship now as a curated multi-concept theme |
| Ibogaine & addiction | Major current regulatory and news attention, with a concrete compound–indication question | Ibogaine/noribogaine plus addiction-condition co-coverage retrieves 87 reports | Ship now, with safety visible in the resulting analysis |
| Policy & access | Active federal and state policy discussion and strong relevance to implementation | Policy, access, equity, implementation, and service-delivery fields retrieve 694 reports | Ship now after consolidating obvious category aliases |

Good candidates for a later “More” menu are **Short-acting psychedelics** and **Safety outside trials**. The graph can already retrieve substantial DMT/5-MeO-DMT and real-world-harm subsets, but the public-facing promises need care: short duration does not by itself establish scalable care, and report counts do not estimate risk incidence.

### How to determine what is trending

Use a monthly or per-release editorial pipeline rather than live browser calls or an opaque score:

1. **Research momentum:** compare equal recent and prior publication windows in PubMed or OpenAlex, require a minimum recent volume, and review the query behind every topic.
2. **Public attention:** compare rolling news volume and acceleration, deduplicate syndicated stories, and require coverage from several independent sources. Search interest can be a supporting signal, especially for recognizable public terms such as microdosing.
3. **Regulatory and practice activity:** track material FDA, trial, legislation, public-health, and service-delivery developments. These can make a topic timely even before publication counts surge.
4. **Graph fitness:** require a documented structured predicate, a sufficient report set, and an inspectable list of what matched. Topics that depend on unstructured text need an offline derived tag and review before appearing as shortcuts.
5. **Editorial review:** keep the three signals visible rather than compressing them into one unexplained “hotness” number. Public attention can reflect controversy, promotion, or harm; it is not evidence of efficacy.

The directional literature scan used equal three-year PubMed windows (16 September 2023–16 September 2026 versus 16 September 2020–15 September 2023). All shortlisted themes grew in the newer window: microdosing 114 versus 75; non-hallucinogenic psychoplastogens 80 versus 33; neuroplasticity 302 versus 84; therapy/setting/expectancy/blinding 1,077 versus 579; ibogaine and addiction 57 versus 31; and policy/access/implementation 1,046 versus 597. These searches overlap and are query-sensitive, so they validate momentum rather than provide mutually exclusive topic rankings.

The public-attention check also changes the ranking in a useful way. Microdosing has measurable search and mainstream-news interest. Ibogaine and access move into the first tier because of 2026 federal action and broad news coverage despite a smaller scientific base. Trial design, psychotherapy, and expectancy remain current because regulators and public agencies continue to identify blinding and the role of psychological support as core interpretation problems. Relevant sources include the [FDA's April 2026 action](https://www.fda.gov/news-events/press-announcements/fda-accelerates-action-treatments-serious-mental-illness-following-executive-order), the [GAO medical-psychedelics assessment](https://www.gao.gov/products/gao-25-108021), [Nature's coverage of ibogaine research](https://www.nature.com/articles/d41586-026-01286-1), and [AP's coverage of microdosing](https://apnews.com/article/390c99ba54ef9d75727f39e2ec78fb34).

## What is already present

Analyze already includes publication history, evidence-type composition, entity rankings, research-area and topic profiles, momentum, primary-versus-synthesis coverage, overlap, entity landscapes, entity coverage matrices, and a general Evidence coverage matrix. The working code also contains study-characteristic and transparency components using population/model, design, sample size, comparator, follow-up, administration route, outcome scales, assay family, data source, review design, studies included, trial registration, preregistration, documented data, and documented code.

New work should extend or reorganize these components rather than introduce duplicate charts.

## Best additions using current data

### 1. Context-specific evidence structure

Turn the existing Evidence coverage matrix into a domain-aware component. Keep its general dimensions when all research areas are selected, then offer only meaningful dimensions for a selected area:

| Selected area | Useful existing dimensions |
| --- | --- |
| Conditions | Condition, study design, population, comparator, follow-up, outcome instrument, route, dosing schedule, session context |
| Safety | Safety outcome, safety context, population/model, study design, route, dosing schedule, session context |
| Real-world use | Topic, measure, data-source type, use context, study design, compound |
| Brain regions | Region/network, brain measure, assay/modality, experimental system, compound |
| Molecular effects and targets | Entity, parent process/system, assay family, relationship type, experimental system, compound |
| Cognition and behavior | Construct, population/model, study design, experimental system, administration/session context |
| Subjective effects | Construct, population, study design, administration route, dosing schedule, session context |
| Reviews | Topic, review approach, review focus, evidence base |
| Meta-analyses | Topic, synthesis design, included-study-count band, comparator, follow-up |

Most of the required category functions already exist in `ui/app.js`; several are simply unavailable as Evidence coverage axes.

The counting semantics must change for this use. The current matrix unions characteristics across all findings in a report before forming a cell. That is acceptable for report-level co-coverage, but it can create a combination that was never attached to the same finding. For study-method questions, match the two characteristics on the same finding first, then deduplicate the matching reports. Label the result as reports with a matching finding.

No question presets are required. A contextual default pair can be selected the first time a research area is chosen, while the two explicit axis controls remain visible.

### 2. Absolute versus proportional evidence profiles

Add a display toggle to existing entity-by-area and entity-by-topic matrices:

- **Reports:** current unique-report counts.
- **Profile:** percentage of each entity's reports that cover the area or topic.

Raw counts mainly reproduce corpus size: ketamine will dominate most comparisons. A within-entity proportion makes it possible to see how compounds, authors, and journals differ in research emphasis. Because one report can cover more than one area, describe each value as “percentage of this entity's reports covering this area”; do not imply columns sum to 100%.

This reuses current memberships and requires no new extraction.

### 3. Finer-grained primary and synthesis coverage

Extend the existing research-area coverage view down to compounds and topics. Use one row per compound or topic with separate counts for:

- primary reports;
- meta-analyses;
- systematic/scoping/umbrella reviews;
- narrative and other reviews.

This is more interpretable than combining every review with meta-analyses on one axis. It can reveal areas with substantial primary literature and little formal synthesis without claiming that the evidence is mature, sufficient, or unsynthesized outside this corpus. Every count can use existing paper types and graph memberships and can drill into its reports.

### 4. Methods over time

For a selected compound or topic, show five-year bins of study-design families or research systems. Suitable examples are clinical trials versus observational work for Conditions, survey versus registry versus drug-checking data for Real-world use, and assay families for mechanistic areas.

This answers whether the *methods used to study a subject* have changed. It should not be labelled evidence maturity or scientific progress. Use report counts and retain an explicit unclassified category.

### 5. Outcome-instrument coverage for clinical research

For a selected condition or compound, show the outcome instruments used and their report counts, optionally crossed with follow-up windows or study design. This helps trial designers and reviewers see measurement concentration or fragmentation without comparing effects.

The active local dataset has at least one normalized outcome instrument for 1,456 of 2,545 primary clinical reports; 1,089 reports have none. Some reports contain both populated and unpopulated finding rows, so completeness must be calculated at report level. Compound-specific views should disclose their own completeness. This is useful as a scoped clinical view, not as a global chart.

### 6. Meta-analysis search currency

When Meta-analyses is selected, visualize the reported last-search date and publication date for each synthesis in the current topic or compound scope. Of 321 local meta-analysis reports, 243 have a recorded search-end date. A dot or interval timeline can reveal old searches and publication lag using only source-reported dates.

The first version should stop there. Identifying primary reports published after a search as candidate missed studies requires eligibility matching and is not low-hanging.

## What should not be prioritized

- **Result-direction summaries:** semantically incompatible across domains and highly skewed.
- **Effect-size or dose-response plots:** metrics, outcomes, units, timepoints, populations, routes, and comparators are not harmonized enough for broad comparison.
- **Safety incidence:** report counts do not supply exposed-participant denominators or consistent ascertainment.
- **Pharmacokinetic curves:** isolated values and units exist, but comparable parameter/analyte/matrix/species subsets require a separate normalization and eligibility review.
- **Funding as an immediate entity lens:** funding is abundant, but aliases remain visibly duplicated (for example, full NIH institute names and acronym forms). Normalize funder identity before ranking portfolios.
- **Open-science rates as a major field benchmark:** current fields record identified positive signals; a missing assertion is not evidence of absence, and detection varies by source and year. The existing transparency component is an appropriate secondary view.
- **Cross-domain causal or translational pathways:** same-report coverage does not establish a causal connection between molecular, brain, subjective, and clinical findings.
- **Generic question-preset navigation:** it does not add analytical value and is unnecessary unless usability testing shows that people cannot operate the matrix controls. The curated Trending now themes above are distinct because they apply reproducible cross-cutting graph filters and are updated from external signals.

## Layout

Retain the current continuous Analyze page. The All view should remain a landscape overview. After the user narrows the scope, prioritize panels in this order:

1. Evidence profile and publication history.
2. Entity/topic coverage, with Reports/Profile toggle.
3. Context-specific Evidence structure.
4. Methods over time or meta-analysis currency when applicable.
5. Overlap, connections, findings, and bibliography.

This is a modest reordering within Analyze, not a new product mode. Panels that have no valid dimensions in the current scope should not render.

## Data audit notes

The original completeness audit used the local `author_identity_20260906_reviewed` Parquet tables. The trending-theme feasibility counts use the active `living_update_20260916_complete` findings table. These counts are feasibility measurements, not published UI totals. Primary-report field availability varies sharply by domain. Examples:

- Clinical outcomes: 2,545 reports; 2,141 with a substantive study-design category, 1,598 with a substantive comparator category, 1,456 with normalized outcome instruments, and 2,427 with a substantive follow-up category.
- Real-world/public-health evidence: 4,466 reports; all have a public-health topic and measure, 4,319 have a substantive data-source category, and 3,795 have a recorded use context.
- Brain-system evidence: 2,247 reports; all have a readout and 1,994 have an assay family.
- Molecular pathway evidence: 4,641 reports; 4,548 have a parent process, 4,034 a relationship type, and 3,221 a substantive assay family.
- Molecular target evidence: 2,975 reports; 2,481 have a relationship type and 2,376 a substantive assay family.

Local sources reviewed: `ui/app.js`, `ui/research-analysis.js`, `ui/research-model.js`, `scripts/build_analysis_index.py`, `schema/graph_view_contract.json`, the extraction-profile schemas, `pipeline/kg/build_evidence_tables.py`, and the active local knowledge-graph tables.
