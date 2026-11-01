# Pipeline review — 31 October 2026

> **Status, 1 November 2026.** The code reviewed here was committed in `fb6c963`; the suite then had one failure (`bs4` not installed). Two recommendations were withdrawn by project decision:
>
> - No papers will be re-screened (S1, S2, I3, I9, §4, §7.1 item 4, §7.2 item 7).
> - "Open access" keeps its project definition: the pipeline obtained the paper's full text. Publisher and OpenAlex open-access flags are not used because they are often wrong (U1).
>
> Release safety was addressed on 1 November (not yet published): U3 by a retention policy and a release archive that keeps earlier releases viewable, U2 by frozen paper keys for public refreshes, and U4 by a check that a scoped update's base release is still active. See `docs/r2_deployment.md`.

## Scope and method

This review covers the whole pipeline, from search to the public site and API. It reviews the current working tree, including about 17,700 uncommitted lines of pipeline changes. The data checked are:

- the 30 October local candidate `luna_v5_20261030_core_pipeline_repairs`: 23,058 represented publications and 118,324 findings;
- the frozen Luna V5 inputs and outputs under `data/processed/model_runs/luna_v5_20261017/`;
- the deployed release `living_update_20260917_author_identity_reviewed`.

Seven stage reviews ran in parallel: discovery; metadata and prescreen; screening and routing; full text; extraction; normalization and KG; and release, UI and API. Each read the code, reproduced suspected defects on synthetic inputs and queried the saved data. I added cross-stage checks and re-checked the most consequential claims against the code and the candidate tables.

No model calls were made and nothing in the repository was changed apart from this file. This is not a representative accuracy study. Counts describe how many rows are affected by an identified mechanism; they are not error rates. The stage reviews' reproduction scripts and query outputs (117 scripts) were written to a temporary session folder outside the repository and are not preserved with this document.

Evidence labels:

- **[V]** — I checked it directly against the code or the candidate data during this review.
- **[R]** — reproduced by a stage review (synthetic reproduction or data query); I did not re-run it.
- **[P]** — the mechanism is shown, but it is not established that it has occurred.

Severity scale:

- **Critical** — wrong or misattributed evidence is shown in the main graph, or evidence is lost from it.
- **High** — likely to cause that, or it breaks the update or release path.
- **Medium** — reliability, efficiency or operational risk.
- **Low** — maintainability.

---

## 1. Summary judgment

### What works and should be kept

- **Model transport.** Strict JSON schemas, custom-ID reconciliation that fails on missing, duplicate or unexpected results, explicit errors for truncation and refusal, frozen request files with hashes, and a spending guard. All 137,256 screening requests and 42,004 extraction tasks completed with no truncation.
- **Cost.** The complete Luna rerun cost $67.51 in settled model spend, covering screening, extraction and the audits.
- **Full text.** Europe PMC/PMC XML is preferred, and only the article node with an exactly matching DOI is kept. Identity gates refuse to continue on a mismatch. The September loss of JATS figure and table captions is fixed.
- **KG build.** It is deterministic: the 29 and 30 October builds are byte-identical. Null and mixed results pass through, and no code inverts a direction.
- **Release mechanics.** The promoter stages files, rolls back on failure, verifies checksums and binds run and release IDs. The PRISMA arithmetic of the candidate closes. The API rejects unknown fields.
- **Documentation.** The evaluation documents state their limits honestly, for example that labels came from an AI assessor and not from independent human experts.

### Main problems

The serious problems are scientific rather than mechanical. They fall into five groups.

1. **Errors are not measured.** No human-adjudicated reference set exists for screening, extraction or normalization. The one fresh screening sample retained 51 of 63 relevant papers (81%, 95% CI 69.6–88.8). That sample was labelled by the same AI assistant that wrote the prompt. Repeating identical requests changed 7% of decisions. Recall is not monitored in updates. The searches also miss papers:
   - 480 included papers (1.8%) were never retrieved by the current searches and came only from earlier searches. One identified cause: class terms such as "psychedelic" are searched only together with domain terms.
   - 61,951 records without a DOI never reach screening.
2. **Identity is wrong at several levels, and the errors reach the main graph:**
   - **Paper.** The same abstract is attached to unrelated DOIs; one report appears under several DOIs; some full texts belong to a different document.
   - **Study.** Several reports of one trial are counted as independent papers.
   - **Finding subject.** The compound a finding is attributed to is chosen by searching free text, so absent drugs, comparators and enantiomers that were not tested become subjects.
   - **Scope.** 16 compounds listed as in scope are missing from the entity registry.
3. **Results lose their meaning in the data model:**
   - 9 of 11 primary schemas have no result-direction field, so 70% of primary findings carry no structured positive, null or mixed label.
   - Where direction exists, it is valence: it does not separate within-arm change from between-arm contrasts and has no significance field.
   - Primary findings have no supporting quotes; statistics are free text.
   - One result is copied to several conditions or several compounds.
4. **Operations put data and releases at risk:**
   - The candidate was built from uncommitted code (committed on 1 November in `fb6c963`).
   - Run state, including the spending ledger, lives in Dropbox, which has already produced conflicting copies of that ledger.
   - The release scripts delete every unpromoted run.
   - A routine public refresh would publish headline counts from mutable state.
   - A full rerun erases curated overrides.
5. **The code is complex and duplicated.** The normalizer has grown by patch rules to 13,123 lines. Classification logic is written twice, in Python and in the browser, and the copies disagree. There are five model-runner stacks, about 18 DOI normalizers and many orphaned scripts.

---

## 2. Cross-cutting problems

### 2.1 Correctness is not measured

| Observation | Evidence |
|---|---|
| All screening and extraction evaluations use AI assessors | Stated in `docs/evaluation/luna_screening_prompt_comparison_2026-10-16.md`, `luna_primary_source_audit_2026-10-17.md`, `model_selection_2026-10-16.md` [V] |
| V5 screening keeps 51/63 relevant papers in its one fresh sample (81.0%; 95% CI 69.6–88.8) | `luna_screening_prompt_comparison_2026-10-16.md:45-54` [V] |
| In the same sample, 12 of 142 exclusions were relevant (8.5%). Projected to that pool's 25,294 V5 exclusions: about 2,100 relevant papers (1,240–3,590) | Screening review [R] |
| Identical requests repeated on the same 199 papers changed 14 decisions (7.0%; CI 4.2–11.5). Including a paper when either run includes it gives 57/63 (90.5%) | Screening review, byte-identical inputs [R] |
| The planned V6.1 correction re-screens only inclusions, so it improves precision, not recall | `run_screening_correction.py:116-121` [R] |
| The project's own estimate: about 300 independently adjudicated relevant papers are needed to support a 99% sensitivity claim | `model_selection_2026-10-16.md` [V] |
| 480 of 26,149 included DOIs (1.8%) were never retrieved by any current (v3) search and came only from earlier searches. 39 of them have "psychedelic" or "hallucinogen" in the title (D1); the causes for the rest were not established. The known-record recall check is hard-disabled (D10) | Discovery review [R]; code [V] |
| 87,479 records are excluded for lacking a usable abstract, 12,685 of them with a psychedelic or ketamine term in the title (I9). 61,951 records without a DOI are never screened (D9) | [R] |

Without a reference set, these questions cannot be answered:

- How much relevant literature is missing?
- How often is a finding attributed to the wrong compound?
- Did a repair pass make the graph more accurate or only different?

The Methods page states the limitation in words but gives no numbers.

### 2.2 Identity errors at four levels

**Paper identity**

- 2,020 abstracts of 50 or more words appear verbatim on more than one DOI (5,212 DOIs). In 171 of these groups the titles differ. Findings come from 15 of the groups: 51 findings in the deployed release and 64 in the candidate [R]. Examples:
  - "Curing agents" (Additives for Polymers, 1994, `10.1016/0306-3747(94)90197-x`) carries a wastewater drug-analysis abstract and yields the main-graph finding "Bufotenin / Population use & trends" [V].
  - A 1917 BMJ news item ("Our Belgian colleagues at home and abroad", `10.1136/bmj.1.2935.429-a`) carries a modern ketamine abstract. It yields three main-graph ketamine findings (VTA, nucleus accumbens, prefrontal cortex). The model warned about the mismatch, but the warning check missed the wording [V].
- 1,680 identical-abstract groups also have matching titles, but only 21 are registered as aliases. In 68 such groups in the candidate (506 findings), both DOIs carry findings, so one report is counted twice [R].
- 41 PMIDs and 154 PMCIDs are each shared by distinct DOIs that are not aliased [R].
- 153 ledger keys are PubMed "pii: …" strings rather than DOIs. 10 of them are represented in the candidate and produce broken doi.org links [R].
- Full text: 223 artifacts that passed the identity check carry a document DOI conflicting with the requested DOI; 141 of them are in the frozen extraction packets [R]. The stricter guard that would reject them is uncommitted. Example: the Lyme/PCP case report `10.1016/j.jadr.2023.100525` was extracted from an unrelated trial protocol [V].

**Study identity**

- 107 trial registry IDs are attached to more than one paper with primary findings (345 papers) [V].
- Some of these links are wrong: registry IDs are harvested from reference lists as well (§3.2, I7).
- Many are real. NCT00088699, the NIMH intramural ketamine protocol, is attached to 40 represented reports [V].
- Graph and Analyze counts are publication counts, so repeated analyses of one cohort look like independent support. This was raised in September and is unchanged.

**Finding-subject identity**

The normalizer searches the subject text for registry compound names (`text_contains_registry_label`). 17,312 main-graph rows, 21% of the main graph, depend on this route [R]. It creates these errors:

| Mechanism | Main-graph rows | Verified example |
|---|---:|---|
| Absent drug becomes the subject: the negation check misses "no X" and "non-use of X" (`build_evidence_tables.py:3111-3120`) | 57 (32 DOIs) [R] | `10.1093/ijnp/pyaf022`: "SAPAP3 knockout genotype (HOM vs WT); vehicle-treated, no psilocybin" is shown as a psilocybin readout [V] |
| Comparator or context drug becomes the actor | 106 [R] | `10.3389/fpsyt.2021.786622`: methamphetamine-use-disorder vs ketamine-use-disorder patients becomes "Ketamine → Methamphetamine use disorder (negative)". `10.1002/hbm.24679`: an MDD-vs-control baseline imaging difference becomes "Ketamine → Thalamus" [V] |
| Several compounds named in the text are placed on every compound node; enantiomers are masked one at a time (`:3335-3359`, `:4646-4653`) | 2,955 main edges with more than one compound node [V]; 141 at racemic ketamine when only enantiomers are named [R] | `10.1002/advs.202416481`: "S-ketamine reduced TNF-α, whereas R-ketamine did not" appears at S-ketamine, R-ketamine and racemic ketamine [V] |
| Combinations and classes reduced to one compound | 788 [R] | "MDMA and cannabis co-intake" becomes MDMA; "Amphetamine, methamphetamine, and MDMA" becomes MDMA [R] |
| Non-treatment designs shown as treatment evidence | not counted | `10.3389/fpsyt.2024.1301960`: a survey of palliative patients' interest in psilocybin becomes "Psilocybin → Distress associated with life-threatening disease (mixed)" [V] |

**Scope identity**

- 16 of the 54 compounds in `config.example.yaml` `allowed_compounds`, which the Methods page lists as in scope, are missing from `data/curated/entity_registry.json` [V]: 4-HO-MET, 4-HO-MiPT, DOC, DOET, 2C-C, 2C-D, 2C-P, 2C-T-2, 2C-T-7, alpha-methyltryptamine, AL-LAD, ETH-LAD, PRO-LAD, 1P-LSD, 25B-NBOH and 25C-NBOH.
- All of their findings are kept out of the main graph as `uncontrolled_subject_detail_only`. 1P-LSD alone has 19 findings from 6 papers [V].
- The draft `protocols/psychedelics/entities.yaml` has the same gap.
- The reverse gap also exists: hydroxynorketamine, MDEA and methoxetamine are in the registry and are eligible under the screening prompt, but are not search terms (D5).
- The scope vocabulary is held in at least five places: config allowlists, prescreen synonym dictionaries, the engine's acronym list, two JSON sections of the search strategy, and the registry. Nothing checks that they agree.
- No compound in the registry (0 of 84) and no disorder (0 of 74) has an external identifier such as PubChem or MONDO; 131 of 187 targets do [V].

### 2.3 Result meaning in the data model

- **Direction.** `result_direction` exists only in the clinical and safety primary schemas [V]. Primary edges with no direction, by domain [V]:
  - 100% for molecular pathway, cognitive-behavioral, brain system, molecular target, subjective experience, pharmacokinetics, intervention context and general;
  - 66,197 of 94,433 primary edges overall (70%).
  The README principle "null, mixed, uncertain and positive findings are retained" holds only in free text for those domains. A user cannot filter for null results in those views.
- **Direction semantics.**
  - `positive`/`negative` are valence (benefit/harm) and do not separate within-arm change from between-arm contrasts. Example: `10.1186/s13063-025-08836-4`, ketamine vs buprenorphine. HAM-A and craving are coded `positive` in the main graph, although the between-group tests were not significant and the model's own summary says so [V].
  - A heuristic finds 401 of 6,027 `positive` items whose text contains only non-significance wording [R].
  - `direction_normalized` puts three vocabularies in one column: valence (positive/negative), quantity (increase/decrease) and support (supports/does_not_support) [V].
- **Statistics and quotes.**
  - Primary findings: 0 of 94,433 have a supporting quote; confidence-interval and p-value columns are empty; statistics are free text, often several arms or timepoints in one string [V].
  - 2,718 numeric tokens in 1,503 primary items (735 DOIs) cannot be explained from the supplied text after allowing for conversions. Some are silent repairs of garbled source values; one lost a minus sign [R].
  - 14% of review quotes in a 400-quote sample are paraphrases rather than verbatim quotes [R].
  - Meta-analysis v2 already has quote and number verification (`run_meta_analysis_v2_batch_api.py:566-593`). The primary and review paths do not use it.
- **Copying one result to several nodes.** `condition_expanded_rows` (`build_evidence_tables.py:8981-9046`) still copies primary and review results once per condition named [R]: 206 source statements become 481 rows, 360 in the main graph. Examples:
  - An esketamine next-morning driving-safety null (`10.1177/02698811221078764`) is shown as "S-ketamine → Major depressive disorder: no detected effect" [V].
  - A single-patient MADRS change is copied to anorexia nervosa, BPD, PTSD and suicidality [R].
- **Mismatch between observations and the graph projection.** Extraction now produces structured observations, but the graph still projects onto compound → category nodes with fixed label lists.
  - 31.5% of candidate edges are `paper_detail` (37,277 of 118,347), and 4,530 represented papers appear only in paper details [V].
  - The project's own 31 October assessment reports fewer papers visible in an overview area than in the deployed release (17,662 vs 18,504), although more papers are represented (`normalization_state_assessment_20261031/report.md`).
  - The largest single detail reason is an unregistered or uncontrolled subject: 19,027 edges [V].
- **Source location.** Locators are packet chunk IDs such as "C008". They renumber whenever the section policy changes, and the findings table does not store task ID, input fingerprint, model or prompt hash [V]. The interface never displays `evidence_location`, `evidence_locator` or `supporting_quote` (`ui/app.js:13279-13280` only copies them) [V]. The Methods page says source locations keep the results auditable; in the interface, users only get a link to the paper.

### 2.4 Operational safety

| Problem | Evidence | Severity |
|---|---|---|
| Release scripts delete every non-active run | `prune_release_history.py:341-358` keeps only the active run ID in `graph_payload_runs`, `kg_routed_runs`, `query_api_runs` and `extraction/routed_runs`, and empties `release_staging`. It runs with `--execute` in `refresh_public_release.sh:92` (default) and `build_routed_kg_payload.sh:185` (when publishing) [V]. Run today, it would delete 31 entries (26 GB), including the candidate's KG directory [R]. The R2 prune also removes every earlier release, so rollback is impossible | High |
| A public refresh would publish wrong headline counts | `refresh_public_release.sh:77` calls the exporter without `--candidate-papers`, so the denominator comes from the canonical ledger (`export_evidence_payload.py:49, 2107`), which now holds Luna-era decisions [V]. Simulated result: 18,279 reports instead of 21,735, while the PRISMA flow would still say 21,735 [R]. `validate_active_pointer_pair` compares only IDs | High |
| A scoped update can revert a newer release | `finalize`/`promote` do not check that the base release is still active (`run_scoped_paper_update.py:1050, 1300-1345`) | High [P] |
| A full rerun erases curated overrides | `rerun_luna.py:70-83` empties `screening_decision_overrides.json` and `manual_extraction_route_overrides.json` [V]. After the 17 October rerun, 45 of 101 archived curated exclusions became V5 inclusions and 33 were retained for extraction; identity holds had to be found again [R] | High |
| The spending ledger can silently reset | `llm.py:71` starts an empty ledger whenever `budget.json` is missing; `llm.py:61-67` disables enforcement when the state file lacks a budget [V]. Dropbox wrote conflicting copies of `budget.json` on 17 October; two contain an empty ledger [V]. Reproduction: after the file is renamed, a $50 reservation is accepted with $99 already spent [R] | Medium |
| Run state lives in Dropbox | Lock files, ledgers, Parquet tables and `.git` sit in a synced folder. `flock` protects one machine only. A conflicting copy of `.git/index` exists [V] | Medium |
| The candidate was built from uncommitted code | The last commit is 18 October (plus 22 October merges). 94 modified and 93 untracked files; pipeline diff +17,676/−2,580 [V]. Provenance is kept by copying source trees into run folders: 12,952 code files under `data/` [V]. Committing `build_extraction_routes.py` without the untracked `review_source_types.py` breaks its import [R] | High |
| No CI and inconsistent dependency pins | No `.github/`. `requirements-models.txt` pins `pandas<3` and `openai<3`, but the environment has pandas 3.0.0 and the batch runtime recorded openai 3.36.1. `bs4` is missing [V] | Medium |
| Writes to the candidate ledger and metadata cache are not locked | No lock in any writer. Several writes are non-atomic (`enrich_paper_metadata.py:141-146`, `refresh_paper_titles.py:258-272`, `run_deterministic_prescreen.py:715-717`). Each 100-row checkpoint rewrites the whole 141 MB cache in 3.2 s [R]. Still present from September (#4, #11) | Medium |
| Active-run overwrite (September #5) | The KG builder deletes tables in `kg_routed_runs/<run_id>` for any run ID, including the active one (`build_evidence_tables.py:12923-12931`). A missing registry or vocabulary file loads as empty (`:2366-2373`) [R] | Medium |

### 2.5 Complexity and duplication

- **`build_evidence_tables.py`.**
  - It is 13,123 lines: 238 functions, `build_tables` alone is 1,003 lines, about 4,300 lines are rule tables, and it has 635 `re.compile` calls and 363 inline regexes [R].
  - It grew from 11,411 lines (HEAD) to 13,123 during the last two weeks of repair passes.
  - It contains compound-specific rules, such as per-compound supersession masks, a ketamine-uropathy rule and a condition hierarchy written in code.
- **The `*_identity.py` modules.** Seven of them repeat the same helpers. They test for exact schema versions (`== "primary_clinical_outcome_v1"`), so a schema version bump would silently switch them off [V].
- **Python and browser code classify findings separately, and the copies disagree.** Examples:
  - The browser sends some reviews to meta-analyses by `publication_type`, while Python uses `paper_type`. Rows with a mismatched key are dropped, which loses 12 findings in the candidate (`ui/app.js:1526`, `:13108`) [V code; R count].
  - Comparator categories, hidden domains, five implementations of a study key, display thresholds and PRISMA labels are also duplicated.
- **Model runners.** There are five runner stacks (primary sync and batch, review sync and batch, meta batch). Each has its own environment handling, batch paths, completion key (route_id, task_id or DOI) and checks. The identity-warning check exists only in primary; the control-character check is missing in meta; quote and number checks exist only in meta [R].
- **Repeated helpers.** There are about 18 DOI normalizers (12 in ingest, 6 in full text), five HTTP clients, at least six atomic-write helpers, three section parsers and three alias loaders [R].
- **Unused code.**
  - Seven orphaned full-text scripts (about 1,850 lines) and two ingest pilots (1,786 lines).
  - 899 lines of legacy topical prescreen rules that production no longer uses.
  - 24 v1 secondary schemas, and Gemini-era options such as temperature, thinking budget and JSON repair [R].
- **Production orchestration sits outside `pipeline/`.**
  - The batch controller, queue and recovery code live in `data/processed/model_runs/.../implementation/`.
  - The final candidate was assembled by scripts in a run folder (`finalize_local_report.py`, `prepare_final_comparison.py`), not by the documented promoter [V].
- **Storage.** `data/processed` is 155 GB. The Luna run folder alone is 107 GB in about 60 subfolders, because each repair pass copies a full KG. There were 12 Luna KG builds between 26 and 30 October [V]. `primary_evidence.json` is 520 MB. The findings table has 253 columns plus a `raw_row_json` copy.
- **Documentation volume.** `docs/` holds about 197,000 words. `pipeline/luna_v5_rerun_2026-10-17.md` is a 311 KB chronological log rather than a runbook. The current state is spread across `WORK_STATE.md`, run reports and evaluation documents [V].

### 2.6 What the cost structure implies

The complete Luna rerun cost $67.51 in model fees [V]. The expensive parts are elsewhere: repeated repair passes (about 60 run folders and 12 full KG builds in five days), storage, and correctness that nobody measures.

Several design choices were made to save tokens:

- low reasoning effort for screening;
- primary packets limited to methods and results;
- a separate call per research area;
- no verification pass.

At current prices, a verification call for each main-graph finding would cost in the low tens of dollars per full rebuild. A second screening pass over excluded records that name an in-scope compound would cost less. That money would buy more accuracy than further prompt or alias tuning.

---

## 3. Stage-by-stage findings

### 3.1 Discovery

The retrieval mechanics are sound:

- boolean grouping;
- inclusive, contiguous date partitions;
- PubMed `retstart` kept below 10,000;
- OpenAlex cursors;
- a count-drift tolerance of min(3 records, 0.1%);
- resumable runs;
- a frozen plan per run.

The September promotion-recovery defect (#3) is fixed: the promotion intent and its cohorts are written before any canonical write, and a test covers four failure points.

The weaknesses are in the search design and the alias handling.

| # | Finding | Sev. | Location / evidence | Fix |
|---|---|---|---|---|
| D1 | Class terms (psychedelic, hallucinogen, entactogen, …) are searched only inside the compound-and-domain "core" blocks (`strategy.py:436-441`, ANDed with module terms at `:469-475`). The scope layer searches compound names only (`:491-528`). A paper about psychedelics as a class, with no listed domain word, is not retrieved. Of the 480 included DOIs that no v3 search retrieved, 39 have "psychedelic" or "hallucinogen" in the title. 33 of those 39 contain no listed domain term, and 36 are in the graph, e.g. `10.1016/j.tics.2023.01.003`, `10.1038/s41386-023-01567-7`. Living updates will miss future papers of this kind | High | Code [V]; counts [R] | Quick: a class-identity search per provider with truncation (hallucinog*, psychedel*, entactogen*, empathogen*, entheogen*) |
| D2 | The next standard update will search bare "PCP". `pcp` is a synonym for phencyclidine (`deterministic_prescreen_rules.py:89`) but is missing from `strategy.AMBIGUOUS_ACRONYMS` (`strategy.py:26-39`), so core blocks will use `pcp[Text Word]` (24 PubMed executions in the next plan). This contradicts the README and Methods | Medium | [V] | Add `pcp` to the acronym list, or let core use only the full-name override |
| D3 | PubMed drops ambiguous acronyms instead of adding context: DOI, DMT, DOM, DOB, MDA, DPT, DiPT, LSA, DOC and DOET are removed from PubMed queries (`strategy.py:166-170`), while OpenAlex gets acronym-plus-context queries. 10 included, represented papers on DOI (the compound) were never retrieved, e.g. two titled "1-(2,5-dimethoxy-4-iodophenyl)-2-aminopropane (DOI)". ESearch warnings are never read, so the Supplementary Concept branch with short labels is unverified | Medium | [R] | Add PubMed acronym-plus-context branches like the PCP override; add IUPAC and SCR names |
| D4 | Noise. "Psychotropic Drugs"[MeSH] is ORed into every PubMed core block (`search_strategy.v3.json:97-100`) [V]; it alone brought 115,270 DOIs, of which 49,240 were screened and 717 included (1.5%) [R]. S-/R-ketamine aliases include bare "ketamine" (`deterministic_prescreen_rules.py:87-88`) [V], giving about 45,000 records per search with 0–2 exclusive. TMA, bare LSD (least significant difference, lysosomal storage disease) and "San Pedro" add thousands of irrelevant records. The heading is not disclosed on the Methods page | Medium | [V]/[R] | Drop the heading; run the class block once instead of once per module chunk; remove bare "ketamine" from the enantiomer aliases; contextualize TMA and LSD |
| D5 | The search vocabulary is narrower than screening eligibility and the registry. Hydroxynorketamine (180 included), MDEA (127), methoxetamine (92), ALD-52, 25H-NBOMe, MMDA, tabernanthalog and 1cP-LSD are not search terms; they were reached only through other terms | Medium | [R] | One scope vocabulary that drives search, screening and registry (§7.3) |
| D6 | A one-day partition above the provider limit is dropped on retry and the run is reported complete (`runner.py:417-426`, `562-575`). It has not happened yet, but broader fields make it likelier | Medium (latent) | Reproduced on a fake provider [R] | Check the limit before removing the range; block the completion gate |
| D7 | Composite runs mark full coverage without checking that the update component covered all providers and layers (`composite.py:266-277`) | Medium | [P] | Require matching providers, datasets and layers |
| D8 | OpenAlex records indexed more than 14 days late are lost for non-PubMed papers. Updates filter by publication date; the README relies on periodic all-time reruns that are not scheduled | Medium | [P] | Schedule an annual all-time OpenAlex rerun, or use `from_created_date` |
| D9 | The no-DOI records have no path to screening: 61,951 rows marked `needs_identifier_resolution`, read only by promotion. 11,618 have a compound or class term in the title, 39,532 have a PMID and 1,539 a PMCID. They are neither counted nor reported in PRISMA | High (recall) | [R] | Resolve DOIs through the PMID; screen PMID-only records under a non-DOI work ID |
| D10 | No recall check. The known-record calibration is hard-disabled (`strategy.py:908-916`) although the strategy file says it is required for promotion; citation expansion has only a plan | Medium | [R] | Use the included set: track the share of included papers that each update's searches retrieve; run citation expansion on recent systematic reviews |
| D11 | Query provenance: aliases imported from the prescreen module are not covered by `strategy_hash`; sorting by (length, lowercase) over a set makes 100 of 232 query strings depend on the hash seed | Low | `strategy.py:13-16, 162-169, 800` [R] | Hash the generated queries; sort deterministically |
| D12 | "pii: …" pseudo-DOIs are taken from PubMed `elocationid` (`providers.py:432`); 6 groups merged distinct PMIDs. The longest DOI wins in a group (`promote_search_run.py:210-212`), overriding the PubMed DOI in 38 groups | Low | [R] | Accept only `10.` DOIs; prefer the DOI verified by the provider |

Structural:

- Alias policy is spread over five places: the config allowlists, the synonym dictionaries in the screening module, a hard-coded acronym list that has diverged from the prescreen's list, and two JSON sections.
- `SUPPORTED_DATASETS` and the compound × domain design are hard-coded in the engine.
- Duplicates: `DEFAULT_RUN_ROOT` defined four times; three atomic JSON writers; two DOI normalizers, of which only one lowercases.
- Vestigial code: the disabled calibration, v2 retirement code, and plan-only run folders.
- The provider, runner and artifact layers are cleanly separated.

### 3.2 Metadata enrichment and rules-based prescreen

| # | Finding | Sev. | Location / evidence | Fix |
|---|---|---|---|---|
| I1 | No check that an abstract belongs to the titled paper or is unique to its DOI. Wrong abstracts produce findings (see §2.2) | Critical | `abstract_quality.py:119-163`; examples [V] | Quick: hash normalized abstracts; treat abstracts shared by non-aliased DOIs or with negligible title overlap as unverified. Larger: per-field provenance; abstract-only extraction only from a DOI-verified abstract source |
| I2 | The same report under several DOIs; the alias registry is manual (129 records, 69 without an evidence basis) | High | 68 duplicate groups with findings in the candidate [R] | Generate alias candidates from shared PMID, PMCID or OpenAlex ID, or identical title, abstract and year; block release while candidates are unreviewed; later a DOI-independent work ID |
| I3 | The canonical prescreen table is stale and labelled with a rule version that was never run. `rerun_luna.py:154-168, 199-201` copied the July (v2_9) decisions and stamped them `cleanup_only_luna_v5_20261017`. Re-running the current rules changes 4,657 decisions: 793 excluded records would be retained, including 218 case reports and 46 trials; 319 retained records would be excluded, 15 of them represented | High | [R]; examples such as "LSD flashbacks" (`10.1001/archpsyc.1984.01790170105015`) are currently excluded as non-evidence letters [V] | Re-screening declined (1 November). Label the table with the rule version that produced it (v2_9) and store a rule-set hash with each decision |
| I4 | One PubMed record with an epub/print year gap aborts a whole metadata write after the cache was already written (`metadata_utils.py:509-522` vs `:933-944`; `materialize_candidate_metadata.py:63-85`) | High when triggered | 56 such rows in the cache [R] | Quarantine conflicting rows; take year and date from the same element |
| I5 | The language rule depends on which provider filled the field. 50% of rows have no language. PubMed "English Abstract" (a non-English article) is mostly not excluded: 17 such reports with 40 findings are in the candidate. The batch PMC path can take a translated abstract | Medium | `run_deterministic_prescreen.py:844-864`; `run_batch_abstract_enrichment.py:261-269` [R] | Use PubMed Language and the "English Abstract" type; restrict PMC to the main front-matter abstract |
| I6 | Provider identity checks are inconsistent: the per-record Semantic Scholar lookup accepts another DOI's record; batch PMC and PMID-only matches skip the DOI check | Medium | `metadata_utils.py:1437-1506`; `run_batch_abstract_enrichment.py:290-300, 327` [R] | Reject any response whose DOI differs |
| I7 | Trial registry IDs are harvested from the whole PubMed XML, including reference lists, so reviews inherit the IDs of trials they cite | Medium | `metadata_utils.py:992-997`; 452 reviews carry 3,699 such IDs [R] | Limit to title, abstract, DataBankList and the Crossref clinical-trial number |
| I8 | Writes unlocked and partly non-atomic; full-cache rewrite at each checkpoint (§2.4) | Medium | [R] | One ledger lock, one atomic-write helper, append-only checkpoints |
| I9 | The abstract gate excludes plausibly relevant records. 87,479 records are excluded for having no usable abstract; 12,685 of them have a psychedelic or ketamine term in the title (320 case reports, 320 trials, 287 with a PMCID). Short-abstract formats are excluded systematically: "Key Clinical Message" case reports, JAMA research letters | Medium (recall) | [R] | Declined for existing records (no re-screening, 1 November). For new records in later updates: send title-term records with a PMCID or a short abstract to title-only or full-text screening |
| I10 | DOI keys are not validated: 153 "pii: …" keys; trailing-dot handling differs between normalizers ("10.1124/mol.67.1." is represented, while the correct DOI is not); `open_science_features.py:343-344` strips a valid trailing ")" | Low | [R] | One shared, validating normalizer |
| I11 | Abstract provenance mislabelled: 5,205 abstracts are attributed to Unpaywall, which never returns abstracts. The contamination check depends on that label | Low | `enrich_paper_metadata.py:312` [R] | Record the provider per field |
| I12 | SSRN preprints pass preprint detection (117 records); `10.2139/ssrn.4237108` duplicates its journal version | Low | `preprint_detection.py:9-22` [R] | Add the `10.2139/ssrn` pattern and link versions |
| I13 | Retractions are not tracked. `is_retracted` is set on 1 of 277,094 rows; OpenAlex `is_retracted` is requested but ignored. The 97 records with "Retracted" in the title are not represented, which works only because of the title text. Papers retracted after ingestion are never re-checked | Medium (missing step) | [V]; OpenAlex handling [R] | Re-check retraction status (OpenAlex/Crossref) at each update |
| I14 | Funder names are not normalized: "National Institute of Mental Health" appears 3,590 times, "NIMH NIH HHS" 2,409 | Low | September item, unchanged [R] | Map funders to ROR/Crossref Funder IDs |

Domain hardcoding:

- `run_deterministic_prescreen.py` contains corpus-specific DOI blocks, article ranges and journal names.
- `deterministic_prescreen_rules.py` (899 lines) is imported unconditionally although it is used only for legacy audits.
- Otherwise the ingest modules are mostly field-neutral.

### 3.3 LLM screening and extraction routing

| # | Finding | Sev. | Location / evidence | Fix |
|---|---|---|---|---|
| S1 | The schema puts the decision before the reasons: `domain_tags`, `primary_domain`, `screening_decision`, `screening_reason`, …, `rationale` (`run_domain_routing.py:124-160`). Median reasoning is 24 tokens. 53 accepted decisions contradict their own reason: 52 inclusions whose reason concludes exclusion, 1 the reverse. 34 of them contribute 160–166 edges in the candidate (25–27 in the main graph). Separately, 12,778 exclusions wrote area tags, which were stripped without a record because `validate_record` returns early for V5 | High | Schema order [V]; examples `10.1182/blood-2024-194510` (epoetin), `10.2196/73815` (VR-CBT), `10.1002/dta.3519` (HHC), all "include" with reasons ending "excluded" [V]; counts [R] | Re-screening declined (1 November). Fix the early return in `screening_contract.py:220-221`. For new records in later updates, order fields as evidence → reason → decision → type → tags |
| S2 | Recall is not monitored (§2.1). Seven of the 12 sampled misses concern ketamine purpose rules, and rule 3 (a drug's own mechanism or toxicity qualifies) conflicts with rule 4 (anesthesia and analgesia exclusion) in `docs/screening/title_abstract_screening.md:49-79`. There is no needs-review state | High | [R] | A second pass over existing exclusions was declined (no re-screening, 1 November). For later updates: resolve rules 3 and 4; a human-labelled random audit of exclusions in each update |
| S3 | Unscreened papers can reach extraction. A prescreen-retained DOI with no Luna row gets a retained `general_primary` route with an empty decision (`build_extraction_routes.py:1231-1238, 910-924`). The documented `--refresh-derived` scoped update runs prescreen and route rebuild without screening (`run_scoped_paper_update.py:394-418`). `parsed_rows_from_raw` drops rows that fail the current validator (`run_domain_routing.py:707-712`), so a rebuild would turn the 53 rows from S1 into unscreened routes | High | [R] (mechanism reproduced; not observed in production) | Mark such DOIs `awaiting_screening` and not retained; assert routing ⊇ prescreen-retained before canonical writes |
| S4 | A full rerun erases curated overrides (§2.4) | High | `rerun_luna.py:70-83` [V] | Keep identity and format curation and reapply it automatically; put scope curation on a re-review list |
| S5 | A scoped route build still overwrites the canonical route table (September #2) | Medium | `build_extraction_routes.py:1217, 1823` [R] | Refuse `--doi-file` when the output is the canonical table |
| S6 | Overrides are inconsistent and hard to audit. Curated screening overrides accept exclusions only (`:329`). A `route_domains` rescue is ignored for secondary literature (`:791-830` runs before `:832`). Curated decisions are spread over 4 JSON files plus code lists. The canonical route table is a composite of a 22 October build and 80 rows spliced in on 26 October; its summary JSON describes a different file | Medium | [R] | One typed override registry with explicit precedence, applied only by the builder |
| S7 | One extraction call per area tag: 36,641 primary tasks for 20,142 papers; 1.88 billion characters sent against 0.94 billion unique. 3,414 tasks (9.3%) returned nothing, including 28.6% of molecular-target tasks. Area tags and paper types were never assessed for accuracy. A `thesis` title regex sends four Luna-primary inclusions to context-only | Medium | `build_extraction_routes.py:888-906, 241, 963-973` [R] | See X6; validate tags and types on a sample |
| S8 | The synchronous runner can overwrite the canonical 3.7 GB raw log (opened with `"w"` unless `--resume`) and then rewrite the canonical routing table. Failed responses are cached and replayed on retry (`llm.py:211-220`) | Medium | `run_domain_routing.py:615, 927-933` [R]; caching [V] | Default to run folders; never cache non-completed responses |
| S9 | The active prompt is resolved from mutable state (`title_abstract_screening_v5_pcp.md` via `model_pipeline_state`), while the rerun freezes a different file. The contract hard-codes a run path (`screening_contract.py:111`). Screening rows store no input fingerprint: 50 included DOIs now have a different title or abstract from the one screened | Low | [R] | Hash and store the instruction and input per decision |

Domain hardcoding:

- The area vocabulary is hard-coded in 15 modules.
- A psychedelic substance list, acronym checks and a "sperm" check are in `screening_contract.py:153-201, 275-289`.
- PCP cohort regexes are in `run_screening_correction.py`.
- `decision_state.py` defines a `model_screening` stage that the Luna path never uses.

### 3.4 Full text

| # | Finding | Sev. | Location / evidence | Fix |
|---|---|---|---|---|
| T1 | The identity gate verified documents whose own DOI conflicts with the requested one (§2.2). The guard is uncommitted (`source_identity.py:412-417`). The next PMC or conversion run will stop at the gate until the 223 are curated | High | [R]; example `10.1016/j.jadr.2023.100525` [V] | Commit the guard with a test. Triage the 223 into version relationships (decide whether preprint text may stand in for a published DOI) or quarantine them. Re-extract the affected reports |
| T2 | Tables from PDFs are flattened. GROBID tables are packed as plain text (`build_llm_evidence_packets.py:528`), and only JATS tables keep rows and notes (`:531-541`). This affects 11,461 tables in 4,288 papers; empty cells disappear, so values cannot be assigned to columns | High | [V] code; counts [R] | Quick: render TEI row/cell like JATS tr/td, keep empty cells, add notes |
| T3 | The primary-study section filter drops results text. Subsections are classified by their own heading, without inheriting the parent's type (`:685-703`, `:402-418`): 269 papers lost 632 results subsections (about 400k characters). The figure filter (`:935`) drops 27% of captions, including 932 that contain statistics in 579 papers. None of this is flagged | High | [R] | Inherit the parent section type; keep all figure captions for primary studies; report dropped characters |
| T4 | PMC XML is not tried when a PDF already exists (`build_fulltext_enrichment_worklist.py:403-417`; `fetch_pmc_fulltext_xml.py:445-454`). 4,128 non-XML packets have a PMCID that was never tried; PMC succeeds about 75% of the time, so about 3,000 papers could get structured XML | Medium–High | [R] | One PMC pass including papers with local PDFs; prefer the JATS artifact |
| T5 | Supplements, data-sharing statements and very short documents pass. The supplement detector knows five exact headings. There is no completeness gate (`artifact_ready` needs only `char_count > 0`; one packet has 94 characters). An exact DOI is accepted without title evidence: `10.1007/s12325-023-02623-w` is a myeloma CAR-T cost study filed under a ketamine title, so that paper's evidence is lost without notice | Medium | `pdf_alternate_sources.py:102-108, 198-219`; `build_extraction_routes.py:569`; `source_identity.py:587-590` [R] | Broaden the patterns; add a minimum body/structure gate; flag "exact DOI, no title overlap" |
| T6 | Characters and units are damaged: superscripts and subscripts are joined with spaces ("10 −5", "mg kg −1", "I 2"); 192 packets have private-use Symbol-font characters (µ becomes ""; one paper has every digit encoded); 18 have control characters. Model outputs contain none of these, so the model is currently guessing correctly | Medium | `convert_pdfs.py:138` [R] | Render sup/sub without the inserted spaces; add a Symbol/PUA mapping; flag affected packets |
| T7 | JATS peer-review sub-articles get into the article text (22 packets); tables nested in `<p>` are duplicated (146) | Low–Medium | `build_llm_evidence_packets.py:433` [R] | Walk only the main `<body>` |
| T8 | September #10 is still present, but it now stops at the gate instead of passing silently | Low | `convert_routed_local_pdfs.py:463` [R] | Refresh the audit whenever anything was written |

Structure:

- 44 scripts: about 17 on the standard path, about 13 for browser or manual recovery, 7 orphaned.
- 3 conversion entry points with different post-conditions, 4 download entry points, more than 10 queue builders, 3 section parsers.
- The section-selection markers contain drug and disorder names (`build_llm_evidence_packets.py:116-155, 227-261`).
- 99 frozen packets come from back ends that are not in `pipeline/`: browser DOM captures and Tesseract OCR.
- Curated identity records contain absolute Dropbox paths.

### 3.5 Extraction

| # | Finding | Sev. | Location / evidence | Fix |
|---|---|---|---|---|
| X1 | Mismatches the model reports itself are not enforced. The primary warning regex misses common phrasings (`run_route_extraction.py:91-105`). The review and meta parsers have no check: 7 primary routes and 6 review bundles (30 main-graph relationships) carry "different papers" warnings and are still included | High | [V] (BMJ 1917 example); counts [R] | Quick: required enum `source_identity_check` (consistent/mismatch/uncertain) in all schemas, failing closed; hold those 13 DOIs |
| X2 | The direction field mixes within-arm change, between-arm contrast and significance; 9 of 11 domains have none (§2.3) | High | [V] | Add comparison basis, result pattern, reported significance and valence as separate fields (`primary_observation_contract.py` already drafts this but is not wired in) |
| X3 | Primary numbers cannot be traced or checked: no quote field in any of the 11 primary schemas, statistics in free text, no number check. Review quotes are not verified | High | [V] schemas; numeric scan [R] | Verbatim `supporting_text` per item, plus one shared parse-time quote and number verifier reusing the meta helpers |
| X4 | Source text is not pinned to the task. Runners reload packets by path and never compare the task's `source_fingerprint` (September #8, now also primary). If the packet is missing, the abstract is sent under the article prompt and stamped `article_text` (`run_route_extraction.py:403-425`). Production was protected by frozen copies | Medium | [R] | Re-hash at prepare and parse; raise instead of falling back |
| X5 | The primary batch parse joins results to the current task file by route_id and overwrites task_id and text_depth (`run_route_extraction_batch_api.py:664, 674, 717`) | Medium | [R] | Require the task fingerprint to equal the manifest's |
| X6 | Per-area routing re-reads papers and disagrees with itself. 60% of papers have two or more routes; 46% of primary input tokens are re-reads. Study design category disagrees across routes of the same paper in 14% of DOIs, and population/model category in 15%. Identical statistics appear in several routes for at least 379 papers | Medium | [R] | Extract the study frame (design, arms, N, population, timepoints) once and pass it to each area call; or test one call per paper with area sections |
| X7 | Retry and selection defects: stale-fingerprint re-selection (September #7) still present; the materializer reads only `batch_*_raw.jsonl`, so a retry with another batch ID is overwritten by the older error; failed responses are cached; the review sync runner marks completion by DOI | Medium | `run_routed_extraction_batch.py:114-131, 526`; `llm.py:211`; `run_review_relationship_extraction.py:324` [R] | Latest-attempt logic; a batch list taken from the manifest; no caching of non-completed responses |
| X8 | Contradictory instructions: schema descriptions say "use the closest allowed value", the prompt says "not the nearest available label", and the parser rejects "closest proxy" warnings. Domain addenda refer to fields that do not exist | Low | [R] | Align the texts; generate the field lists from the schema |
| X9 | Validation gaps: 7 outputs are `extracted` with 0 items; the meta parser lacks the control-character check; the meta "supports" rule hard-codes p > 0.05 | Low | [R] | Status/items consistency check; shared checks |
| X10 | Abstract-only tasks also receive MeSH terms and keywords, so 371 rodent items name a species found only in MeSH while the locator says "Abstract" | Low | [R] | Mark metadata-derived values, or leave MeSH out of abstract-only tasks |
| X11 | Gaps in the reproducibility record: the contract fingerprint hashes the files, not the code-generated instruction text or the wire schema. The sync path saves no request bodies. `validate_response` requires the model string to be exactly `gpt-6-luna`, so the dated snapshot is never recorded and a snapshot name would fail every response (`llm.py:191`) | Low | [R] | Hash the final request body; record the returned model snapshot |

Spot check (14 random items; small and not representative) [R]:

- Every number checked matched the source.
- 5 items had a non-psychedelic focal exposure: oxygen, a tryptophan-deficient diet, an mPFC lesion, Jobelyn, amphetamine.
- 1 suicidality case was coded as a clinical outcome rather than safety.
- Some location and locator values were swapped.

### 3.6 Normalization and KG build

Main findings are in §2.2 and §2.3. Additional items:

| # | Finding | Sev. | Location / evidence | Fix |
|---|---|---|---|---|
| K1 | The negation check misses "no X" and "non-use of X"; the fallback picks the only registry compound found in the text (§2.2) | Critical | `build_evidence_tables.py:3111-3120, 3473-3487` [V] | Quick: extend the negation list. Larger: do not admit text-search subjects to the main graph without a role check against the comparator and exposure fields |
| K2 | Comparator and context drugs become actors (§2.2) | Critical | [V] examples | Drop subjects that appear only in a comparator clause |
| K3 | Pooled primary and review results are copied to each named condition (§2.3) | Critical | `:8981-9046` [V] example | Interim: send splits to `paper_detail`. Larger: one row indexed to several conditions, with a pooled role |
| K4 | Multi-compound subjects are placed on every compound node; enantiomer masking bug (§2.2) | Critical | `:3335-3359, :4646-4653` [V] | Quick: apply the enantiomer masks cumulatively. Larger: keep pooled subjects as one pooled node |
| K5 | Combinations and classes are reduced to one compound; `COMPOUND_COMBO_TEXT_RE` lacks "in combination with"; a ketamine-assisted psychotherapy regimen is overridden to atomic ketamine | High | `:4628-4633, :4524` [R] | Keep these in `paper_detail` unless the role contract confirms a single actor |
| K6 | Aliases that equate distinct concepts (examples below) | High | Registry [R] | Delete or split them. Give every alias a mapping type (exact / broader / narrower) and never treat broader as a synonym |
| K7 | Animal results are not always marked as animal: the regex covers only mice, rats and rodents; 178 main findings in baboons, marmosets, rabbits and dogs have design "unspecified". Edges have no species column | Medium | `convert_routed_extractions_to_evidence_rows.py:474-483` [R] | Use a species vocabulary; add population/model category to edges |
| K8 | Fan-out inflates counts. 81,055 main rows come from 68,779 distinct (DOI, support) statements. 6,760 of 8,822 `routed_clinical_endpoints` rows duplicate an extraction row. Text splitting adds 10,647 rows | Medium | [R] | Count distinct statements; remove duplicated endpoint rows |
| K9 | Helpers ignore `--registry` and use the curated registry. The manifest records mutable vocabulary paths without hashes | Medium | `real_world_subjects.py:21`, `subject_role_guards.py:12,23` [R] | Pass `registry_path` to every helper; hash all inputs |
| K10 | The new PCP-site rule misses "N-methyl-D-aspartate" and "NMDAR" | Low | `target_identity.py:157-158` [R] | Extend the regex |
| K11 | Normalization takes about 22 minutes against about 1 minute for conversion, at about 5 ms per row (regex per registry key, repeated matching) | Medium | [R] | Compile one matcher per registry (e.g. Aho–Corasick); cache subject matches |
| K12 | Misclassified subjects: an injury model ("Spared nerve injury") and a genotype ("Disc1tr Hemi mice") are typed `atomic_compound`. They are held correctly but show that the schema forces every finding to have a compound subject | Low | [V] | Allow non-drug independent variables in the schema |

K6 alias examples:

- "recurrent depressive disorder" → persistent depressive disorder: still present from September, 5 main rows.
- "Difficult-to-treat depression" → TRD.
- "anorexia" → anorexia nervosa; in safety tables "anorexia" usually means loss of appetite.
- "smoking" and "smoking cessation" → tobacco use disorder.
- "methamphetamine use" → methamphetamine use disorder.
- "terminal cancer" → distress associated with life-threatening disease.
- "mTOR signaling" → mTORC1.
- "GSK-3" → GSK3B.
- LTP and spine density → neuroplasticity.
- Parenthetical keys such as "(WT)" depend on dictionary order.

Data observations from the candidate:

- 147,667 rows after expansion: 54.9% main graph, 25.2% paper detail, 19.9% held.
- Largest held reasons: `entity_unmapped` 12,190; `paper_scope_not_graphable` 4,348; `compound_unmapped` 3,067.
- 164 main-graph rows have `needs_human_review = True`.

### 3.7 Release, interface and API

| # | Finding | Sev. | Location / evidence | Fix |
|---|---|---|---|---|
| U1 | "Open access" means the pipeline obtained the paper's full text; publisher and OpenAlex flags are not used because they are often wrong (project definition, confirmed 1 November). The default Explore view shows these reports (`ui/app.js:549, 1448-1457, 6458-6466`). The label is consistent within each paper: no paper mixes access levels [V]. It is wrong only where the retrieved document is a different paper (T1, T5) or where the extraction fallback sends the abstract and stamps it `article_text` (X4) | — | [V] | No change to the label or the default; fix T1, T5 and X4 |
| U2 | A refresh would publish denominators from the mutable ledger (§2.4) | High | [V] code; simulation [R] | Freeze a ledger snapshot and hash per release; `--check-active` should validate the ledger and the represented DOI set |
| U3 | Pruning deletes candidates; the remote prune removes all earlier releases (§2.4) | High | [V] | Protect candidates; keep the last N releases; make pruning a separate opt-in command |
| U4 | Scoped update against a superseded base (§2.4) | High | [P] | Require the base release ID to equal the active pointer's |
| U5 | Reports users cannot browse are counted as "included in the knowledge graph". 31% of findings are detail-only. Pharmacokinetic rows are downloaded and then discarded (`app.js:13107`), so 742 PK-only reports are never shown. Header 23,058 against 17,873 in the Analyze index | Medium | [R] | Report "catalogued" and "browsable" counts separately, or add a PK view |
| U6 | Node tooltips add up per-edge counts: Ketamine shows 748 against 577 unique reports (+30%) | Medium | `app.js:5469-5488` [R] | Export unique counts per node |
| U7 | Display thresholds exist in three versions and are not disclosed: bootstrap 1 for reviews, summary 2, the browser exempts secondary views, the documentation says 2 | Medium | `export_evidence_payload.py:1604-1610, 1985`; `app.js:7313-7352` [R] | One threshold, stated on the page, with "below display threshold" shown separately from "no evidence" |
| U8 | Browser reclassification drops findings (§2.5) | Medium | [V] code | Export `source_key` per row and have the browser use it |
| U9 | Locations and quotes are never shown (§2.3) | Medium | [V] | Show `evidence_location` and review quotes on finding cards; drop the fields from payloads if they will not be shown |
| U10 | Payload size: about 10.9 MB at first paint; an idle prewarm of 62 MB of Analyze data (16 MB gzip) on every Explore visit; finding search loads 112.8 MB; the Methods record table is 111 MB (34 MB gzip) and is parsed in full; each finding is stored about four times per release (about 488 MB) | Medium | [R] | Deduplicate; paginate the record table; load Analyze on demand; set Content-Encoding |
| U11 | PRISMA semantics: "Records identified" is the deduplicated DOI ledger. It leaves out 61,951 records without a DOI and has no duplicates-removed box. There is no retrieval stage, although 51% of included reports were extracted from abstracts only | Medium | [R]; arithmetic closes [R] | Add identification counts by source, a duplicates box, no-DOI records, and a full-text retrieval box |
| U12 | Static artifacts are not tied to the data release: `compounds/psilocybin/data.json` comes from the July release; the Methods prose describes Luna and PCP screening, which the deployed PRISMA does not reflect | Medium | [R] | Build them in the same release step |
| U13 | Identity defects in payloads: 12 deployed reports appear under both alias and canonical DOI; 10 candidate reports use PII strings as their DOI and get broken links | Medium | [R] | Fall back to PMID or OpenAlex links; DOI syntax gate |
| U14 | API edge cases: blank `subject_ids` match all papers; `%` and `_` act as wildcards in `query`; data syncs only at startup | Low | [R] | Validate blanks; escape LIKE |

UI domain hardcoding:

- `PATHWAY_READOUT_FAMILY_RULES`;
- `specificPathwayReadoutLabel` (BDNF, PSD-95, cortisol);
- `CONDITION_GRAPH_LABEL_OVERRIDES`;
- comparator regexes that name specific drugs.

Assets are cached as immutable for one year while cache-busting is done by hand.

---

## 4. Missing, redundant and questionable steps

**Missing steps**

- A human-adjudicated reference set and recall monitoring in each update.
- A class-level search: "psychedelic", "hallucinogen" and similar terms on their own, not ANDed with domain terms.
- Retraction re-checks.
- Study or trial identity, with links between reports of the same study.
- Version links between preprint, published and translated editions.
- Structured direction and significance for all primary domains.
- Verbatim support and number verification for primary findings.
- A screening path for new records without an abstract (title-only, or full text when a PMCID exists); existing records are not re-screened.
- A path for the 61,951 records without a DOI.
- External identifiers in the registry.
- A consistency check between the scope vocabulary and the registry.
- CI.

**Redundant steps**

- Per-area re-reads: 46% of primary input tokens.
- Duplicated clinical endpoint rows: 6,760.
- Four copies of each finding in the release payloads.
- Duplicated helpers: DOI normalizers, HTTP clients, runners, parsers.
- Orphaned scripts and unused pilot modules.
- Legacy prescreen rules.

**Questionable steps**

- Excluding a record solely because its abstract has fewer than 50 words.
- Separate extraction calls per research area.
- A schema that asks for the decision before the reasons.
- Finding subjects chosen by searching free text.
- Copying results across conditions and compounds.
- Undisclosed display thresholds.
- The PRISMA "identified" definition.
- Copying source trees into data folders as provenance.

---

## 5. Earlier audit findings

| Item | Status |
|---|---|
| 09-06 #1 JATS captions and footnotes | Fixed for JATS; TEI tables still flattened (T2) |
| 09-06 #2 scoped route build overwrites the table | Still present (S5) |
| 09-06 #3 discovery promotion recovery | Fixed: the promotion intent is persisted before writes and covered by a test |
| 09-05 no-DOI records outside screening | Still present and larger: 61,951 records (D9) |
| 09-05 no recall estimate | Still present; known-record calibration hard-disabled (D10) |
| 09-06 #4 concurrent ledger writes | Still present (I8) |
| 09-06 #5 active-run overwrite and ledger drift | Still present; drift is now larger (U2) |
| 09-06 #6 batch model mismatch | Moot (only `gpt-6-luna` accepted) |
| 09-06 #7 stale-fingerprint re-selection | Still present (X7) |
| 09-06 #8 source fingerprints not enforced | Still present; now also primary (X4) |
| 09-06 #9 batch completion and retry | Fixed; new gaps X7(b, c) |
| 09-06 #10 conversion audit refresh | Still present, now stops at the gate (T8) |
| 09-06 #11 checkpoint rewrites | Still present (I8) |
| 09-05 pooled copy across conditions | Fixed for meta-analyses; still present for primary studies and reviews (K3) |
| 09-05 "recurrent depressive disorder" alias | Still present (K6) |
| 09-05 control characters in doses | None in candidate outputs; still in deployed (57 dose fields) and in inputs (T6); no release gate |
| 09-05 reports counted as studies | Still present (§2.2) |
| 09-05 no primary quotes, free-text statistics | Still present (X3) |
| 09-05 "Open access" conflated with depth | Not a defect: "Open access" is defined as full text obtained by the pipeline (U1) |
| 09-05 duplicated Python/JS classification | Still present, now with an observed divergence (U8) |
| 10-25 readiness: hold dispositions | Fixed |
| 10-25 readiness: V6.1 boundary | Still open; it does not address misses among exclusions |

## 6. Test suite

`python3 -m pytest tests`: **2,690 passed, 5 failed** [V].

- `test_build_fulltext_enrichment_worklist` (2 cases): a stale test. Commentaries accepted for the review lane now enter retrieval, as intended. The untracked `review_source_types.py` must be committed together with `build_extraction_routes.py`.
- `test_persistent_identity_registry_has_all_curated_benign_classes`: a stale exact count (112 vs 110). Replace exact counts with invariants.
- `test_pcp_binding_site_remains_a_target_not_a_compound`: stale. The registry deliberately dropped the "PCP binding sites" → NMDA alias; also fix K10.
- `test_repository_requires_report_specific_identity_and_abstract`: `bs4` is not installed in the main environment.

A red suite that is expected to be red stops failures from being noticed. Fix these four and add CI.

Update, 1 November: after commit `fb6c963`, 2,694 passed and 1 failed (`bs4`).

---

## 7. Recommended sequence

### 7.1 Before publishing the Luna candidate (mostly quick fixes)

1. **Subject resolution (K1, K2, K4, K5):**
   - add "no X", "non-use of X" and "vehicle-treated" to the negation guard;
   - send comparator-only mentions to `paper_detail`;
   - apply enantiomer masks cumulatively;
   - do not place multi-compound or combination subjects on single-compound nodes.
2. **Copying (K3):** send condition splits for primary studies and reviews to `paper_detail`.
3. **Identity holds (X1, I1, T1):**
   - enforce model-reported identity mismatches in all three parsers;
   - hold DOIs that share an abstract with a differently titled DOI;
   - commit the full-text identity guard and triage the 223 artifacts.
4. **Screening (S1):** fix the validator's early return. Re-screening the 53 decisions was declined (1 November).
5. **Registry (§2.2, K6):** add the 16 missing in-scope compounds; add a test that every scope compound resolves; remove the aliases that equate distinct concepts.
6. **Interface (U5–U7, U9):**
   - show evidence locations and quotes;
   - export unique per-node counts;
   - state the display threshold.
7. **Release safety (U2, U3, U4, S4):**
   - protect unpromoted runs from pruning;
   - freeze the ledger snapshot per release;
   - check the base release in scoped updates;
   - stop full reruns from erasing identity curation.
8. **Code state:**
   - done on 1 November: the code is committed (`fb6c963`) and four of the five failing tests pass;
   - install `bs4` or mark that test as needing it;
   - pin one environment;
   - add CI that runs the suite.
9. **Retractions:** run a retraction check before the release.
10. **Search (D1, D2):** before the next monthly update, add the class-level search and remove bare "PCP" from the core blocks.

### 7.2 Next one to three months

1. **Reference set.** Two domain experts code a stratified random sample independently, and disagreements are adjudicated:
   - Screening: about 400 exclusions, including no-abstract and no-DOI records, and about 200 inclusions.
   - Extraction and normalization: about 100 papers across domains and text depths, judged at the finding level (subject, comparator, direction, numbers, condition).
   - Keep a holdout that prompt development never sees, and publish sensitivity and finding-level accuracy with intervals on the Methods page. Repeat a smaller random audit in every living update.
2. **Primary contract v2:**
   - verbatim `supporting_text` per item;
   - structured statistics (estimate, CI, p, n, arm, timepoint);
   - comparison basis, significance and valence as separate fields;
   - direction for all domains.
   `primary_observation_contract.py` is the starting point.
3. **Shared verification at parse time.** Quotes must appear verbatim in the supplied text and numbers must be present, reusing the meta-analysis helpers. Add an optional low-cost model call that checks each main-graph finding against its quote.
4. **Paper-level primary extraction.** Extract the study frame once and pass it to each area call, or test one call per paper. Measure consistency and cost against the current routes.
5. **Report and study identity.**
   - Generate alias candidates automatically.
   - Cluster reports by trial registration, using IDs from title, abstract and DataBank only.
   - Show "N papers from K studies" in the interface and API.
6. **Full text:**
   - a PMC-first pass for papers with PDFs (about 3,000);
   - TEI table rows;
   - section-type inheritance and all figure captions;
   - sup/sub and Symbol-font repair;
   - supplement detection and a completeness gate.
7. **Screening (new records in later updates only; no re-screening, 1 November):**
   - reorder the schema (evidence → reason → decision);
   - resolve the rule 3 / rule 4 conflict.

### 7.3 Architecture, including generalization to other fields

1. **One source of truth for scope.** One protocol file generates the search terms, the screening scope list, the entity registry and the view definitions, and validation checks that they agree. The draft in `protocols/` is the right place; the 16-compound gap shows what happens without it. It also needs the identifiers decided under D4.
2. **Split the normalizer into an engine and data.**
   - Resolve the subject from structured extraction fields (actor, comparator, co-exposure) rather than free-text search.
   - Store alias mapping types, supersession and combination patterns, and a species vocabulary as data.
   - Move compound-specific code rules into the registry or the protocol.
   - Replace the seven exact-version `*_identity.py` checks with a declared mapping per schema version.
3. **Observations are canonical; graph edges are projections.** Edges are derived from the observations under written projection rules, including how pooled, multi-arm and comparison results are shown. The browser reads the facets computed in Python (D6 in `protocols/SPEC.md`) and keeps no classification logic of its own.
4. **Operations:**
   - Move the repository and run state out of Dropbox, or exclude `data/processed` and the run folders from sync.
   - Make the spending ledger append-only and stop when it is missing.
   - Use one lock for the candidate ledger.
   - Put one orchestrator for runs inside `pipeline/`.
   - Record the git commit SHA plus the hashes of the inputs instead of copying source trees.
   - Keep the last N runs and delete the rest under a written policy.
   - Generate one release card per release (counts, versions, known limits, validation results) instead of chronological runbooks.
5. **Consolidate duplicated helpers:** one DOI normalizer, one HTTP client with rate limits, one atomic writer, one model runner with per-family adapters, one section parser.
6. **Separate the regular monthly update from contract changes.** A monthly update should run incrementally under frozen contracts with a short checklist. Reserve full reruns for prompt, schema or normalizer changes, with a before/after comparison against the reference set.
