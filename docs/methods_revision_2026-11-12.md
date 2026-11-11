# Methods page: proposed revision (12 Nov 2026)

Proposed text for `methods/index.html`, section by section, in the page's current order. The structure is unchanged; two blocks are removed (the PCP paragraph and the PCP historical-search box). Each section has a short note on what changed and why. Nothing is applied to the page yet.

## Inaccuracies found in the current text

1. **Out of date (overview):** "uses GPT-6 Luna for new title-and-abstract screening and the planned replacement evidence extraction. The published graph continues to represent its last completed release while that replacement is prepared." With release 3.0.0, all screening and extraction are done with GPT-6 Luna.
2. **Overstated (Validate and publish):** "Extracted findings are checked for … support in the source publication." No step checks that a finding's supporting text appears in the source. What exists: findings must fill the schema's required fields, and a finding whose stated location is only the background, introduction or references is kept out of the main graph.
3. **Incomplete (rules-based screening):** the rules also exclude letters, editorials, comments and news items without original data, retraction notices, supplementary material and data deposits. The list names only protocols, corrections, peer-review and citation-only records.
4. **Missing:** retraction checks. Every build re-checks all papers; retracted publications are held out of the graph, and expressions of concern are shown with the paper.
5. **Missing (source text):** the preprint rule (decision D1): a preprint's text is not used for the published article, while accepted manuscripts are. Also, a converted PDF without an article body (for example a meeting abstract) is not used as full text.
6. **Vague:** "Each publication is then interpreted according to what it actually contains" and "During evidence extraction, each selected report is also evaluated for graph representation".

---

## Methods (page introduction)

> How the graph is built: literature search, screening, source text preparation, evidence extraction, and graph assembly.

*Note:* "how everything is maintained" is covered by the last overview step and the release notes.

## Pipeline overview

> The pipeline turns database search results into graph findings in seven steps, summarized below and described in detail in the sections that follow. Searches are broad; the later steps decide which publications and findings enter the graph. Screening and extraction combine fixed rules with GPT-6 Luna, a large language model (LLM). Every finding in the graph links to its publication and, where available, to its location in the text. The pipeline is [open source](…), and a [workflow guide](…) documents its implementation.

*Note:* replaces the paragraph you flagged. It says what the overview is, states the one design principle (broad search, selective inclusion), names the model once, and states traceability concretely. The out-of-date sentence about planned extraction is removed.

**1. Define the evidence scope**
> Fixed vocabularies define the compounds and research areas the graph covers: molecular targets, pathways and readouts, brain systems, cognition and behavior, subjective experience, pharmacokinetics and exposure, intervention context, real-world use, clinical outcomes and functioning, and safety. The same vocabularies determine what the searches look for.

**2. Find records**
> PubMed and OpenAlex are searched for each compound, alone and combined with each research area. Results are merged by DOI. Bibliographic data, abstracts and links to full text are added from PubMed, PMC, OpenAlex, Crossref, Semantic Scholar and Unpaywall.

**3. Screen and classify records**
> Rules exclude publication types that are not source evidence and records without a usable English abstract. GPT-6 Luna then reads each remaining title and abstract, decides whether the publication is in scope, and records its publication type and research areas. These two classifications select the extraction instructions.

**4. Prepare source text**
> Full text is taken from Europe PMC or PubMed Central XML when available, and otherwise from PDFs converted with GROBID. Each text is checked against the publication's identifiers and title before it is used.

**5. Extract evidence**
> GPT-6 Luna extracts findings using instructions specific to the publication type, the research area, and whether the full text or only the abstract is available. Each finding records the compound or exposure, what was measured or examined, the study context, and its location in the text.

**6. Build the graph**
> Compound names and other concepts are mapped to consistent graph entities. Findings that cannot be mapped without changing their meaning, or that are reported only in a paper's background, are kept out of the graph.

**7. Update**
> Each update searches the period since the previous search, overlapping it by 14 days, and passes new records through the same steps. Each update is published as a numbered release with release notes; earlier releases remain available.

*Note:* "Validate and publish" becomes "Build the graph", with the overstated support check removed and retractions added. "Maintain the living graph" becomes "Update" and says what an update does instead of what it is designed to do.

## Literature search strategy

> The searches combine two vocabularies. The compound vocabulary contains compound names, chemical, botanical and common aliases specific enough to identify each compound, and psychedelic class terms. Each research area has its own vocabulary of concepts, methods, measures and outcomes, with PubMed subject headings where available.
>
> In each research area search, the compound terms are joined with OR, the research area terms are joined with OR, and the two groups are combined with AND. Each compound is also searched alone, to find relevant publications whose wording falls outside the research area vocabularies. Aliases that are short or have other common meanings are searched only together with drug-related terms; for example, PCP must appear with terms such as NMDA, ketamine or intoxication, which avoids matches for primary care and pneumonia.
>
> PubMed queries use text words together with MeSH and Supplementary Concept terms; OpenAlex queries search titles and abstracts. The two databases index the literature differently, so together they find records that either would miss. Searches cover publications from 1800 onward, and a compound added to the scope is searched across its full publication history. Results are merged by DOI. Coverage depends on the vocabularies, query structures and the two databases; the vocabularies are revised when gaps are found. The vocabularies are listed below.

*Removed:* the paragraph on phencyclidine's addition on 19 October and the "PCP historical search — 19 October 2026" box. PCP stays in the compound list and in the alias examples. The acronym rule is now a general sentence, with PCP as its example. Search dates and counts for specific updates belong in the release notes.

*Removed:* the sentence listing the research areas a second time, which repeated the vocabulary tables below it.

## Screening and classification

> Screening has two stages. The first applies fixed rules to bibliographic metadata and abstracts; the second uses GPT-6 Luna to judge relevance from the title and abstract.

**1. Rules-based screening** (list)
> Records are excluded before LLM screening when:
> - no abstract of at least 50 words is available, or the abstract is not usable;
> - the publication is not in English;
> - the publication is a book, book chapter, thesis, preprint, or conference abstract;
> - the record is a protocol, correction, retraction notice, peer-review record, supplementary material, data deposit, or citation-only record;
> - the publication is a letter, editorial, comment, or news item without original data.

**2. LLM-based screening and classification** (cards, unchanged structure)
> For the remaining records, GPT-6 Luna reads the title and abstract, with publication labels, MeSH terms and keywords as supporting context, and makes three linked decisions:
> - **Inclusion:** whether a psychedelic compound, exposure or intervention has a substantive drug-specific finding, or is a central topic of a review or meta-analysis. Background examples, incidental mentions and items in broad lists do not qualify. When relevance is plausible but the abstract is too limited to decide, the publication is retained.
> - **Publication type:** primary study, meta-analysis, review, or another type.
> - **Research areas:** the research areas the publication substantially addresses.

*Note:* the current prose paragraph and the two cards say the same things twice. The proposal keeps the cards and moves the inclusion criterion into the first card. The rule list now matches the screening code.

## Source text preparation

> For each selected publication, the pipeline first looks for full-text XML from Europe PMC or PubMed Central, in the Journal Article Tag Suite (JATS) format, which marks sections, paragraphs, tables, figures, references and identifiers. When an XML record contains several articles, only the one whose DOI matches the publication is kept. Otherwise, an accessible PDF is retrieved and converted with GROBID to Text Encoding Initiative (TEI) XML, which reconstructs the same structure from the PDF. Openly accessible PDFs that the automated retrieval cannot obtain are downloaded manually and enter the same conversion.
>
> Before a text is used, its identifiers and title are checked against the publication. A preprint's text is not used for the published article; an accepted author manuscript is used. A converted document without an article body, such as a meeting abstract, is not used as full text. When no usable full text is available, the abstract is used. The [source text workflow](…) documents retrieval, file checks, conversion and provenance.

*Note:* adds the manual downloads (a real part of retrieval), the preprint rule and the article-body rule. Removes "the original XML, parsed sections, and source metadata are stored together", which describes storage rather than method.

## Evidence extraction

> For each paper, GPT-6 Luna receives three inputs: the source text, an extraction prompt that describes what evidence to identify, and an output schema that defines the fields of each finding. The prompt and schema are selected by publication type and, for primary studies, by research area; full text and abstracts have separate prompt variants, and abstract extraction is limited to what the abstract states. Primary study prompts target original empirical findings. Meta-analysis prompts record the questions and pooled results, and review prompts record the relationships a review discusses in substantive detail. All prompts instruct the model to extract only what the supplied text states, keep the publication's terminology, and give the location of each finding. Outputs that do not match the schema are rejected; papers with no extractable finding, or flagged for human review, are recorded but not added to the graph.

*Note:* about one sentence shorter; "checked for the required fields" becomes "outputs that do not match the schema are rejected", which is what happens. The diagram is unchanged.

## Entity normalization and graph inclusion

> Compound names and other extracted concepts are mapped to consistent graph entities, while the publication's own wording and context are kept with each finding. Names and spellings of the same compound map to one compound entity; compound classes, combinations, exposure contexts and treatment regimens stay distinct. Other concepts are matched to existing graph entities directly or through recognized aliases, and a broader parent entity is used only when it keeps the original meaning. The repository provides the [compound and entity registry](…) and the [controlled vocabularies](…).
>
> A finding enters the graph when it names a compound, exposure or intervention and a concept that can be represented without changing its meaning. Findings that cannot be mapped confidently, that need human review, or that are reported only in a paper's background, introduction or references are held out. Findings that are valid but too specific for the visualization remain searchable. Retracted publications are held out of the graph; publications with an expression of concern or a partial retraction stay in the graph with the notice shown. The [graph inclusion rules](…) document these decisions.

*Note:* "supported only by background text" becomes the actual rule (the stated location is only the background, introduction or references), and the retraction handling is added. The diagram is unchanged.

## Search results and study selection

> The PRISMA flow diagram reports how many records and reports reached each stage, and the table below it gives the selection decision for every record the searches found. A publication selected for extraction can still be absent from the graph: when its text is insufficient, when extraction fails, or when it reports no finding specific enough to represent.

*Note:* removes "The sections above describe how publications move through the pipeline" and the vague "each selected report is also evaluated for graph representation".

## Search records and selection decisions

> The table lists every record the searches found, its status at each selection stage and, when it was excluded, the reason. Records can be searched by author, title, journal, year or DOI.

## Limitations

> The pipeline is automated at every step, and each step has limits that affect what the graph contains. The searches find publications through their wording, so relevant publications that describe their work in terms outside the search vocabularies can be missed. Screening and extraction use GPT-6 Luna, a cost-efficient language model. It can misjudge whether a publication is relevant or misread a finding, and a more capable model may be more accurate, particularly in judgments that require more nuance.
>
> When no full text is available, findings are extracted from the abstract alone, so they can include only what the abstract reports. Abstracts often leave out details such as sample sizes, comparators, and secondary outcomes, and they can summarize the results less completely or less precisely than the article itself. Full text is also missed for some openly accessible articles, because retrieval depends on article links and open-access metadata from external providers that are not always complete or correct.

*Note:* rewritten as connected prose: each limitation is explained, not just stated.

## Release notes

Unchanged now; the 3.0.0 entry is written with the release metadata. The PCP addition and the 10 Nov 2026 literature update go there.
