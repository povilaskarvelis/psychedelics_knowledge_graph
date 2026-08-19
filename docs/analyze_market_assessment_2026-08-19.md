# Analyze: product and market assessment

**Assessment date:** 19 August 2026  
**Product reviewed:** the newly added Analyze section of the Psychedelics Knowledge Graph

## Executive conclusion

Analyze is genuinely useful. Its strongest value is not that it draws publication charts; publication charts are already common and increasingly commoditized. Its value is that it lets a user explore a continuously maintained, psychedelic-specific evidence graph across compounds, research areas, concepts, authors, journals, evidence types, time, and access status, then move from an aggregate pattern back to the underlying records.

The most accurate category is **living psychedelic evidence intelligence** or **scientific landscape intelligence**. It is not yet a complete life-science competitive-intelligence or commercial market-intelligence product, because it does not systematically cover development assets, sponsors, trial phases and endpoints, patents, deals, financing, regulatory events, sales forecasts, or catalysts.

There is a real market for what it does:

- Academic researchers, evidence-synthesis teams, funders, foundations, psychedelic research centres, and science-policy groups can use it now.
- Biotech, pharma, CRO, and advisory teams would value it, but would pay materially more once scientific evidence is joined to clinical-development and commercial data.
- Investors and corporate-development teams will find it interesting today, but it is not yet sufficient for investment or pipeline decisions.
- Existing paid psychedelic products—especially Blossom and Psychedelic Alpha—prove that individuals and organisations already pay for curated field intelligence. The much larger markets for SciVal, Dimensions, InCites, Citeline, Cortellis, Evaluate, and evidence-synthesis platforms demonstrate willingness to pay for adjacent capabilities.

The product is differentiated, but not by basic bibliometrics. Its defensibility can come from the maintained ontology, structured findings, evidence-type separation, cross-domain relationships, provenance, validation, longitudinal history, and workflow/API integration. The charts themselves, the open code, and bibliographic metadata are weak moats.

The recommended business model is **open core with paid intelligence services**: preserve an open, auditable public map while charging for continuously updated hosted datasets, alerts, exports, saved workspaces, team features, custom/private evidence, deeper clinical-development layers, API access, service levels, and analyst-supported reports. Any data already released as CC0 or sent to a browser cannot later be made technically exclusive.

## 1. What the product actually offers

Analyze currently provides four lenses—All, Compounds, Authors, and Journals—with controls for research area, concept, paper type, text/access status, year, and search. Depending on the lens, it offers:

- evidence composition by primary study, meta-analysis, and review;
- publication history and recent momentum;
- leading compounds, authors, and journals;
- research-area and concept profiles;
- primary-study volume versus synthesis volume;
- cross-domain and cross-concept overlap;
- entity landscapes combining breadth, volume, and recent activity;
- entity-by-area or entity-by-concept coverage matrices;
- focused profiles, relationship graphs, reciprocal rankings, and record drill-down;
- compound co-mention and area-comparison views;
- shareable URL state.

This sits on top of a corpus of more than 21,000 publications, separated into primary studies, reviews, and meta-analyses, with ten evidence domains and source-traceable records. The project already preserves null, mixed, uncertain, and positive findings, and it distinguishes full-text from abstract-only extraction. Those characteristics matter more than raw paper count because they support interpretation and auditability. See the project [README](../README.md), [evidence policy](evidence_policy.md), and [public-data policy](public_data_policy.md).

### The core jobs it can do

The interface is particularly good for four questions:

1. **Orientation:** What has been studied, in which parts of the field, and how has that changed?
2. **Gap discovery:** Which compounds, outcomes, populations, mechanisms, or contexts appear under-studied or under-synthesised?
3. **Landscape comparison:** How do compounds, authors, journals, research areas, and concepts differ in volume, breadth, and recent activity?
4. **Evidence navigation:** Which underlying papers contribute to an apparent trend or relationship?

The fourth job is an important differentiator from a conventional market chart: a user can inspect the evidence rather than only consume a summary.

## 2. Who would find it useful

| Audience | Decisions it can support now | Present usefulness | Likely willingness to pay | What would increase value most |
|---|---|---:|---:|---|
| Psychedelic researchers and labs | Literature orientation, collaborator and journal discovery, topic selection, review scoping | High | Low–medium individually; medium institutionally | Alerts, export, saved searches, citation analysis, institution/funder views |
| Systematic reviewers and guideline teams | Scoping, corpus discovery, evidence clustering, update monitoring | High for discovery; medium for synthesis | Medium | PRISMA-compatible workflow, deduplication, screening state, risk of bias, certainty, effect sizes |
| Research centres, libraries, and universities | Portfolio mapping, benchmarking, collaboration strategy, public communication | High | Medium | Institution normalisation, affiliation history, benchmarks, report export, SSO/team access |
| Funders and philanthropies | Find neglected areas, duplication, emerging investigators, portfolio balance | High conceptually | Medium–high | Grant linkage, investigator/institution geography, gap methodology, outcome and population coverage |
| Biotech/pharma R&D and medical affairs | Indication, mechanism, safety, comparator, KOL, and evidence landscapes | Medium–high | High | Trial registry integration, sponsor/assets, phases, endpoints, patents, regulatory events, quality assessment |
| CROs, clinics, and trial designers | Protocol precedent, endpoints, dosing, administration, follow-up, sites and investigators | Medium | Medium–high | Structured trial design, sites, recruitment, eligibility, therapist model, expectancy/blinding, adverse events |
| Policy, regulators, HTA, and public health | Field surveillance, safety signals, evidence gaps, real-world use | Medium–high | Medium–high institutionally | Validated evidence grading, population/geography, harms denominators, policy/regulatory linkage, versioned reports |
| Investors, consultants, and corporate development | Scientific diligence, KOL mapping, landscape context | Medium | High if decision-ready | Companies/assets, catalysts, financing/deals, IP, market forecasts, trial readouts and failure history |
| Clinicians and educators | Understand evidence breadth and locate material | Medium | Low individually | Clinical question views, evidence summaries, guideline status, safety and interaction views |
| Journalists and the interested public | Understand growth and composition of the field | High interest | Low | Plain-language explanations, stable shareable charts, careful caveats |
| Data scientists and AI product teams | Use a clean domain graph for retrieval, evaluation, or model development | Potentially high | Medium–high | Rich documented API, bulk/versioned data, licences, identifiers, embeddings, change feeds, SLAs |

The best initial customers are probably **organisations whose job is to allocate attention or money across the field**: funders, research centres, biotech strategy teams, evidence groups, and specialist advisers. Individual researchers are excellent users and advocates, but generally weaker economic buyers.

## 3. The broader market in which it sits

### A. Research analytics and bibliometrics

Commercial research-intelligence systems already sell publication trends, impact, collaboration, institutions, countries, emerging topics, and benchmarking:

- [Elsevier SciVal](https://www.elsevier.com/en-in/products/scival) covers research performance, benchmarking, collaboration, and trends across more than 24,800 institutions and 21 million researchers. Its topic system explicitly uses momentum and prominence and is marketed to universities, funders, governments, and corporate R&D teams.
- [Dimensions Landscape & Discovery](https://dimensions.digital-science.com/products/all-products/landscape-discovery/) creates custom visual landscapes from publications, grants, patents, and clinical trials, including growth, organisations, funding, collaboration, and translation.
- [Clarivate InCites](https://clarivate.com/incites-benchmarking-analytics) provides citation-normalised benchmarking, trend identification, and research-program and funder analysis.
- [The Lens](https://about.lens.org/what/) links scholarly works to patents and offers a free public layer plus licensed APIs and custom datasets.

There is also a powerful free/open substitute layer. [OpenAlex](https://developers.openalex.org/) provides a CC0 scholarly graph and API; [Bibliometrix](https://www.bibliometrix.org/) and [VOSviewer](https://www.vosviewer.com/) provide free science-mapping, co-authorship, citation, keyword, and clustering tools.

**Implication:** publication counts, author rankings, journal rankings, topic trends, and co-occurrence networks are useful but not unique. A technically capable user can recreate much of that layer from OpenAlex or bibliographic databases. Analyze should not be positioned primarily as a bibliometrics product.

### B. Life-science and competitive intelligence

High-value commercial products join science to assets, trials, organisations, patents, deals, and forecasts:

- [Citeline Pharmaprojects](https://www.citeline.com/en/products-services/clinical/pharmaprojects) profiles drug pipelines, development status, companies, competitors, and trends, with expert curation and use by pharma, biotech, and CRO teams.
- [Clarivate Cortellis Drug Discovery Intelligence](https://clarivate.com/life-sciences-healthcare/research-development/discovery-development/cortellis-pre-clinical-intelligence/) links drugs, targets, diseases, biomarkers, models, patents, safety, and other curated evidence for pharma, biotech, academia, CROs, and government.
- [Evaluate](https://www.evaluate.com/solutions/) serves pharma, biotech, consultants, banks, venture capital, private equity, and public-market investors with pipeline, product, company, deal, forecast, and commercial data.
- [BioCentury BCIQ](https://bciq.biocentury.com/) focuses on biopharma companies, pipelines, financing, deals, earnings, investing, and dealmaking.

**Implication:** the willingness to pay is highest when an evidence landscape helps a customer make an asset, portfolio, trial, partnering, funding, or investment decision. Analyze currently supplies the scientific half of that decision, but not the commercial-development half.

### C. Systematic-review and living-evidence platforms

[DistillerSR](https://www.distillersr.com/products/distillersr-systematic-review-software), [Nested Knowledge](https://about.nested-knowledge.com/), and [Covidence](https://www.covidence.org/about-us-covidence/) sell systematic-review workflows, screening, extraction, audit trails, critical appraisal, PRISMA reporting, and living updates. DistillerSR reports more than 300 customers, while Covidence reports use by hundreds of organisations. [Epistemonikos Living Evidence](https://living-evidence.epistemonikos.org/) demonstrates the public-interest form of continuously updated synthesis.

**Implication:** Analyze is not currently a review-production system. Its opportunity is different: it is an already-maintained, field-wide evidence environment. It can become an upstream discovery and monitoring layer for review teams, or add review-grade workflows for selected questions.

## 4. The psychedelic-specific market

There is already a small but demonstrable paid market.

### Direct and adjacent providers

- [Blossom](https://www.moreblossom.com/pricing) is the closest direct comparison. It offers daily-updated psychedelic papers, trials, compounds, outcomes, organisations, and regulatory information. Its listed individual subscription is $249 per year, with research-team and enterprise offerings. Its [developer/API product](https://www.moreblossom.com/developers) exposes papers, trials, forecasts, compounds, topics, countries, people, journals, outcome measures, adverse events, trial arms, dosing, eligibility, and catalysts.
- [Psychedelic Alpha](https://psychedelicalpha.com/) serves researchers, practitioners, pharma/healthcare, funders, and industry readers through news, policy and pipeline trackers, paid membership, reports, and advisory work. Its [drug-development tracker](https://psychedelicalpha.com/resources/psychedelic-drug-development-tracker/) focuses on the commercial pipeline, while its [advisory practice](https://psychedelicalpha.com/advisory/) describes work for investors, philanthropists, government agencies, startups, and larger firms.
- [Psychedelic Business Intelligence](https://www.psychedelicbusiness.co/) sells industry analysis covering market size, segmentation, growth, capital, M&A, regulatory developments, and datasets for executives, companies, clinics, and investors.

The academic literature also already contains static psychedelic bibliometric studies. Examples include a 2022 analysis of 31,687 documents and their themes, performance, and influence networks ([PubMed](https://pubmed.ncbi.nlm.nih.gov/36191546/)); a bibliometric analysis of psychedelic clinical-study publications through 2021 ([PubMed](https://pubmed.ncbi.nlm.nih.gov/36218281/)); and newer indication-specific studies on psychedelics for depression ([PubMed](https://pubmed.ncbi.nlm.nih.gov/39281459/)] and psilocybin in mental disorders ([PubMed](https://pubmed.ncbi.nlm.nih.gov/40933206/)).

**Implication:** neither “psychedelic research trends” nor “a searchable psychedelic evidence database” is unique by itself. The opportunity is to outperform static papers and complement or differentiate from paid databases through a richer evidence graph, transparent provenance, cross-domain relationships, and flexible exploratory analysis.

### Where Analyze fits against the psychedelic alternatives

| Capability | Analyze today | Static bibliometric papers | Blossom | Psychedelic Alpha / business intelligence |
|---|---|---|---|---|
| Continuously explorable research landscape | Strong | No | Strong | Partial |
| Evidence types separated | Strong | Varies | Present, depth unclear publicly | Limited |
| Research-domain and concept relationships | Strong | Usually keyword based | Strong topic metadata | Limited |
| Source traceability and open auditability | Strong | Strong for method, fixed corpus | Proprietary curation | Proprietary/editorial |
| Record-level structured scientific findings | Potentially distinctive | Rare | Some structured fields/summaries | Limited |
| Trials, arms, endpoints, eligibility | Partial/not central | Sometimes | Stronger | Pipeline-level |
| Companies, assets, sponsors, phases | Weak | Rare | Present | Strong |
| Patents, deals, financing, forecasts, catalysts | Absent | Absent | Some forecasts/catalysts | Stronger |
| Citation/institution/country/funder analytics | Incomplete | Often strong | Some | Some |
| Open-source and reusable | Strong | Results only | No | No |

Public product pages do not expose every provider’s data model, so this comparison should be validated in product demos. Nevertheless, the strategic boundary is clear: **Analyze is deeper than conventional trend reporting in evidence structure, but currently shallower than commercial-intelligence products in development and market context.**

## 5. How unique is it?

### Meaningfully distinctive

1. **A field-wide living evidence graph rather than a set of isolated dashboards.** The same ontology and records support multiple analytical cuts.
2. **Cross-domain structure.** Conditions, safety, mechanisms, brain systems, cognition, subjective effects, pharmacokinetics, intervention context, and real-world/public-health evidence can be related in one environment.
3. **Evidence-type separation.** Primary studies, reviews, and meta-analyses are not treated as interchangeable publications.
4. **Provenance and drill-down.** Aggregate patterns can be traced to source records, with extraction depth and validation context.
5. **Negative and uncertain evidence is retained.** That reduces the usual “only interesting positive findings” distortion if it is surfaced effectively.
6. **An open and inspectable foundation.** This can produce trust, citations, contributions, and adoption that closed databases struggle to obtain.

### Useful but easy to copy

- publication timelines;
- author and journal rankings;
- raw volume and absolute-growth charts;
- topic and entity co-occurrence;
- basic filters and matrices;
- attractive interactive visualisation by itself.

### The potential moat

The defensible asset is the accumulated system around the interface:

> ontology + identity resolution + structured evidence extraction + validation + provenance + continuous updates + historical versions + user workflow + trusted interpretation

If those elements are reliable, a competitor can copy the charts without copying the product. If the underlying semantics and counts are not reliable, visual richness will amplify rather than solve the trust problem.

## 6. Product issues found in the live review

These are not cosmetic details. They affect whether an analyst can cite or act on a result.

### Highest priority: make every denominator and scope unambiguous

- Some panels produced different totals for what appeared to be the same focused entity and filter scope. For example, a compound coverage matrix and its research profile showed different publication totals in the same session. Every number should expose its grain, inclusion rules, and denominator in a tooltip or details drawer, and automated cross-panel consistency tests should be added.
- The focused concept-overlap panel appeared not to change when the access filter changed, while the evidence profile did change. If a panel intentionally ignores a filter, label that directly; otherwise all panels should inherit the visible scope.
- Concept-menu counts appeared global even inside a focused compound view. Label global counts or replace them with counts under the current focus.
- The default inherited “Open” state can silently exclude a large part of the corpus. Analysis should probably default to All, or display an unmistakable persistent scope banner.
- Internally, the “Open access” filter appears to be based on article/full-text extraction availability. That is not necessarily identical to conventional legal open-access status. Rename it to “text availability” or model legal OA status separately.

### Highest priority: avoid analytical overclaiming

- **“Evidence maturity”** currently means primary-study volume plotted against review/meta-analysis volume. That is synthesis coverage, not necessarily maturity or evidential quality. Rename it to **“primary evidence vs synthesis coverage”** unless risk of bias, certainty, replication, sample size, and effect consistency are incorporated.
- **“Studied together”** is based on papers mentioning both compounds. In reviews, co-mention need not mean a head-to-head or combination study. Use **“co-mentioned in the same publication”** and create separate comparative-study and combination-study views when the design data support them.
- Momentum is based largely on absolute recent-versus-prior publication counts, favouring already large topics. Add relative growth, annualised growth, share-of-field growth, acceleration, and a minimum-base threshold. Allow the user to switch metrics.
- The latest window includes an incomplete 2026. Mark partial years and either annualise cautiously, compare equal completed periods, or exclude the incomplete year from rankings.

### Important usability and ontology refinements

- Spell out ambiguous compound labels. **DOI** is correctly the psychedelic 2,5-dimethoxy-4-iodoamphetamine, but most users initially read it as “digital object identifier.” Display “DOI (2,5-dimethoxy-4-iodoamphetamine).”
- Make compound hierarchies explicit. Esketamine/S-ketamine should be scientifically distinguishable from racemic ketamine, while users should also be able to aggregate related forms.
- Improve long-label wrapping in charts and make chart data available as accessible tables.
- Put a compact “How this is calculated” disclosure on every analytical module, including unique-paper versus claim counts, evidence types included, date coverage, and filter exceptions.

## 7. What a mature product in this market would normally include

### A. Scientific analytics missing or underexposed

- citation impact, field-normalised impact, influential references, and citation networks;
- institutions, countries, affiliations, collaboration networks, and geographic coverage;
- grants and funders, including grant-to-publication linkage—[NIH RePORT](https://www.grants.nih.gov/funding/explore-data-on-funded-projects) is one relevant public source;
- populations, diagnoses, subgroups, setting, sample size, comparator, dose, route, session model, follow-up, outcome instruments, and adverse-event denominators as first-class filters;
- effect direction and magnitude, confidence intervals, heterogeneity, replication, and contradiction views;
- risk of bias, certainty/quality, study power, preregistration, data/code availability, and retraction/correction status;
- explicit evidence-gap maps based on a declared framework rather than low publication counts alone;
- longitudinal snapshots so users can ask what changed since a date.

### B. Psychedelic-specific analytical fields

Psychedelic studies have design issues that ordinary publication metadata do not capture. FDA’s draft industry guidance discusses the special difficulty of interpretable trials involving acute perceptual effects and psychological support ([FDA guidance PDF](https://www.fda.gov/media/169694/download)). Useful structured fields include:

- expectancy assessment, blinding method and blinding success;
- active placebo or comparator rationale;
- preparation, monitoring, psychological support, therapist qualifications, number of therapists, and treatment manual;
- treatment fidelity and separation of drug and psychotherapy effects;
- acute subjective intensity and mediation analyses;
- rescue medication, cardiovascular monitoring, suicidality, mania/psychosis, abuse potential, and longer-term adverse events;
- prior psychedelic exposure and participant expectancy;
- durability, retreatment, functional outcomes, and healthcare utilisation;
- setting, music, group versus individual administration, and remote components;
- access, equity, race/ethnicity, sex/gender, socioeconomic status, and geographic representativeness.

The graph already captures parts of dose, administration, session context, safety, follow-up, and design. The commercial opportunity is to normalise these consistently and promote them from record details into comparative analytics.

### C. Clinical-development and commercial context

To compete for biotech, investor, and strategy budgets, add:

- registered and unregistered trials, phase, status, sponsor, sites, arms, endpoints, eligibility, enrolment, dates, and readouts;
- named assets, salts/formulations, prodrugs, delivery methods, ownership/licensing, target product profile, and indication strategy;
- sponsor/company histories and parent/subsidiary resolution;
- patents, families, claims themes, expiry, assignments, and scholarly-to-patent links;
- regulatory designations, meetings, submissions, decisions, and jurisdictional policy changes;
- partnerships, licensing, financing, M&A, trial costs, and catalysts;
- analyst forecasts and scenario models, clearly separated from observed evidence.

This does not all need to live in the open project. It is a natural paid layer joined to the public scientific graph.

### D. Professional workflow features

- saved views, watchlists, email/Slack alerts, and “what changed?” digests;
- CSV/Excel/image/citation exports and reproducible report snapshots;
- team annotations, collections, comments, and private workspaces;
- documented API and bulk data with stable identifiers, versions, change feeds, and SLAs;
- custom taxonomies and private-corpus ingestion;
- report builder and embeddable charts;
- confidence/provenance filters and an audit log;
- analyst support for high-value questions.

These workflow features are often more monetisable than another chart because they make the product part of a repeated organisational process.

## 8. Positioning and business model

### Recommended positioning

**Category:** Living psychedelic evidence intelligence  
**Promise:** “See what psychedelic science has studied, where evidence is accumulating, how domains connect, and which sources support every pattern.”

Avoid presenting the current product simply as “market intelligence.” That phrase sets an expectation of companies, assets, trials, IP, financing, forecasts, and catalysts. Use **scientific/evidence intelligence** now and add **development intelligence** as a paid extension.

### Open-core model

Keep open:

- the public explorer and major evidence map;
- transparent methodology, provenance, and definitions;
- stable public snapshots or a meaningful public API;
- code that supports scientific reproducibility;
- selected baseline analyses suitable for citation and public education.

Charge for:

- continuously updated hosted datasets and change alerts;
- advanced exports, saved workspaces, watchlists, collaboration, and private notes;
- full structured evidence fields and higher API limits;
- trials/assets/sponsors, patents, grants, regulatory, company, deal, and catalyst layers;
- custom taxonomies, private-document ingestion, bespoke landscapes, and analyst briefings;
- institutional authentication, SLAs, data feeds, and support.

The legal and technical boundary matters. The current [public-data policy](public_data_policy.md) correctly notes that browser-visible data are retrievable. Previously released CC0 data cannot practically be made exclusive after the fact. A commercial boundary should therefore apply prospectively to new hosted services, private inputs, continuously updated derived datasets, and features enforced server-side. Specific licence changes should be reviewed by counsel.

### Indicative—not yet validated—commercial packaging

| Tier | Illustrative offer | Price hypothesis |
|---|---|---:|
| Open | Public map, basic Analyze, methodology, source links | Free |
| Professional | Alerts, saved views, richer filters, exports, advanced evidence fields | $20–50/month or $200–500/year |
| Team / research centre | Shared workspace, API allowance, reports, institution/funder views, support | $3,000–15,000/year |
| Enterprise / custom | Private data, clinical-development and IP layers, feeds, custom analysis, SLA | $15,000–75,000+ per year |

These are interview hypotheses, not a market-size claim. The low tier is anchored loosely by current listed prices from Blossom and Psychedelic Alpha; enterprise value depends on adding decision-grade data and service.

## 9. Recommended product sequence

### Next 4–8 weeks: make the analysis trustworthy and legible

1. Publish a metric dictionary and per-panel calculation disclosures.
2. Fix or explain all cross-panel count and filter-scope inconsistencies.
3. Rename “maturity” and “studied together”; mark partial years.
4. Add alternative momentum metrics and comparable completed periods.
5. Clarify compound aliases/hierarchies and ambiguous labels.
6. Add accessible chart tables and reliable CSV/image export.
7. Create three task-oriented entry points: **Find a research gap**, **Compare compounds**, and **Monitor a field**.

### Next 2–4 months: prove repeated professional use

1. Add saved analyses, watchlists, and change alerts.
2. Add institution, geography, funder, grant, and collaboration views.
3. Promote design, population, dosing, comparator, outcome, follow-up, and safety fields into filters and matrices.
4. Add evidence-quality layers and a contradiction/replication view.
5. Offer versioned exports and a better documented API.
6. Produce one funder-grade gap report and one biotech-grade indication/competitor report from the system.

### Next 4–12 months: choose the commercial wedge

Choose one of two routes after customer discovery:

- **Evidence/funder wedge:** grants, portfolios, gaps, research capacity, living synthesis, and policy-grade reporting.
- **Biotech/development wedge:** trials, assets, sponsors, KOLs, endpoints, safety, patents, regulatory events, and catalysts.

Trying to build both simultaneously would spread the ontology and data-acquisition effort too thin. The existing graph makes the evidence/funder route easier; the biotech route may support higher contracts.

## 10. Validation plan

Conduct 12–18 interviews across six groups: research centres, systematic reviewers, funders/philanthropies, biotech/pharma, CRO/advisory, and investors. Do not mainly ask whether the dashboard is interesting. Ask for the last real decision they made, what sources and spreadsheets they used, what was slow or uncertain, how often the decision recurs, and who owns its budget.

Test three paid concierge products before building large new data layers:

1. **Evidence-gap and grant-portfolio map** for a funder or research centre.
2. **Indication/compound/KOL landscape** for a biotech or strategy team.
3. **Monthly “what changed?” field monitor** for a professional team.

The strongest validation would be five paid design partners who each name a recurring decision, accept the data definitions, and use an update or export more than once. Page views or compliments alone will not validate a market.

## 11. Overall judgement

Analyze has already crossed the line from “interesting visualisation” to a useful research-intelligence interface. It gives people unusually flexible control over a specialised, structured corpus, and its ability to connect an overview to the underlying evidence is valuable.

Its present strengths are best suited to research orientation, gap discovery, portfolio understanding, and evidence navigation. Its main weaknesses are analytical semantics, missing quality/impact/context dimensions, and the absence of the asset/trial/company/IP layer required for high-value commercial intelligence.

The psychedelic niche is large enough to support a specialist professional product, especially as a mix of subscriptions, institutional access, data/API services, and bespoke analysis. It is less likely to become a very large software market on psychedelic publication analytics alone. The larger strategic option is to treat this as the first vertical implementation of a reusable **living evidence-intelligence engine** for fast-moving scientific domains, with psychedelics as the place where the ontology, provenance model, and product workflow are proved.

The central product decision is therefore not “open source or closed source?” It is:

> Which recurring, high-consequence decision will the graph help a specific buyer make better, and which continuously maintained data and workflow make that outcome difficult to reproduce?

The public graph can remain the trust and distribution layer. The maintained decision-support layer can be the business.

## Research note

This assessment combined a repository and live-interface review with current provider research. The literature comparison used PubMed searches for psychedelic bibliometric/scientometric analyses. Provider capabilities and prices reflect public product pages available on the assessment date and should be checked in sales conversations or demonstrations before procurement or formal competitive claims.
