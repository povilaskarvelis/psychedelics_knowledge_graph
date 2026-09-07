# Research-area classification audit — 6 September 2026

The MDMA–Parkinson’s example is a real routing error, and the problem is systematic. A targeted semantic audit identified **209 high-confidence misclassified normalized finding rows from 171 distinct DOI records**, spanning 72 compound–entity–kind pairs. **197 of these rows are in Conditions.** These are errors relative to the saved finding’s meaning; they are not 209 independently verified medical claims or independent experiments.

The audit covers the **active local release**, `full_corpus_normalization_patch_qa_20260724`, not a fresh download of the live website. No extraction, KG, UI, active pointer, or published data was changed.

## Scope and counts

The release contains 97,195 normalized rows; 80,824 are marked `main_graph`. Conditions contains 9,697 rows in total, of which 8,592 are marked `main_graph`.

Automated checks inspected the admitted rows for disease/adverse-event confusion, population and comparator roles, reverse therapeutic-to-safety routing, disease-model language, and selected boundaries across Cognition, Subjective experience, Brain, Molecular effects, targets and PK. The checks selected **621 distinct candidate rows**. Manual semantic review of the candidate text and metadata produced the 209-row high-confidence set. The other **412 are not confirmed errors**: they include legitimate therapeutic findings, mixed-role statements and unresolved cases. They must not be reported as 412 additional errors.

All 209 reviewed errors have a matching compound–concept–kind edge in the relevant active graph bootstrap. This verifies exported graph relevance, not survival of every row through every interactive UI filter. The set includes 157 primary-evidence rows, 48 review rows and 4 meta-analysis rows. There are 202 distinct DOI–compound–entity–support-text combinations; seven row repetitions disappear under that exact-text deduplication. Neither count substitutes for scientific finding-level deduplication.

| Error class | Rows | Appropriate handling |
|---|---:|---|
| Adverse events, safety or tolerability filed under Conditions | 106 | Safety; some exposure-risk associations also belong in Real-world |
| Ketamine-associated uropathy filed as a ketamine indication | 38 | Safety; separate management by surgery, cessation or other drugs |
| Disease models or induced disease-like symptoms filed as indications | 16 | Cognition/psychotomimetic effects or Safety, depending on context |
| Cognitive, neural, molecular or endogenous-analyte findings using diagnosis as outcome | 11 | Route by measured endpoint and keep diagnosis as population context |
| Therapeutic findings filed under Safety | 11 | Therapeutic conditions/symptoms; remove spurious duplicate safety projections |
| Preferences, preparation, acceptability and intervention context filed as efficacy | 10 | Intervention context or Real-world attitudes |
| Exposure or population comparisons filed as treatment research | 8 | Real-world or paper detail |
| Policy, scheduling or economic modeling filed as clinical outcomes | 5 | Real-world/policy/health economics |
| Bibliometric research trends filed as clinical outcomes | 3 | Research-topic coverage or paper detail |
| Hospitalization for psychosis filed as a transient cognitive construct | 1 | Safety |
| **Total** | **209** | |

By displayed compound, the largest counts are ketamine (104), MDMA (26), psilocybin (21), S-ketamine (16) and LSD (9). These are counts of identified errors, not comparative error rates: compound evidence volumes differ substantially.

This is a **targeted lower-bound inventory, not an estimate of total prevalence**. All rows were eligible for specified automated checks; all rows were not independently read and adjudicated. The audit is deepest at the Conditions/Safety boundary and shallower elsewhere. It does not establish that the remaining research areas are clean. Manual judgments mostly assess internal semantic consistency against saved extraction text, not independently re-read source articles.

## The MDMA–Parkinson’s example

DOI: `10.1186/s13256-023-04147-x`.

The original report describes one genetically vulnerable patient with early-onset Parkinson’s following MDMA use. Its abstract explicitly characterizes the overall evidence as mixed and limited. This is a suspected safety association, not proof that MDMA causes Parkinson’s and not a therapeutic MDMA study. [Source abstract](https://pubmed.ncbi.nlm.nih.gov/37740189/).

The saved routed evidence already contains **both** a Safety row and a clinical-outcome row describing this suspected association. The clinical row survives normalization as Parkinson’s disease and receives the `studied_for_condition` relation. The correction therefore needs to reconcile the duplicate semantic contribution; simply adding another Safety row would not fix the misleading Conditions edge.

Two other MDMA–Parkinson’s entries, `10.2174/1874402801104010020` and `10.5860/choice.44-6879`, describe retracted claims in their saved support text. They should not be therapeutic indications or affirmative evidence of harm. They require explicit retraction/context handling. The latter has book-review metadata and a chapter locator, which also warrants a separate source-identity/inclusion check; this audit does not independently establish its source validity.

## Representative additional problems

These examples paraphrase saved findings. Their DOIs and full saved text are in the audit CSV; they are not independently verified medical conclusions.

- **DMT → PTSD and major depression**, `10.7759/cureus.79308`: the finding describes persistent delusional parasitosis after recreational DMT use. PTSD and depression are pre-existing diagnoses, not treated endpoints.
- **Psilocybin → ADHD and bipolar II disorder**, `10.3389/fpsyt.2023.1221131`: the finding describes a manic episode with psychosis and hospitalization. The subject’s diagnostic history has become two misleading condition links.
- **Ketamine → treatment-resistant depression**, `10.1192/bjo.2025.10711`: the row reports ketamine-induced cystitis during depression treatment. It belongs to Safety even though the parent study concerns a therapeutic use.
- **Ketamine → ketamine-associated uropathy**, `10.21037/tau-21-188`: several rows report outcomes of bladder surgery. Ketamine is the damaging exposure, not the surgical treatment. This needs subject-role correction as well as area correction.
- **Ketamine/NMDA antagonists → schizophrenia**: a group of rows concerns provoking or reproducing symptoms to study the disorder. Legitimate therapeutic schizophrenia findings also exist, so deleting every schizophrenia edge would be wrong.
- **Ketamine → Psychosis risk**, `10.1016/j.psycr.2022.100100` and `10.1186/s43045-024-00420-x`: six rows report depression remission or reduced/resolved suicidality but are labeled as psychosis risk. Correct therapeutic projections of these statements also exist.
- **MDMA → Psychotomimetic effects**, `10.3390/ijerph9072283`: the saved finding describes new psychosis requiring hospitalization. Normalization calls this transient psychotomimetic activity, losing the clinically serious context.
- **MDMA → PTSD and psilocybin → TRD**, `10.38126/jspg280103`: statements about proposed drug scheduling are filed as condition findings. They are policy claims, not observed clinical outcomes.

## Root causes supported by the data and code

1. **Research area is inferred from the entity instead of the finding’s role.** In `pipeline/kg/build_evidence_tables.py`, `entity_kind_for` (around line 7990) accepts existing kind overrides or domain defaults. `relation_type_for` (line 8105) then turns a primary condition kind into `studied_for_condition`. The relation does not independently establish therapeutic intent. A disease can instead be an adverse outcome, population feature or experimental model.

2. **Upstream duplication is not resolved semantically.** The saved MDMA–Parkinson’s input already contains parallel clinical and safety interpretations. Downstream normalization preserves the clinical interpretation. Existing exact/proposition checks do not necessarily reconcile paraphrases spanning different domains.

3. **The psychosis boundary is too aggressive and ignores negation in the anchor.** `apply_psychosis_family_boundary` (line 8971) searches entity labels and original text for psychosis-family wording. Unless model-like wording matches its other regex, it defaults to Safety. The upstream label for `10.1016/j.psycr.2022.100100` is a patient description containing **“without psychotic symptoms”**. That negated phrase still triggers the rule. Calling the function with this label and a depression-remission statement reproduced `safety_tolerability`, `Psychosis risk`, and reason `induced_or_exacerbated_psychosis_routed_to_safety` in the current code.

4. **Other boundaries are narrow and wording-dependent.** The nontherapeutic checks around lines 9426–9575 cover selected substance-use contexts, HPPD, research history and psychosis models, but do not constitute a general finding-role classifier. Semantically equivalent statements can be handled differently. The psychotomimetic regex also includes PANSS/BPRS names, which alone cannot determine whether symptoms are transient, therapeutic endpoints, or a serious clinical adverse event.

5. **Disease cohorts and other interventions become compound indications.** Uropathy management is the clearest example. A source may study a disease caused by ketamine and then treat it with surgery. A correct disease name and a correct compound mention are insufficient evidence for a ketamine-treatment edge.

6. **A clinical study generates many kinds of finding.** A depression trial’s adverse-event count, acceptability survey, brain readout and symptom response should not all inherit the same clinical condition anchor. Conversely, a therapeutic response in someone with psychotic symptoms must not automatically become a risk claim.

## Correction strategy

- Assign a **finding-level relation role** before normalization: therapeutic outcome, induced harm/risk, disease model, population context, mechanism/readout, intervention context, exposure association, policy/economics or research metadata. Keep outcome direction and evidence certainty separate from this role.
- Require a condition edge’s disease to be the actual therapeutic endpoint or explicit therapeutic review topic. Keep patient diagnoses as metadata when a different endpoint is measured.
- Preserve negative/null therapeutic results in Conditions. Do not infer an adverse event solely from worsening scores or lack of efficacy. Preserve no-event and reduced-risk results in Safety when safety is the measured endpoint.
- Make psychosis handling explicitly sensitive to negation, baseline disease, treatment response, persistence, hospitalization and model intent. A psychosis keyword or PANSS/BPRS measure alone should not force a safety/cognition label.
- Reconcile equivalent cross-area projections within each DOI. Remove spurious projections and preserve valid distinct findings; do not blindly move every row or discard all evidence on an affected compound–condition pair.
- Re-extract only reports whose structured roles or source support cannot be repaired reliably from saved material. Rebuild a versioned candidate release and inspect changed edge support counts before promotion.
- Use the reviewed errors as a regression set alongside valid controls: treatment nonresponse, symptom worsening as a therapeutic endpoint, no manic switch, genuine ketamine schizophrenia treatment, disease-model psychosis, persistent drug-induced psychosis, and postmortem drug concentration measurements. The last can legitimately remain in PK even when the surrounding case is fatal.

No production correction was performed as part of this investigation.

## Artifacts and reproduction

- `docs/evaluation/research_area_audit_2026-09-06/high_confidence_findings.csv`: the 209 reviewed rows with IDs, DOI, original text, category, proposed destination and rationale.
- `review_queue.csv` / `review_queue.json`: all 621 candidates and assessment status.
- `manual_judgments.json`: explicit ID-based semantic judgments, separate from selection rules.
- `summary.json`: counts, release ID, source SHA-256 and limitations.
- `upstream_trace_examples.json`: saved routed inputs for the Parkinson’s and reverse-psychosis examples.
- `audit.py`: read-only scan and aggregation; does not call a model or change KG data.

Run from the repository root:

```bash
python docs/evaluation/research_area_audit_2026-09-06/audit.py
```

Validation completed: the scan reran successfully; every judgment ID resolves to a selected current finding; all selected errors have an exported matching graph edge; row/category/source counts reconcile. The negation failure was separately reproduced by calling the current boundary function. No application tests were needed because this change adds investigation artifacts only.
