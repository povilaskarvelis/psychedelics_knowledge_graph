# Source identity: causes and fix design — 1 November 2026

> **Status, 1 November 2026.** Steps 1–3 of §8 are implemented.
>
> 1. The full-text gate decides per artifact, and a paper whose stored text is rejected falls back to its abstract.
> 2. The shared metadata merge applies curated decisions last.
> 3. `pipeline/identity/` holds the decision file (`data/curated/source_identity_decisions.jsonl`) and the `migrate` command, which gathers 363 decisions on 352 papers from six older files.
>
> The pipeline still reads the older files until step 5.

## Scope and method

This note covers item 4 of the 1 November fix list: findings extracted from a text that is not the paper they are attributed to. It explains how this happened and proposes one way to fix it. That way has two parts: changes to the main pipeline, and helper commands for correcting existing data.

Data checked:

- the current candidate `model_runs/luna_v5_20261017/latest_graph_preview_vocabulary_20261031/kg` (125,199 findings; 83,569 main graph, 41,630 paper detail);
- the frozen extraction inputs and outputs it was built from;
- the candidate ledger, the metadata cache and the full-text store.

Three read-only investigations covered abstracts, full texts, and the extraction and graph stages. They traced 386 abstracts, 223 full texts and every model warning in 41,945 extraction outputs. Their scripts and tables are in the session scratchpad, not in the repository.

Labels:

- **[V]** — checked directly in code or data for this note.
- **[R]** — reproduced by one of the investigations.

"Open access" keeps its project definition (the pipeline obtained the full text). Nothing here proposes re-screening.

---

## 1. Summary

**What reaches the candidate graph.** Rows overlap; do not add them.

| Problem | Papers with findings | Findings (main / detail) |
|---|---:|---:|
| Text from another work: wrong abstract, wrong edition or a collection DOI | 14 | 32 (21 / 11) |
| Correct text shown under another work's title or year | 12 | 38 (22 / 16) |
| Preprint text used for the published paper, not flagged | 44 | 359 (264 / 95) |
| One report counted under two DOIs (full-text pairs) | 42 | 368 duplicated |
| One report counted under two DOIs (shared-abstract groups) | 70 groups | not counted |
| Supplement used as the article | 1 | 4 (4 / 0) |
| Ledger records whose title and DOI belong to different works. They cause the second row, or the paper's evidence is lost (e.g. `10.1007/s12325-023-02623-w`) | 59 confirmed, 168 candidates | — |

Text from another work is rare, but each case is a false statement in the main graph. Examples:

- a 1917 BMJ news item carries three ketamine findings;
- a Crossref funder DOI (`10.13039/501100000780`) is a "paper" with two findings.

The larger effects are versions and duplicates: preprints standing in for published papers, and one report under two DOIs.

**How it happened.** There are six causes:

1. **Upstream records are taken as they come.** 367 of the 386 abstracts that belong to another work came from OpenAlex, whose own record for the DOI holds the other text. OpenAlex legacy work IDs that equal a PubMed PMID merge two works: 34.7% of OpenAlex IDs below 45M disagree between title and abstract, against 1.8% of other IDs.
2. **Records were assembled field by field.** The July discovery promotion took the longest value of each field across records linked by any shared identifier. One record could therefore combine the title of one work with the DOI and abstract of another. Later code does not revisit those rows.
3. **Each retrieval path has its own identity rule, and most accept on one piece of evidence:** a DOI alone, a title alone, or a PMCID alone. Abstracts are never checked after retrieval.
4. **The extraction model sees mismatches but is neither asked nor heard.** The prompts do not ask it to compare title and text. Its warnings are free text, checked by a pattern on primary outputs only.
5. **Decisions do not persist.** Identity decisions are spread over at least six files with different formats. A cleared abstract is refilled from the metadata cache when routes are built. A full rerun empties the file that holds identity holds.
6. **The full-text gate stops everything or nothing.** One unresolved artifact stops all routing; a rejected artifact is never set aside. "Same paper, other version or DOI" cannot be recorded, so versions are either rejected or accepted unmarked, and both copies are counted.

**Fix.**

- **Main pipeline:** one identity module checks every text against its paper with the same rule: an identifier from the source and the title must agree. It writes one verdict per text, which routing, extraction and the graph build read.
- **Decisions:** all identity decisions go into one append-only file that reruns never touch.
- **Corrections:** three helper commands (audit, decide, apply) produce a DOI list. The existing scoped updater then re-extracts or removes only those DOIs. About eight per-incident scripts and six decision files can then be retired.

---

## 2. How it happened

### 2.1 Upstream records are taken as they come

- **OpenAlex abstracts.** OpenAlex abstracts are decoded from `abstract_inverted_index` and accepted by `best_valid_abstract`, which ranks by provider and length (`abstract_quality.py:244-261`) [R].
  - The per-record OpenAlex lookup checks the DOI (`metadata_utils.py:858`) but not whether the text belongs to the titled work [R].
  - Of 386 abstracts that belong to another work:
    - 223 came through discovery promotion and 144 through the per-record OpenAlex lookup;
    - 10 came from Semantic Scholar, 1 from PubMed batch and 1 from Crossref batch;
    - 7 have no recorded provider (pre-July) [R].
- **OpenAlex IDs that equal PMIDs.** Example [V]: `10.1007/s12325-023-02623-w` carries the title of a 2011 ketamine connectivity paper, OpenAlex `W37597153`. PMID 37597153 is the myeloma CAR-T cost study that owns this DOI.
  - The full text fetched by DOI is the myeloma paper, so the ketamine paper's evidence was lost without a warning [R].
  - 59 ledger records have a title that disagrees with PubMed's title for the same DOI, and every one traces to such a collision [R].
- **Non-paper DOIs enter the corpus.** Examples: a funder DOI [V]; issue, ISSN and version DOIs [R].

### 2.2 Records were assembled field by field

- **July promotion.** The 16 July promotion used `first_best`, the longest value of each field across a group linked by shared identifiers (`cf5adef:pipeline/discovery/promote_search_run.py:87-91, 124-125`) [V].
  - A group joined by an ID collision produced one row with one work's title and another work's DOI and abstract.
  - The funder-DOI record was built this way: a ketamine title and a wastewater abstract [R].
- **Current promotion.** The current code anchors on the title that most records agree on (`promote_search_run.py:123-146, 211`). But `merge_candidates` fills only blank cells on rediscovery (`:336`), so the July values remain [R].

### 2.3 Each retrieval path has its own rule

| Path | Accepts when | Missing check |
|---|---|---|
| OpenAlex per-record | the DOI matches | content |
| Semantic Scholar per-record | always | DOI (`metadata_utils.py:1437-1462`) [R] |
| PMC abstract batch | the PMCID matches | DOI (`run_batch_abstract_enrichment.py:293-299`) [R] |
| PubMed abstract batch | PubMed does not list a different DOI | title; PMID-only matches pass (`:327`) [R] |
| PMC / Europe PMC XML | the JATS node's DOI matches | title (`fetch_pmc_fulltext_xml.py:284`) [R] |
| OA PDF, landing page | page-one title score ≥ 0.86 | DOI; numbers are dropped from titles, so editions and years cannot be told apart (`pdf_alternate_sources.py:160`) [V] |
| Manual or browser import | the requested DOI appears anywhere in the first 12,000 characters | other DOIs, unless already in the corpus (`import_manual_pdfs.py:294-321`) [R] |
| Audit rule R1 | exact DOI plus a JATS or TEI header | title (`source_identity.py:587-590`) [V] |
| Audit rule R1d | title score ≥ 0.88 with no DOI found | supplement detection [V] |
| Audit rule R4 | page-one title rescue | DOI; it accepted all 223 conflicting artifacts on 22 October [R] |

Consequences:

- **Abstracts are never identity-checked.**
  - `source_identity_verified` is False for all 13,457 abstract-only records and all 21,705 abstract-only routes [V].
  - `abstract_quality.py:119-163` checks form only: no title–abstract agreement and no check for the same text on other DOIs [R].
  - The ledger does not record which provider supplied an abstract. `enrich_paper_metadata.py:312` labels it with the first provider that responded, so 5,205 abstracts are labelled Unpaywall, which supplies no abstracts [R].
- **Full texts with a conflicting DOI are mostly the same paper.** Of the 223 [R]:
  - 47 are preprints;
  - 82 are repository deposits or version DOIs;
  - 30 are the same article under another publisher DOI;
  - 47 are DOI-reading errors (truncated DOIs, `.supp` suffixes, ISSN or issue DOIs) where the text is the requested paper;
  - 10 are containers that hold the target with neighbouring items, 4 are peer-review reports, and 3 are unrelated.
- **Two concrete defects:**
  - The South Australian Drug Trends 2020 record received the 2025 edition because numbers are dropped from titles. Its 4 main findings describe 2025 interviews [R].
  - `10.1038/s41467-026-70885-3` was accepted by R1d although the PDF is the supplement; its 4 main findings come from Supplementary Figures 14–15 [R].

### 2.4 The extraction model sees mismatches but is neither asked nor heard

- **Not asked.** The prompts never ask the model to compare the title or metadata with the text. The schemas have no identity field (`primary_article_text.md:26-29, 78`) [R].
- **Seen anyway.** The model wrote warnings that title and text belong to different works for 36 DOIs. Hand-reading confirmed 33 [R].
  - Examples: "title and 1917 publication metadata appear inconsistent with the modern ketamine abstract"; "identify a 2020 report, but the article text describes 2025 interviews".
- **Not heard.**
  - Only primary outputs are checked, by a pattern (`run_route_extraction.py:91-105`) that finds about 19 of 41 such DOIs [R].
  - Review and meta-analysis outputs are not checked [R].
  - Converters only join the warnings into the `extraction_warnings` text (`convert_routed_extractions_to_evidence_rows.py:1083`) [R].
  - Nothing after task building reads `source_identity_verified` or `source_text_state` [R].
- **Sometimes not seen.** The model said nothing for 3 of 17 known wrong abstracts. A check for the same abstract on two or more DOIs with dissimilar titles finds 2 of those 3 [R].
- **Source text pinning.** No task was sent a different text from the one it declared. The protection came from frozen packet copies, not from a check: runners re-read packets by ID without comparing fingerprints. If a packet is missing, the primary runner sends the abstract labelled as article text (`run_route_extraction.py:400-425`) [R].

### 2.5 Decisions do not persist

Identity decisions today:

| File | Records | Read by | Problem |
|---|---:|---|---|
| `data/curated/paper_metadata_overrides.json` | 138 | metadata materialization, replay | applied to the ledger only; the route builder refills cleared fields from the cache |
| `pipeline/extract/manual_extraction_route_overrides.json` | 27 holds | route builder, batch runner | emptied by every full rerun (`rerun_luna.py:70-83`) [V] |
| `pipeline/fulltext/source_identity_registry.json` | 112 | the audit only | can only accept; needs title ≥ 0.9, so 36 of the 223 can be recorded only as a PDF hash |
| `pipeline/fulltext/source_identity_pdf_hash_registry.json` | 75 | identity checks | hand-written; no writer exists |
| `pipeline/validate/doi_alias_registry.json` | 129 | about 20 modules | 69 records have no relation type, the rest use 16 ad hoc names; the full-text audit does not read it; it covers 21 of 2,020 shared-abstract groups |
| `data/curated/graph_inclusion_disposition_overrides.json` | `source_not_verified` added today | KG build (uncommitted) | a fifth format |

Further gaps:

- **Cleared abstracts come back.** `merged_extraction_metadata` lets the metadata cache fill blank ledger cells: "Empty candidate strings do not erase a legacy cache value" (`build_extraction_routes.py:1716-1726`) [V]. The 1917 BMJ abstract was cleared by a curated override and returned at task build [R].
- **One-off repair decisions are not reapplied.** `repair_abstract_contamination.py` applied its 16 July decisions once and nothing reapplies them. It also introduced 4 of the 386 wrong texts [R].
- **One script per incident.** Each correction since July added its own script with its own decision format:
  - `repair_abstract_contamination.py`;
  - `repair_extraction_inputs.py`;
  - `apply_pdf_source_url_corrections.py`;
  - `register_retrieved_pdf_aliases.py`;
  - `register_retrieved_pdf_exclusions.py`;
  - `audit_fulltext_source_identity.py` with `source_identity_audit_gate.py`.

### 2.6 The full-text gate stops everything or nothing

- **One unverified artifact stops all routing.** The audit covers the whole store, and routing stops if any artifact is unverified (`source_identity_audit_gate.py:170-174`) [V].
- **Staleness is judged by file times, not code version** (`:94-122`) [V].
- **The pipeline is blocked now.** One artifact (`10.1016/j.jad.2026.121662`) was rewritten after the last audit, so route and packet rebuilds stop today. The scoped updater cannot run until the 223 are resolved [R].
- **A rejected artifact is never set aside.** The paper's route becomes "convert local PDF", which is not runnable, so the paper loses its abstract extraction as well [R].

---

## 3. Principles

1. **One rule, applied where text is attached.** A text (abstract or full text) is verified for a paper only when an identifier taken from the source itself and the title both agree with the paper. The identifier is a DOI, PMID or PMCID in the provider record or document header. Numbers are kept in titles. An identifier alone or a title alone leaves the text unconfirmed.
2. **Two kinds of identity fact, kept apart.**
   - *Work identity*: which identifiers name the same work, and how (other DOI, repository copy, preprint, translation, part of a larger item).
   - *Text binding*: whether a given text belongs to a given work.
3. **One record per paper comes from one source record.** Title, abstract, authors, year and DOI are taken together from one provider record that is bound to the DOI, never field by field across records.
4. **Decisions are data.**
   - Every decision, human or automatic, is one entry in one append-only file.
   - Each entry is bound to the exact text it was made on (SHA-256) and records its evidence and reviewer.
   - Reruns never remove entries; a new decision supersedes an old one.
5. **Fail per item, not per store.** An unverified text is not used, and the paper falls back to its next verified text or is held. The run continues, and the item goes to a review queue.
6. **Findings carry their source.** Each task records the binding it used. The graph build admits findings only from verified bindings, or from versions the policy allows. No other identity logic runs downstream.
7. **Corrections go through the scoped updater.** Change the decision, rebuild the derived tables, and re-extract or remove only the affected DOIs. Nothing outside the scope changes.

---

## 4. Changes to the main pipeline

### 4.1 One identity module

The module, `pipeline/identity/`, is field-agnostic and part of the shared engine:

| File | Content |
|---|---|
| `evidence.py` | Identifiers and titles from provider records and documents. DOI cleaning: truncation, suffixes, issue/ISSN/funder/version DOIs, cited DOIs ignored. Title comparison with numbers kept. Document-kind detection: article, supplement, data statement, container, peer-review report, erratum. |
| `verify.py` | One function: `verify(paper, source) -> verdict, rule, evidence`. |
| `works.py` | The work registry (`doi_alias_registry.json`, widened). |
| `register.py` | Load, validate and append identity decisions. |
| `bindings.py` | The verdict table: one row per paper and text. |

The comparison helpers already in `pipeline/fulltext/source_identity.py` move here, and the old module re-exports them so callers keep working.

Verdicts:

| Verdict | Meaning | Used for extraction |
|---|---|---|
| `verified` | identifier and title agree | yes |
| `version_of` | another version of the same work, per the work registry | per policy (decision D1), and flagged on findings |
| `unconfirmed` | only one kind of evidence | no, until decided |
| `conflict` | identifier and title point to different works | no; if the source's DOI equals the record's DOI, the record itself is suspect |
| `wrong_kind` | supplement only, data statement, container, peer-review report, non-paper DOI | no |
| `model_reported` | the extraction model reported a mismatch | no, until decided |
| `not_this_work` | decided: the text belongs to another work | no |

Two corpus-level checks feed the verdicts:

- the same text fingerprint bound to two works that the registry does not link;
- OpenAlex work IDs that equal a PMID.

### 4.2 Where it runs

1. **Discovery promotion.** Take all bibliographic fields from one provider record. Reject non-paper DOI types. Treat OpenAlex IDs that equal a PMID as unconfirmed until another source agrees.
2. **Metadata enrichment.** Every abstract candidate from every provider becomes a binding with its provider, provider record ID and fingerprint. The ledger abstract is the best verified binding, and `source_identity_verified` then means the same thing for abstracts and full texts.
3. **Full-text acquisition and audit.** Every retrieval path calls `verify`. The gate looks up (DOI, artifact SHA-256) in the verdict table. It never stops the store, and it judges staleness by verifier version and file hash.
4. **Routes and tasks.**
   - Use only usable bindings: fall back to the verified abstract, and hold the paper when nothing is verified.
   - Each task records its binding ID and fingerprint, and the runners re-check that fingerprint when sending and parsing.
   - Curated values are applied once, in one place: the cache can no longer refill a cleared field.
5. **Extraction contract** (at the next contract change).
   - Add a required `source_check` object to the primary, review and meta-analysis schemas: does the text match the title, what kind of document it is, and a note.
   - The prompt asks the model to make this comparison first.
   - A "does not match" answer sets the binding to `model_reported` for that paper.
6. **KG build.** One step holds findings whose binding is not usable. This generalizes the curated-file holds that another session added today (`split_source_identity_holds`, uncommitted) and reads the verdict table instead of three curated files.

### 4.3 Work registry

`doi_alias_registry.json` gets a fixed relation list. Each entry keeps its evidence.

| Relation | Effect |
|---|---|
| `same_work` (alternate or legacy DOI) | deduplicate |
| `repository_copy` | deduplicate |
| `preprint_of` | deduplicate |
| `accepted_manuscript_of` | deduplicate |
| `version_doi_of` | deduplicate |
| `translation_of` | deduplicate |
| `part_of` (supplement, peer-review report, item in a collection) | do not merge |
| `not_a_work` (funder, issue, ISSN DOIs) | remove from the corpus |

Registering the 42 full-text pairs and the 70 shared-abstract groups lets the existing alias suppression count each report once.

---

## 5. Helper commands for corrections

All corrections use four commands plus the scoped updater that already exists.

| Command | What it does | Writes |
|---|---|---|
| `python -m pipeline.identity audit` | Recomputes verdicts from stored evidence. Adds model warnings (the investigation's detector: 93% precision on 43 hand-read warnings), shared-text groups, ID collisions and DOI–title disagreements. Lists everything that feeds the current release with its evidence and a suggested decision. | only `review_queue.csv` in a run folder |
| `python -m pipeline.identity decide` | Appends reviewed decisions, from a CSV or one at a time. Checks that the text hash exists, the verdict and relation are valid, the related DOI exists, and a basis and reviewer are given. Never edits earlier entries; it supersedes them. | `data/curated/source_identity_decisions.jsonl` and the work registry |
| `python -m pipeline.identity apply --update-id …` | Recomputes verdicts with the decisions. Projects them into the ledger and route table. Writes `scope_dois.txt` with every DOI whose usable text changed, and states for each whether it will be re-extracted or only removed. | ledger and route projections; the update folder |
| `run_scoped_paper_update.py prepare / finalize / promote` | Unchanged. Re-extracts or removes exactly the listed DOIs. | as today |
| `python -m pipeline.identity migrate` (once) | Converts the existing identity files (§2.5) and today's curated holds into the decision file and the widened registry. | the same two files |

The commands give these guarantees:

- The audit changes nothing.
- A decision is a reviewed line in a file.
- Applying it changes only the listed DOIs.
- A full rerun reads the same decisions again.

This one route replaces the per-incident scripts listed in §2.5.

---

## 6. Correcting the current candidate

No re-screening is involved. The audit's queue for the candidate will contain, from the investigations:

- 223 conflicting full texts;
- 25 exact-DOI full texts with title similarity below 0.5;
- 33 model-reported different works;
- 98 shared-abstract groups in which 386 DOIs carry text that is not theirs;
- 59 confirmed and 168 candidate DOI–title disagreements.

Expected decisions:

- **DOI-reading errors** (47 full texts): `verified`. The rule fix in `evidence.py` resolves them automatically.
- **Versions and other DOIs** (159 full texts, 70 shared-abstract groups): registry entries. This removes 368 duplicated findings, and preprint findings are flagged or replaced according to decision D1.
- **Text from another work** (14 papers with findings): `not_this_work`. Each paper falls back to its verified abstract and is re-extracted, or is held when no verified text exists. Another session has already recorded 13 of these 14 and holds them in its KG build.
- **Wrong title shown on correct text** (12 papers): replace the title and year from the DOI's registered record. No re-extraction.
- **DOI belongs to another paper** (59 confirmed): find the correct DOI for the screened title, retrieve its text and re-extract. The screening decision stands, because it was made on the right title and abstract.
- **Screening made on another work's abstract** (such as the 1917 item): hold the record (decision D2).

---

## 7. Decisions needed

- **D1. Preprint or accepted-manuscript text for a published paper** (44 papers, 264 main findings).
  - Recommended: use it, flag the findings as extracted from that version, and replace it when the published text becomes available.
  - Alternative: require the published version.
- **D2. Records whose screening was done on another work's abstract.**
  - Recommended: hold them from the graph. This avoids re-screening.
- **D3. A title check against Crossref and DataCite for every DOI.** This is needed to find all record-level DOI errors: 98,135 DOIs have no PubMed record to compare against.
  - It costs about 24,000 read-only lookups for represented papers: about 80 minutes at 5 requests per second.
  - Recommended.

---

## 8. Order of work

| Step | What | Unblocks or changes | Model calls |
|---|---|---|---|
| 1 | Per-item full-text gate: set rejected artifacts aside so the paper falls back to its abstract | Scoped updates can run again | none |
| 2 | Stop the metadata cache from refilling cleared fields | Curated clears hold | none |
| 3 | Identity module, decision file, migration | One place for decisions; no change in outputs | none |
| 4 | `audit` | Review queue for the candidate | none |
| 5 | `decide` and `apply`, then scoped updates for the candidate | Corrected candidate | re-extraction of affected papers only |
| 6 | Ingest changes: one-record assembly, abstract bindings, provenance, ID-collision check | Prevents recurrence for new records; existing abstracts are re-verified offline | none |
| 7 | `source_check` in the extraction contracts | Model check for future runs | at the next contract change |
| 8 | KG gate reads the verdict table | Replaces the curated-file holds | none |

Coordination with other sessions:

- Another session has uncommitted changes to the files below; step 8 should start after those are committed:
  - `pipeline/kg/build_evidence_tables.py`, which adds the source-identity holds;
  - `data/curated/paper_metadata_overrides.json` and `data/curated/graph_inclusion_disposition_overrides.json`.
- Step 3 read the working-tree versions of those two curated files. 26 of the 363 decisions come from entries that are not in git: 23 metadata overrides and 2 graph dispositions not yet committed, and the one record in `data/curated/pdf_source_url_corrections.json`, which git ignores. In a checkout without these entries, `python -m pipeline.identity migrate --check` reports a mismatch. Run the check again after the curated files are committed.
- Steps 1 and 2 touch `pipeline/fulltext/source_identity_audit_gate.py` and `pipeline/extract/build_extraction_routes.py`, which no session is editing now.
