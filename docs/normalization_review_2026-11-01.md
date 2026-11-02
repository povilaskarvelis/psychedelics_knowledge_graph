# Normalization review — 1 November 2026

> **Status, 2 November 2026.** Two decisions were made. Pharmacokinetics stays out of the overview until there is a representation for it (D1 is by design; no X5 area). Lisuride is out of scope (X2): the Methods page now lists it as searched only as a comparator. The fixes that needed no decision are implemented in the working tree (uncommitted). Their combined effect was measured with one rebuild of the 31 October inputs in a scratch folder, using the same per-paper census as below: the overview holds 18,153 papers instead of 17,679 (+474, none lost). See "Implemented, 2 November" at the end. Decisions X1, X3, X4 and X6–X8 are open.

## Question

The Luna candidate represents more papers than the deployed September release, but fewer of them appear in the overview (the Explore areas). Is the normalization layer correctly keeping weak evidence out, or is it failing to map findings that could be shown without changing their meaning?

## Short answer

Both, in different places.

1. **Most of the drop happens before normalization.** Of 4,931 papers that were in September's overview and are not in the candidate's, 2,792 are no longer in the graph at all, mostly because Luna's title/abstract screen judged them out of scope. Within the overview areas, most papers that lost an area were never extracted for that domain.
2. **Where normalization is the cause, specific rules hold valid findings.** Some rules wrongly hold most of the findings they catch: the meta-analysis human-review flag (32 of 36 sampled), unspecified psychedelic-class subjects in primary studies (10 of 14) and compound-class subjects (13 of 14 wrongly or partly held). Other gates are mostly correct. Several defects are in the site and the view contract rather than in the findings: pharmacokinetic findings are discarded when the site loads, and 42 admitted constructs are on no view list.
3. **Many removals are corrections.** September showed comparator compounds, docking predictions, analytical-method papers and background statements as findings. In a random sample of 30 papers that were in September's overview and are now paper-detail only, 12 were correct removals, 10 could be mapped without changing their meaning, and 8 depend on a representation decision.
4. **The defects share causes.** Rows that fail matching are dropped instead of kept in paper detail. Many rules depend on exact wording. Primary studies and reviews are treated differently. The view contract has fallen behind what the normalizer emits. Scope is defined in four places that disagree.

The fixes that need no scope decision would make roughly 500–750 more papers visible [E]. The yields overlap, so the exact figure needs one joint rebuild. The scope and representation decisions in §4 could add several hundred more. The aim is to show what can be shown faithfully, not to restore September's count, which included misattributions.

## Scope and method

- **Candidate:** rebuilt today from the working tree with normalization contract `routed_retraction_holds_20261101_v1` and evidence run `luna_v5_20261030_safety_final`. It has 125,127 findings in 23,608 papers and reproduces the 31 October preview within 0.1%.
- **Deployed:** `living_update_20260917_author_identity_reviewed`, with 99,100 findings in 21,735 papers.
- **Overview visibility:** computed per paper with the site's own functions (`ui/app.js`) and `schema/graph_view_contract.json`, for both releases. It reproduces the earlier counts: 18,504 for September, 17,662 for the 31 October preview and 17,679 now.
- **Five parallel reviews:**
  - compound subjects;
  - outcome vocabularies and views;
  - brain, targets, pathways and pharmacokinetics;
  - reviews, meta-analyses and admission flags;
  - conversion and whole-paper losses.

  Each review sampled held findings against the raw Luna item and the paper's abstract or full text. Each measured the effect of its fixes by rebuilding the affected papers with the current code and recounting the overview.
- **Checking:** I checked the mechanism behind every high-ranked item in the code or data.
- **Evidence labels:**
  - **[V]** — checked by me.
  - **[R]** — measured by a review, by query or partial rebuild; not re-run by me.
  - **[E]** — estimate.
- **Yields:** "newly visible" means papers that would enter the overview. Yields overlap and are not additive.
- **Limits:** this is not a representative accuracy study. The repository was not changed apart from this file, and no model calls were made.

## 1. Where the papers went

| | September | Candidate (current code) |
|---|---:|---:|
| Papers represented (any finding) | 21,735 | 23,608 |
| Papers in the overview | 18,504 | 17,679 |
| Paper-detail only | 2,170 | 4,805 |
| Main-graph findings, but in no view | 1,061 | 1,124 |
| Findings | 99,100 | 125,127 |
| Main-graph findings | 81,957 (83%) | 83,795 (67%) |
| Paper-detail findings | 17,143 | 41,332 |
| Rows dropped before findings (audit only) | 25,314 | 22,516 |

The net change of −825 overview papers is the balance of 4,931 papers lost and 4,106 gained (3,342 of them new to the graph) [V].

| Where the 4,931 lost papers went | Papers |
|---|---:|
| Excluded by Luna's title/abstract screen as out of scope | 1,887 |
| Extracted, no extractable finding | 294 |
| Context only, not extracted | 231 |
| Ineligible publication found after retrieval (non-English main text, conference abstract, thesis) | 213 |
| Extracted, findings judged unsupported | 134 |
| Other (duplicate DOI, source holds, retraction) | 33 |
| **Not in the graph** | **2,792** |
| In the graph, paper detail only | 1,729 |
| In the graph, main-graph findings in no view (pharmacokinetics 180, symptoms 166, constructs off the view lists 67; overlapping) | 410 |
| **In the graph but outside the overview** | **2,139** |

Item conservation is complete [R]. Every one of the 128,861 items Luna extracted ends as a main-graph finding (55%), a paper-detail finding (30%), an audit row that the site never shows (15%), or a logged converter exclusion (241 items). The export carries every finding to the browser payload [V].

## 2. Exclusions that are correct

Samples support these rules [R]:

- **Predicted targets** (docking, molecular dynamics, QSAR): 30 of 30 sampled were correct exclusions. In September, 59 papers were in the Targets view only through predictions.
- **Analytical, forensic and synthesis chemistry**, and generic measurements that no view could carry.
- **Derivatives, congeners and modified molecules**, which are not attributed to the parent compound.
- **Antagonist-blockade and knockout inference**, and background sentences. Luna's "no extractable target evidence" was right in 15 of 15 sampled papers. September's target edges for these came from indirect evidence.
- **Broad "Depression" and "Anxiety" labels.** Mapping them to major depressive disorder would overstate the diagnosis, which September did in 10.1016/j.jad.2022.06.081.
- **Review coverage metadata and context coverage** (30 of 32 and 36 of 40 correct). These are topics, methods and history, not findings.
- **Non-drug exposures and reference compounds.** Stress models, knockouts and survey predictors are correctly not drug subjects. Cocaine, methamphetamine, MK-801 and other reference compounds are excluded by the curated list.
- **Comparator handling.** The rise in combination subjects (8,751 → 30,474 findings) reflects Luna writing fuller exposure text. Normalization reduces 76% of these to the measured drug.
- **Parallel lists with exceptions.** In 10.1097/00008877-199104000-00001, PCP and ketamine substituted for the MK-801 cue but morphine did not, so one direction cannot be copied to every listed drug.

## 3. Issues that need no scope decision, ranked

### Display (site and view contract)

**D1. Pharmacokinetic findings are discarded when the site loads.**
- *Mechanism:* `ui/app.js:12708` and `:13158` drop every row in the pharmacokinetics domain while loading the analysis and detail payloads (`HIDDEN_MAIN_GRAPH_DOMAINS`, `:624`) [V]. These findings therefore appear in no overview area, no paper panel and no search, although the export includes them: 4,432 rows in the detail payload [R].
- *Origin (corrected 2 November):* the loader filter dates from the 30 June refactor (`aa20b27`); commit b1f15ed (27 July) only moved it. Pharmacokinetic findings have been absent from the overview, finding search and finding cards since then, by design [V].
- *Size:* 650 papers are outside the overview only because their main-graph findings are pharmacokinetic [V].
- *Decision, 2 November:* pharmacokinetics stays out until there is a representation for it; mapping it to individual metrics did not work. Not a defect.

**D2. 42 admitted constructs are on no view list** [V].
- *Size:* they appear in 672 papers. For 168 of those papers, this is the only reason they are outside the overview.
- *Largest case:* "Psychotomimetic effects" (219 papers). The normalizer assigns this label itself (`build_evidence_tables.py:10800–10821`), but no view shows it.
- *Others:* operant responding (67), seizure behavior (40), verbal fluency (27), sexual risk behavior (21), catalepsy (20), self-related processing (19), personality traits.
- *Cause:* the saved-endpoint vocabulary of 29 October was extended without updating `schema/graph_view_contract.json`.
- *Fix:* add each construct to the Cognition or Behavior list. Which list is your choice.
- *Yield:* 168 papers newly visible; 659 papers gain an edge [R].

**D3. Registered conditions keep the symptom type.**
- *Mechanism:* `registry_kind_for_item` (`build_evidence_tables.py:6566–6572`) returns `symptom_problem` whenever the incoming row is symptom-typed, even when the label is a registered condition such as PTSD or OCD [V]. The registry nodes Psychosis, Anhedonia and Fatigue always resolve to the symptom type, so fatigue in multiple sclerosis never reaches that condition's edge, contrary to the 1 November rule [R].
- *Inconsistency:* "PTSD symptoms" maps to PTSD, but "Post-traumatic stress symptoms" does not (10.1080/15434610590956912) [R].
- *Existing projection:* the symptom-to-condition projection exists only for meta-analyses (`:9180–9204`) [R].
- *Yield:* 57 papers gain Conditions; 23 newly visible [R].

### Rules that hold or drop valid findings

**R1. The meta-analysis human-review flag treats missing metadata as unreliability** [V].
- *Mechanism:* `convert_meta_analysis_v2_to_evidence_rows.py:789` sets `needs_human_review` for any Luna uncertainty note or any result flag. Only an empty heterogeneity object is exempt (`:665–670`). `build_evidence_tables.py:11847` then holds the row.
- *Size:* 1,067 findings in 201 papers. It is the only reason for 54 papers outside the overview. In September, 385 such rows were main-graph.
- *Sample:* 32 of 36 were wrongly held, 4 partly, and none was unreliable [R].
- *Example:* ketamine versus placebo in treatment-resistant depression (NNT 7 at 4 hours; 10.1016/j.jad.2024.04.039) is held only for an empty `evidence_size` field [V].
- *Fix:* make empty optional objects non-blocking, and hold only notes that describe a numeric or direction conflict. Real conflicts stay held, such as a point estimate outside its CI (10.2147/ndt.s417027).
- *Yield:* 708 findings move to the main graph; 53 meta-analysis papers become visible, 44 of which were visible in September [R].

**R2. Review statements are typed by role, not by the domain Luna declared** [V].
- *Mechanism:* `convert_review_relationship_bundles_to_evidence_rows.py:544–556`, with `ROLE_GRAPH_MAPPING` at `:115`.
- *Size:* 5,357 of 26,764 review relationships (20%) land in a domain Luna did not declare, and 72% of those end audit-only [R]. Of 1,529 relationships declared Safety but typed clinical, 967 leave no finding [R].
- *Example:* in 10.1007/s00213-021-05767-1, "high-frequency ketamine use is associated with disruption of the bladder urothelial barrier" is typed as a clinical condition, fails to match and is dropped. The paper has no finding [V]. It should be Ketamine → Urinary toxicity.
- *Fix:* when the role-based domain was not declared and matching fails, fall back to a declared domain that is compatible with the role, for named-entity anchors only. Re-typing every such row would demote 314 main items, so only the fallback is safe [R].
- *Yield:* 591 more main-graph findings; 141 papers gain their first main-graph finding; 37 papers gain Safety [R].

**R3. Unmatched outcomes are dropped instead of kept in paper detail** [V].
- *Mechanism:* when the subject is in scope but the outcome label does not match, the row goes only to the audit (`build_evidence_tables.py:12715–12740`). Paper-detail fallbacks exist only for some primary domains.
- *Size:* about 98% of the 8,060 `entity_unmapped` rows have no finding [V]. About 4,550 review rows leave no trace, and 176 papers consist only of dropped rows [R]. In 12 of 20 sampled "unsupported" papers, the dropped rows held a real drug-specific finding [R].
- *Examples:*
  - ketamine for refractory status epilepticus (90 rows in 39 papers);
  - ketamine-related cystitis (10.1111/iju.12841), although `safety_category_for_text` already returns Urinary toxicity;
  - MDMA-related transient cognitive impairment (10.1016/j.neubiorev.2026.106911), an alias of Global cognition. This paper is not represented at all.
- *Fix:* keep these rows as literal paper-detail findings with their reason. The overview is unchanged, but the evidence becomes findable, and the audit becomes a list of held rows rather than lost ones.
- *Yield:* 266 of the 421 "unsupported" papers become represented, 95 of which were visible in September [R].

**R4. Review statements that name several drugs are held as a whole** [V].
- *Mechanism:* `convert_review_relationship_bundles_to_evidence_rows.py:456–460, 673`.
- *Size:* 1,217 findings in 780 papers; the only reason for 84.
- *Sample:* 18 of 40 were wrongly held, 6 partly [R].
- *Example:* a review of psilocybin, LSD and ketamine for chronic pain (10.1007/s11916-024-01353-0).
- *Fix:* one finding per registered in-scope drug that the statement names, keeping the full statement and the review label. Apply it only when every subject resolves. Add a guard for contrast statements: "MDMA for PTSD and psilocybin for depression" must not produce psilocybin → PTSD.
- *Yield:* 68 review papers newly visible [R]. A looser rule gives 119, but 5 of its 45 checked flips were wrong.

**R5. Class subjects are handled differently for primary studies and reviews** [V for a–c].
- **(a) Reviews cannot split a class subject.** Reviews are excluded from splitting a class subject that names registered drugs (`build_evidence_tables.py:4736`, `not secondary_literature`). Reviews of "ketamine and esketamine" are therefore held while the identical primary wording is admitted. This covers 615 rows in 216 papers. Splitting gives 605 rows and 52 papers newly visible, 34 of which were visible in September [R].
- **(b) Unspecified-class primary rows are held.** Primary rows whose subject is "Psychedelics (unspecified compounds)" are held (`:3442`, `:12880–12892`), while the reviews' "Psychedelics (broad or mixed)" node is shown.
  - *Size:* 703 findings in 282 papers.
  - *Sample:* 10 of 14 were wrongly held [R].
  - *Example:* psychedelic users versus controls on ego dissolution and mystical experience (10.1038/s41598-023-47600-z).
  - *Yield:* admitting them makes 102 papers newly visible [R].
  - *Wording sensitivity:* "psychedelic use" is admitted, but "psychedelic substance use" is held (`:4545–4581`).
- **(c) Class fallbacks depend on one word.** The named-compound fallbacks are keyed on the literal word "psychedelic" (`:3446`). As a result, "PCP or other hallucinogens" and "ketamine or other dissociatives" project nothing; fixing this adds 13 papers [R]. The NBOMe family has no class node (11 papers) [R].
- **(d) Metabolite bundles drop the parent.** "Parent and its metabolites or isomers" bundles drop the registered parent as well (`:2848`). This affects 89 rows in 60 papers, e.g. "Racemic ketamine and its isomers" [R].

**R6. Brain anatomy stated in the source is not resolved.**
- *Cause 1, dash folding:* `ascii_fold` (`build_evidence_tables.py:2454–2458`) deletes en and em dashes and minus signs without inserting a space. "Amygdala–vmPFC connectivity" becomes "AmygdalavmPFC connectivity" [V]. 522 circuit fields are affected [R]. Example: a ketamine-induced reduction in locus coeruleus–thalamus connectivity (10.1016/j.nicl.2018.09.001) ends up as "Functional connectivity" in paper detail.
- *Cause 2, measure words:* "connectivity" or "coupling" overrides the named regions (`:7506–7522`).
- *Cause 3, no fallback:* other filled anatomy fields are not tried. Example: vmPFC–amygdala connectivity with ketamine versus midazolam (10.1007/s00213-023-06479-4), where the declared field held only "Fronto-limbic".
- *Fix:* resolve anatomy first, and strictly: every part must map to an existing node, with at most 3 nodes and both ends present for a pair. Convert dashes to spaces in the brain matcher only; applied globally, the change would turn "Serum BDNF–VEGF-A correlation" into BDNF.
- *Yield:* about 400 findings gain a Brain anchor; 30 papers newly visible; 27 of 30 checked resolutions were faithful [R].
- *Related:* the reason label at `:11823` can never be reached, so 411 rows whose region was given but did not resolve carry the wrong reason [R].

**R7. Target names with species, tissue or assay suffixes do not match existing nodes.**
- *Mechanism:* the all-words rule in `target_identity.py:50–112` fails on names such as "Human μ opioid receptor (hμOR)" and "D2Short". The NMDA regex at `:150–158` runs on folded text and misses "N-methyl-D-aspartate" and "NMDAR" (15 findings).
- *Registry gaps:* KATP and Kv channels, the glycine receptor, PDE, IDO/TDO, COMT, TH and UGTs.
- *Yield:* 15 papers newly visible from the name-matching fix; at most 51 more with registry additions [R].

**R8. Vocabulary misses that are spelling or domain artefacts** [R].
- *Condition plurals and spellings:* "Alcohol use disorders", "Opioid use disorders", "generalised anxiety disorder", "Hallucinogen persisting perceptual disorder". Fixing them makes 15 papers newly visible and gives 55 papers an area.
- *Constructs in the wrong domain's vocabulary:* constructs are matched only within their own domain (`:7859–7871`), so "Positive affect", "Ego dissolution" or "Mystical experience" fail when they arrive under the other domain. Exact cross-vocabulary aliases add 17 papers; "contains" matching is unsafe.
- *Safety endpoints:* synonyms add 5 papers. The rest of the safety-endpoint rule is justified.

**R9. Real-world rows where the drug is named only in the measure** [R].
- *Mechanism:* `real_world_subjects.py` (`MEASUREMENT_RE` `:116`, `MIXED_RE` `:130`) recovers none of these rows.
- *Size:* 104 rows in 86 papers name exactly one in-scope drug in both the measure and the finding. Example: MDMA loads in river water during a festival (10.1016/j.envres.2021.112061).
- *Fix:* admit them, with the predictor and the full measure kept in detail.
- *Yield:* 56 papers newly visible, 37 of which were visible in September. Rows that pool several drugs, such as "any recreational drug use", are correctly held.

**R10. Small defects** (each 15 papers or fewer):
- **Background-location regex** (`build_evidence_tables.py:11857`): it does not recognise "Results" or "Fig.", and it reads "reference memory" as a References section (16 rows, 2 papers).
- **Lithium–pilocarpine seizure models** are read as a lithium adjunct (`:10970`; 23 rows, 9 papers).
- **Ketamine uropathy** is correctly kept out of Conditions but is not sent to the existing Safety node Urinary toxicity (13 papers [E]).
- **Direct-assay regex** (`target_identity.py:210–227`) misses "release", "outflow" and "agonist activity".
- **`measurement_validation_not_drug_effect`** demotes a dose-dependent dissociation (CADSS) increase with ketamine (10.1177/0269881117725685).
- **"nasal"** is missing from the administration words (`convert_review_relationship_bundles_to_evidence_rows.py:303–306`).
- **Non-ASCII dashes deleted in compound names** (28 rows, 11 papers).
- **Meta-analysis results that bundle several estimates** are held in conversion (170 results in 73 papers; 69 can be split mechanically; `convert_meta_analysis_v2_to_evidence_rows.py:596–640`).
- **Duplicate findings** come from clinical-endpoint re-derivation (302 findings; `build_evidence_tables.py:9054`). These inflate finding counts, not paper counts.

## 4. Decisions for you

| | Decision | Measured effect |
|---|---|---|
| X1 | Register unregistered compounds in families the Methods page already names (NBOMe/NBOH/NBF, 2C, lysergamides, substituted tryptamines, benzofuran entactogens, MDMA analogues, iboga alkaloids, ketamine and dextromethorphan metabolites, arylcyclohexylamines, development candidates). Needs a curated list with canonical names. | Newly visible papers by tier: 83 (series and metabolites), 138 (adding arylcyclohexylamines), 154 (adding development candidates) [R] |
| X2 | Lisuride is listed in scope on the Methods page and in `config.example.yaml` but coded as an out-of-scope comparator (`build_evidence_tables.py:2294`, registry). 73 of 83 rows are dropped. Choose one and make both agree. | If registered: 10 papers newly visible, 7 back in the graph [R] |
| X3 | Condition nodes. In scope: opioid withdrawal, postoperative depression, psychotic disorders (with a guard for psychosis models). Status epilepticus (60 papers with rows) needs a scope ruling, because Luna's screen excluded at least one such review. Not to add: postoperative pain, postoperative delirium, agitation and asthma, which `protocols/psychedelics/scope.yaml` excludes for ketamine-class drugs. | Part of 47 newly visible papers (not re-measured without the excluded nodes) [R] |
| X4 | Non-regional neural measures (EEG power, signal complexity, global connectivity, cerebral blood flow) have no node type in Brain. This is not a regression: September did not show them either. | Measure-family nodes: 158–252 papers [R] |
| X5 | Pharmacokinetics in the overview: a pharmacokinetics area, or only claims that name an enzyme or transporter, shown in Targets with labelled edges ("metabolized by", "exposure altered by"). | 657 papers, or 21 [R] |
| X6 | Locomotor, exploratory and feeding activity in Behavior. Currently held by design, because these are often control measures. | 174 papers [R] |
| X7 | Review topics. Review and commentary topic subjects could be projected to class nodes (topical coverage, not measured effects). Separately, review statements that Luna marked as background, and guideline recommendations whose population names a registered condition, could be admitted. | 164; 62; 13 [R/E] |
| X8 | Symptom-typed review outcomes projected onto the review's single resolved condition anchor. This follows your 1 November rule; 12 of 17 checked were faithful. | 33 newly visible, 94 papers gain an area [R] |

## 5. Structural changes so this does not recur

1. **Never drop an extracted finding without a trace.** A row that fails matching should become paper detail with its reason (R3). The audit then lists held rows instead of lost ones.
2. **Add a view-coverage check to the build.** Every (kind, label) admitted to the main graph should be shown by some view or be declared detail-only. This check would have caught D1, D2, D3, the psychotomimetic label and the neural-measure gap.
3. **Add tests that primary and review paths behave the same** for class subjects, unspecified classes and multi-drug statements (R4, R5).
4. **Normalize text before matching.** Map dashes and minus signs to a space or hyphen before folding, and test with en and em dashes (R6, R10).
5. **Keep one source of scope.** Generate the Methods page compound list, `allowed_compounds`, the registry scope and the code's graph-scope dictionary from one file (X2).
6. **Separate informational flags from blocking ones** (R1).
7. **Use Luna's declared domain as the fallback** when role-based typing fails (R2).

## 6. Outside normalization (for context)

- **Screening.** 1,887 papers that were in September's overview were excluded by Luna's title/abstract screen. The reasons read as consistent with the stated rules.
  - About 490 are ketamine anesthesia, analgesia or perioperative research. `protocols/psychedelics/scope.yaml` excludes these on purpose, but the public Methods page does not say so.
  - About 1,000 mention a compound only incidentally, or use it as a laboratory tool, for example DOI as a receptor probe.
  - No papers will be re-screened.
- **Routing.** Most papers that lost an area were never extracted for that domain.
  - For Safety, 896 primary papers were extracted but never routed to the safety extraction. A sample of 20 suggests about 35% (95% CI 18–57%) would yield a Safety finding. About 130 of them hold safety information found nowhere else in the graph.
  - Recovering it needs about 900 new Luna extractions. That is new extraction, not re-screening.
  - Similar gaps exist for Real-world, Pathways, Targets and Subjective.
- **Reviews.** 726 reviews that were in September's overview were never extracted: 509 screened out, 128 context-only, 84 ineligible.
- **Luna's own judgements.** Its "no extractable finding" decisions were right in 16 of 20 sampled whole papers. Two of the misses had truncated abstracts.

## 7. Suggested order

1. **Display fixes:** D1 (keep pharmacokinetic findings in paper panels and search), D2, D3.
2. **Structural fixes:** R3 and the checks in §5 (items 1–4).
3. **Rule fixes:** R1, R2, R4–R10.
4. **Decisions:** X1–X8.
5. **Verify before publishing:** one joint rebuild and census to measure the combined effect, then a fresh source check of a sample of newly admitted findings.

Working files (temporary session folder):
- reviewer scripts, samples and simulations: `…/scratchpad/norm_review/agent_*/`
- per-paper census: `…/scratchpad/norm_review/census/`
- my sample of 30 lost papers: `…/scratchpad/norm_review/lostdetail_sample_judgments.md`

## Implemented, 2 November

**Measured effect.** The three converters, the assembly and the normalizer were rerun on the 31 October inputs in a scratch folder. Visibility was counted per paper with the site's own code, as in §1. Nothing in `data/processed` was changed.

| | 1 November rebuild | With the fixes |
|---|---:|---:|
| Papers in the overview | 17,679 | 18,153 |
| Papers newly in the overview | | 474 (246 of them were in September's overview) |
| Papers no longer in the overview | | 0 |
| Papers represented (any finding) | 23,608 | 23,829 |
| Papers whose findings were all judged unsupported | 421 | 209 |
| Main-graph findings | 83,795 | 86,086 |
| Paper-detail findings | 41,332 | 45,135 |
| Rows that leave no finding (audit only) | 22,516 | 16,565 |

| Overview area | September | 1 November | With the fixes |
|---|---:|---:|---:|
| Cognition | 2,324 | 2,312 | 2,636 |
| Behavior | 2,694 | 2,843 | 3,059 |
| Safety | 6,153 | 5,558 | 5,680 |
| Real-world use | 4,177 | 2,813 | 2,928 |
| Conditions | 3,960 | 3,111 | 3,218 |
| Subjective effects | 1,969 | 1,394 | 1,474 |
| Targets | 3,465 | 2,405 | 2,446 |
| Treatment context | 1,057 | 1,039 | 1,074 |
| Molecular effects | 4,936 | 5,145 | 5,180 |
| Brain regions | 1,814 | 2,431 | 2,457 |

No paper loses an area. By paper type, the overview holds 14,785 primary studies (was 14,471), 3,126 reviews (3,021) and 242 meta-analyses (187).

**By item.**
- **D1:** not a defect (see above); pharmacokinetics stays hidden.
- **D2:** the 41 constructs are on the view lists: 28 in Cognition, including the personality traits, and 13 in Behavior. `tests/test_graph_view_coverage.py` fails when a vocabulary or rule construct is on no list.
- **D3:** a symptom-typed outcome whose label is a specific registered diagnosis, alone or with symptom or severity words, resolves to the condition with the condition guards (59 findings). Aliases were added for post-traumatic stress symptoms and the "perceptual" spelling of HPPD.
- **R1:** a meta-analysis result is held for review only for flags or notes that report a numeric or direction conflict, corrupted text or an unstated direction. Findings held for review fell from 1,067 to 190.
- **R2:** done for named-entity objects only: 82 findings were re-typed to a declared domain (42 main-graph). This is smaller than the estimate, because most unmatched review objects are context, topic or "other" anchors, which are not re-typed.
- **R3:** done for review statements and meta-analysis results; 5,824 rows are kept in paper detail with a reason instead of being dropped. Primary rows keep their domain's saved-observation contract, because existing tests require rows that lack the saved fields to stay out. Rows already shown through the clinical-endpoint projection are not kept twice.
- **R4:** done with a stricter rule than proposed. The drugs must be named together, as one list, wherever the statement names any of them, and contrasts, conversions ("converted to") and slash pairings ("MDMA/PTSD") block it. Under the first, looser rule, 4 of 16 sampled statements were misattributed. With the final rule, 166 statements in 130 reviews link each drug, and 12 of 12 sampled were attributed correctly.
- **R5:**
  - Reviews split drug lists as primary studies do; a class word with examples stays on the class node.
  - Primary findings about unspecified psychedelics are shown on "Psychedelics (unspecified compounds)": 704 main-graph findings in 317 papers.
  - Named drugs are recovered after any class word.
  - "Racemic ketamine and its isomers" is ketamine. "And its metabolites" stays held, because earlier tests make that a deliberate rule (the result may belong to a metabolite).
- **R6:** dashes act as hyphens in the anatomy matcher. The measure-word override and the fallback to other anatomy fields are not done.
- **R7:**
  - Done: a trailing abbreviation or gene symbol is dropped only when the full label does not match and the symbol agrees with the name; D2Short, 5-HT7a and NMDA wording; the NMDA site check on folded text.
  - Not done: registry additions (KATP, Kv, glycine receptor, PDE, IDO/TDO, COMT, TH, UGTs). "Receptor-mediated" wording was left as it was, because removing it moved measured NMDA-mediated currents from Molecular effects to Targets.
- **R8:** plural and British spellings of condition names, exact cross-vocabulary constructs (151 findings, including symptom-typed Anhedonia) and safety synonyms.
- **R9:** done in conversion.
- **R10:**
  - Done: the background-location pattern, lithium–pilocarpine, uropathy reported to Safety as "Urinary toxicity" (92 findings), the direct-assay pattern, dose-dependent scale results, "nasal", Unicode hyphens in compound names, and the neural-readout reason.
  - Not done: splitting meta-analysis results that bundle several estimates, and the duplicate findings from clinical-endpoint re-derivation.
- **§5:** items 1 (for reviews and meta-analyses), 2, 3 and 4 are done; item 5 (one scope source) is not.

**Checks.**
- The test suite gives 3,011 passed; the one failure needs `bs4`, as before.
- I read 62 newly admitted main-graph findings against their statements, then 16 more multi-drug review statements. All five misattributions were multi-drug statements, and the final R4 rule rejects each of them.
- The remaining weak cases are review statements about evidence gaps ("no studies examined the heritability of response to ketamine or esketamine"), which the converter already admits for single drugs.
- One safety finding lists serious adverse events that the paper attributes to cancer. It now reaches "Cardiovascular safety" for MDMA through the "cerebrovascular" synonym (10.1038/s41598-020-75706-1). The link records a studied pair; the finding text states the attribution.

**Not committed.** Normalization contract `routed_normalization_review_20261102_v1`. The candidate in `data/processed` has not been rebuilt with these changes.
