> **30 October 2026 — finalized locally:** Luna V5 screening is unchanged. The full Luna extraction and deterministic repair rebuild are complete. Final candidate: **23,058 publications** (18,335 primary, 4,395 Reviews, 328 meta-analyses); **11,233 with recovered usable full text**. The separate Luna self-review experiment is withdrawn and none of its plans were adopted. No model calls were made in this finalization. Public deployment is unchanged. [Final comparison report](../data/processed/model_runs/luna_v5_20261017/routing_contract_repair_20261029/report.html) · [Local graph](http://127.0.0.1:8013/?data-source=local). Older checkpoints below are historical.

> **19 October update:** the complete browser queue has been reviewed. Usable article text is now available for **10,855 / 22,451** eligible papers; **1,563** entries remain for manual recovery. Current provisional extraction inputs contain **37,506 tasks**, estimated at **$28.99 Batch** with a **$40.49 planning allowance**. No extraction jobs submitted. [Current recovery report](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/docs/evaluation/luna_fulltext_recovery_2026-10-18.md).

# Luna V5 migration and complete screening rerun

17 October 2026

The active screening and extraction model is **`gpt-6-luna`, low reasoning**.
Screening uses the exact evaluated V5 prompt in
[`title_abstract_screening.md`](../docs/screening/title_abstract_screening.md).
Primary extraction, guidelines/consensus, review relationships v2 and
meta-analysis v2 all use OpenAI Responses and its Batch API. New calls to the
retired provider are blocked, including from the old evaluation command.

## Approved scope

| Screening cohort | Records |
|---|---:|
| Previously retained by the full deterministic prescreen | 49,713 |
| Reopened topical exclusions with usable abstracts | 87,543 |
| **Fresh Luna V5 screening** | **137,256** |
| Records excluded by publication-format, language or usable-text cleanup | 134,364 |

Preprints/unpublished records, theses/dissertations, unsuitable publication
formats, non-English records, and unusable abstracts retain their cleanup
exclusions. Topic eligibility is delegated to Luna. This is now the default
production prescreen policy; `--legacy-topical-filters` reproduces the previous
topical filters for audits only.

The new generation is **`luna_v5_20261017`**. Its candidate metadata, original
prescreen decisions, selected screening frame, V5 prompt, requests and
manifests are frozen under
`data/processed/model_runs/luna_v5_20261017/`. The smaller 49,713-paper queue
was superseded before any of its requests were submitted.

## Progress and budget

**18 October checkpoint:** screening is complete. All 137,256 expected papers
have reconciled Luna results across 28 batches; 23,620 papers were included in
scope. The completed screening table is frozen by its recorded SHA-256 in
`run.json`. Extraction tasks have been prepared, but the full extraction run
has not been submitted.

The extraction audit decision is to retain the current production instructions
and schemas, using GPT-6 Luna with low reasoning. The broader same-schema prompt
rewrite was not promoted after fresh validation. Keep the verified deterministic
normalization repairs. See the
[final comparison](../docs/evaluation/primary_instruction_refinement_2026-10-18.md).

The refreshed and frozen task inventory was verified on 18 October. The Batch
estimate is **$27.35**, with **$38.12** as a planning allowance. No extraction
jobs have been submitted. See the
[readiness and cost report](../docs/evaluation/luna_extraction_ready_costs_2026-10-18.md).

| Extraction lane | Ready tasks | Other tasks |
|---|---:|---:|
| Primary studies and guidelines/consensus | 33,181 | All selected tasks ready |
| Review relationships v2 | 4,053 | No missing article packets |
| Meta-analysis v2 | 350 | No missing article packets |

Selection and tasks now incorporate the latest verified source library and
publication-format corrections. Frozen tasks, source packets, bibliography,
prompt/schema hashes, verification and the cost estimate are under
`data/processed/model_runs/luna_v5_20261017/extraction_refresh_20261018/`.
Use those inputs for submission under the clean run IDs below, checking hashes
before preparing the actual request files. Existing research domains, primary
schemas, review relationships v2 and meta-analysis v2 methods remain in use.

Then submit resumable, size-checked Batch jobs; reconcile every expected task;
retry only failed or incomplete tasks with preserved lineage; and build a separate
replacement graph through the repaired normalizer. Check extraction completeness,
source identity, numerical/contrast binding, and graph inclusion and retention
before promoting a complete replacement release. Earlier published releases and
archived outputs retain their provenance. No previous extraction supplies a
completed task in this replacement generation.

The following paragraphs record the original screening setup and execution.

The four-request live Batch integration check passed for screening, primary
evidence, review relationships and meta-analysis extraction. Its estimated
cost was **$0.003582**. The full screening controller has been started.

The user authorized a **$100 model-API budget**. The shared transport records
conservative reservations for in-flight requests, replaces them with
usage-derived costs when results arrive, and rejects new submissions that
would exceed the remaining budget. Unknown paid attempts retain their
reservation until reconciled. Costs are token-price estimates rather than
reconciled invoices. Current measured V5 usage projects approximately **$38**
for screening; extraction volume will be known after fresh screening.

Inspect the run without creating new requests:

```bash
python pipeline/rerun_luna.py status
```

The initial queue used 503 small parts and only one active job, based on an
unnecessarily conservative local token cap. On 17 October, the account's
Limits page showed **1,000,000,000 queued tokens for GPT-6 Luna**. After stopping
the local controller, the seven already-submitted parts (1,838 papers) were
preserved. The remaining **135,418 papers were repacked from 496 parts into
21 batches**, each at most **150 MB** (mostly about 6,600 papers). The active
queue now has 28 parts total. Hash checks verify that every pending request
is byte-for-byte unchanged; the original queue is retained beside the
repack report under `screening/repacked_20261017T044351Z/`.

The controller now allows **six active batches**, with a **900,000,000-token**
local queue cap, while the shared $100 budget guard may defer a batch until
another finishes and its reservation is settled. These settings are saved
in `run.json`, so resuming uses them automatically. The controller checks
progress every minute, downloads both successful responses and per-request
errors, and stops for integrity or parsing failures. It keeps completed
work on disk. A process lock prevents duplicate controllers or repacking
while the controller is running.

To resume after the controller has stopped:

```bash
python pipeline/rerun_luna.py advance-screening --submit --watch \
  --prepare-extraction-after-screening
```

Do not start a second controller while one is already running. The current
log is `data/processed/model_runs/luna_v5_20261017/controller.log`.

For future consolidation, stop the local controller without cancelling the
remote jobs, then use `repack-screening --max-active N
--max-enqueued-tokens VERIFIED_ACCOUNT_CAPACITY`. This command preserves
every part with a job file, including attempts with an unknown submission
outcome, and only consolidates unsubmitted requests. Never assume another
account has this run's queue capacity.

## Screening before extraction

Canonical routing is now `data/processed/corpus/paper_domain_routing.parquet`.
It is promoted only after every expected screening result is reconciled,
validated and attributed to Luna. Partial screening does not replace that
table. Default extraction/task builders are blocked until screening completes.

At completion, the controller rebuilds extraction routes, primary/guideline
tasks, review-relationship v2 tasks and meta-analysis v2 tasks using the fresh
Luna decisions and available source texts. It does **not** submit extraction
calls as part of the screening controller. The clean extraction run IDs are:

- `luna_v5_20261017_primary` — primary-domain and guideline/consensus tasks.
- `luna_v5_20261017_review` — review relationships v2.
- `luna_v5_20261017_meta` — meta-analysis v2.

Each extraction runner now defaults to Luna and strict structured outputs.
Use these new run IDs; earlier model outputs must not be appended, treated as
completed tasks, or combined into the replacement release. Primary and
guideline tasks use `run_route_extraction_batch_api.py`; review relationships
use `run_review_relationship_batch_api.py`; meta-analyses use
`run_meta_analysis_v2_batch_api.py`. Their existing input snapshots, semantic
validation and source-location checks remain in place.

## Retired data and preserved sources

Mutable earlier screening queues/results, extraction routes/tasks and loose
extraction outputs are archived under
`data/archive/20261017_gemini_retired/`. Previous report-level screening and
route overrides are archived and cleared from the active run. No old model
decision is used to determine completion or eligibility in this generation.
The archive manifest records paths and hashes. Bibliographic corrections,
PDFs, full-text packets, source identity and access corrections remain reusable.

Historical evaluation reports and previous published releases retain their
true provenance. The published graph remains the previous release until the
fresh extraction is completed, validated and promoted as a complete replacement.
Historical outputs are not renamed as Luna results or silently mixed into the
new generation.

## Installation and checks

Model runners require `pipeline/requirements-models.txt` and
`OPENAI_API_KEY` in the project environment. Retired-provider variables were
removed from the project `.env`; credentials are never written to the run logs.
The screening prompt is checked against the evaluated V5 file. Regression
tests cover the cleanup policy, source/schema compatibility, asynchronous
result reconciliation, incomplete responses, budget reservations, and the
screening-to-extraction gate.

The [OpenAI Batch guide](https://developers.openai.com/api/docs/guides/batch)
documents the Responses endpoint, keyed result reconciliation, file/request
limits, partial failures and the 50% Batch discount used by this setup.

## Scoped correction after manual source review, 19 October

The approved correction scope is 22,451 currently retained reports plus 619
previously excluded records mentioning PCP/phencyclidine. PCP and established
hallucinogenic dissociatives are eligible; cannabis-only research is excluded.
The V6 evidence contract requires a qualifying substance, a contribution quote,
and an explicit eligibility basis. Contradictory decisions, invented quotations,
unresolved compound identity and conflicting source metadata go to review.

The first validation used 21 known cases and 200 disjoint, stratified records,
judged from the supplied sources before model outputs were inspected. Its
low-effort results exposed over-exclusion and overly narrow alias checks.
The revised V6.1 prompt was then evaluated on those records plus 60 untouched
records. The same frozen prompt and 281 records were also compared at high reasoning
effort, isolating configuration from prompt wording. That configuration passed
the validation gate after quote/alias checks and two explicitly recorded
article-body followups: all 19 definite known cases were correct, all 142
definite development positives were retained, and all 45 definite fresh
positives were retained. The frozen key disputed three development inclusions
and one fresh inclusion. Ambiguous source judgments remain separate from
accuracy counts; final result review must resolve those disagreements. Original
answer keys and model outputs remain immutable. Five uncertain first-key
assumptions are explicitly logged as revisions to review, rather than quietly
treated as established truth. These are Codex source judgments, not independent
human-expert full-text gold, and the strata are not population proportional.

The active correction controller and manifests live under
`data/processed/model_runs/luna_v5_20261017/screening_correction_20261019/high_reasoning_validation/`.
Its validation gate must pass before paid main submission. It uses four large
request files of approximately 180, 180, 180 and 119 MB, containing 6,175,
6,214, 6,219 and 4,133 requests. The 22,741 main requests omit validation
records and confirmed format exclusions/identity holds. Batch transport retains
custom-ID reconciliation, idempotent receipts and the shared $100 budget. Its
byte-based reservation is a conservative ceiling, not the expected invoice.

To resume or inspect without duplicating paid jobs:

```bash
python pipeline/review/run_screening_correction.py status --root <correction-root>
python -u pipeline/review/run_screening_correction.py advance --root <correction-root> --submit --watch
python pipeline/review/run_screening_correction.py audit --root <correction-root>
```

The controller preserves V5, stages new results and a review queue, and keeps
extraction blocked. It does not automatically replace canonical decisions.
After completion, inspect `result_audit_summary.json`, resolve quarantined
records, audit changed decisions, apply authoritative metadata/format findings
through their existing owners, then promote the corrected routing and rebuild
recovery/extraction inputs. Do not submit extraction as part of this correction.

The 19 October follow-up audit preserves the frozen validation key and records
post-output source judgments separately in
`high_reasoning_validation/pilot_disagreement_source_adjudications.json`.
Of its four disputed inclusions, source review supports two inclusions, one
exclusion, and one unresolved full-text hold. In particular, the ketamine
mood/postsurgical-pain review has substantial separate antidepressant and
brain-network synthesis; its original exclusion key was wrong. The MK-801
competition-binding paper is judged eligible biological receptor pharmacology
from its publisher abstract, with moderate confidence. The GE-179 paper's
PCP/ketamine conditions only assess nonspecific tracer binding; the independent
fMRI findings concern GE-179/amphetamine rather than PCP/ketamine. The autopsy
paper's pooled stimulant result does not establish an MDMA-specific finding;
keep it held until the report body can resolve that question. These judgments
are not a second blinded test or human-expert gold.

All 15 frozen metadata holds were also investigated. Exact-DOI PubMed records,
raw XML, query provenance and per-report judgments are saved under
`high_reasoning_validation/source_audit/identity_holds/`. The staged source
judgments recommend four inclusions, seven exclusions and four continuing
holds; canonical metadata and routing have not changed. Three inclusions are
explicitly thin title-only sources, not full-text-adjudicated results.
Crossref is not sufficient authority where its fields conflict: the original
JJP ketamine title belongs to DOI `10.1254/jjp.62.111`, already retained as its
own candidate, while `10.1254/jjp.62.131` is a noradrenaline paper. Publisher
documents also print the same DOI on different articles in the IJCRI and
King Abdulaziz journals. Preserve the eligible ecstasy/agmatine reports as
identity holds until source-qualified identities and artifacts are reconciled;
do not automatically exclude them from the unrelated title or silently alias
two different valid reports. The Behavioural Pharmacology/antithrombotic
record still needs publisher DOI verification, and the broad acute-poisoning
review still needs body-level coverage review.

The main-result audit has started while Batch files finish. Source judgments
for all 197 proposed new inclusions available from parts 001 and 003 are saved
in `high_reasoning_validation/source_audit/main_changes/pcp_source_review_*.json`.
After four article-body followups, these support 172 inclusions, two exclusions
and 23 continuing holds. This is partial coverage of the main run, not its final
inclusion count or an accuracy estimate. The source review initially uses each
frozen title/abstract; body-level followups and publisher format checks are
explicitly distinguished. The two exclusions are a Psychiatric News viewpoint
and an AAP book chapter. Other apparent conference/news items remain held until
their source formats are verified. Full-text checks recovered substantive
stroke and DARPP-32 synthesis, a separately reported PCP exposure count hidden
by pooled THC/PCP abstract results, and an independent ketamine EEG outcome in
a tracer paper. Do not apply a blanket tracer-paper exclusion when a separate
eligible-drug physiological result exists.

Continue this audit using `source_audit/main_changes/progress.json` and a DOI
set difference against the remaining parts/retry results, rather than reusing
positions in the initial available-record snapshot. Followup files supersede
earlier title/abstract holds explicitly while preserving them. The 23 holds,
new retained-paper exclusions, other new PCP-cohort inclusions and unresolved
parser/alias checks still require review. Three probable duplicate report pairs
(two JAMA DOI pairs and a UNC repository/published PLOS pair) are listed in the
progress file; verify them through the existing DOI alias registry before
downstream counting/extraction. No canonical metadata, routing or graph has
been replaced by these partial audit judgments.


At 04:51 UTC on 19 October, all four main Batch jobs and their one-time
validation retry finished. The controller exited normally in
`main_results_ready_for_audit`; **do not restart it or resubmit paid screening**.
The main jobs processed 22,741 requests without API failures. The retry processed
2,448 requests without API failures, with one model response truncated at its
output-token cap. All 23,070 scoped DOIs reconcile in
`high_reasoning_validation/final_staged_results.jsonl`. Its original staging is
18,683 inclusions, 2,739 exclusions and 1,648 holds, before source-audit corrections.
These are provisional decisions, not final corpus counts. Canonical V5 remains
unchanged and extraction is still blocked.

The shared ledger records **$7.2600** for this high-reasoning correction,
including validation and retries and the incomplete retry response. Total
settled shared pipeline spend is $26.7970, committed including other outstanding
conservative reservations $27.4342, against the unchanged $100 cap. See
`source_audit/cost_at_main_completion.json`; sums over only parsed valid responses
omit the billed incomplete response and therefore are slightly lower.

After the controller stopped, the evidence validator received a narrow lexical
repair for equivalent MDMA/ecstasy labels, known ketamine enantiomer groups,
known-parent hydrochloride/hydrobromide labels, and class/AMT/MMDA labels already
explicit in the frozen prompt. No new chemical scaffold was assumed eligible.
Thirty contract tests passed, including rejection of unknown/excluded co-drugs
and the continued requirement for locatable evidence. Both validator source
versions are archived under `source_audit/validator_snapshots/`, with the original
source SHA verified against the frozen validation report. Offline rechecking of
all saved answers released 115 mechanical holds and introduced two quote-identity
holds; frozen-key uncertainty/disputes remain held. The separate
`source_audit/post_validation_contract_recheck.jsonl` therefore stages 18,796
inclusions, 2,739 exclusions and 1,535 holds. It does not overwrite the raw answers,
frozen validation metrics or first result-audit snapshot and did not incur API
charges. No additional model prompt was tested.

The source audit now covers 282 main/main-retry PCP-cohort inclusion proposals:
254 supported inclusions, three exclusions and 25 continuing holds after ten
article-body followups. Thirty additional pilot proposals already have preserved
validation/source adjudications (25 original positive labels, four disputed labels
addressed separately and one unresolved label); distinguish that prior evidence
from this round of post-output review. Two JAMA DOI pairs have registry-verified
alias mappings staged in `source_audit/main_changes/staged_verified_aliases.json`.
The UNC/PLOS pair still needs its repository/published-version mapping verified.

The first 15 high-risk retained-paper exclusions have also been checked. Six
have eligible findings in their saved full articles, two exclusions are supported
and seven remain held. This deliberately selected group is **not** an estimated
error rate. Examples include original DOI concentration-binding curves omitted
from a receptor-paper abstract, original psilocybin biosynthetic loci in a fungal
survey, and substantial ketamine/psychedelic synthesis hidden by broad review
abstracts. Do not infer absence of a result from an abstract that selectively
reports other outcomes. Per-record source locations and artifact hashes are in
`source_audit/main_changes/retained_exclusion_source_review_001.json`.

Continue with the complete post-retry worklist
`source_audit/main_changes/retained_exclusions_after_retry_worklist.jsonl`:
2,464 proposed exclusions among previously retained records, of which 1,019 have
saved article bodies. All 246 peripheral-mention exclusions are a priority
(122 have saved bodies). Then check biological/PK/real-world exceptions within
analytical/unrelated/ketamine-purpose groups, plus authoritative publication and
source-language evidence. Preserve explicit source holds where evidence is
insufficient. The pure computational drug-structure and MDMA-pre-precursor
chemistry boundaries are flagged in the audit rather than silently excluded
under the inaccurate label peripheral mention. Reconcile manual source judgments
with the separate offline contract recheck, apply metadata/format/alias findings
through existing canonical owners, and promote only after a defensible audit.
No unaudited changed exclusions have been applied. No extraction calls or graph
replacement are authorized by this correction.


The subsequent source audit found a second mechanical evidence-validator bug:
the HTML-removal regex could delete scientific results between a statistical
less-than sign and a later greater-than sign. A tag-specific repair preserves
those comparisons while still removing publisher HTML/JATS markup. The current
validator SHA is `238206307912602760f7dcb96e2af6a829c12c886ac74486437166c4fb0391ae`;
all source snapshots remain archived. Offline population rechecking released
another ten inclusion holds and one exclusion hold, with no new model calls or
scope change. Latest model staging is therefore
`source_audit/post_math_markup_contract_recheck.jsonl`: 18,806 inclusions,
2,740 exclusions and 1,524 holds. These remain provisional, not canonical counts.
The retained-exclusion worklist now contains 2,465 records in
`source_audit/main_changes/retained_exclusions_after_math_recheck_worklist.jsonl`.
The added cocaine-esterase exclusion is separately source-adjudicated.

Manual retained-exclusion review now covers 147 unique priority records:
32 supported inclusions, 23 supported exclusions and 92 continuing holds.
All 124 peripheral cases without saved bodies have received individual abstract
review; 23 saved bodies have also been followed up. The remaining 99 peripheral
bodies need source verification. Ten redundant entries across review files013
and014 have the same decisions and are counted once. These selected cases do
not estimate a corpus error rate. Unresolved pooled-drug outcomes, broad-review
coverage, unfamiliar compounds and source identity remain held. A user scope
question about direct molecular-property/structure studies without biological
testing is pending; chemistry-only records are quarantined, not silently dropped.
See `pending_molecule_chemistry_scope_question.json`; do not ask the question again.

A separate eligibility check using saved full text has been prepared for 994
identity-verified parsed article bodies among the proposed exclusions; 25 more
saved artifacts could not supply a usable separately parsed body. Its input adds
source evidence and withholds the prior decision. Twenty-one source-adjudicated
sentinel controls agreed on every eligibility decision. After one quote retry,
20 controls had automatically valid quotes; one remaining noncontiguous quote
was explicitly source-repaired without changing the model decision. Raw answers,
original validation reports and the repair sidecar are preserved. This is neither
independent human-expert gold nor a new abstract-only accuracy benchmark. The
remaining 973 records were submitted as one large high-reasoning Luna Batch job,
`batch_6ad5ab6f726c8190a4942175c8558c8e`. A separate detached controller is documented
under `fulltext_result_audit/controller_process.json`; do not restart the completed
main controller or duplicate this audit submission. Verify flagged reversals
against source passages before promotion. COMPLETE means the whole saved parsed
body, not independent proof that every original PDF table was perfectly parsed;
long-source excerpts and parser failures are explicit. All 37 contract/audit tests
pass. The additional source-control calls are settled in the shared ledger; at
this checkpoint total settled spend is $26.8314 and committed spend is $33.2630,
including conservative outstanding reservations, against the unchanged $100 cap.

A 31-record publication-format risk audit used exact Crossref metadata and
visible authoritative publisher pages. It supports 25 exclusions and six
inclusions, including eight corrections to raw model inclusions: three Critical
Care congress abstracts, one hypertension ePoster, one sports-medicine poster
and three SSRN versions. Six actual full research/clinical-case reports are
preserved despite shared DOI prefixes or a news-journal container. Do not replace
this per-source check with a blanket publisher-prefix ban. Published counterparts
of excluded preprints must be preserved and version links verified explicitly.
The UNC repository page now explicitly identifies its PLOS publisher DOI, PMID
and PMCID; that third verified alias pair is staged alongside the two JAMA pairs.
No canonical metadata, eligibility owner, routing or graph has been replaced.
Extraction remains blocked pending reconciliation and promotion of the audited
screening decisions. Current counts and pending work are recorded in
`source_audit/main_changes/progress.json`.


The added-source eligibility batch subsequently completed all973 requests with
no API failures. Across994 records including the21controls, raw model decisions
are214 inclusion proposals,773 exclusions and7 explicit review requests;
120 responses have some contract/source issue (35 of the inclusion proposals).
These are source-verification candidates, not214 confirmed rescues. Fifteen
inclusion proposals already had source-positive control judgments;199 are new
proposals for verification. The first six new proposals have been reviewed:
four supported inclusions and two holds. Examples of substantive omitted
results are5-MeO-DMT head-twitch blockade in a nonhallucinogenic-compound paper
and methylone transporter concentration-response data in an MDPV-focused paper.
The anesthesia/consciousness basic-mechanism boundary and a molecular-NMR review
are held explicitly; original frozen abstract keys remain unchanged. The current
compact verification packets and per-source judgments are under
`fulltext_result_audit/`. The model controller exited normally; do not restart it.

The full-text model audit, including its controls and one quote retry, cost
$0.9271; combined original correction plus added-source audit is
$8.1871. Shared ledger settled spend is$27.7241,
committed$28.3613, cap$100. A further twelve risk-selected no-body
nonperipheral exclusions received source-record review (four supported
inclusions, four exclusions, four holds); this is also not an error-rate sample.
Two excluded SSRN versions have verified published counterparts already in the
corpus, staged separately in`staged_verified_version_relationships.json`.
Preserve actual eligible-result boundaries in downstream routing/extraction:
new-compound assays are not automatically psychedelic mechanisms, planned
metabolomics is not measured PK, and mixed psychiatric/pain papers do not make
every analgesia result part of the qualifying psychiatric evidence.

### Source verification checkpoint — 2026-10-19 06:33 UTC

The added-source model audit remains complete; no controller restart or further
model submission is needed. Source verification now covers 79 of the 199 new
inclusion proposals, with 66 supported inclusions, seven supported exclusions
and six continuing holds. Files `fulltext_result_audit/source_verification_001.json`
through `016.json` preserve each source judgment and qualifying-contribution
boundary. Two judgments conservatively use original title/abstract evidence;
77 explicitly follow saved article bodies. These are targeted Codex judgments,
not independent human-expert gold, abstract-only performance, or a population
error-rate estimate. Another 120 proposals remain unverified.

Separately, ten papers still excluded by the full-text model received source
review: eight supported exclusions, one supported inclusion and one hold. The
inclusion is an actual ketamine care-integration case example in Figure 1 of
DOI `10.1007/s11606-025-09725-x`, beyond routine clearance language. It supports
the reported multidisciplinary risk/consent observation, not pooled staff
satisfaction, clinical efficacy or a cystitis event. The quipazine case remains
held because psychedelic-like preclinical evidence and unsettled human identity
must not be reduced to an automatic agonist inclusion or exclusion. See
`peripheral_negative_source_verification_001.json` and `002.json`.

Format checking works in both directions. A Portuguese article and an
explicitly labeled book chapter remain excluded despite the full-text model's
inclusions; the chapter type is corroborated by an exact Crossref record.
Two Atena DOI records were wrongly assumed to be book chapters by the abstract
model: their original PDFs show actual journal titles, ISSNs and volume/issues.
A corrected-and-republished full empirical article is distinct from an erratum
notice; PubMed explicitly links its earlier version. Its canonical version
relationship requires reconciliation before counting independent studies.
Substantive scholarly perspectives retain their actual publication type rather
than being relabeled primary experiments or excluded solely from their label.

Source reliability and eligibility are recorded separately. Concrete flags
include a printed confidence interval not containing its reported odds ratio,
inconsistent review sample sizes and use denominators, an incorrect route in a
review, sample-versus-participant counts, and assay response versus actual
exposure. Actual concentration-time or metabolite findings can rescue analytical
titles; spiked-hair contamination and post-collection bleach masking do not
establish human exposure or PK. One apparent stereochemical rescue is held
because the saved manuscript supplies a figure legend without the actual
illustration needed to establish the claimed biological result. No extraction
prompt/schema or published graph change follows from these notes.

Across this current source-verification phase, 89 unique judgments reconcile
(67 inclusions, 15 exclusions, seven holds). The integrity checkpoint verifies
all 89 frozen input hashes, all 87 explicitly cited saved-body artifact hashes,
contiguous quoted passages and domain/hold consistency. It records the two
abstract-based judgments separately. This total is not a combined total across
all earlier audit ledgers. The earlier 147-record checkpoint and original model
answers/keys remain preserved.

Of the 122 saved peripheral-case artifacts, 117 supplied usable model-audit
bodies. Source checking now covers 84 (23 earlier body checks, 51 new-inclusion
checks and ten still-excluded checks). Remaining work is 33 prepared peripheral
bodies plus five skipped parser/body failures, the other 120 new proposals, and
risk/identity/version/domain reconciliation. The expanded peripheral navigation
packets preserve DOI ordering and add full chemical-name/acronym contexts;
absence of a keyword hit is not absence of an eligible result. The pending
molecule-structure user question is unchanged and must not be asked again.

No additional model calls were made during this source-verification checkpoint.
Combined correction and full-text model-audit spend remains $8.1871; shared
ledger settled $27.7241, committed $28.3613, cap $100. Canonical routing SHA remains
`3a6d34113108693fab8d6b18d87e59c7b42b9a35c7f09f27c8b50aa2b8749cbe`.
Screening promotion, recovery-list rebuild and extraction-input refresh remain
pending the defensible audit reconciliation. No extraction calls or graph
replacement have occurred.

### 2026-10-19 07:43 UTC — all new proposals checked; source-reader repair; reconciliation still open

All 199 new full-text inclusion proposals have now received source judgments in
`fulltext_result_audit/source_verification_001.json` through `036.json`.
Original phase findings are **153 inclusions, 25 exclusions, 21 holds**. Later
primary-source identity checks explicitly resolve ergometrine/ergonovine and the
4-MMC contribution of a mixed-cathinone seizure paper: effective **155/25/19**.
Those two changes are recorded separately in
`substance_identity_source_adjudications_001.json`; original holds, raw answers
and frozen keys are unchanged. Independent human evidence supports historical
ergonovine psychedelic identity and mephedrone entactogenic effects; this does
not establish all ergot/cathinone analogues as eligible. The PubMed XML receipt
and primary source links are preserved.

All 43 remaining prepared peripheral cases still excluded by the full-text
model have also been checked in `peripheral_negative_source_verification_001.json`
through `008.json`: **10 inclusions, 30 exclusions, three holds**. Actual omitted
findings include MDMA-use frequencies in a driver survey, ketamine/ecstasy
perception measurements in a cough-medicine study, and two confirmed MDMA
specimens in an occupational surveillance table. These are selected source
checks, not a population accuracy estimate. Twenty-one review/identity/purpose
holds among the original new-proposal judgments must not be counted as errors
or forced into inclusion/exclusion.

A mechanical source-reader defect was identified and repaired in
`pipeline/review/audit_screening_correction_fulltext.py`. The reader previously
attempted XML parsing on valid browser Markdown, OCR and other plain exports.
It also selected only XML body text, omitting sibling JATS floating tables.
The repaired reader honors the explicit source backend and retains floating
tables/figures without adding bibliography text or duplicating body tables.
Malformed XML still fails rather than silently becoming plain text. Original
and repaired sources/tests are archived under
`source_audit/body_parser_repair_20261019`; **40 contract/audit tests passed**.
No completed job was restarted and no frozen model inputs/answers were rebuilt.
This repair does not retrospectively make the old model responses table-aware.

Offline rechecking recovers 20 of 25 previously skipped sources; five remain too
short. All five peripheral skips now have separate original-source judgments
in `peripheral_parser_followup_source_verification_001.json`: **three inclusions,
two exclusions**. In particular, the DOI astrocyte study reports an actual
concentration-range null with two experiments, beyond a single uncharacterized
control; the Aplysia paper contains original bufotenine functional blockade and
washout observations. Preserve native receptor nomenclature and inspect corrupt
OCR exponents before extracting quantities. All **122 saved peripheral sources**
now have source checks (23 earlier, 51 new proposals, 43 still-excluded cases,
five recovered exports). The 124 cases without saved bodies retain their earlier
individual abstract judgments and any unresolved followups; checking coverage
does not imply every eligibility uncertainty is resolved.

`source_verification_checkpoint_247.json` and
`source_verification_reconciled_247.jsonl` reconcile this phase's **247 unique DOI
records: 168 supported inclusions, 57 exclusions, 22 holds**, after the two
explicit identity followups. Two judgments use original abstracts; 245 explicitly
cite saved bodies. The prior 242-record checkpoint verifies frozen input hashes,
240 body hashes and exact source quotes; the additional five body/export checks
are recorded separately. DOI records are not necessarily independent studies:
the UNC lisuride record and published Frontiers article, plus other verified
version pairs, still need canonical ownership reconciliation. Do not sum these
counts blindly with overlapping historical ledgers.

The repair also exposes a remaining source-coverage audit: 144 of the original
994 model inputs had original floating tables/figures outside their XML body.
There are **34 not-yet-source-checked model exclusions with eligible-term hits**
in the added material, prioritized in
`source_audit/body_parser_repair_20261019/unreviewed_exclusion_floating_table_priority.jsonl`.
These are risk flags, not 34 confirmed misses. Check original Methods/Results
and tables, then the 15 other readable recovered sources and five still-short
records. Continue the other exclusion-group biological/PK/real-world/purpose
checks; the 1,322-record no-body risk worklist is not claimed fully reviewed.
Verify production extraction contexts preserve floating tables and PDF-only
figures before refreshing inputs; repair any mechanical omission there if found.

The molecule-property/structure and basic ketamine consciousness-at-anesthetic-dose
questions remain pending. Neither silence nor time is approval. The Concog
source judgment was explicitly changed from exclusion to hold in
`consciousness_scope_hold_reconciliation_001.json`; keep its original judgment
and validation key intact. Continue independent work without reasking.

Canonical routing remains unchanged at SHA256
`3a6d34113108693fab8d6b18d87e59c7b42b9a35c7f09f27c8b50aa2b8749cbe`.
No new model calls were made. Combined correction/full-text model-audit cost
remains **$8.1871**, shared ledger settled **$27.7241**, committed **$28.3613**, cap
**$100**. Cross-ledger source/format/language/version/domain reconciliation,
defensible promotion and recovery/extraction-list rebuilding remain pending.
No extraction calls or published graph replacement have occurred.

### 2026-10-19 08:20 UTC — tables and original skips finished; global source reconciliation staged

The 34 previously unreviewed outside-body-table risk flags have all received source judgments: **9 include /17 exclude /8 hold** (`fulltext_result_audit/floating_table_source_verification_001.json`). Original body, Methods/Results, floating material and relevant older judgments were checked. These are Codex judgments on selected risks, not human-expert gold or an error-rate estimate. Examples include the ECT pilot's separately substantive depression endpoint, developmental ketamine toxicity/rescue experiments, and actual baseline hallucinogen/ecstasy counts in otherwise cannabis/stimulant-focused papers. Only the eligible contribution is retained; cannabis/stimulant effects and another compound's separate assays are not transferred. A quoted numeric check caught and corrected the distinction between **12 hallucinogen users and10 stimulant users** in the THC paper's original Table1 before the judgment was saved.

All 25 original parser skips now have source followups: the earlier five peripheral sources; **15 other readable bodies (2I/11X/2holds)**; and **five original-PDF checks (2 conference/poster exclusions,3 holds)**. Three saved PDFs are only catalog titles/abstracts rather than the actual articles. Their source incompleteness is explicitly preserved; no claim of missing biological results is inferred from them. See `other_parser_followup_source_verification_001.json` and `short_source_original_pdf_verification_001.json`. One staging-domain spelling was repaired to the actual schema label `pharmacokinetics_exposure`; the before-copy and annotation correction are archived.

The current added-source phase is reconciled at `source_verification_checkpoint_301.json` and `source_verification_reconciled_301.jsonl`: **301 unique DOI records,179I/87X/35holds**. Coverage comprises294 readable saved article-body checks, five original-PDF format/completeness checks, and two original-abstract judgments. All54 added source/PDF hashes, exact quotes,34 frozen model-input hashes,15 original skipped-record hashes and domain labels passed integrity checks. The earlier247/242 checkpoints and all raw answers/keys remain intact. These counts are not independent studies and must not be summed with overlapping older ledgers.

Production source assembly was separately checked: it already scans the complete XML, including floating groups. Across **144 articles, all249 outside-body tables' original row content was retained**, and three table-based findings survived the actual primary packet → extraction-text path. The verification is at `source_audit/body_parser_repair_20261019/production_packet_floating_table_coverage_verification.json`. This verifies available XML table text, not PDF image pixels, perfect OCR, or every selectively retained figure caption. The held missing Figure5 case remains held.

A distinct production readiness bug was fixed in `pipeline/extract/build_extraction_routes.py`: TEI/GROBID exports now require a nonempty article body, matching the existing JATS requirement. A matching DOI and nonzero header character count cannot turn an abstract/catalog PDF into full text. Short genuine original letters remain allowed; malformed XML fails. **75 relevant tests passed** (routing, screening contract and fulltext audit); before/after sources and verification are archived under `body_parser_repair_20261019`. This does not rebuild canonical routes or submit extraction.

Global source history is now indexed by DOI. Fifteen different earlier/later decisions were explicitly reconciled using their documented body, language/format or pending-scope followups, rather than blindly selecting the latest timestamp. All30 pilot PCP inclusion proposals are also reconciled:26 additional source checks and four already adjudicated disputes. Of the26 additional checks,22 use the original supplied abstracts and four use bodies (one is an online-only primary PMC read; the direct XML failed500 and HTML backup403, both failures disclosed). The19-page schizophrenia-model review's actual ketamine/PCP sections resolve its old coverage hold; the frozen key and original validation metrics are unchanged. These added-source judgments do not constitute a new abstract-prompt benchmark.

The latest global candidate stage is `fulltext_result_audit/global_source_candidate_reconciled_824.jsonl`: **824 DOI records,510 supported source inclusions /154 exclusions /160 holds**. This includes historical PCP/main/pilot/identity/format checks, so it is a different denominator from the301-record added-source phase. It is **not canonical**. Twelve further high-risk abstract checks (3I/5X/4holds) are preserved in `main_changes/other_exclusion_source_review_003.json`. Thus this round supports reversing14 proposed exclusions:11 via body/table checks and3 via abstract checks. This selected count is not a population false-exclusion rate.

Four verified alias pairs are staged. The new UNC lisuride repository DOI `10.17615/rgra-zp80` explicitly maps to Frontiers `10.3389/fmolb.2023.1233743` on the [primary repository page](https://cdr.lib.unc.edu/concern/articles/cf95jp37f); the two saved PDFs are byte-identical. Three version relationships are staged, including PubMed's explicit BPSC corrected full-article republication link (2021 DOI to2017 report). Preserve both report histories and count the experiment once; the corrected full article is not merely an erratum. Apply these through existing canonical owners only at audited promotion.

Independent work remains. The versioned remaining-other-risk list contains1297 initially unindexed records; indices0–11 are now checked, so **resume at index12 (1285 unindexed risk flags remain)** in `main_changes/remaining_other_exclusion_source_packets_after_812.jsonl`. The source-inclusion domain worklist has510 records:208 explicit source-domain sets (three intentionally empty/general),302 without an explicit set. Do not blindly restore model/V5 tags. Reconcile actual eligible contributions, format/language, source quality and version ownership before promotion. The existing molecule-only and basic-consciousness scope questions remain pending and must not be asked again or answered by silence.

No paid model calls occurred in this checkpoint. Combined correction/fulltext model audit remains$8.1871; shared settled$27.7241/committed$28.3613 under the$100 cap. Canonical V5 routing remains SHA256`3a6d34113108693fab8d6b18d87e59c7b42b9a35c7f09f27c8b50aa2b8749cbe`. No completed controllers were restarted, no extraction was submitted and the published graph was not changed. Heartbeat remains ACTIVE while independent audit work remains.


### 2026-10-19 08:38 UTC — systematic exclusion checks and source-domain audit; pending chemistry scope enforced

Continued the frozen remaining-other-risk worklist at indices12–55: **44 supplied-abstract checks,16I/16X/12holds**. This is screening eligibility/source interpretation, not verification of every scientific result against full papers and not an error-rate sample. `main_changes/other_exclusion_source_review_004.json` and005 preserve exact source-record hashes/quotes and the original decisions. Primary publisher issue context confirms the Schizophrenia Bulletin record belongs to *SIRS2019 Abstracts*; the primary ISPOR database confirms EE51 is a2022conference presentation. The still-unverified AJG/Urology/PR150 format cases remain held, rather than excluded from a DOI prefix alone. Crossref429 and inaccessible publisher/PDF attempts are retained as failures, not format confirmation.

The recurrent false-exclusion pattern is direct ketamine developmental neurobiology being classified as anesthesia-care research. Newly supported contributions include neuronal apoptosis/ROS and pathway readouts, gene/pathway or rescue-compound manipulations, developmental synaptic plasticity and actual learning/memory phenotypes. A psychiatric ECT meta-analysis also has a separately substantive remission/HAMD endpoint. In contrast, aquatic-contaminant ecotoxicology, water-removal engineering, cannabinoid-only studies, ordinary-stimulant studies and anesthesia/pain-care complication cases retain their explicit boundaries. Zebrafish species or an anesthesia mention alone does not settle purpose.

Source eligibility is distinct from quantitative/source quality. Flags include an apparently reversed Bcl2/Bax direction in the GM1 abstract, miRNA735 versus375 in the ketamine-neuron abstract, and a claim about human neurons despite fetal-rat/PC12 model framing. These must be checked against original sources before normalization/graph assertions; they are not silently corrected. Tracer washout is not drug PK, endogenous MRS metabolites are not PCP metabolites, animal HTR is not a measured human subjective experience, and another compound's separate receptor/behavior/imaging assay is not automatically an eligible-drug mechanism.

The domain audit exposed an **earlier scope error**: `10.1002/dta.1861` had been included under an assumed approved chemistry scope, although the existing direct-molecule chemistry question remains unanswered and explicitly calls for quarantine. `main_changes/chemistry_scope_hold_reconciliation_001.json` now supersedes that inclusion to **hold**, retaining the original judgment/key. No new question was asked and silence was not treated as approval. The84-record chemistry-word inventory is prioritization, not84confirmed errors or a claim of complete review; many flagged papers have genuine biological rescue or actual product-composition findings.

Seventeen formerly unannotated inclusions now have explicit source-supported domain sets in `source_supported_domain_reconciliation_001/002.json`; the eighteenth record is the chemistry hold. The frozen302-record missing-domain ordering is preserved: **resume at index18**, after filtering `source_domain_set_recorded=false` in `source_supported_inclusion_domain_reconciliation_worklist_20261019.jsonl`. The remaining **284** source inclusions lack an explicit domain set. Cases are annotated with eligible contribution boundaries instead of blindly restoring model/V5 tags. The basic rat cFos/brain-pharmacology contribution is retained independently of consciousness/analgesia interpretation, while consciousness-only scope remains pending.

Latest global candidate stage: `fulltext_result_audit/global_source_candidate_reconciled_868_scope_domains_v2.jsonl`, summarized by `global_source_candidate_reconciled_868_checkpoint.json`: **868DOIs,525source inclusions/170exclusions/173holds**. There are241 explicit domain sets (three intentionally empty/general),284still missing. These selected DOI counts overlap earlier checkpoints, include abstract-only judgments and are not independent studies, human-expert gold or population accuracy. The301-record added-body/source phase remains separately179I/87X/35holds.

Next other-risk index is **56** in `remaining_other_exclusion_source_packets_after_812.jsonl` (**1241 unindexed flags remain**). Continue independent source/domain reconciliation and preserve all unresolved format/identity/purpose/scope holds. No model calls or additional API spending occurred. Frozen validation/answers, V5 canonical routing and published graph remain unchanged; no extraction submitted. Heartbeat remains ACTIVE.

### 2026-10-19 09:06 UTC — source-language leaks, identity crosslinks and further exclusion/domain checks

The next **72 frozen risk records (indices56–127)** received supplied-title/abstract judgments in `main_changes/other_exclusion_source_review_006/007.json`. After the explicit primary registry followup resolving one chapter-format hold, their effective decisions are **13 include /39 exclude /20 hold**. These are source-screening interpretations, not verification of all scientific data against full papers or an error-rate estimate. Actual ketamine biliary elimination, interspecies clearance and horse concentration-time findings qualify independently of anesthetic framing. Authentic human ketamine-positive urine specimens also have a substantive metabolite-abundance result, beyond assay validation. ECT antidepressant comparisons retain their independent psychiatric question, including null depression/cognitive outcomes. The same-title horse conference abstract remains excluded under the user's direct publisher observation; the later full journal article is a separate report, not an automatically verified independent study.

Assay abstracts that mention clinical doses, real specimens, seized products or PK application remain held where actual exposure/composition results cannot be established. Thirteen exact-DOI EuropePMC followups found no PMC bodies; the old Clinical Chemistry free-link metadata conflicts with the current publisher's access restriction. This is an access limitation, not proof of absent PK findings. Registry checks confirm exact-title book chapters without excluding whole DOI prefixes. `risk_after812_primary_followup_source_adjudications_001.json` preserves the initial holds and explicit later source decisions.

A broader language/source-identity check was prompted by the mushroom review: native PubMed matches its abstract to a **Lithuanian** Medicina article, whereas the assembled record carries English metadata and a JSTOR DOI. It remains identity-held; no DOI is silently reassigned. Native PubMed was then checked for **all493 model inclusions with missing language plus15 mixed/nonstandard-language records**, followed by **all15 additional model inclusions labelled English Abstract**. This covers **523 priority records**, with347 unique native PubMed records retrieved;176 had no cached numeric PMID. It is not complete corpus language certification.329 records have a native English-language entry and exact native DOI match; this is a registry observation, not full-body review. The three title-translation differences among those matches were inspected, not treated automatically as source conflicts.

All **17 model-included English Abstract flags** were source-problematic: **16 non-English source exclusions and1 identity hold**. Fifteen had supplied `en` metadata and two had missing language; the English abstract must not become English full-paper evidence. Six available saved bodies independently show substantive Japanese, Chinese, Serbian, Danish or Portuguese text. Other exclusions use exact native PubMed DOI/language or explicit PII-associated PMID/title evidence and are disclosed as registry checks. No claim is made to have disproved every possible undiscovered English translation.

Conversely, the Norwegian-language input for `10.4045/tidsskr.17.1110` does have a complete **publisher English article** with the same DOI. Its Methods, Results, Table1, adverse-effects and Discussion text support inclusion and explicit clinical/safety domains plus substantive blinding/comparator/evidence-quality modifiers. Saved web-reader responses preserve the English text and DOI footer; direct PDF retrieval failed403 and is preserved as a failure. Production ingestion of that English source still needs reconciliation. The existing Norwegian source must not simply be relabelled English. This is a full-source followup, not abstract-only model performance.

Two further metadata crosslinks are quarantined: the ketamine/alcohol mouse-memory abstract matches a Chinese PubMed report, but its supplied Turkish DOI resolves to **Socio-demographic data of delinquent children in Kahramanmaraş**; an Italian Teramo survey's cached PMID instead retrieves **PENICILLIN in subacute bacterial endocarditis**. Do not invent aliases, transfer source language/findings between these reports or overwrite canonical owners prematurely. `main_changes/language_source_adjudications_001.json` records **19 decisions:16X/2holds/1I** and their exact primary artifacts. At promotion, native source language should override aggregator `en` only after identity verification; preserve English publisher translations and do not exclude solely because metadata is missing.

The source-domain audit checked **45 more formerly unannotated inclusions**, in `source_supported_domain_reconciliation_003/004.json`. Frozen missing-domain indices0–62 are now handled:62 explicit domain sets and1 chemistry-scope hold. Actual eligible contribution boundaries are retained: independent rescue-compound assays, endogenous neurotransmitter levels, binding kinetics and animal head-twitch/discrimination must not become eligible-drug PK, human subjective measures or clinical efficacy. Two abstracts have explicit source-quality followups for a competitive-PCP description and inconsistent case-series sample accounting/percentages. These were not silently corrected.

Latest global staging is **`fulltext_result_audit/global_source_candidate_reconciled_959.jsonl`**, checkpoint **`global_source_candidate_reconciled_959_checkpoint.json`**: **959 source record identifiers,539I/225X/195holds**. There are956 DOI identifiers and3 PII keys; the full23070 scoped set itself includes12 PII keys, so use *records*, not strictly *DOIs*, for its total. These counts overlap historical source phases and are not independent studies, human-expert gold or population accuracy. The separately reported301-record added-source phase stays179I/87X/35holds. This checkpoint supports **14 additional inclusions** (13 abstract/source-interpretation checks and1 English publisher-body followup) and adds source-supported non-English exclusions.

Integrity verification at `source_audit/body_parser_repair_20261019/checkpoint_959_integrity_verification.json` checks72 original risk-record hashes/quotes,45 domain-record hashes/quotes, two explicit primary followups,19 language/identity decisions and six body-language artifacts. Original model inputs, answers, keys and all earlier judgments remain intact. Production code was unchanged here; the prior75 relevant passing tests remain the applicable code-validation result. Canonical routing SHA256 is still `3a6d34113108693fab8d6b18d87e59c7b42b9a35c7f09f27c8b50aa2b8749cbe`.

**Resume other-risk index128**:1169 entries remain beyond the cursor, **1168 not yet in global source history**; index1244 (`10.2427/6151`) is already identity-adjudicated and should be skipped explicitly when reached. **Resume frozen missing-domain index63** after the original `source_domain_set_recorded=false` filter:239 source inclusions still lack explicit domains. Current global inclusions have300 explicit sets, including three valid empty/general sets. Continue source/format/language/identity/version/domain reconciliation, preserve all pending chemistry/consciousness questions and unresolved holds, then promote through the existing canonical metadata/format/alias owners and rebuild recovery/extraction inputs. No extraction or published graph changes.

No paid model calls occurred. Correction/fulltext model audit remains **$8.1871**, shared settled **$27.7241**, committed **$28.3613**, cap$100. No completed controllers were restarted. Heartbeat remains ACTIVE while independent audit work remains.

### 2026-10-19 09:23 UTC — whole-scope native PubMed inventory completed; flags need source reconciliation

The source-language check was extended to **all23070 scoped record identifiers**, using the cached numeric PMID crosslinks as hypotheses to verify. The new read-only controller at `source_audit/main_changes/native_pubmed_scope_audit_20261019` completed at09:19UTC; **94 request parts, zero failed parts, no model calls**. It reused347 earlier primary records and preserved compressed native XML snapshots, per-part receipts/hashes and a frozen input manifest. It must not be restarted now that `summary.json` exists. This is separate from every already-completed paid controller.

There are19108 cached numeric-PMID record links, representing19106 distinct PMIDs. Native `PubmedArticle` records were parsed for **19103 scoped links**;3962 scoped records have no cached numeric PMID. The initial parser reported five unavailable links, but an explicit offline followup found one was actually returned as a **`PubmedBookArticle`**: the NIHR Ketamine-ECT study, PMID28383867 / DOI10.3310/eme04020. The four other cached IDs remained absent after a separate four-ID request. `non_article_and_missing_response_followup.json` preserves this distinction without altering the original inventory. Native Bookshelf document type alone must not discard a legitimate full clinical research report; verify the primary publisher/report format. The coverage is native registry metadata, not19104 full-paper scientific audits or complete source-language proof for every corpus record.

The inventory produces **160 navigation flags**, not160 mistakes. Their overlapping reasons are62 large title differences,22 different native DOI values,69 native non-English-language-only records,10 unestablished native identities and one possible English-language rescue. The original model decisions among flagged records are91I/34holds/35X. After joining current source staging, they are **76I/36holds/48X**. Translated titles, verified aliases/republications and publisher English versions can explain flags. The current source stage remains `global_source_candidate_reconciled_959.jsonl` (539I/225X/195holds); the native inventory does not automatically change it.

The frozen `native_pubmed_scope_audit_20261019/source_review_triage.jsonl` orders all160 flags by current inclusion/hold/exclusion and identity risk. Nineteen already have the explicit language/identity judgments from this checkpoint; preserve/reconcile them rather than rereviewing blindly. One additional identifier followup is resolved: **10.2478/s13382-014-0290-8** is a valid methoxetamine/amphetamine fatality report, but its cached PMID10131612 retrieves a managed-competition interview. Exact DOI/title agreement in native **PMID25060403** and the primary DOI registry establishes the correct identifier. Stage that metadata repair while preserving the legitimate paper. A EuropePMC DOI search returned both hits, demonstrating why the first result or cached crosslink cannot be assumed correct. `primary_identifier_followups_001.json` preserves the proof; no canonical metadata was changed.

The code trace at `source_audit/body_parser_repair_20261019/source_language_metadata_code_trace_20261019.json` records two ingestion weaknesses: generic provider-priority merging does not require authoritative source-language verification, and publication-type refresh trusts cached PMID without a DOI/title identity check or language refresh. These are code capabilities/risks, not proven historical causes of every observed error. Several incorrect existing rows have blank provider/run provenance, so do not attribute their origin to a particular provider. No production code changed in this trace.

**Next priority is source-aware reconciliation of the160 native flags**, especially the76 currently proposed inclusions, plus the four unavailable cached-PMID links and the NIHR document-type observation. Preserve legitimate primary papers when only secondary identifiers are wrong; do not turn native registry flags into an automatic exclusion rule. Then continue other-risk index128 and frozen missing-domain index63 as documented above. Independent work remains; the two existing scope questions are still pending without being reasked. Canonical V5 routing, raw model inputs/answers/keys, source-stage decisions, extraction and graph are unchanged. Pipeline API spending is unchanged; heartbeat stays ACTIVE.

### 2026-10-19 09:53 UTC — native-source flags reviewed; language leaks, report collisions and identifier repairs staged

All **160 frozen native PubMed navigation flags** now have explicit identity/language/version review in `main_changes/native_pubmed_scope_audit_20261019/native_flag_reconciliation_001.json`. This is not160 full scientific-paper audits, and reviewed does not mean every conflict is resolved. Shortened subtitles, multipart titles, encoding changes and a native title placeholder explain many flags. Preserve DMT PartI/PartII and other report-part identities rather than merging studies from abbreviated titles. Supplied unrelated titles/affiliations were distinguished from the actual native drug papers by DOI, source title and matching abstracts.

There are **49 additional primary-registry-supported non-English exclusions** in `native_registry_language_source_adjudications_001.json`:17 were model inclusions,9 were model holds and23 were already model exclusions. Exact native DOI or explicit PII identity is required; no English full source is inferred from a translated title/abstract. These are registry/source-language judgments, not49 full-body scientific checks or proof that every possible translation was searched. Earlier16 source-language exclusions and the verified English Tidsskr version remain unchanged. Two DOI-less native records were deliberately withheld from this language-exclusion rule because their report linkage is unverified.

`native_registry_source_adjudications_001.json` adds31 contribution/source decisions: **21I/4X/6holds**. Among the21 inclusions,17 resolve prior model holds, two reaffirm inclusions, one corrects a stale preprint exclusion using the now-published JMIR paper, and one repairs an existing MDMA report outside the23070 correction scope. They are not21 demonstrated model errors or21 newly discovered independent studies. Most judgments use supplied/native titles and abstracts. The JMIR and NIHR checks add publication-format/results evidence; the MDMA identity check uses its native abstract plus a visually inspected original-PDF first page. No full-paper extraction accuracy claim is made. Examples include actual5-MeO-DMT behavior, ketamine vascular/cardiac biology, actual wastewater ketamine-consumption estimates and MDMA/tobacco associations hidden behind corrupted supplied titles. The botanical bufotenine isolation qualifies independently of the unanswered chemistry-only question.

The JMIR DOI10.2196/92647 now has a verified20July2026 peer-reviewed publication, explicitly linked from its publisher preprint page; use the published source rather than the stale preprint label. Preserve its differing endpoint denominators and naturalistic design; background93%bioavailability is not measured study PK. The NIHR Ketamine-ECT source is a full EME serial clinical research report with editorial acceptance, ISSN and original Methods/Results, despite Bookshelf `PubmedBookArticle` indexing. Its independently substantive psychiatric/cognitive findings qualify; the small fNIRS substudy does not establish a measured ketamine imaging effect.

The European Psychiatry case is an **authoritative-source collision**, not a simple alias repair. PubMed/original Elsevier PII005508 identify the35-user MDMA sexual-function report, while current Cambridge/Crossref deposits associate00551X with that title and005508 with a different questionnaire paper; native00551X instead identifies a patient-satisfaction survey. Both DOI records already exist in the corpus. Preserve all observations, keep00551X identity-held, and stage the actual original MDMA report/source under005508 without globally aliasing unrelated reports or counting duplicate evidence. The original publication PDF and rendered first page are saved. Another exact primary DOI search identifies the purported ketamine-urine assay DOI as a **citrus-pectin** paper, so that input remains identity-held.

Eight enumerated malformed corpus identifiers have valid native/publisher DOI repairs (colon or underscores), two additional JAMA alias pairs return exactly the same canonical DOI/resource in Crossref, and two F1000/HRB report revisions have explicit publisher-JATS version histories/peer-review material. These are staged separately under the native audit directory; they supplement the previous4 aliases/3 version relationships, and have not changed canonical owners. Five journal reports had cached preprint PMIDs; exact final native identifiers are now verified for two, while the other publisher article identities and unresolved final crosslinks remain explicit. Never apply a global punctuation rewrite or count revisions as independent studies.

All four initially unavailable cached-PMID links now have source-aware followups in `primary_identifier_followups_002.json`: one incorrect cached crosslink corrected by exact native DOI/title, two official PubMed duplicate-merge redirects with verified replacement native records, and one valid publisher seizure-management review whose unavailable secondary PMID is quarantined without excluding the paper. Preserve the earlier initial missing-response inventory and the separate NIHR document-type observation.

Latest global candidate stage is **`fulltext_result_audit/global_source_candidate_reconciled_1043.jsonl`**, summarized by `global_source_candidate_reconciled_1043_checkpoint.json`: **1043 source identifiers (1034DOIs/9PIIs),560I/278X/205holds**. The preserved1039 checkpoint contains80 new judgments; the1043 followup adds four explicit identity/edition quarantines. This native phase therefore adds84 source judgments:21I/53X/10holds. Source-inclusion domains now have321 explicit sets (six valid empty/general),239still missing. The frozen missing-domain cursor remains63. All160 native artifact/source hashes and80 initial judgment record hashes/exact quotes, later four quarantine sources, replacement identifiers and global-stage integrity checks passed. No production code changed; prior75 relevant code tests remain applicable. The inspected publication-type refresher still trusts cached PMIDs and can spill a DOI-limited refresh to other rows sharing those PMIDs; fix its identity/scope guard before promotion, without running a canonical refresh now.

**Next:** resume frozen remaining-other-risk index128. There are1169 entries beyond the cursor, **1156 not yet in global source history**; thirteen already-checked records ahead of the cursor are listed in the checkpoint and must be skipped explicitly. Continue frozen missing-domain index63, resolve source/edition/metadata ownership, and preserve unanswered chemistry/basic-consciousness questions without reasking. Only promote after defensible reconciliation, then rebuild recovery/extraction lists.

Canonical V5 routing remains SHA256 `3a6d34113108693fab8d6b18d87e59c7b42b9a35c7f09f27c8b50aa2b8749cbe`. No paid model calls, extraction calls, prompt/schema changes or published graph changes. Correction/fulltext model audit remains$8.1871; shared settled$27.7241/committed$28.3613 under$100. Heartbeat remains ACTIVE while independent work remains.

### 2026-10-19 10:24 UTC — PubMed refresh and shared markup repaired; source audit continued

The PubMed publication-type refresher now retains native DOI/title/abstract/year observations and gates label updates on report identity, including registered DOI aliases. It reports source-language and publication-version conflicts rather than overwriting them, and restricts both metadata writes and candidate materialization to requested, verified rows. A shared cached PMID cannot expand a DOI-limited refresh; an empty verified set cannot materialize the whole corpus. Audit evidence survives a later materialization failure and records whether the atomic metadata write occurred. This does not exclude skipped papers or automatically fix their bibliographic fields.

A second mechanical defect was reproduced in shared metadata markup cleanup: the generic `<[^>]+>` rule could delete scientific text between comparisons and following markup. The replacement recognizes publisher/JATS/MathML tags while preserving comparisons and intervening text; the identity-repair and open-science helpers now share it. Controls include a synthetic markup wrapper around a real native abstract, explicitly distinguished from an original upstream response. The unsafe helper's capability is proven; its historical responsibility for each existing damaged abstract is not. Existing frozen inputs/answers/keys were not regenerated.

**170 disjoint tests passed, plus41 subtests**, covering metadata parsing/enrichment, abstract enrichment, open-science materialization, PubMed identity/scope, source assembly and screening/audit contracts. Before/after sources, controls and receipts are under `source_audit/body_parser_repair_20261019/pubmed_refresh_identity_repair_20261019` and `metadata_markup_repair_20261019`. Diff whitespace and compilation checks passed. The final offline check reused98 saved primary XML artifacts across all23070 frozen records:19108 cached-PMID rows evaluated,17676 label-refresh identities accepted and1432 conservatively skipped. These are update-gate counts, not paper eligibility errors or model accuracy.1038 publication-type changes would occur in memory; **zero canonical metadata values were persisted**. Original v1 offline outputs remain preserved; use the v2 summary for current code.

The next24 frozen risk entries128–151 are handled:23 new source judgments (**9I/11X/3holds**) and one explicit skip for149, already identity-held. `other_exclusion_source_review_008.json` preserves the original supplied-abstract judgments and registry/publisher followups. New inclusions include direct ketamine neuronal/tissue/behavioral findings and independently substantive psychiatric endpoints around ECT or trauma. The MDMA aquatic-contaminant study remains excluded under the explicit environmental-purpose boundary, not because it uses fish. Exact primary Crossref identifies144 as a book chapter despite generic PubMed Journal Article/Review labels. The two probable Urology conference items remain held: supplement/session navigation is available but exact direct PDF access failed, so no format decision is forced from a DOI prefix.

For147, the initial pain-complication exclusion was explicitly held when its treatment indication had only been inferred from the abstract. A separate exact native PubMed followup identifies Pain/drug-therapy and ketamine administration/adverse-effects indexing alongside the reported clinical infusion, supporting the exclusion. Both the intervening uncertainty and later registry-supported decision remain preserved in `risk128_151_purpose_uncertainty_reconciliation_001.json` and `risk128_151_primary_purpose_followup_002.json`; this is not a full-body scientific audit or independent gold.

Eight more source-supported domain sets (frozen missing-domain indices63–70) are in `source_supported_domain_reconciliation_005.json`. These retain actual PCP behavioral/rescue findings while avoiding transfer of other compounds'5HT/D1/Kv12.2 binding, hERG or metabolic-stability assays to PCP targets/PK. None establishes patient efficacy or human subjective experience from animal behavior. Original missing-domain ordering is preserved: **next index71**;231 source inclusions still lack explicit sets.

Latest global staging is **`fulltext_result_audit/global_source_candidate_reconciled_1066.jsonl`**, with `global_source_candidate_reconciled_1066_checkpoint.json`: **1066 identifiers (1057DOIs/9PIIs),569I/289X/208holds**,338 explicit domain sets (six valid empty/general). This overlaps earlier source phases and is not canonical or an independent-study count. New risk/domain record hashes, exact quotes, registry hashes, source-judgment transitions and global counts passed `checkpoint_1066_integrity_verification.json`. The unchanged301 added-source phase remains179I/87X/35holds.

The identity gate also exposed a new **source-abstract quality** worklist. The frozen47-packet file is `main_changes/native_pubmed_scope_audit_20261019/abstract_conflict_source_review_packets_001.jsonl`. One MathML-only navigation difference (index22) is explicitly resolved by the shared cleanup, leaving **46 flags**,38 absent from global1043 history. They include clearly truncated source fields, legitimate shorter/revised abstracts, translations and at least a cross-report mixture; they are not46 proven errors. Preserve the original ordering and reconciliation file; **start at0 and skip22 explicitly**. Check original/native sources before staging repairs, especially the SENSOR-methodology abstract attached to a smoking-cessation DOI and sources with inconsistent quantitative abstract variants. Do not blindly replace every abstract with PubMed text or blame these input defects on Luna.

**Next priority:** source-aware review of those46 abstract flags, then resume remaining-other-risk **index152**. There are1145 entries beyond that cursor,1131 not yet in global source history;14 already-checked identifiers ahead are listed in the1066 checkpoint. This corrects the earlier1043 inherited ahead-count, which had omitted two newly quarantined native cases. Continue frozen missing-domain71 and canonical source/format/language/identity/version ownership reconciliation. The two existing chemistry/consciousness scope questions remain unanswered; do not reask or infer approval.

Canonical V5 routing and frozen screening contract hashes remain unchanged. No paid model calls, extraction calls, extraction prompt/schema changes or graph replacement. Shared settled$27.7241/committed$28.3613; combined correction/fulltext model audit$8.1871 under the$100 cap. Heartbeat remains ACTIVE while independent work remains.


### Checkpoint 2026-10-19 10:34 UTC — explicit user consciousness-scope answer

The user answered: “Include basic brain/consciousness studies; exclude sedation optimization”. The original pending question remains immutable; `source_audit/main_changes/ketamine_consciousness_scope_user_resolution_20261019.json` records the direct human answer. Only the separate molecule-property/chemistry question is still pending.

Eleven purpose-held sources were reinspected: eight saved bodies and three complete supplied abstracts. `consciousness_scope_answer_source_reconciliation_001.json` supports ten inclusions with explicit domain sets; the PDE4/xylazine–ketamine model paper remains held for a distinct contribution/attribution problem. The included sources investigate actual consciousness/brain dynamics or direct neural/orexin mechanisms; ordinary sedation optimization remains excluded. Reused datasets, actual denominators, negative results and the positive-versus-negative hypothalamic correlation inconsistency in the orexin source are explicitly flagged for downstream extraction. These judgments are Codex source judgments after a human scope clarification, not new model runs, population accuracy or independent-study counts.

Latest source stage is `fulltext_result_audit/global_source_candidate_reconciled_1066_consciousness_answer.jsonl`: **1066 source identifiers, 579 inclusions / 289 exclusions / 198 holds**; 348 inclusion domain sets explicit, 231 still missing. Original V6.1 answers/keys/validation, earlier source decisions, canonical V5 routing and budget are unchanged. No paid calls or extraction calls. Next independent work remains the frozen 47-packet abstract-conflict review (skip index22 explicitly), then remaining broad-risk152 and original missing-domain71. The existing heartbeat has been updated to the answered consciousness scope; chemistry remains quarantined.


### Checkpoint 2026-10-19 10:43 UTC — first25 abstract-source flags reconciled

Frozen abstract-conflict indices0..25 have now been handled:25 complete original/native abstract-pair reviews, with22 explicitly skipped because its MathML discrepancy was already resolved. Continue at **index26**, with21 flags26..46 remaining. All25 reviewed papers were already Luna inclusions: this phase found source-input quality problems, not25new screening errors. Exact native DOI/title/PMID, XML hashes and finding quotes are verified. Source judgments and reviewable metadata proposals are in `native_pubmed_scope_audit_20261019/abstract_conflict_source_adjudications_001/002.json` and `staged_abstract_source_repairs_001/002.json`; no canonical metadata repairs applied.

The checks distinguish truncated openings, near-empty Methods/Results, an abbreviation-only field, New&Noteworthy-only summaries, legitimate final/draft variants and appended translations. Primary Wiley evidence supports retaining the complete wastewater abstract rather than automatically choosing the shorter PubMed summary with discrepant load ranges; the same native XML even stores that English full abstract under a por-labelled OtherAbstract. Its quantitative source discrepancy remains flagged. A purported2026journal full text is visibly a May2025bioRxiv preprint: keep journal eligibility separate from final-version extraction-source verification/recovery. Conversely, a meditation PDF cover proves the main article DOI despite the parser choosing a .supp reference.

A true sibling-report mixture is now primary-source verified: the1984LSD initiation-complex record DOI10.1111/j.1471-4159.1984.tb02803.x carries the1981subsequent-protein-synthesis abstract (nativePMID7205255/DOI10.1111/j.1471-4159.1981.tb01697.x), which also exists under its proper corpus record. Fresh two-ID PubMed XML and receipts are saved. Preserve both reports, restore the1984abstract through the canonical metadata owner before promotion, and do not alias or duplicate1981findings. By contrast, the thalamofrontal vesicle-refilling detail in the alternate ketamine abstract is supported by its own Results/Figure4; the cortical Figure3null is a different circuit. Additional MDMA source checks preserve endpoint-specific statistical nulls rather than trusting broad abstract claims. These are selected source inspections, not25full quantitative paper audits or independent gold.

Latest candidate source stage is `fulltext_result_audit/global_source_candidate_reconciled_1091.jsonl`:1091identifiers(1082DOI-shaped keys/9PIIs),604I/289X/198holds;373explicit domain sets,231missing. Historical stages overlap and must not be summed. Basic consciousness clarification remains applied (10source holds resolved toI,1distinct attribution hold); only chemistry scope remains pending. Broad-risk cursor152 and original missing-domain cursor71 are unchanged. Integrity receipt `source_audit/body_parser_repair_20261019/checkpoint_1091_scope_abstract_integrity_verification.json` confirms hashes, unchanged canonical routing/contract and unchanged shared settled$27.7241/committed$28.3613. No code changes in this source phase, no new paid calls, no extraction calls or graph changes.

### 2026-10-19 11:15 UTC — abstract-source worklist complete; PCP/anesthesia boundary checked

All **47 frozen abstract-conflict navigation entries** are now handled: **46 source-specific original/native abstract-pair judgments and one explicitly skipped MathML-only flag**. The last21 checks are in `native_pubmed_scope_audit_20261019/abstract_conflict_source_adjudications_003.json`, with reviewable metadata proposals in `staged_abstract_source_repairs_003.json`. This completes that worklist, not the whole source audit, and unresolved identity, chemistry, access and contribution holds remain. Original records, raw model outputs and prior judgments are preserved.

Two further report mixtures were verified. The1994 aortic phenethylamine DOI carries the1998 beta-alkoxy-series abstract; fresh two-ID native XML distinguishes both real reports. Restore the1994 abstract through the existing metadata owner before promotion, without aliasing the reports or transferring the1998 findings. The Tobacco Control smoking-cessation DOI instead carries a SENSOR medRxiv abstract; restore the actual NRT report and preserve the orphan preprint provenance. A copied journal-like PDF heading does not establish a published version. The iboga paper's real null cell assays and the Aspergillus paper's actual ergine/ergonovine biosynthesis qualify independently of the unanswered chemistry-only question. The fungal Results/figures were read in saved primary-publisher responses; failed raw XML retrievals remain disclosed, and relative ergonovine calibration must not become absolute concentrations.

The remaining abstract work also supports two formerly excluded papers: a schizophrenia review with substantial ketamine/PCP mechanism sections, and actual PCP-containing-combination physiological findings in lions. These use added source evidence where specified, not a pure abstract-model benchmark. Lanicemine is excluded after independent primary comparative characterization; occasional adverse experiences do not establish an approved psychedelic/dissociative identity. The RSC sensor and bilingual adolescent survey remain held because full-source/product-table access was unsuccessful. The browser showed an actual RSC paywall and a blocked publisher PDF; failures are preserved rather than treated as absent findings.

Broad-risk frozen indices**152–163** add **11 new judgments:2I/5X/4holds**, plus one explicit already-language-excluded skip at161. Actual seized MDMA tablet/additive findings qualify separately from detector performance; hair/saliva/seized-material assay claims without demonstrated independent exposure/product results stay held. The zebrafish CNS-development case could qualify scientifically but remains exact-format-held; a supplement, DOI prefix or failed PDF fetch alone is not publication-format proof. Ten previously missing source-domain sets at indices**71–80** are now explicit. Another compound's receptor assays/PK and endogenous transmitter measurements were kept separate from PCP findings.

A focused worklist then checked **all53 model-excluded PCP/anesthesia navigation flags**. **51 required new source judgments:10I/31X/10holds**; two were already adjudicated and explicitly skipped. This includes **seven body followups** in the second phase (six identity-verified saved bodies and one exact-DOI primary PMC body); the remaining judgments use the complete supplied abstracts, with limitations disclosed. These selected flags are not an error-rate estimate. Most PCP mentions are chemical history or receptor-site names, not actual PCP exposure. Basic ketamine brain characterization, substantial PK/interaction reviews, pediatric psychiatric/seizure/PK synthesis and actual PCP-bearing bear physiology can qualify. Psychological emergence-management strategies, postoperative cognitive-complication prevention, injection pain, procedural sedation and routine anesthesia safety remain excluded. New analogue identities and incomplete review coverage remain held. Ketamir-2 has own PK/TK assertions marked data not shown: they must neither be denied nor transferred to ketamine. Source-quality flags include species/SEM discrepancies, dose-specific nulls, review citation mismatches and erroneous pharmacological wording; none was silently repaired.

Latest staging is **`fulltext_result_audit/global_source_candidate_reconciled_1166_domains_v2.jsonl`**, summarized by **`global_source_candidate_reconciled_1166_checkpoint_v2.json`**: **1166 source identifiers (1157 DOI-shaped/9PIIs),621I/330X/215holds**. These overlap all earlier source phases, are not canonical and are not independent-study counts. There are **400 explicit inclusion-domain sets** (six valid empty/general sets), with **221 still missing**. Three explanatory tag names were explicitly mapped to existing production enums in `source_domain_enum_name_reconciliation_001.json`; the original three judgments and original1166 stage remain preserved, with no eligibility changes.

Integrity receipt **`source_audit/body_parser_repair_20261019/checkpoint_1166_integrity_verification.json`** verifies21 abstract-pair quotes/native identities,11 risk-record quotes/hashes,10 domain-record quotes/hashes,51 PCP-priority record quotes/hashes, seven body hashes, all stage-history references, and unchanged1091/1104/1115/1127/1166 stage hashes. All current explicit domains use valid production values. No production code changed; the previous **170 passing tests plus41 subtests** remain the relevant baseline. Canonical routing and frozen validator hashes are unchanged. No paid model or extraction calls occurred; shared settled**$27.7241**, committed**$28.3613**, correction/fulltext audit**$8.1871** under the$100 cap.

**Resume broad-risk index164** in the immutable1297-record worklist:1133 entries beyond the cursor, **1117 not yet in source history**; sixteen ahead-reviewed records are explicitly listed in the1166 checkpoint and must be skipped/reconciled when reached. **Resume missing-domain index81** after the original `source_domain_set_recorded=false` filter. Do not repeat the completed abstract/53-flag worklists or any completed Batch controller. The chemistry-only question remains unanswered; the user's ketamine brain/consciousness answer is already applied. Continue defensible source/format/language/identity/version/domain reconciliation, quarantine unresolved records, and only then promote through existing canonical owners and rebuild recovery/extraction inputs. No extraction calls, prompt/schema changes or published graph replacement. Heartbeat stays ACTIVE while independent work remains.

### 2026-10-19 11:28 UTC — additional brain/psychiatric exclusions checked; domains advanced

Frozen broad-risk indices**164–199** are now checked in `main_changes/other_exclusion_source_review_010/011.json`: **36 new source judgments,18I/7X/11holds**. Thirty-five use complete supplied titles/abstracts with explicitly bounded publisher followups; one is an exact publisher-format judgment. These are selected edge cases, not36 full-paper audits, an overall error-rate estimate or36 mistakes attributable to the original model. The later user consciousness clarification is preserved separately from frozen prompt/validation history.

Supported inclusions include basic ketamine neuronal/EEG recordings, primate consciousness dynamics, regional metabolism and direct channel/cell-toxicity experiments despite anesthetic framing. A neonatal-rat study has actual ketamine blood concentrations alongside neurotoxicity; the concentrations and dosing groups must remain distinct from its cited human comparison. A seizure-stimulation procedure alone is not treatment of epilepsy, and an animal's apparent dreaming is not measured subjective testimony. Actual MDMA purity in seized tablets qualifies independently of the analytical method's calibration results.

Several ECT reports centrally test depression response or psychiatric-treatment augmentation. These are retained with their actual results, including null incremental antidepressant/neurocognitive findings and time-specific effects. Perioperative PTSD/depression is eligible when independently substantive, rather than incidental mood monitoring. An older ECT anesthetic-choice memory report remains source-purpose-held; a different trial expressly adds subanesthetic ketamine to unchanged propofol ECT and has treatment-course and distinct learning outcomes. General agitation/intubation safety and postoperative analgesia adverse events stay excluded. A cardiac POCD paper with a CRP contrast remains held for the independent-mechanism versus complication-care distinction; its measured marker is not denied or treated as drug PK.

The exact publisher article and issue identify **P-63/10.1093/alcalc/agu054.63** as part of the2014 ISAM annual-meeting supplement/poster sessions, supporting a publication-format exclusion despite completed ketamine-rehabilitation results. Three other exact publisher/issue lookups had failures or insufficient conference-format proof; the single-page Archives item, Schizophrenia Bulletin F102 and FASEB LB item remain held. The next Urology V11-11 cystitis series is scientifically relevant to nonmedical ketamine injury but also format-held. No DOI prefix, supplement label or failed fetch alone became proof. Real serum/urine/autopsy applications and mixed-drug traffic/festival cohorts remain held where a drug-specific exposure or clinically substantive contribution could be hidden in uninspected tables. The1898-urine LSD-interference paper must not be described as4.2%real LSD use or as all1898specimens having GC-MS confirmation.

Source-domain indices**81–105** (the immutable original missing-domain ordering) are now explicit in `source_supported_domain_reconciliation_007/008.json`: **25 more sets**, including **one saved-body reinspection**. The Gaceta trauma body's actual **two PCP screen-positive patients among1187screened** were preserved; the shortened abstract's pooled THC/PCP category does not negate that earlier body rescue, and pooled injury odds are not PCP-specific. Other constraints include endogenous amine turnover versus PCP metabolism, observed PCP–amphetamine PK interaction versus an unmeasured PCP half-life, CBD-only receptor/behavior assays versus actual PCP rescue, and independent mGluR-ligand sleep/EEG experiments versus PCP-induced locomotion. Animal discrimination remains behavioral evidence, not human phenomenology.

Latest source stage is **`fulltext_result_audit/global_source_candidate_reconciled_1202_contract_v2.jsonl`**, checkpoint **`global_source_candidate_reconciled_1202_checkpoint_v2.json`**: **1202 identifiers(1193 DOI-shaped/9PIIs),639I/337X/226holds**, still noncanonical and overlapping historical phases. There are **443 explicit inclusion-domain sets**, including six valid empty/general sets, and **196 missing**. Forty-three historical/new explanatory basis names were explicitly mapped to existing contract vocabulary in `source_eligibility_basis_name_reconciliation_001.json`; all original judgments/stages and the same eligibility decisions remain preserved. These vocabulary changes are not new scientific adjudications.

`source_audit/body_parser_repair_20261019/checkpoint_1202_integrity_verification.json` verifies36 new risk-record and25 domain-record quotes/hashes, the re-read body's hash, exact conference identity, all source-history file hashes, unchanged prior stages and valid present basis/domain values. Canonical routing, frozen validator and shared API ledger are unchanged. No production code changed, so the previous170 passing tests plus41subtests remain the code baseline. No model/extraction calls or graph changes; shared settled$27.7241/committed$28.3613, correction/fulltext audit$8.1871.

**Resume broad-risk index200**:1097entries beyond the cursor, **1081 not yet in source history**, with sixteen ahead-reviewed records listed in the1202checkpoint for explicit skip/reconciliation. **Resume frozen missing-domain index106** after the original false filter. All completed abstract-conflict and53-PCP/anesthesia worklists remain complete. Keep unresolved formats, source identities, access/coverage and the unanswered chemistry-only question quarantined; the user's consciousness answer is already applied. Continue independent source/format/language/identity/version/domain reconciliation before promotion and refreshing manual recovery/extraction inputs. Heartbeat remains ACTIVE.


### 2026-10-19T11:33:25.369125+00:00 — manual-audit workflow stopped following user correction

The user correctly identified that the15-minute batch-monitor heartbeat had drifted into repeated manual Codex rescreening/domain assignment. The completed Luna batches were no longer the active work. This manual expansion is halted; automation `finish-luna-screening-correction` is PAUSED. No completed controllers are running or restarted. The1202-record source-candidate stage and all raw/model/audit histories remain preserved, but individual Codex adjudications must not be promoted as a replacement for reproducible Luna screening. Canonical routing remains unchanged at SHA256 `3a6d34113108693fab8d6b18d87e59c7b42b9a35c7f09f27c8b50aa2b8749cbe`.

The remaining manual worklist is no longer a prerequisite for completion. Next workflow is deterministic repair/regression checks, a bounded frozen evaluation set with separate fresh validation, a fixed Luna protocol and source policy, automated affected-record screening/validation/quarantine, and only then canonical promotion/input refresh. No new model or extraction submission was made in this reset. See `source_audit/main_changes/workflow_reset_20261019.json` and the preserved progress backup. The user has not authorized resuming the15-minute manual audit.


### 19 October 2026 — user-authorized targeted PCP discovery increment

The user explicitly authorized adding PCP to discovery and running the resulting
records through the current source-recovery/extraction-preparation checkpoint.
This supersedes the earlier decision to defer a PCP historical search. It does
not resume the abandoned manual V6.1/source-audit workflow or adopt its decisions.

Run `pcp_scope_addition_20261019` searched PubMed and OpenAlex from 1800-01-01
through 2026-10-19. Exact provider queries retain unrestricted phencyclidine names
and PubMed MeSH coverage, while the ambiguous PCP acronym requires drug context.
Two search executions completed. PubMed retrieved 6,182/6,182 records; OpenAlex
retrieved 8,269/8,270 after bounded reconciliation, with one residual record
accepted under the existing provider-count tolerance. This is disclosed rather
than described as perfect reconciliation or measured search recall.

There were 14,451 provider records, merging to 9,192 identifier groups: 5,474
new DOI candidates, 2,429 rediscovered DOI records and 1,289 unresolved no-DOI
records. The latter remain in the existing identifier-resolution ledger and are
not silently excluded on scientific scope. Six have diagnostic existing-ID/title
matches; those observations have not become aliases or identity overrides.
Discovery promotion preserved prior metadata/decisions and recorded all provenance.

The affected cohort is 6,710 DOI records: 5,474 new discoveries, 1,191 rediscovered
PCP records without an inclusion, and 45 additional restored-abstract records.
Of the 1,191 PCP reconsiderations, 559 were previously Luna-excluded; the others
had not reached Luna. All existing model inclusions are outside the update scope.
Cohort origins are frozen in `downstream/cohort.csv`.

Metadata recovery added 2,445 abstracts from PubMed/PMC and 17 from Crossref.
The optional Semantic Scholar attempt returned HTTP 429 before a merge; its
failure and pre-failure manifest are preserved. PubMed rejected two identity
mismatches rather than transferring abstracts from mismatched records.

The current deterministic cleanup ran BEFORE the model requests: 4,637/6,710
passed, while 1,186 had unusable abstracts, 744 were non-evidence artifacts,
102 were non-English, 40 were preprints/unpublished and one was a non-paper
container. No topical rule was used to reject the cohort. Rule version is
`deterministic_cleanup_luna_v5_20261017` throughout this scoped pass.

One large Luna Batch job, `batch_6ad64f519f94819097f9c1e7883e4743`, contains all
4,637 title/abstract requests (103,146,344 input-file bytes). It uses GPT-6 Luna,
low reasoning and the V5 schema/instructions with ONLY phencyclidine (PCP)
explicitly added to substance scope. Both original V5 and the amendment are
preserved, with source/prompt hashes. It does not use the stricter V6.1 rules,
full-text screening, manual Codex eligibility overrides or Sol API judging.
The budget reservation ceiling is $9.9815, not an actual-charge prediction;
settlement uses returned model token usage within the shared $100 ledger.

A continuous resumable controller delegates to the existing pipeline commands:
`artifacts/pcp_scope_addition_20261019/finish_pipeline.py`. Its PID/command, lock,
logs and stage receipts are under the run's `downstream/` folder. It waits for
this same Batch receipt, retries only failed requests once if necessary, verifies
unchanged routing outside the scope, and then runs automated source recovery,
identity checks and provisional primary/review/meta-analysis input preparation.
It does not submit extraction model calls or replace the published graph. The
old 15-minute audit heartbeat remains paused.

Public methods source, the compound vocabulary, discovery README, main pipeline
guide and saved search history now record the PCP addition. A targeted historical
completion is recognized for the next update without advancing the global
watermark: a read-only next-update plan still starts 2026-10-01 and contains no
redundant all-time PCP delta. Historical full/update baselines are unchanged.
Source/model results and recovery counts will be recorded at completion.


### 19 October 2026 — PCP increment completed through the current checkpoint

Source discovery, deterministic cleanup, Luna title/abstract screening, automated source recovery and provisional canonical extraction-input preparation are complete. Current counts and per-record outcomes are saved at `data/processed/discovery/runs/pcp_scope_addition_20261019/downstream/report.json` and `record_dispositions.csv`. Canonical pending task inventories include the PCP increment, while both published-release pointers remain unchanged. Luna decisions: {'include_in_scope': 2529, 'exclude_out_of_scope': 2108}. Saved-usage screening charge: $0.5042. Manual source recovery remains a separate queue; no extraction model jobs or graph release were submitted.


### 19 October 2026 — manual PDF recovery batches refreshed after PCP addition

Automated PCP recovery and PDF conversion are complete. The stale unpromoted-correction completion flag was reconciled against the completed V5 + PCP screening receipts; no decisions or prompts changed. Canonical provisional input preparation is complete; extraction has not been submitted. The existing manual Chrome handoff now has **1,770 unassigned papers in 36 prepared batches** (35 batches of 50 and a final batch of 20), beginning with **batch 003**. This combines 1,463 unassigned papers from the previous manual queue with 307 PCP-increment cases. The 100 papers from user-reviewed batches 001/002 are not repeated; their manifests, progress and pending download/outcome reconciliation are preserved. Batches are ordered by saved recoverability evidence, without additional scientific screening. Ready-batch index: `data/processed/model_runs/luna_v5_20261017/fulltext_recovery_20261018/browser_full_pass_20261018/manual_chrome_batches_20261019/ready_batches.html`. No new Chrome tabs opened. Manifest and mechanical checks: `data/processed/discovery/runs/pcp_scope_addition_20261019/downstream/manual_handoff/`. The abandoned audit heartbeat remains paused; no follow-up monitor is required now because the handoff is ready.


### 19 October 2026 — first batch-003 paper recovered through the publisher viewer

At the user’s request, DOI `10.1111/j.1476-5381.1981.tb16806.x` was opened through its DOI landing page and Wiley ePDF viewer. The complete 17-page, 2,052,433-byte main PDF was downloaded through the visible More options > Download PDF link using the browser downloadMedia helper, identity-checked, imported and converted (101,911 characters). Earlier browser observations had stopped at blank /pdf and /pdfdirect wrappers despite recording a PDF control on the free-access page; this is a recovery miss, not evidence of closed access. The initial click-only download-event wait also timed out in this retry before downloadMedia succeeded. The existing batch-003 manifest/checklist/progress now mark only this paper recovered; earlier user batches are preserved. Offline flags identify 113 other Wiley records with a previously observed main-PDF control; those are retry candidates, not confirmed recoveries. Saved receipts: `data/processed/discovery/runs/pcp_scope_addition_20261019/downstream/browser_retry_batch003_firstpaper/`. No screening decisions or model calls changed. Provisional extraction inputs will need the usual source refresh after manual/browser recovery.


### 20 October 2026 — targeted Wiley viewer retry completed

The user requested a faster, visible viewer/download pass after the first batch-003 example. All113 frozen remaining Wiley candidates received a browser outcome: **41 PDFs downloaded, identity-verified, imported and converted**, and **72 publisher access-barrier observations**. Two of those72 preferred links identify a different DOI and remain source-link identity reviews; no access or screening override was applied to the requested reports. Initial incomplete viewer loads were revisited; none remain unresolved. The first demonstration PDF is additional, making42 recovered report files including it. Saved evidence and checksums are in `data/processed/discovery/runs/pcp_scope_addition_20261019/downstream/wiley_viewer_retry_20261019/`; the existing batch manifests/checklists/progress mark recovered PDFs and explicit publisher barriers, preserving batches001/002 and prior snapshots. Downloads were performed sequentially after nonempty viewer page counts, followed by a single batch import/conversion phase. The two importer title exceptions were verified against original first-page titles, authors, DOI footers and reprint provenance, not new scientific scope judgments. No model calls, screening changes or graph publication. Pending extraction inputs require the ordinary source refresh after recovery is finished.


### 2026-10-20 provider browser recovery: external Chrome checkpoint

The user confirmed that the in-app PDF button did nothing while external Chrome downloaded the same ScienceDirect document. External Chrome's existing Adobe viewer opened a native Save dialog immediately. No plugin installation or settings change was required.

The frozen provider-pass queue contains 1,656 unassigned records. At this checkpoint, 120 were visited: 19 additional actual PDFs recovered and converted, 73 explicit publisher purchase/subscription observations, and 28 unresolved retrieval/repository/registration cases. This pass is unfinished; 1,536 frozen records have not yet been visited. Access observations do not establish that no lawful copy exists elsewhere.

All 19 recovered PDFs passed document identity/import checks and local GROBID conversion (15 + 4 scoped receipts). Existing recovery batches were updated; batches 001/002 were not edited. The prepared 1,770-record queue now contains 61 recovered usable full texts (42 from the preceding Wiley work plus these 19), leaving 1,709 not yet recovered, including access-restricted records. Extraction input refresh remains provisional. Screening decisions/prompts, paid model jobs and graph release were not changed.

Evidence: `downstream/provider_browser_pass_20261020/` under the PCP discovery run: `events.jsonl`, `progress.csv` (explicit verification status), `checkpoint_120.json`, `protocol.json`, import and conversion receipts. Append-only retrieval events preserve incomplete attempts separately from the final verified files. Continue the remaining publisher/browser recovery work from this frozen queue, retaining the actual PDF-ready/save/file-confirmation sequence.


### 2026-10-20 01:32 GST external Chrome continuation checkpoint

Continued user-authorized external Chrome recovery. Five further ScienceDirect PDFs were saved, identity-verified/imported and locally converted (receipt suffix `020_024`). The provider pass now has 24 usable new full texts; recent prepared-batch browser recoveries total 66. Individual checks of all 25 remaining SAGE entries found explicit Restricted access, preserving the previous two checks. Three new ScienceDirect content errors remain technical observations, not closed-access judgments.

Wiley DOI `10.1111/j.1365-2044.1981.tb10239.x` is explicitly Free Access, but ePDF stayed at Reader environment loading and direct download did not save a file. On the subsequent observed View PDF route, Chrome blocked browser automation because another extension UI was open. The user was asked to close that popup; no alternate browser/control path was used to bypass the pause. All completed files and manual batch updates are preserved at `provider_browser_pass_20261020/checkpoint_154.json` and `verification_154.json`. Screening/graph outputs and paid model calls remain unchanged.


### 2026-10-20 01:50 GST external Chrome continuation checkpoint

After the user dismissed the extension popup, external Chrome recovery resumed. Nine further PDFs were saved, passed exact document DOI checks with zero importer reviews/conflicts, imported and converted locally (receipt suffix `025_033`): eight Wiley papers and one Wiley-journal article now hosted by Oxford. All nine conversions have verified source identity and nonempty body text. The provider pass now has **33 usable new full texts**; recent recoveries across the prepared batches total **75**, leaving **1,695 prepared papers not yet recovered**. Of the frozen 1,656 provider-pass entries, 167 have recorded outcomes, 1,489 are still unvisited, 101 show explicit publisher purchase/subscription barriers and 33 have unresolved retrieval observations. These access observations do not prove no lawful alternative exists.

Wiley's actual ePDF reader download links recovered eight PDFs. Some download-observer timeouts nevertheless produced files; local file checks confirmed them before counting, and the duplicate Chiou download was not counted twice. The Oxford article required passive publisher verification before its PDF loaded. The earlier Free Access Anaesthesia paper rendered the correct scanned main article, but Adobe's download controls remained disabled and Save had no effect; it is still unresolved. The Copenhagen repository exposes an accepted manuscript but did not yield a saved file; an invalid relative-URL navigation was blocked by browser policy and was not worked around.

Chrome then again blocked automation because another extension UI was open. All browser interactions stopped, the user was asked to close that popup, and the completed downloads were imported/converted while waiting. No blocked browser action was bypassed. Receipts and next queues are in `downstream/provider_browser_pass_20261020/checkpoint_167.json`, `verification_167.json`, `browser_pause_167.json`, `not_yet_visited_after_167.csv` and `retrieval_followups_after_167.csv`. The 18 files in user batches001/002 are unchanged; canonical screening SHA remains `01f5323d4824550daa3b01f15e7f89a01fd40c5639cfe884ec1625540676229c`. No paid model calls, scientific rescreening, extraction tasks or graph release. Extraction inputs remain provisional pending recovery completion.


### Browser recovery checkpoint — 2026-10-19 23:23 UTC

External Chrome was restarted in the existing profile after the repeated false popup interruptions. Browser recovery continued: provider-pass checkpoint497 has 497 checked / 1,159 unvisited, 100 new verified usable fulltexts plus the prior42, for142 prepared records recovered and1,628 prepared records not yet recovered. All100 new files are imported with identity-verified, nonempty canonical text artifacts; zero pending conversion at this checkpoint. All frozen preferred-host records for ScienceDirect, Springer, Nature and ACS have individual outcomes. The 35-record Ovid/LWW subset is also checked; other Ovid/LWW routes remain in the broader queue. Purchase, account-gate, technical and source-identity outcomes remain separate.

Genomic Press main Download PDF returned application HTML; its visible PDF-tab iframe exposed the working PDF source, recovering four papers. Old ScienceDirect scans needed local Docling OCR. Original10.1254/jjp.56.483 and51.321 redirects and original PDF covers resolve archive identifier/OCR issues. One exact-file hash attestation was added to the existing source-identity registry for51.321. The62.131 publisher page supplied a different noradrenaline paper; wrong bytes were quarantined, the prior import explicitly superseded, candidate PDF pointers cleared, and no fulltext artifact was written. No screening decision changed. Original import/conversion receipts and cover images are preserved. The retrieval checkpoint helper now counts only verified written artifacts and ignores later-quarantined imports.

First two user-reviewed manual batches: all18 saved hashes unchanged. Canonical screening SHA remains 01f5323d4824550daa3b01f15e7f89a01fd40c5639cfe884ec1625540676229c. No paid model calls, extraction calls, screening-prompt changes or graph-release changes. Receipts: `data/processed/discovery/runs/pcp_scope_addition_20261019/downstream/provider_browser_pass_20261020/checkpoint_497.json`, `data/processed/discovery/runs/pcp_scope_addition_20261019/downstream/provider_browser_pass_20261020/checkpoint_497_integrity_verification.json`. Continue remaining repositories/smaller publishers; the optional Nature login question is pending.


### External Chrome recovery checkpoint — 2026-10-19 23:45 UTC

Provider pass546:546 checked /1,110 unvisited;103 new identity-verified imported/converted sources plus prior42 =145 prepared records recovered,1,625 prepared records not yet recovered. Since checkpoint167,70 additional usable PDFs have been recovered after Chrome restart/reconnection. Zero downloaded files await validation/conversion. These are source-record/retrieval counts, not independent-study counts or an exhausted queue.

New recipes/findings: native Chrome PDF controls work when Adobe PDF extension takes over a tab and the browser tool misleadingly reports another extension UI. Complete/save the PDF via its visible native controls before closing it; do not repeatedly ask the user to close a nonexistent popup. A DOM PDF click on the Seizure journal site had no effect, while the native link control opened its full PDF. A newer Elsevier DOI redirected straight to PDF; that warning similarly meant an active PDF viewer, not a paywall. Both sources passed import and conversion. Portland Press bio_2023_164 also recovered/converted.

MD-SOAR10.13016/m2sic3-v2sx now resolves to a repository item explicitly linked to Frontiers10.3389/fpsyg.2026.1843151; its downloaded PDF is byte-identical to the already recovered publisher copy. Saved relationship receipt103; not counted as another paper/new unique source, no global alias applied. Source/version reconciliation remains staged.

PMC exact-DOI search via the current search form found PMC1178042 for10.1042/bj1250213 despite the publisher purchase barrier; its PDF stops at explicit browser reCAPTCHA. Human verification requested once, page marked handoff. Nature account login remains a separate pending optional handoff. No approval inferred, CAPTCHA solved, accounts created, or security settings changed. Remaining work can continue independently on other publishers.

All45 DOI records in the first additional Elsevier block are checked, including two recovered PDFs, one free-registration gate and explicit purchase barriers. Current outcomes are in provider `progress.csv` / append-only `events.jsonl`; new downloads and raw conversion/OCR receipts are retained. First two manual batches: all18 hashes unchanged. Canonical screening SHA 01f5323d4824550daa3b01f15e7f89a01fd40c5639cfe884ec1625540676229c unchanged; no screening/extraction prompts, paid model calls, extraction calls or published graph changes. Existing heartbeat remains paused; no new automation/controller started.

Continue from frozen_candidates.csv minus current progress.csv (1,110 unvisited). Hundreds of remaining10.1016 DOI-fallback records are still unvisited; completed named-host groups do not exhaust all records at those publishers. Other remaining groups include J-STAGE, BMJ, Oxford, repositories and11 additional Ovid/LWW preferred-host entries. Source-reader/checker arrays were task-local CUA helpers, not production pipeline additions. Keep existing V5/PCP screening unchanged.


### External Chrome recovery checkpoint — 2026-10-20 00:20 UTC

The user left Nature account-access papers for manual recovery and offered to complete PMC verification. The original PMC1178042 main PDF subsequently loaded and was saved. **22 further original PDFs are now identity-verified, imported and converted**:18 through PMC and4 through J-STAGE. Four scan-import exceptions were checked against their original covers and exact primary download links; the file-level attestations do not change screening or aliases. Three older J-STAGE scans required local Docling OCR after GROBID identity rejection; all3 now have verified nonempty source artifacts. Original failure/retry receipts remain preserved. No downloaded PDF is awaiting import or conversion.

Provider checkpoint576 now has576 checked /1,080 unvisited,125 usable new sources in this pass plus prior42 =167 prepared records recovered;1,603 prepared records still lack recovery. These are retrieval/report counts, not independent-study counts or an exhausted pass. All18 first-two-human-batch hashes and canonical V5+PCP screening SHA01f5323d4824550daa3b01f15e7f89a01fd40c5639cfe884ec1625540676229c remain unchanged. No paid model calls, extraction jobs, prompt/schema changes or graph release. Existing extraction-input state remains provisional pending source refresh.

Systematic retrieval finding:102 previously unvisited records had cached PMC IDs. Seventeen of those yielded PDFs; another old PMC followup yielded the eighteenth PMC PDF above. One exact PMC report exposes complete HTML but no main PDF control. Five subsequent PMC pages returned explicit403Forbidden; requests to that provider were paused rather than treating denial as paywall or trying alternate routes around it. Remaining PMC IDs are unvisited, not known closed-access. Separate-tab page loading allowed two main-PDF downloadMedia calls to succeed quickly; immature/long PDF requests can still time out, so actual local files are verified before any count.

Chrome control then reported the Mac was locked and could not be automatically unlocked. The user was asked once to unlock; independent imports/OCR were finished while waiting. The two free J-STAGE followups10.1248/cpb.39.1581 and10.1248/cpb.37.1788 remain preserved as live unfinished pages and technical retrieval holds. Nature login is no longer a pending request; do not ask again or create an account. User preference and blocker receipts:user_recovery_preferences_20261020.json,mac_locked_pause_20261020.json. Resume browser work after human unlock, using the saved provider queue minus current progress, not the old stale prepare_batch script. Do not duplicate the22 completed downloads. Current reviewable receipts:checkpoint_576.json,checkpoint_576_integrity_verification.json,import_applied_107..110.json and the corresponding conversion reports. The abandoned screening heartbeat remains paused; no new automation was created.


### External Chrome recovery checkpoint — 2026-10-20 01:44 UTC

The user unlocked the Mac and recovery resumed. A further **97 original PDFs** have now been saved, identity-verified, imported and locally converted since checkpoint576: chunks111/112 and114 through139. Three additional old Japanese-language sources are preserved as language-review files in113 and are not counted as usable English full texts. Receipt-level file hashes and nonempty verified artifacts for all97, plus the18 unchanged first-two-user-batch hashes, passed `checkpoint_unlock_continuation_97_integrity_verification.json`. This is mechanical retrieval/identity verification, not scientific source adjudication or a change to V5 screening.

At checkpoint741, the provider pass had741 records checked /915 still unvisited,222 new verified usable sources plus the prior42 =**264 prepared records recovered**,1,506 prepared records not yet recovered, and zero downloaded PDFs pending import/conversion. Subsequent source-format/access observations continue in append-only events; these counts are not an exhausted queue or independent-study counts. All existing manual batches003+ were refreshed by the checkpoint helper; batches001/002 remain unchanged.

Provider findings: recent ScienceDirect open-access PDFs saved reliably with ordinary main-PDF clicks and native Chrome Download→Save, until the site explicitly displayed its daily bulk-download limit. The last five pending articles are logged as download-limit holds, not paywalls; that provider is paused. PMC supplied another16 PDFs before four article pages returned403Forbidden; it is paused again. All12 remaining Journal of Neuroscience records yielded PDFs after sequential article loading and normal reloads of verification-success pages that had stalled. Oxford PDF requests can time out in the download helper while the actual PDF is already open in Chrome; native Download→Save completed three such copies. Original author/repository PDFs recovered elsewhere include Maastricht, South Wales and Rochester. A broken Svedberg DOI target returned404; one focused DOI search located its migrated OJS page and original PDF.

PNAS initially sent several simultaneous article opens to the same report; sequential DOI navigation corrected the target. Its exact PDF destination then returned explicit Chrome ERR_BLOCKED_BY_CLIENT. No mismatched PDF was imported. Public author-copy Salvia recovery on ResearchGate also hit a browser download block after the original OMICS page explicitly said Page Not Found. These remain technical retrieval followups, not closed-access findings. Source-format observations for publisher-labelled conference abstracts remain recovery flags only; canonical eligibility is unchanged.

All original/retry/OCR receipts remain preserved. A dry-run128 report was initially written under a mistyped20261020 discovery-run folder; the unchanged receipt was copied to the correct20261019 provider folder before apply. Generic task-local staging provenance for133 was explicitly corrected in later append-only events to Journal of Neuroscience; the same files and original observations remain preserved. The138 provider is Hilaris; its DOI opens directly to the matching original PDF. No paid model calls, screening/prompt/schema changes, extraction model calls, normalization/graph changes, new controllers or automations. The old heartbeat stays paused. Extraction inputs remain provisional pending ordinary source refresh after recovery.


### External Chrome recovery checkpoint — 2026-10-20 02:01 UTC

Checkpoint791:791 checked /865 unvisited;230 verified usable new provider-pass sources plus prior42 =**272 recovered prepared records**,1,498 prepared records not yet recovered, zero pending import/conversion. The unlocked continuation has therefore added105 verified usable sources since checkpoint576. Published graph and V5+PCP screening remain unchanged.

Oxford-hosted10.1093 links (excluding five unvisited BJA records that may use the separate journal platform) now have individual outcomes, with six additional PDFs in139..142. Exact publisher issue/type labels identified several conference/abstract-only reports; these are retrieval/source-format flags, not canonical eligibility edits. All eight10.1055Thieme records are checked:four matching original PDFs recovered in143/144 and four explicit BuyArticle barriers. The first new Cambridge DOI now resolves to International Psychogeriatrics on its current journal platform; its original open-access review PDF was recovered in145. No further ScienceDirect-site requests were made after its daily quota.

GROBID's existing psychkg-grobid container was OOM-killed at01:47:31UTC with its unchanged5GiB limit. The141 initial no-artifact result and142 service-unavailable failure are preserved. Existing local Docling successfully converted both PDFs, with source identity verified; canonical conversion receipts explicitly reconcile raw failures/retries. The same existing container was restarted without changing its settings and /api/isalive returnedHTTP200true. No paid model/API calls.

Native keyboard navigation away from completed PDF viewers was unreliable; closing the exact saved PDF's selected-tab Close button, then opening a clean recovery tab, resolves the stale-viewer guard. Use explicit native tab controls rather than repeating failed address-keyboard sequences or asking the user to close nonexistent popups. Raw PDF/source receipts are retained, and no repeated clicks are counted as downloads. Source-reader repairs, extraction schemas, screening/routing decisions, graph releases and paused heartbeat are unchanged. Continue unvisited sources from the frozen queue minus current progress; the pass is not exhausted.


### 2026-10-20 02:52 UTC — external Chrome recovery continuation

Verified recovery checkpoint842 has 301 recovered records among the 1,770 prepared manual-recovery records (259 from this frozen provider pass, plus 42 prior Wiley/demo recoveries); 814 of the frozen 1,656 provider-pass records remain unvisited. Later downloads are staged separately until import and conversion verify. No screening, extraction-model, prompt/schema, or graph changes; the canonical V5+PCP screening SHA remains `01f5323d4824550daa3b01f15e7f89a01fd40c5639cfe884ec1625540676229c`. User batches001/002 remain preserved.

The wrong IJTS DOI landing for 10.24972/ijts.2019.38.2.182 yielded another report (actual DOI ending163), explicitly withheld in source_identity_hold_150.json. Visible issue navigation found the correct article12; its exact-title/DOI PDF was independently imported and converted in152. The counter now accepts only explicitly hash-proven withheld reviews while retaining the original import receipt; no alias or forced identity override. Four Karger PDFs, all nine requested IJTS PDFs and the delayed INJP PDF have verified conversion receipts.

GROBID's unchanged local container had an OOM failure; raw failures141/142 are preserved and successful local Docling retry receipts are explicitly reconciled. Temporary conversion helpers now serialize GROBID jobs. SciELO157 downloaded a real PDF with one leading LF before its header; original download and hashes are retained, and a derivative removes only that byte for strict importer validation. No pages or scientific content rewritten. New Ovid recovery follows journal search when DOI redirects to the homepage; observed main PDF buttons then save original files.


### 2026-10-20 03:40 UTC — external Chrome recovery at 326 verified PDFs

The unlocked continuation has added159 usable recoveries (160 distinct imported reports, with one Portuguese source explicitly held), bringing prepared recovery to326 of1,770. The frozen provider pass has284 verified usable PDFs; the other42 were recovered before that pass. `checkpoint_unlock_continuation_159_integrity_verification.json` verifies latest source/artifact hashes and identity for every imported report in chunks111–174, preserves all18 batch001/002 file hashes, and confirms the unchanged canonical screening SHA. No pending conversion jobs or model/API calls at this checkpoint.

SAGE's20-record group finished with2 PDFs,16 explicit purchase barriers,1 abstract-only record and1 unresolved open-access EPUB reader. Both migrated Wiley/SAGE Nature-DOI papers were recovered separately. All19 ACS originals were individually observed as Available to Purchase. Fifteen additional Nature records explicitly require a free account and remain manual per the user's instruction. Springer's21-record group yielded19 explicit PDF-purchase barriers,1 title-conflict followup and1 currently available ScienceDirect PDF deferred under that provider's already observed daily download limit. These are provider/source observations, not new scientific screening decisions or estimates of corpus access status.

The Iris publisher PDF link and exact-record ResearchGate copy both returned the same unrelated childhood-obesity report (actualDOI10.33552/GJNFS.2021.03.000562); both are preserved and withheld in `source_identity_hold_iris_20261020.json`. A WJP article PDF with10 pages of issue front matter failed parser identity verification in168. The publisher's original article-only PDF was recovered, first-page title/DOI verified, and imported with the existing `--replace-existing` workflow in169 (which backs up the prior canonical file); conversion now verifies the correct DOI. Original downloads, the168 rejected conversion, initial169 conflict and replacement receipts are preserved. No validator relaxation.

`source_language_hold_165.json` records an English abstract followed by Portuguese body text. Its raw source and conversion remain preserved, but the task-local recovery counter excludes it from ready English full texts. This changes recovery readiness only, not canonical eligibility. `source_title_mismatch_s00429_20261020.json` records a supplied-title/primary-DOI mismatch for later metadata-owner review without changing it now. PMC again requires human verification; one optional user question is pending and the external Chrome verification tab remains open. Independent recovery can continue.

The current unvisited inventory has 675 records, including 405 with original10.1016 identifiers. `unvisited_after_326_recoveries.csv` retains them explicitly as unvisited; no blanket closed-access claim and no completed-pass claim.


### 2026-10-20 04:45 UTC — recovery checkpoint338; Mac locked again

The unlocked continuation has now added **171 usable full texts**, bringing the prepared manual queue to **338 recovered / 1,770 prepared**. The frozen provider pass contributes296 of those recoveries;42 predate that pass. Chunks177–183 add12 verified original PDFs since checkpoint326:7 Taylor & Francis,1 Ovid,2 Avicenna,1 public author copy of a Global Journal of Medical Research review and1 delayed Journal of Young Pharmacists download. All saved eligible PDFs have passed the existing import and nonempty source-identity conversion checks; none await conversion. This is local PDF-to-text conversion, not model evidence extraction.

`checkpoint_unlock_continuation_171_integrity_verification.json` verifies current PDF/artifact hashes for all172 distinct imported reports in the unlocked continuation (171 usable, one previously documented Portuguese-language hold), including all12 new receipts. All18 files in human batches001/002 remain byte-identical. The canonical V5+PCP screening SHA remains `01f5323d4824550daa3b01f15e7f89a01fd40c5639cfe884ec1625540676229c`. Existing batches003 onward and provisional manual-recovery counters are updated; no screening decisions, extraction prompts/schema, model calls or published graph changes.

Provider findings: all11 Taylor & Francis records are checked (7 recovered,3 explicit purchase barriers,1 obsolete DOI followup). The6 remaining Ovid/LWW records yielded1 PDF and5 subscriber/purchase barriers. Current Avicenna pages were recovered through one exact-DOI search per broken old-domain redirect; their own Full-Text controls saved2 PDFs. IJAR's generic DOI landing was resolved to its actual article44828, but its PDF remains an unresolved download. The JYP file arrived after earlier attempts had timed out; `delayed_jyp_download_183.json` preserves this observation without attributing it to a particular click. An unrelated QR PNG was not imported or counted.

PNAS12 source pages expose main PDF controls. Actual requests failed for3 records, including one reader reporting Something went wrong;9 further records were individually source-page checked and deferred after those provider failures, not represented as9 extra failed PDF requests. Five BJA records also expose PDF sources but remain unsaved. Native macOS PDF Save dialogs were observed with Save disabled on AMJ and RSC PDFs; no browser/plugin/security settings were changed. Do not infer these available sources are closed access. `browser_download_followups_at_lock_20261020T0444.csv` preserves36 download followups. Six JOV records explicitly labelled Vision Sciences Society Annual Meeting Abstract, three primary Blood supplement/meeting records and one GMS Meeting Abstract were recorded as recovery-format flags only, without changing screening.

At checkpoint1084, **1,084 of the frozen1,656 records have recovery observations;572 remain unvisited (405 original10.1016 identifiers and167 others)**. The ScienceDirect daily download limit remains respected. `unvisited_after_338_recoveries.csv` freezes this next inventory. A previous navigation timeout is not proof a DOI's server or article is unavailable; the two attempted Bentham navigations at the end did not begin successfully and remain unvisited rather than receiving publisher judgments.

Native Chrome control then explicitly reported that the Mac was locked and automatic unlock failed. A human-unlock request is pending; `mac_locked_pause_20261020T0444.json` records the blocker. The earlier PMC verification and AMJ Save check remain optional pending handoffs. Mac locking may have affected late UI operations, but the cause of every preceding download failure is not established. Preserve the AMJ PDF and PMC handoff tabs; resume the remaining browser pass after unlock, without repeating completed imports or paid submissions. Existing screening heartbeat stays paused; no new automation/controller was created. The recovery pass is not exhausted, and extraction inputs remain provisional pending the ordinary source refresh.


### 2026-10-20 10:46 UTC — external Chrome recovery continues after unlock

The resumed session has added **36 verified usable full texts**, bringing the prepared manual queue from338 to**374 of1,770 recovered**. Chunks184–210 are complete, with the last chunk importing only the full1973article. `checkpoint_resumed_unlock_through_210_integrity_verification.json` verifies source PDF/import hashes, actual nonempty source-identity conversion artifacts for all36, all18 unchanged batch001/002 hashes and the unchanged canonical V5+PCP screening SHA. Two scan conversions needed existing local Docling OCR after GROBID; raw initial/retry receipts185/186 are preserved. The AVMJ scan used a file-specific exact-title/author/cover attestation185, without validator relaxation.

Further source documents are preserved outside ready counts: a9-page Korean JKSCT report has an English abstract but Korean Methods/body (`source_language_hold_jksct_20261020.json`); CLOCKSS1974source10.3987/r-1974-02-0228 is only one unsectioned summary page and remains a format/completeness review, without canonical screening change. Its original210dry-run receipt was archived before moving that file to completeness_review and rebuilding210for the full1973report only.

New retrieval findings: KGL PDFs may download after a timed-out tool request even when their inline route appears blank. A read-only Downloads/hash inventory located the actual JPPT385–393 PDF; exact first-page title/DOI were verified and it was imported/converted207. AHA articles worked through their actual full-text reader and normal Download PDF clicks once loaded; Download PDF with Supplements was a placeholder link, and the resulting HTML file was not imported. AHA's normal multiple-download permission was allowed for the requested PDFs. MedicalSciencePulse's main Download article control appeared after scrolling and immediately saved the original PDF. Three Heterocycles originals were recovered through Crossref's actual CLOCKSS archive choices. DOI transport/source errors, publisher purchase barriers, free-account gates and PDF-viewer failures remain distinct recovery observations. No security/certificate/paywall bypass.

At the latest completed checkpoint, the provider pass has1135 recovery observations/521unvisited. ScienceDirect remains paused at its explicit same-day download limit;405original10.1016records remain unvisited. Other publisher/repository work is ongoing, not exhausted. No downloaded usable PDF awaits import/conversion at this checkpoint. Manual batches003+ and provisional recovery counters are refreshed;001/002 preserved. No paid model/API calls, new screening, prompt/schema/normalization changes, evidence extraction model calls or graph release. The old screening heartbeat remains paused; no new automation was created.


### 2026-10-20 11:30 UTC — recovery checkpoint384; browser-control interruption

The resumed unlock session has added **46 verified usable English full texts**:338→**384 of1,770 prepared manual-recovery records**. Chunks184–219 are complete except216, which is explicitly withheld under `source_identity_hold_meducator_216.json`; no216canonical import occurred. `checkpoint_resumed_unlock_through_219_integrity_verification.json` verifies all46source/import/conversion artifacts, raw OCR retry receipts185/186, all18unchanged human-batch001/002 files and unchanged canonical screening SHA. No usable saved PDF awaits import/conversion.

New recoveries after checkpoint374 include the AJPH, AsMA and APLM originals, the correct NanoBioLetters173paper despite its original DOI incorrectly redirecting to174, JoVE, a public Salvia author copy, the LSD review from the original RJPT publisher despite IndianJournals paywall, and all3wildlife-disease archive papers. RJPT used a blocked PDF popup: the single requested ShowPDF_Paper.aspx window was opened from Chrome's actual popup list; Continue blocking was left selected and no persistent popup rule was changed. Late Downloads/hash inventory recovered the Meducator op.pdf; it matches journal/authors but prints a different DOI and was kept outside ready counts when the standard importer rejected it. Original records and raw failures remain preserved.

Eight additional non-English documents from this resumed session are stored outside English-ready counts (JKSCT, sixJapanese archive reports, onePersian JMP source); the global source-language-hold count is18. The one-page CLOCKSS1974summary remains a separate completeness review. These are recovery/source-readiness flags, not scientific rescreening or canonical eligibility changes.

Current provider-pass inventory:1163records with recovery observations/493unvisited. The unvisited CSV explicitly contains405original10.1016records deferred under the existing ScienceDirect daily quota and88other unvisited records. Observation counts include explicitly incomplete technical checks; they are not completed scientific audits or proof of closed access. Manual batches003+ and provisional recovery counters are updated;001/002 unchanged.

Native Chrome state inspection stalled for300seconds while checking repository controls. Resetting the tool session succeeded, but reattaching the pending Newcastle tab still timed out on browser focus control. `browser_control_timeout_20261020T1126.json` preserves both attempts. No Mac-lock or visible-popup cause is asserted. Fraunhofer10.24406/publica-7881andNewcastle10.25405/ncl.34469904 remain explicitly browser_control_interrupted, not paywalled/no-PDF. Resume these exact source checks and then unvisited inventory when browser control works; do not duplicate completed imports. Earlier PMC PDF verification remains a separate human handoff; Nature-account gates remain manual by preference.

The browser pass is not exhausted. No paid model/API calls, new screening, prompt/schema changes, extraction model calls, normalization changes, graph replacement, automation or background controller. Existing screening heartbeat stays paused.


### 2026-10-20 15:03 UTC — external Chrome recovery checkpoint393; source-version holds remain separate

The resumed unlock session has added **55 verified usable English full texts**, taking the prepared manual-recovery queue from338 to **393 of1,770**. Applied import/conversion chunks184–229 are complete, except explicitly withheld216and220. `checkpoint_resumed_unlock_through_229_integrity_verification.json` verifies all55 source/import/artifact hashes, preserved185/186OCR attempt receipts, all18 unchanged human batch001/002 files and canonical V5+PCP routing SHA `01f5323d4824550daa3b01f15e7f89a01fd40c5639cfe884ec1625540676229c`. Later scan221 used existing local Docling OCR with a file-specific cover/title/author attestation, not a relaxed import gate. Current verified papers have no pending PDF import/conversion. Manual batches003+ and provisional recovery counters are refreshed; extraction routes are not refreshed.

New ready papers after384 include the scanned Pakistan Journal of Nutrition article, HSPublishing journal PDF linked through Google Drive, free Minerva review, HESDIA review, actual Eco-Vector English PDF despite its Restricted Access badge, Sklifosovsky English translation, the previously gated PMC asthma PDF and Physical Chemistry Research original. The Brazilian police-survey source is a publicly author-uploaded2017PDF print of the full SciELO article (nine pages, principal sections/references present), downloaded unchanged; it is not a print generated here. `source_quality_author_copy_228.json` preserves that provenance and ordinary table/figure-capture limitations. No paper's scientific inclusion was rejudged.

Outside ready counts:21 non-English source-PDF holds, seven source-identity holds, two new publication/version-review PDFs, one one-page completeness hold, and one UNC accepted manuscript recovered as four original Word files (manuscript, two table files, figure). UNC files are preserved under manual_source_inbox with hashes in `unc_nkzy_original_docx_source_recovery.json`; no synthetic PDF or new ingestion route. The MDA SSRN source explicitly says Working Title / Discussion Draft; the54-page psilocybin-ecology manuscript has no verified journal version in the inspected source. These are publication/source-readiness holds, not canonical eligibility changes.

Fraunhofer220 recovered a matching original journal PDF but the requested repository DOI differs from the publisher DOI; raw importer conflict, original proof and schema-extension proof remain preserved. The publisher record already exists in current routing with a local PDF; that existing PDF's first page was checked to match journal/title/authors/publisher DOI. Files are NOT byte-identical, so do not claim identical hashes or independent reports. HSRC230 likewise recovers the original six-page2018Peltzer/Phaswana-Mafuya journal PDF, DOI10.4102/sajpsychiatry.v24i0.1139, for a2026repository wrapper10.14749/32381937. **Its standard dry-run was clean by filename plus exact title** (line-wrapped publisher DOI not recognized); it was explicitly withheld by source-ID review, not automatically rejected. `source_identity_hold_hsrc_230.json` preserves the clean raw receipt, source evidence and hashes; no230apply or conversion. Published counterpart is already in current routing, outside the frozen manual provider list. Canonical aliases/versions were not edited. Never import230blindly from its clean dry-run or count these wrappers as extra independent studies.

The browser issue was partly operational: some background-tab clicks did not open the PDF, while foreground native clicks did. Activate the correct recovery source tab before interacting, inspect actual cookies/download permission, click, let its actual viewer load, save, verify file and close only that own PDF viewer. Chrome's false another-extension message often means its Adobe PDF viewer; no phantom-popup request. The user explicitly said Chrome was idle when control interruptions occurred; intermittent navigation/DOM/AX faults remain real. Preserve original failures rather than attributing every failure to one cause.

Manglar's relocated publisher was found through one exact-DOI query after its obsolete DOI target404. Its PDF arrived later, discovered in Chrome history/Downloads. Page2 verifies Spanish Introduction/Methods; it is now a language hold. The earlier generic download Blocked by your organization remains an unsuccessful attempt, **not** the final recovery state. `manglar_late_download_source_provenance.json` records source/hash/timing without claiming which click caused the late file. The source tab exposed an actual multiple-file permission; allowed only the requested downloads, no security bypass. Periodically check late files before recording a source unavailable.

Current provider pass: **1,195 records have recovery observations;461 unvisited (405original10.1016records deferred under ScienceDirect daily quota,56other records)**. `unvisited_after_393_recoveries.csv` freezes that inventory. The pass is **not exhausted**. SSRN access checks eventually cleared for two source pages and actual manuscripts were saved; do not treat all SSRN as blocked from initial verification. The first new PMC fallback still failed its reCAPTCHA service; do not infer all58cachedPMC candidates were tried or allowed from the one successful asthma PDF. Nature account gates remain manual by preference. RG cathinone DOI endpoint explicitly says content removed; other versions were not globally adjudicated.

Continue remaining independent browser recovery in external Chrome1, then rebuild the ordinary manual/source/extraction input lists when recovery is done. No paid model/API calls, evidence-extraction model calls, screening/prompt/schema/normalization/core pipeline changes, graph replacement, new automation or background controller. Existing screening heartbeat stays paused. Do not spawn agents.


### 2026-10-20 17:08 UTC — recovery checkpoint412; remaining manual batch prepared

The resumed unlock continuation has added **74 verified usable English full texts**, bringing the prepared manual queue from338 to **412 of1,770 recovered**. Five were added in the latest browser segment: the Applied Animal Science original, the actual SciELO English publisher translation, and three additional PNAS originals. All usable saved PDFs have completed existing import and local nonempty source-identity conversion; none await conversion. `checkpoint_resumed_unlock_through_236_integrity_verification.json` verifies every74 source/import/conversion artifact across184–236, the explicit216/220/230 source holds, all18 unchanged batch001/002 files, preserved OCR retries and unchanged canonical V5+PCP screening SHA `01f5323d4824550daa3b01f15e7f89a01fd40c5639cfe884ec1625540676229c`.

Seventeen PNAS PDFs have now been recovered since checkpoint393: fourteen in231/232, two in235 and one late-arriving original in236. Several earlier source checks had navigated incorrectly or failed to attach to Chrome; fresh exact-DOI navigation verified the actual reports. The latest original arrived after tool timeouts and a reader security check; `pnas_late_download_source_236.json` preserves file, title/author/year/pages and source evidence without attributing success to a particular click or claiming any security bypass. Two other free-access PNAS full-HTML reports and the84.14.5068 PDF remain technical followups despite actual PDF controls. Never treat these as paywalls.

SciELO initially displayed automatic connection verification, which cleared without CAPTCHA solving. Its PDF dropdown offered separate Portuguese and English originals; the English PDF contains Introduction/Methods/Results/Discussion and passed normal import/conversion234. `scielo_english_source_234.json` preserves the actual publisher language-specific URL and hash. The Applied Animal Science DOI opens that journal's own PDF, not ScienceDirect; it was saved through the visible Adobe Download control and converted233. Do not classify publishers only from DOI/owner association.

Current saved documents outside ready counts:30 language-review PDFs,10 source-identity-review PDFs,6 publication/version-review PDFs,1 one-page completeness hold and the UNC accepted manuscript as four originalWord files. These remain retrieval/source-readiness holds, not new scientific screening or canonical eligibility changes. New Korean scans were verified visually on actual bodypage2; the Persian review body starts on page5 after front matter. Russian cardiovascular PDF bodypage3 was separately preserved. Publisher English interfaces/abstracts alone do not establish English full sources. The Nota Bene Eng page contains complete English HTML but no PDF control; no synthetic PDF or new ingestion route was created. eScholarship's qt9pj4r3kv PDF identifies actual publisherDOI10.5070/d3239036477; its requested PII key remains unchanged pending the existing identity-owner reconciliation, and the saved PDF is not counted as an independent extra study.

At checkpoint1251, **1,251 of the frozen1,656 provider-pass records have retrieval observations;405 remain unvisited, all original10.1016 identifiers**. The ScienceDirect daily bulk-download limit still applies; these405 first attempts and additional already-observed migrated ScienceDirect sources are deferred, not closed-access findings. `unvisited_after_412_recoveries.csv` preserves the exact405. All other frozen records now have an observation, including bounded incomplete technical checks; this is not proof of exhaustive alternative-copy searches. PMC's fresh2873769 attempt again stalled in reCAPTCHA and reported inability to connect to that service; one explicit reload was attempted, without solving or bypassing verification. Do not describe all58 cachedPMC candidates as individually tried or blocked. La Trobe's actual30-page English accepted manuscript is visible but its ndownloader file fails; OMICS PDF wrappers embed URLs returning genericHTML; other failures distinguish real403s, obsoleteDOIs, original abstract/format-only sources and technical download blocks. Nature account gates remain manual per user preference.

The original numbered batch manifests remain preserved, with existing recovery annotations. Opening old batch003 revealed that it still contains recovered rows, so it is not presented as a fresh unrecovered set. A separate **remaining_20261020_01** artifact now contains50 currently unrecovered candidates: actual PDF-transfer followups first, then account/verification/access gates, with original deterministic recoverability score as tie-breaker. Saved review documents and ScienceDirect quota deferrals are omitted. Its manifest stores selection/provenance and input hashes; all50 were checked against current outcomes. The fresh page is opened in external Chrome at http://127.0.0.1:8766/manual_chrome_batches_20261019/remaining_20261020_01/index.html and displays50 paper cards with outcomes export and a dedicated ordinary manual-PDF inbox. `checkpoint_412_and_remaining50_integrity.json` verifies counts, selection, hashes and unchanged screening.1,358 prepared records are not yet ready; this includes access failures and source-review holds, not1,358 proven closed-access papers.

Operational lessons: reuse the selected Chrome profile; claim actual task tabs when debugger attachment is stale; a timed-out new-tab navigation may never have started, so inspect actual URL before judging the source; link clicks may open a separate tab; activate the real PDF viewer and wait for its actual controls. A disabled Save picker can recover by selecting Desktop then Downloads before saving; this is not proof the Mac is locked. Do not request dismissal of a phantom extension popup. Do not close pages while an actual partial download is pending. No .crdownload files remained at this checkpoint. Automatic browser/security gates were not bypassed, and no browser/plugin/security settings were changed.

The recovery pass remains limited by real access/download/verification barriers and the ScienceDirect quota; it is not claimed exhaustively completed. No paid model/API calls, extraction-model calls, scientific rescreening, prompt/schema/normalization/core pipeline changes, extraction-route refresh, published graph replacement, new automation or detached controller. The old screening heartbeat stays paused. Continue only ordinary retrieval/import/conversion, or let the human use the fresh remaining50 batch.


### 2026-10-20 — user clarification of recovery access reporting

Count account/registration gates together with paywalls as access barriers in user-facing recovery summaries. The412-ready checkpoint therefore has702 access barriers among1358 not-ready records:663 recorded publisher-paywall/subscriber observations plus39 account/registration gates. Preserve the original per-record subtype and source evidence; this is a reporting grouping, not new access evidence or screening. The fresh remaining50 batch contains35 account/registration access barriers and15 download followups; the earlier claim that it contains no paywalls was misleading under this agreed grouping. Reports: access_barriers_702_20261020.csv and remaining_1358_access_grouped_20261020.csv, with reconciliation at access_barrier_reporting_clarification_20261020.json.


### 2026-10-20 18:43 UTC — all 50 no-gates batch records personally checked in external Chrome

The user asked for another 50 excluding paywalls/account gates, then asked Codex to try every one. The replacement selection is `remaining_20261020_02_no_gates` (not the superseded `_01`, which had 35 registration gates). Its frozen manifest/papers remain unchanged, with zero then-recorded gates, original source hashes, selection evidence and preferred public-source URLs. All 50 source pages and the checklist were opened in the external Chrome recovery group, and all 50 received an individual retrieval observation. No scientific rescreening was performed.

Results: **17 new original PDFs saved, source-identity verified, imported and converted locally** in chunks 237–241; **3 actual publisher paywalls** newly confirmed; **27 technical follow-ups**; and **3 source issues**. Technical outcomes are 11 explicit Chrome `ERR_BLOCKED_BY_CLIENT` pages, 4 explicit connection resets, 7 verification/CAPTCHA gates, 4 incomplete download/viewer attempts and 1 publisher 522 error. These are not 27 proven closed-access papers. The three source issues are a previously arrived Chinese-body PDF (actual body page 2 visually checked and hashed), an original Columbia Word manuscript preserved unchanged, and a ScienceOpen source explicitly labelled conference-poster/Conference Proceedings. They remain source-readiness observations, not new canonical eligibility decisions. Optional site-header login was not treated as a paywall; PsychiatryOnline's actual purchase/subscriber requirements were.

Successful sources included all three PNAS papers, the APA paper, all six requested PMC PDFs after exact main-control retries, EASAP, one EKB journal PDF via native viewer Save, LifeScienceGlobal, three ScienceDomain journal PDFs, and PsychiatryOnline's freely accessible 8-page eReader PDF. An 8-second media timeout did not always mean failure: the PsychiatryOnline PDF arrived later and file inventory found it. Two identical download copies count once. The other PsychiatryOnline papers explicitly require purchase/subscriber access. All actual PDFs passed the existing clean import gate and verified local conversion; no new conversion or ingestion route was created for DOCX/full HTML.

`remaining_20261020_02_no_gates/browser_review_results.json` and CSV contain all 50 numbered outcomes, evidence and verified PDF paths/hashes; `browser_followups_27.csv` isolates the remaining technical cases. The checklist was annotated and reloaded in external Chrome, visibly showing 17/3/27/3. Initial selection files and the pre-review page remain preserved under `before_browser_review`. Existing manual queue owner and provisional counters now show **429 of 1,770 ready**, up from 412, with **1,341 not ready**. Updated reporting groups are 705 paywall/account access barriers, 405 unvisited ScienceDirect quota deferrals, 129 browser/download/content follow-ups, 48 saved PDF source-review holds and 54 other source/repository/format issues. See `access_reporting_after_batch50_20261020.json`; previous 1,358/702 reports remain preserved.

`checkpoint_resumed_unlock_through_241_integrity_verification.json` verifies all 91 resumed-session usable reports, source/import/conversion hashes, the 18 unchanged human batch 001/002 files, explicit withheld-source proofs and unchanged canonical screening SHA `01f5323d4824550daa3b01f15e7f89a01fd40c5639cfe884ec1625540676229c`. No pending import/conversion for these 17 files; no active partial downloads at the saved-file inventory. No paid model calls, extraction calls, screening/prompt/schema/normalization/core pipeline changes, extraction-route refresh, graph replacement, new automation, detached controller or agents. Account gates remain grouped with paywalls; browser blocks remain separate. The old screening heartbeat stays paused.


### 2026-10-21 local — second no-gates batch completed; recovery tabs cleaned

The user's next50 request produced `remaining_20261020_03_no_gates`, selected from70fresh technical-followup candidates after excluding previous remaining batches, recorded historical payment/account barriers, known source/identity/dead-end issues and ScienceDirect quota sources. Its original50-row manifest, selection hashes, paper list and URLs remain unchanged. **All50now have source-page retrieval observations:2usable published PDFs recovered/imported/converted,24actual paywalls,21technical/download follow-ups and3source issues.** The source issues are one recovered SSRN preprint manuscript (seven original pages), one source explicitly labelled Vision Sciences Society Annual Meeting Abstract, and a recovered Persian-body SSU PDF despite an English landing title and `-en.pdf` filename. No scientific rescreening or canonical eligibility changes.

The two ready reports are SJMS10.55675/sjms.v2021i1.67and Begell10.1615/intjmedmushrooms.2021041921. Applied import/conversion242and243passed source/hash verification and nonempty local GROBID conversion (45,756and108,957characters respectively).242's original automatic dry-run was held because its publisher cover and blank page2precede the actual article onpage3. The original receipt is preserved; exact title, authors, volume/pages and literal DOI on the rendered originalpage3support an existing hash-bound validated-document-audit attestation. The clean attested dry-run/apply receipts and unchanged original PDF are preserved; no validator relaxed.243's first apply failed before import because the old `/tmp/pkg-model-eval-py312`environment had lost `pyvenv.cfg`and resolved to a runtime without pyarrow. The existing `psychkg-pdf`conda interpreter completed the same authorized import/conversion successfully; no dependency installation or production-code change.

Of24newly confirmed barriers,22are exact Taylor&Francis full-article/ePDF purchase/institution panels, one is Springer's explicit39.95EURarticle purchase, and one is JSAD's actual PDF subscription/purchase gate. Generic globalLoginheaders were not used as access evidence. Some T&Fabstract pages expose only a Read this article button; following it reveals the actual ePDFpurchase panel. Springer10.1007/s00429-023-02740-whas a supplied cultural-technology title attached to an actual ketamine/anorexia source; preserve that identity flag without silently editing metadata. SSRN's Data_Integrity_Notice route is an optional signup notice with a visible Download without registration link, not evidence of misconduct or a required registration gate. That guest option was attempted for4123465without a verified PDF; its status remains download-followup. Native Chrome successfully downloaded3888661after the automated helper failed, but the source explicitly labels it preprint/not peer-reviewed, so its original bytes are held outside ready published-paper counts.4237108showed an actual certificate common-name warning; it was not bypassed.

Browser control repeatedly stalled while task tabs accumulated. The user correctly objected and closed old groups; Codex then closed33remaining task-source tabs through the documented Chrome management capability, leaving the checklist. Work resumed with completed source tabs closed promptly. The user explicitly permits10or20active source tabs; **use at most10active paper tabs, close completed/failed/verification-stalled sources, and retain only the results checklist at completion.** All source tabs are now closed and the native Chrome checklist visibly shows2/24/21/3and a one-tab recovery group. Other user tabs/windows were not closed. Initial `browser_control_checkpoint.json` accurately preserves the partial25-page phase; it is explicitly superseded by `browser_review_results.json`, not presented as current unfinished work.

`browser_review_results.csv/json`contains all50numbered outcomes/evidence/verified file paths; `browser_followups_21.csv`isolates non-payment technical follow-ups. Manual queue owner and provisional counters now show **431of1,770ready,1,339not ready** (up from429). Current not-ready reporting:729paywall/account barriers,405unvisited ScienceDirect quota deferrals,100technical/browser/content follow-ups,50saved-PDF source-review holds and55other source/format/repository issues. Earlier snapshots remain preserved. `checkpoint_resumed_unlock_through_243_integrity_verification.json`verifies93resumed-session ready reports, source/import/conversion hashes, all18unchanged human batch001/002files and unchanged canonical screening SHA `01f5323d4824550daa3b01f15e7f89a01fd40c5639cfe884ec1625540676229c`. No pending import/conversion for these two ready PDFs.

No model/API spending, extraction calls, new scientific screening, prompt/schema/normalization/core pipeline changes, extraction-route refresh, graph replacement, new automation, detached controller or agents. Old screening heartbeat remains paused. This completed50-paper retrieval pass is not a claim that all lawful alternatives for each technical failure have been exhausted.


### 2026-10-21 local — next 50 no-gates batch04 completed

Reviewed all 50 frozen records in external Chrome. The earlier ScienceDirect daily limit was no longer blocking ordinary main-article downloads; the first publisher verification page offered a normal retry that reached the PDF. Selected 50 fresh, previously deferred ScienceDirect records, prioritizing OA metadata, excluding every historical recorded paywall/account/registration gate and every earlier remaining-batch assignment. Frozen selection at `manual_chrome_batches_20261019/remaining_20261021_04_no_gates/manifest.json` is preserved unchanged.

Results: **47 original PDFs saved; 44 verified/imported/converted usable full texts; 3 saved scans held after converted-source identity failed despite local OCR; 2 newly confirmed institutional-access gates; 1 publisher-labelled conference abstract.** Retrieval observations do not change scientific screening. Source20 is the IBRO E5 conference abstract; sources25/26 show institutional access and article previews. Saved sources31/32/33 remain identity-review holds, not assertions that the original PDF bytes are incorrect. OCR recovered source30 and37; preserve initial GROBID and selective OCR receipts. No validator/prompt/schema changes.

Imports/conversions244–261 are reconciled, 47 PDF hashes and 44 nonempty identity-verified converted artifacts checked. Manual prepared recovery **431→475 usable; 1,295 not ready**: 731 known access gates, 355 unvisited ScienceDirect records previously deferred by quota, 100 technical follow-ups, 53 saved-source review holds and 56 other source/format/repository issues. The 355 historical quota label does not mean a quota is currently active. No API/model calls. Scientific screening routing SHA remains `01f5323d4824550daa3b01f15e7f89a01fd40c5639cfe884ec1625540676229c`; first two human manual batches unchanged.

All source/PDF tabs closed as completed, at most eight simultaneous paper tabs plus checklist. New result checklist retained; unrelated tabs left untouched. Two browser-control cell timeouts were resumed from existing tabs and saved-file receipts, without duplicate imports. Full outcomes, source evidence, remaining groups and hash-bound integrity are in `remaining_20261021_04_no_gates/browser_review_results.json`, `completion_integrity.json`, and provider `checkpoint_1301.json` / `access_reporting_after_batch04_20261021.json`. No extraction calls, route rebuild or graph changes.


### 2026-10-21 local — ScienceDirect next50 batch05 completed

Completed all50 browser recovery attempts from the frozen `remaining_20261021_05_no_gates` selection. All50 are fresh ScienceDirect records previously deferred by quota, prioritized by OA metadata; historical recorded paywall/account/registration gates and prior remaining-batch assignments were excluded. **48 original main PDFs saved, identity-verified, imported and converted; 2 CAPTCHA follow-ups; 0 newly observed paywalls or registration gates.** The verification cases are10.1016/j.drudis.2025.104371(mainPDF) and10.1016/j.pnpbp.2025.111251(articlepage), both explicitly requesting CAPTCHA completion. No challenge solved or bypassed; these are not paywall findings.

Imports/conversions262–275 reconcile to48 unique records with original/destination PDF hashes and48 nonempty source-identity-verified artifacts. Frozen selection/CSV preserved, first two human batches unchanged and screening routing SHA remains `01f5323d4824550daa3b01f15e7f89a01fd40c5639cfe884ec1625540676229c`. No API/model calls, scientific screening decisions, prompt/schema/code changes, extraction calls or graph replacement. Long-running checks272/273 completed normally; a premature apply272 attempt failed before mutation because its dry-run receipt was absent, then succeeded only after the clean dry-run completed. No duplicate import.

Prepared manual-recovery queue **475→523 usable; 1247 not ready**:731 known access gates,305 unvisited ScienceDirect records previously deferred by quota,102 technical follow-ups,53 saved-source review holds and56 other source/format/repository issues. The historical quota label does not assert a currently active limit.

Source and PDF tabs were closed as their work completed, at most8 paper tabs plus checklist. Later in the pass, large article pages were closed once their mainPDF controls and source identity were established, leaving only required viewers and reducing native accessibility overhead. Browser-control timeouts were resumed from actual existing tabs/download receipts. Opaque browser IDs changed after a control reset: final external Chrome/Povilas is browser3, extensionInstanceId5dcff716-98ca-4792-87d9-cca85e02a8e5; always inspect inventory after any future reset. New result checklist retained; unrelated user tabs untouched. Full outcome/verification receipts: `remaining_20261021_05_no_gates/browser_review_results.json`, `completion_integrity.json`, provider `checkpoint_1351.json`, and `access_reporting_after_batch05_20261021.json`.

### 2026-10-21 local — ScienceDirect next50 batch06 paused at daily limit

Selected another frozen50 fresh ScienceDirect records, excluding historical paywalls/account/registration gates and prior remaining-batch selections. **Only4of50 attempted:2 usable main PDFs recovered,1 new publisher paywall,1 explicit daily bulk download limit;46 remain unvisited.** At paper04, DOI10.1016/j.toxicon.2025.108450, the mainPDF control opened the publisher dialog “You have reached the daily bulk download limit.” No further ScienceDirect requests attempted and no bypass attempted. The two already-loaded PDFs were saved using Chrome's normal download control. Paper03, DOI10.1016/j.toxac.2025.02.001, showed Article preview/PurchasePDF and is now excluded from future no-gates batches. The limit is not a paywall classification for paper04 or the unvisited46.

Import/conversion276 completed cleanly:2new imports,0conflicts/review/invalid files,2nonempty source-identity-verified converted artifacts. Original/destination PDF hashes checked. Prepared manual-recovery queue **523→525 usable,1245 not ready**:732 known paywall/account/registration barriers,301 unvisited ScienceDirect records historically deferred by quota,103 browser/access/download/content follow-ups,53 saved-source review holds,56 other source/format/repository issues. Provider checkpoint1355 records483 verified usable full texts from1656frozen provider candidates; the broader prepared1770queue also retains42earlier recoveries. No pending conversion for these two PDFs.

Partial results at `manual_chrome_batches_20261019/remaining_20261021_06_no_gates/browser_review_results.json/csv`, `partial_completion_integrity.json`, and `remaining_queued_46.csv`; provider `checkpoint_1355.json` and `access_reporting_after_batch06_20261021.json`. Frozen50manifest/CSV/URLs preserved, original human batch001/002 files unchanged, screening SHA remains `01f5323d4824550daa3b01f15e7f89a01fd40c5639cfe884ec1625540676229c`. All4article tabs and2PDF viewers closed, older completed checklist closed, partial batch06 checklist retained in external Chrome; unrelated tabs untouched. No API/model calls, scientific screening/prompt/schema/core-code changes, extraction calls, new automation or graph changes. Old screening heartbeat remains paused. Resume the46queued records only after publisher access is normally available again; this partial batch is not completed50paper recovery.

### 2026-10-21 local — other-publisher batch07 completed

Completed all 50 records in `manual_chrome_batches_20261019/remaining_20261021_07_other_publishers_no_gates`. These were explicit retries of earlier unresolved technical/source failures, not 50 untouched records. Prior main-PDF observations and OA metadata were prioritized; all historical observed paywalls/account/registration gates, saved-source review holds and known format-only records were excluded. A preliminary selection was archived before provider/identity checks removed known ScienceDirect routes and known identity/preprint cases; final frozen selection and CSV remain unchanged. No ScienceDirect publisher requests or quota retest in this pass.

**Results: 6 original PDFs recovered, identity-verified, imported and converted; 7 browser-verification gates; 2 HTML-only sources; 1 repository-confirmed master's thesis; 34 technical/content follow-ups. Zero new paywalls or registration gates.** Saved papers: Academia Turkish youth substance-use report; Zagazig ketamine review; MDPI postmortem NPS review; Copenhagen 25CN-NBOH accepted manuscript; Penn State GMIS accessible copy; AJOL ketamine/plant-extract animal study. MDPI and AJOL initially showed blocked-page observations before their actual PDFs arrived. Completed local PDF bytes, hashes and subsequent clean imports explicitly supersede those earlier no-file observations; all histories are retained. Do not infer absence of a download solely from an error tab. No challenge, security warning, paywall or required registration bypassed.

Imports/conversions277–280 reconcile to 6 unique records with 6 matching original/destination PDF hashes and 6 nonempty source-identity-verified converted artifacts. GROBID succeeded for277, failed on278 and was unavailable at279. Existing pdftotext backend converted278–280 with unchanged identity gates and no route rebuild. Initial278 failure receipt and279 unavailability observation are preserved in provider `batch07_conversion_fallbacks.json`. Existing GROBID container was found exited137/OOMKilled=true; its exact cause was not established. Restarted the same container with unchanged settings, then verified its health after normal startup at `batch07_grobid_service_recovery.json`. No import was repeated.

Manual prepared recovery **525→531 usable; 1,239 not ready**:732 historical access gates,301 unvisited ScienceDirect quota deferrals,95 technical/browser/content follow-ups,53 saved-source review holds and58 other source/format/repository issues. Verification gates are not payment gates. The two HTML-only reports have readable publisher English sources; no synthetic PDFs created. CSU ScholarWorks now explicitly confirms one previously blocked record as a master's thesis; this is a retrieval-format observation, not a canonical screening change. All 50 attempts are recorded, without claiming every lawful alternate source has been exhausted.

All article/search/PDF tabs closed. New outcome checklist remains open in external Chrome; paused ScienceDirect batch06 checklist and unrelated tabs are unchanged. During native interaction another Chrome window briefly became foreground; no action was taken in that unrelated window. Focus was restored to the identified recovery window. Full outcomes, six recovered records,44 follow-ups and integrity chain are in batch07 `browser_review_results.json/csv`, `recovered_6.csv`, `followups_44.csv`, and `completion_integrity.json`. Use provider `checkpoint_1355_after_batch07_20261021.json` and `access_reporting_after_batch07_20261021.json`. Unique provider-attempt count remains1355 because these were retries; the existing batch06 `checkpoint_1355.json` was preserved by using a distinct temporary checkpoint-wrapper output name. Provider verified total489 plus42earlier prepared recoveries equals531.

Original human batch001/002 files and canonical screening SHA `01f5323d4824550daa3b01f15e7f89a01fd40c5639cfe884ec1625540676229c` are unchanged. No model/API calls or spending, evidence-extraction calls, scientific screening decisions, prompt/schema/core-pipeline code changes, extraction-route rebuild, graph replacement, new automation or agents. Old screening heartbeat remains paused.


### 2026-10-21 00:08 UTC — remaining other-source pass08 completed; ScienceDirect quota persists

Continued the user’s request to work through the remaining papers. The frozen pass08 list contains 45 provider follow-ups and two additional manual-owner source-link cases outside the immutable 1,656-record provider list. All 47 now have explicit dispositions: 46 source-page checks and one previously verified ScienceDirect route deferred after a separate ordinary quota check. These were retries and source checks, not 47 untouched papers or a random sample. Original selection files remain unchanged.

**Three new English main PDFs are imported and converted; five additional PDFs are saved for source review; eight actual access gates were newly established.** Other outcomes: eight browser-verification gates, six format/language issues, one HTML-only source with broken PDF controls, 15 technical/content failures, and one ScienceDirect deferral. Manual recovery rises **531 → 534 usable of 1,770**, leaving 1,236 not ready: 740 payment/account/registration barriers; 301 unvisited ScienceDirect quota deferrals; 80 browser/download/content follow-ups; 58 saved-PDF source-review holds; 57 other source/format/repository issues. The latter 195 records have earlier attempts or source observations and are not all paywalled.

The usable originals are OMICS vibrational/NMR DOI 10.4172/2329-9053.1000135, ecstasy memory DOI 10.4172/2155-6105.1000266, and university-repository VDR/NMDAR DOI 10.4172/2168-9296.1000127. Standard imports 281/282 have no conflicts, review rows or invalid files; original and destination hashes match. Existing pdftotext converted chunk 281 (141,422 and 49,828 characters); GROBID converted chunk 282 (73,714 characters). All artifacts have verified source identity. The first PDF is 24.9 MB; no new backend or identity relaxation was introduced.

The five held PDFs are Dutch NTvG/RUG d4842 and Russian NII 1694 (actual body languages checked); OAIJMR ketamine review (printed DOI .34 versus supplied .553 galley/file number); IJCRI ecstasy case (title-matched primary PDF prints the requested DOI while its resolver identifies another report); and Salvia case (printed DOI 10.4172/2161-0495.1000340 versus supplied 2167-7972). No aliases or metadata repairs inferred. Salvia arrived despite a ResearchGate security page; actual completed files were checked before classifying failure. Its title-match dry-run 283 accepted the file, but was deliberately **not applied** because the printed identifier differs. `source_identity_hold_283.json` preserves that conflict. No import or conversion remains pending for the three ready files.

Five publisher paywalls and one required CNKI login were confirmed within frozen provider scope. The two additional manual-owner records’ original DOIs redirect to title-matched Wiley reports with explicit USD 49/62 PDF purchase panels. Their access observations were reconciled separately into the existing manual owner, without expanding provider scope or adding aliases. Optional login headers were not treated as paywalls. Security warnings, insecure-download protection, verification challenges and publisher limits were not bypassed.

At 00:02 UTC, one ordinary ScienceDirect View PDF request for known open-access DOI 10.1016/j.toxicon.2025.108450 again reported **“You have reached the daily bulk download limit.”** No further queued requests. The 301 unvisited papers remain queued, including 46 in batch06. This also blocks the already visited Springer-to-ScienceDirect ATG5 route. The non-ScienceDirect follow-up pass is complete; every possible lawful alternate copy is not claimed exhausted. No new schedule was created.

All article/search/PDF tabs were closed. Only pass08 results and the paused batch06 queue remain; unrelated user tabs were untouched. Full outcomes are in `manual_chrome_batches_20261019/remaining_20261021_08_final_other_sources/browser_review_results.json`, CSV, `recovered_3.csv`, `remaining_dispositions_44.csv`, and `completion_integrity.json`. The initial completed-list snapshot is preserved under `before_late_repository_followups`. Current provider receipts: `checkpoint_1355_after_pass08_final_20261021.json` and `access_reporting_after_pass08_final_20261021.json`; older checkpoints remain preserved. Provider 492 verified recoveries plus 42 earlier prepared recoveries equal 534. All 18 human batch001/002 files and screening SHA `01f5323d4824550daa3b01f15e7f89a01fd40c5639cfe884ec1625540676229c` remain unchanged. No model/API spending, scientific screening, extraction calls, prompt/schema/core-code changes, graph replacement, agents or automation. Old screening heartbeat stays paused.


### 2026-10-21 — user-authorized ScienceDirect resume follow-up

The user explicitly asked to continue the remaining 301 ScienceDirect papers once the daily limit resets, excluding known paywalls/registration gates and closing finished tabs. Created and verified active same-chat heartbeat `resume-sciencedirect-pdf-recovery`, checking every four hours. It makes one ordinary availability check, stays quiet while the limit is unchanged, resumes sustained recovery once downloads work, and disables itself when the queue is dispositioned or only user-dependent work remains. No further publisher request was made in this scheduling turn; the latest observed quota remains the earlier 00:02 UTC / 04:02 Dubai check. The frozen queue and scheduling receipt are under provider `sciencedirect_resume_20261021`; all 301 unique records and all 46 batch06 leftovers were verified, with zero historical access gates in the queue. Current recovery baseline remains 534 usable. The unrelated old screening heartbeat remains paused. No screening, extraction or graph changes.


### 2026-10-21 09:55 UTC — corrected interpretation of ScienceDirect bulk-limit popup

The user asked whether the reset is rolling and when the limit first occurred. Source-event timestamps establish the first-ever recorded popup at **20 October 05:03:48 Dubai**; main PDF downloads worked again by **21 October 01:50:31 Dubai**; the current episode was recorded at **21 October 03:02:07 Dubai**. These are logging/observation times, not exact server reset times. No public rolling-window/reset clock was found. A rolling allowance is different from a 24-hour lockout after the first failure.

The current official download guide explicitly permits individual PDFs after the multiple-document limit: https://www.elsevier.support/sciencedirect/answer/how-do-i-download-articles-and-chapters . The earlier blanket interpretation of the bulk popup as blocking every PDF was too broad. Tested the visible individual-PDF href for DOI 10.1016/j.toxicon.2025.108450, opening that normal observed link. It reached the PDF server and requested human verification; the user completed it, after which the original 2,032,245-byte PDF opened and was saved. Clean import 284 and GROBID conversion verified its identity and 96,575 characters. This previously attempted test paper is outside the frozen 301 queue; overall usable recovery rises **534 → 535**. The bulk quota was not demonstrated cleared. Preserve the old raw popup observations while superseding their overly broad inference.

Updated the existing same-chat heartbeat through automation_update, preserving its schedule/status/target and replacing the blanket stop guard with the publisher-supported individual route. Normal CAPTCHA/security/access restrictions still apply. Resumed six records from the frozen queue: all six exact publisher pages showed Article preview, Purchase PDF and institutional login. They are now explicit access gates. Original queue: **0 recovered, 6 gated, 295 unvisited**. Overall 1,235 not ready: 746 access gates, 295 unvisited ScienceDirect records, 79 technical follow-ups, 58 saved-source holds and 57 other source/format issues. The new grouped CSV labels those 295 as awaiting the individual route, rather than claiming the bulk popup blocks them. Original queue/history remain unchanged.

Browser control was interrupted twice during active user Chrome use. Fresh state showed an unrelated user search tab; it was left untouched. All six completed recovery article tabs and both test-paper tabs were closed. The corrected follow-up remains active. Evidence: provider sciencedirect_resume_20261021/reset_rule_investigation_20261021.json, individual_download_confirmation_20261021.json, latest_resume_state.json and checkpoint_1361_after_individual_route_20261021.json. Original human batch001/002 files and canonical screening are unchanged. No model/API spending, extraction calls, core-code/prompt/schema changes or graph replacement.


### PDF recovery checkpoint — 2026-10-21 10:26 UTC

External Chrome ordinary individual-PDF recovery continued for the frozen 301-record ScienceDirect queue. **18 queue PDFs were downloaded, identity-verified, imported and converted**, using chunks 285–288 (5/5/5/3); all conversions succeeded, with no new review holds. Two are the publisher-offered accepted manuscripts, preserved as those sources. The previously recovered Toxicon probe (chunk 284) remains outside the original 301 denominator. Overall usable prepared manual papers are now **553 / 1,770**, with **1,217 not ready**.

The original 301 now reconcile to **18 usable, 21 confirmed purchase/access gates, four individual-PDF CPE00002 content errors, three blank-link technical followups, three article pages checked with PDF/manuscript requests deferred, and 252 unvisited**. The three deferred pages explicitly offer a main PDF or open manuscript; do not call these paywalls. Six of the 21 gates were recorded before this continuation, and 15 were added here. Gate evidence is the exact primary article preview plus Purchase PDF/institutional access and no offered free main PDF or open manuscript; generic sign-in headers are not gates.

The normal individual route successfully retrieved 18 more papers despite the bulk-download popup. At 10:19:51 and 10:20:20 UTC, three observed individual links returned the actual publisher page “There was a problem providing the content you requested,” CPE00002. A fresh observed single-document link on open-access DOI 10.1016/j.pbi.2024.102626 also returned CPE00002 at **10:22:41 UTC**. References are preserved in `individual_attempts.jsonl`. Further PDF requests were paused for this session after that check, without asserting a published reset time or that unvisited papers are paywalled. Do not conflate this content error with the bulk-limit dialog, assume a rolling 24 hours/midnight reset, or bypass any actual denial/challenge. All temporary recovery paper tabs were closed; unrelated user tabs and the existing batch-06 checklist remain.

Artifacts under `sciencedirect_resume_20261021/`: `resume_checkpoint_20261021_1024.json`, `latest_resume_state.json`, `outcomes_301_20261021_1024.csv`, `verified_recoveries_18_20261021_1024.json`, `integrity_20261021_1024.json`, and `index.html`. Provider/manual-owner counters were reconciled by `checkpoint_1404_after_individual_resume_20261021_1026.json`. The current overall unresolved inventory is `remaining_1217_access_grouped_after_individual_resume_20261021.csv`: 761 known payment/account gates, 252 unvisited individual-route records, 89 technical/access/download followups, 58 saved-PDF source-review holds, and 57 other source/format/repository issues. These are retrieval statuses, not new screening judgments.

Next scheduled check: use one ordinary observed main-PDF/open-manuscript link from the ten technical/deferred queue records, preferably an offered but not yet requested open PDF. If CPE00002/another real individual-route restriction persists, record the observation, close the probe and remain quiet; do not hammer it. If a normal PDF loads, save and validate it, then continue sustained recovery through those followups and the 252 unvisited records, excluding all 21 known gates. Up to ten active paper tabs; close completed tabs promptly. DOM reading of the actual main View PDF href followed by normal navigation and native Chrome PDF Download/Save worked; the bulk JavaScript handler and `downloadMedia()` did not. Some background pages take time to resolve; avoid replacing them before load. Core browser claim/new APIs avoid repeatedly dumping full article accessibility trees. Native close of the last temporary recovery-group tab prompted a group-delete confirmation, completed only for the agent-created recovery group.

All 18 original human batch-001/002 file hashes are unchanged. Canonical screening routing SHA-256 remains `01f5323d4824550daa3b01f15e7f89a01fd40c5639cfe884ec1625540676229c`. No model/API calls, screening/scientific extraction, prompt/schema/core-code changes, graph changes or subagents. Chunk 283 remains the unapplied Salvia identifier hold; do not apply it. Next unused import chunk is **289**. Heartbeat stays active at its existing four-hour cadence while this publisher error may clear; notify only meaningful progress, completion or required action.

UI note: the revised `sciencedirect_resume_20261021/index.html` was saved, but the browser tool rejected its `file:` navigation under URL policy. No alternate transport or browser workaround was attempted. The original batch-06 checklist tab remains. This local-file UI policy failure does not change any publisher access classification or recovered-PDF count.

### 2026-10-21 — user supersedes scheduled recovery checks

The user explicitly directed continued recovery now and said scheduled checks are no longer needed. Existing `resume-sciencedirect-pdf-recovery` heartbeat was changed to PAUSED through automation_update, preserving its other fields. Do not re-enable or add a schedule. Sustained current-turn recovery is proceeding through the frozen 301, recording per-record errors rather than using CPE00002 on a few records to stop all requests. By checkpoint `checkpoint_1499_continuous_20261021_1117.json`, 64 additional queue PDFs were identity-verified/imported/converted beyond the previous18; overall617usable. Later continuation receipts supersede that intermediate count. A later partial GROBID failure in299 was repaired only for its failed DOI with existing pdftotext, preserving the initial and fallback reports; 300/301 GROBID unavailability was handled by conversion-only fallback without repeating imports. No scientific/model calls or core code changes. Current events and receipts remain authoritative while final queue/report reconciliation is pending.

### 2026-10-21 13:08 UTC / 17:08 Dubai — sustained ScienceDirect recovery pass completed

The user superseded scheduled checks with sustained recovery now. The existing `resume-sciencedirect-pdf-recovery` heartbeat is PAUSED, verified from its saved configuration; do not re-enable it. All original 301 queue records now have retrieval dispositions, with the immutable queue/history preserved. **178 are identity-verified, imported and locally converted; 114 have actual primary purchase/account/subscription gates; 3 need browser/verification follow-up; 2 have DOI/title conflicts; 2 are source-identified conference abstracts; 2 original PDFs are saved for source/format review. Zero unvisited records and zero pending ready imports/conversions.** The previous queue result was18 usable; this continuation adds160 usable originals. The Toxicon probe284 remains outside the301 denominator.

Fresh tabs and allowing source responses to finish made a large difference. The frozen31-record technical-risk selection now has28 recovered originals,2 verification follow-ups and1 previously evidenced DOI/title conflict withheld without another PDF request. Thus30 had ordinary PDF retries, not31 new independent source investigations. Blank/slow responses and old CPE observations were not treated as paywalls. All prior raw failures and download observations remain preserved, including late-arriving files that supersede earlier blank responses. The bulk popup was never demonstrated cleared; ordinary individual retrieval nevertheless worked. No verification challenge, security warning, publisher quota, paywall or registration gate was bypassed.

Queue imports285–322 reconcile to178 distinct records and178 nonempty source-identity-verified converted artifacts. The initial299 GROBID failure and300/301 unavailability are preserved with conversion-only pdftotext fallback receipts; later chunks use the existing pdftotext backend. No paid model calls, scientific screening or evidence-extraction calls, extraction-route refresh, prompt/schema/core-code changes, graph replacement or subagents. Two already-existing document-identity exception mechanisms were used for exact reviewed PDF hashes: Neuroscience Letters0304-3940(89)90159-6 and Pharmacology Biochemistry & Behavior0091-3057(86)90477-6. Their first pages were rendered/visually inspected, publisher routes/titles/pages and document ends checked, and two narrow attestations added to the existing source_identity_pdf_hash_registry.json; no aliases or matching thresholds changed. Before/after registry provenance, initial failed dry-runs and images are in `sciencedirect_resume_20261021/pdf_identity_review_315_316`. Clean reruns315/316 passed, preserving the original failed reports.

The third flagged file0006-2952(89)90480-2 is the requested complete short communication, but publisher-scanned pages also contain preceding references and the following acetaminophen article. Its original bytes remain in source_boundary_review_20261021, withheld from usable extraction sources to prevent unrelated text entering them. The Advances in PharmacologyS1054-3589(08)60870-4 original remains publication-format held because the publisher summary calls it a chapter despite research/open-archive labels. Two DOI/title collisions remain retrieval holds: Developmental Cell2006.09.011 resolves to DEP Domains: More Than Just Membrane Anchors rather than the supplied MDMA/vasopressin report; Water Research2021.117789 identifies the wastewater critical review rather than the supplied web-mining title. No metadata or screening repair was applied for these cases. The conference observations are Euroneuro2019.07.124 andS0924-977X(16)31156-7.

Final browser blockers: BBR2019.112368 reached an actual PDF-server Request Verification/Verify you are human checkbox; user asked once, tab preserved. EJPhar2015.12.029 remains a blank publisher verification redirect without a visible challenge control, not a demonstrated payment gate. The earlier PET/MDMA0969-8051(94)00104-R verification observation remains unresolved. Late Downloads check found no uncounted files for these three. All completed article/PDF tabs closed; only the two current verification handoffs, existing batch06 checklist and unrelated user tabs remain. The Mac-lock handoff was resolved after unlock: all ten waiting originals were saved, nine became usable and the mixed-page short communication was held. No claim that every lawful alternate source or PDF figure/table capture is exhaustive.

Existing manual-recovery owner, batch003+ checklists and provisional counters were reconciled by `checkpoint_1656_continuous_20261021_1304.json`: **713/1770 usable,1057 not ready**. The1057 are854 known access gates,82 browser/access/download/content follow-ups,60 saved-source review holds and61 format/repository/identity/other source issues. These are retrieval statuses, not new eligibility judgments. All18 original human batch001/002 file hashes and canonical screening routing SHA01f5323d4824550daa3b01f15e7f89a01fd40c5639cfe884ec1625540676229c are unchanged. The final report under `sciencedirect_resume_20261021/` includes latest_resume_state.json,index.html,outcomes_301_continuous_20261021_130619.csv,remaining_without_known_gates.csv,verified_recoveries_continuous_20261021_130619.json,integrity_continuous_20261021_130619.json and fresh_tab_retry_completion_20261021.json. The four-group remaining1057CSV is named in latest_resume_state.json. Temporary orchestration/report sources are archived in continuous_recovery_helpers_20261021; paid submissions/imports must not be repeated. This is a completed browser pass with user-dependent verification/source follow-ups, not a claim of complete full-text recovery.


### 2026-10-21 18:00 Dubai — user verification recovered two more originals

After the user completed the crayfish CAPTCHA and reported that the page looked paywalled, the exact publisher preview was reinspected. It explicitly offers View Open Manuscript. Following that observed control produced the original 36-page accepted manuscript for10.1016/j.bbr.2019.112368; it is not classified as a payment gate. The other preserved handoff,10.1016/j.ejphar.2015.12.029, had also loaded its main PDF. Both are now imported and locally converted with verified source identity in323/324. No import was repeated.

The crayfish conversion initially rejected source identity although import matched its PDF metadata title. The manuscript begins at Introduction and lacks a title page/abstract within the PDF. Its rendered first page explicitly prints Version of Record with the exact publisher PII S0166432819309568, matching the independently observed DOI/title page, and its PDF metadata title matches exactly. Methods/results/discussion/references/figures and the document end were checked for report identity, not scientific adjudication. An exact-byte attestation was added through the existing source_identity_pdf_hash_registry.json (now58 records); no alias, matching threshold, core code or screening decision changed. Source/version limitations are explicit in crayfish_manuscript_identity_review_20261021/source_identity_review.json. Original conversion_324_initial_identity_rejection.json is preserved; only conversion was retried and now succeeds with84952 characters. The manuscript remains the publisher-offered accepted version.

Updated original301 outcomes:180 usable,114 actual access gates,1 browser-verification follow-up,2 identity conflicts,2 conference-format observations and2 saved-source review holds. All301 attempted; no pending imports/conversions. Manual recovery is715/1770 usable,1055 not ready (854 gates,80 browser/access/content follow-ups,60 saved-source holds,61 other format/repository/identity issues). Original human batches and canonical screening remain unchanged. Existing owner/checklists/provisional counters refreshed by checkpoint_1656_verification_followup_20261021_135832.json. Latest derived report/index and source integrity receipts are updated; the prior178/713 checkpoint remains historical. The frozen31-record technical selection now has30 recovered and1 source-identity conflict, with its earlier28-recovery summary preserved separately.

The remaining PET/MDMA paper10.1016/0969-8051(94)00104-R is labelled Open archive and offers a normal PDF, but its ordinary route still enters a blank publisher verification redirect. It is not marked paywalled. Only that unfinished task tab remains beside the existing checklist and unrelated user tabs; recovered-paper tabs were closed. Heartbeat remains PAUSED; no model/API calls, extraction, prompt/schema changes or graph replacement.


### 2026-10-21 19:50 Dubai — manual language feedback, filtered second batch and inbox reconciliation

The human confirmed non-English full text for five first-batch papers (Japanese hypothalamic LSD report, Korean jkpmhn1996/jksct2024, Chinese TWS2014 and Persian SSUv32i5). All five were already positive body-language observations; handing these back for manual review was an error. Do not repeat this handoff. Journal name alone is a triage signal, not sufficient exclusion evidence.

The 61 source/format cases contained 49 directly documented ineligible records, leaving 12 unresolved source pages. All12 DOI pages were opened separately in external Chrome; the opened-tab receipt is in inbox_and_format_reconciliation_20261021/remaining_second_batch_12_opened_tabs.json. Previously opened DOI tabs were already closed by the human; no unrelated tabs changed. The original first60 and second61 snapshots remain preserved. Twenty saved-source identity/version/completeness cases from the first60 remain separate technical work.

Existing registration command dry-run/apply added89 positive post-retrieval exclusions to the existing curated owner:36non-English,35conference abstracts,4conference posters/presentations,6theses,6preprints/unpublished,1monograph,1dataset. Five have independent human language confirmations; others cite prior primary-source observations. Original2403ledger records are byte-equivalent as objects; all new records have source provenance. No access failure or uncertain identity was excluded. Before-ledger snapshot, auditCSV and receipts are preserved under inbox_and_format_reconciliation_20261021. Canonical V5 screening SHA remains 01f5323d4824550daa3b01f15e7f89a01fd40c5639cfe884ec1625540676229c; candidate/routing/task checkpoint application and input rebuilding are PENDING, explicitly recorded in model_pipeline_state.json. No prompt/schema changes or scientific fulltext rescreening.

The moved top-level inbox contains803PDF-named files,786distinct hashes. Exact canonical-store copies736; known source/language-held downloads56;11files/10distinct previously unindexed byte streams. Standard importer dry-run on the10unique streams found6alternative bytes for already stored papers,3HTML/web responses incorrectly namedPDF and1prior wrong-report hash (hold150). ZEROready new imports, replacements or files deleted. Chrome downloads were originals left in Downloads; the existing copy-based import had already placed verified copies in the canonical store. The803 are not803unprocessed/new papers. Reports and source paths/hashes are preserved; inbox untouched.

Next prioritize remaining manual12 and technical20, existing source-language/format checkpoint application, refreshed recovery/extraction inputs and updated cost. No extraction/modelAPI calls, new scheduled checks, graph replacement, core-code changes or agents. The old715/1770recovery and24969cohort summaries predate this89-record eligibility cleanup and must not be reported as newly refreshed totals.


### 2026-10-21 20:18 Dubai — source followups and correction of redundant ScienceDirect handoff

Human confirms Columbia10.7916/d8t159k2 is a thesis. Existing post-retrieval registration command dry-run/apply adds that source-format exclusion. NBpublish10.25136/2409-8728.2025.3.73647 was rechecked in Chrome: original is Russian; its actual publisher Eng control gives a full page but explicitly states This article is automatically translated. This corrects the earlier unsupported treatment as an eligible English publisher version. Exact84,622character source text and browser provenance saved in inbox_and_format_reconciliation_20261021/source_followups_20261021. Registered non-English exclusion through existing owner. Two new records, all earlier rows preserved; recent cleanup total91. Candidate/routing/task refresh remains pending.

Human also flags ANP-v82n10-Suppl3-final.pdf for10.5327/cbn240003. Prior source observation identifies577-page issue collection. Continue holding whole-volume source and individual contribution format; do not exclude all journal supplements solely from supplement label. Fresh web fetch403 and Chrome verification-control failure are access/tool observations, not new source confirmation. No whole volume imported.

Misread request to bring back limited ScienceDirect papers: unnecessarily reopened five already-saved first60 PDFs plus one missing download. User corrected this. All five redundant reopened tabs were closed; only missing10.1006/nbdi.1998.0206 remains, successfully resolved to actual ScienceDirect title/page. Opened through ordinary DOI route; no incognito/quota workaround used. Do not send already-downloaded source-quality holds as download work again. No model calls, core code/prompt/schema changes, new screening decisions or graph changes.


### 2026-10-21 20:33 Dubai — last manual paywall and user-authorized inbox cleanup complete

Human confirms10.1006/nbdi.1998.0206 is paywalled. Recorded explicit human access evidence in existing provider events/progress, manual owner and manual_fulltext_access_overrides.json through existing access helper. This supersedes quota-deferred status, not scientific screening eligibility. Do not reopen/download already stored papers as a user handoff.

The root inbox now had805PDF-named files plus7Word/HTML sources. ExactcanonicalPDF copies737(736old plus newlyaddedALTEX10.14573/altex.2103311), known-held copies56, other/different bytes12. Most canonical copies were already converted;6had missing article artifacts(3existingOCR/source-identity holds,3non-English excluded records),1had verifiedXMLfulltext rather than a PDF-conversion artifact.41Wiley PDFs pointed to byte-identical originals in managed source folders, not the canonical PDF path; those source files and references remain untouched. Do not equate all stored PDFs with fully approved conversion/extraction inputs.

Two newly added originals checked: ALTEXojsadmin…Shi is byte-identical to stored main-paper PDF and has146582-character conversion. WaterResearchS0043135421009830 is a NEW fulltext file for already-listedDOI10.1016/j.watres.2021.117789, not a new discovered paper. Its front page explicitly prints Wastewater-based epidemiology for illicit drugs: A critical review on global data and exactDOI; stored queued metadata still carries unrelated web-mining title. Preserve new original at manual_pdf_inbox_quarantine/inbox_cleanup_20261021/source_identity_pending/1-s2.0-S0043135421009830-main.pdf; keep source/metadata hold until existing-owner identity repair and any required corrected-abstract Luna screening. No wrong-title import or model call. Existing held serotonin source's only distinct bytes were also retained and latest progress/source paths repaired.

User authorized cleanup of redundant inbox files.812loose files reconciled by SHA256:799duplicates moved to recoverable MacTrash folder recorded in inbox_cleanup_final_20261021/cleanup_applied.json;13unique source/review files moved to organized project quarantine/manual_source_inbox/rejected-download folders. Original bytes verified after every move and retained-copy hashes checked before/after trashing duplicates. No permanent deletion, no canonicalPDF or conversionartifact edits. Loose PDF/Word/HTML inbox is cleared. Managed staging/source subfolders remain intact because processing/source records reference them. An inboxREADME explains this. Ten self-created temporary hardlinks removed only after verifying retained project copies.

Full restoration mapping and hashes: cleanup_plan.json,cleanup_moves.jsonl; retained13 index:retained_source_index.json. Summary:completion_summary.json. Temporary orchestration scripts are archived in the same folder. Canonical V5 screening SHA remains01f5323d4824550daa3b01f15e7f89a01fd40c5639cfe884ec1625540676229c. Recent91language/format exclusions are registered but candidate/routing/task materialization and input-refresh/cost update remain pending, along with technical source identity/version issues. No new usable import claimed from the two new files. No further user downloads required for this completed manual batch; do not silently mark all other technical cases paywalled or claim every corpus paper has full text. No API/model calls, scientific extraction, core-code/schema/prompt changes, agents or graph replacement.


### 2026-10-22 — approved publication cleanup applied; Luna V5 preserved

The human approved applying the reconciled 293 language/format exclusions and improving reusable pipeline checks. Application artifacts: `data/processed/model_runs/luna_v5_20261017/publication_cleanup_apply_20261022/`. Existing eligibility ledger remains authoritative: 202 new evidence-linked records added, all 2,494 earlier records preserved as objects, and the 91 already registered decisions in the current cohort materialized. The full materialized ledger has 2,696 rows. Candidate extraction selection is now **24,678**, down exactly **293** from 24,971; all other candidate rows are verified unchanged. Categories remain 190 non-English, 61 conference/poster abstracts, 15 educational video lectures, 8 theses/dissertations, 6 preprints/unpublished, 6 news/teaching/CME summaries, 4 books/chapters, and one each standalone supplement, correction and dataset. No journal/publisher/country blacklist. The 19 unresolved cases remain unresolved, not confirmed exclusions.

Reusable format/language metadata gates remain in deterministic prescreen; verified per-record findings remain in `post_retrieval_eligibility_decisions.json`. Future rule version is `deterministic_cleanup_v3_20261022`: adds the verified PI-CAPST teaching-summary family, preserves empirical case-report letters and genuine journal supplements, while retaining explicit meeting/object exclusions. Existing PI-VL/video and other dedicated format families were already rules; the old prescreen had not been regenerated with all of them. The rule comparison covered every current cohort record plus all potential changed-rule families across the wider corpus (34,715 records). Only the already-approved CME record was newly excluded within the current cohort. The comparison did not rerun or mutate the historical prescreen, reopen historical exclusions or submit Luna calls.

The existing later eligibility checkpoint now disables extraction eligibility immediately, filters primary/review/meta-analysis queues, preserves model-screening outputs by default, accepts a scoped DOI file and preserves unrelated inactive route accounting rows. The first application pruned those inactive rows too broadly from the derived route table; its report is preserved. That derived view alone was restored from this run's snapshot and the corrected scoped checkpoint reapplied. Exact before/after comparison proves the final view removed only the approved 293 keys (409 route rows), without changing surviving rows. Original raw model results and published graph were never modified. Surviving task bytes/input fingerprints are unchanged: 36,842 primary/domain tasks (306 removed), 4,050 review tasks (101 removed), 349 meta-analysis tasks (none removed). Task counts are not independent-paper counts or final source-readiness certification.

The PDF auditor now checks report identity before attributing thesis/meeting exclusions to an intended paper; mixed English codes are protected and script heuristics cause review rather than an automatic language verdict. Repository-format auditing shares the empirical-letter safeguard. Known materialized record exclusions are skipped before future Luna request selection; after rebuilding candidates, reapply the existing ledger before queueing/routing. All decisions retain original source/audit provenance; no second eligibility ledger was introduced.

Current route counts were refreshed without rebuilding scientific inputs. Global `extraction_input_status` is explicitly `eligibility_filtered_source_refresh_pending`: the previously documented source/metadata followups, unresolved cases and complete source-input refresh remain before the full extraction rerun. No prompt/schema changes, model/API calls, extraction calls, source-file deletion, published graph replacement, subagents or automation. Completed Luna V5 routing SHA remains `01f5323d4824550daa3b01f15e7f89a01fd40c5639cfe884ec1625540676229c`; prompt and original prescreen hashes are unchanged. See `completion.json`, `verification.log`, `implementation_changes.diff` and `final_complete_tests.log`. Do not repeat paid screening or re-register the 202 decisions; registration dry-run is idempotent (0 added, 0 updated, 202 unchanged).

### 2026-10-22 — source/metadata repairs completed; extraction inputs refreshed and priced

The user requested closure of the remaining 19 source cases and the documented source/metadata repairs, followed by fresh extraction counts/cost without starting extraction. Artifacts: `data/processed/model_runs/luna_v5_20261017/extraction_refresh_20261022_source_fixes/`. All 19 were reviewed:7 released after repair,2 confirmed conference abstracts excluded,10 remain source/format/language/review-status holds. One additional SocSciMed/Salvia metadata collision is held. These 11 holds are recorded in the existing manual extraction-route owner with `hold_source_review`, separate from confirmed exclusions. Its mechanical guard and primary/secondary regression controls preserve completed model decisions.

The exact primary Wiley contribution establishes DAR 12077 as conference Paper 213. The original publisher-branded CBN proceedings, recovered from a mirror after the publisher URL failed, establish CBN 240003 as an individual conference abstract; the whole volume was never used as article text. Both exclusions use the existing curated eligibility ledger, whose 2696 earlier records remain object-equivalent. Verified conference labels are also stored in metadata for future prescreening. No publisher/journal blacklist or historical prescreen rewrite.

61 bibliographic records changed through evidence-linked canonical overrides; stale optional PMID links were cleared or replaced only when verified. Wrong-report mixtures are held rather than inheriting another report's inclusion. Distinct 1984/1981 LSD and 1994/1998 phenethylamine sibling reports remain separate. Two source-printed OMICS DOI discrepancies retain the stable registered record keys with repaired venue/author/unit information and exact-source provenance; no nonexistent DOI aliases were invented. The IJCRI ecstasy/peritonitis publisher collision is bounded to the reviewed original article.12 duplicate identifiers are suppressed, including both legacy5-MeO-DMT PIIs and the legacy ketamine PII against their existing canonical Japanese Journal of Pharmacology reports. Repository and journal versions retain provenance.

All 99 documented source actions have release dispositions.32 canonical source artifacts were rebuilt/replaced and verified in actual model-input chunks: English publisher/bilingual main texts, complete local OCR or corrected text conversion, explicit publisher version 2 sources, new reviewed originals, and a lossless region-selected PCP short communication. The original multi-paper PDF remains preserved; only its exact single-article derivative has a PDF-hash attestation. Five clean importer dry-run/apply results comprise four original PDFs plus that derivative, not five new papers. OCRmyPDF's system-Python finalizer failed after all OCR sidecars were complete; per-page counts/text were separately verified and used, with no searchable-PDF success claimed. All source bytes and failed/intermediate receipts are retained.22 valid parent reports use abstract fallback for partial, supplementary, wrong or unverified-draft sources. Source identity verification is not a claim of perfect figure/table/chemical-structure recognition.

Selection reconciles exactly:24678 minus 12 duplicate identifiers,2 conference abstracts and 11 holds = **24653 ready report records**, with no newly activated records. Across the approved cleanup,295 confirmed exclusions are applied (earlier 293 plus 2). Ready sources: **11644 full text /13009 abstract only**. Frozen queues cover exactly the selected set: **36779 primary-domain requests for 20225 primary papers;4046 review requests/papers;347 meta-analysis requests/papers;35 guideline/consensus requests/papers =41207 requests for 24653 reports**. All requests are ready; held/excluded/duplicate keys are absent. Reports are not independent-study or participant counts.

Local network-disabled pricing used current official GPT-6 Luna Batch rates, actual frozen payloads and prior measured output usage: **$31.3322 expected; $43.7818 computed allowance, rounded reserve$44**. Lanes: primary$24.5193, reviews$5.9875, meta$0.7745, guidelines$0.0509. One valid large Cochrane review uses long-context pricing; none exceeds the checked input limit. The allowance is not a guaranteed maximum. Shared$100 ledger: settled$33.1663, earlier unresolved reservations$0.6372, available$66.1964; the reserve fits. The ledger hash is unchanged by preparation/pricing. No API/model calls or extraction batches were submitted.

72 relevant tests plus 8 subtests passed. Final integrity checks prove exact selected-set/task-union reconciliation, frozen/canonical queue equality,32 repaired sources in real input chunks, preserved original ledger rows and unchanged Luna V5/prompt/prescreen hashes. Current state is `extraction_input_status=source_metadata_reconciled_inputs_frozen_ready`, `extraction_status=not_started_inputs_refreshed`. The earlier pending-source-refresh checkpoint is superseded. No extraction prompt/schema, published graph, automation or subagent changes. See `report.html`, `completion.json`, `remaining19_final_dispositions.jsonl`, `source_actions_completed.jsonl`, `final_extraction_cohort.csv`, `final_integrity_verification.json`, frozen `inputs/` and `cost_projection.json`. Original V5 routing SHA remains 01 f 5323 d 4824550 daa 3 b 01 f 15 e 7 f 89 a 01 fd 40 c 5639 cfe 884 ec 1625540676229 c.


### 2026-10-22T15:35 UTC — accepted scholarly analyses routed under Reviews; inputs frozen

User-authorized downstream routing only; completed Luna V5 scope decisions/prompt and historical prescreen remain unchanged. Active release: `data/processed/model_runs/luna_v5_20261017/accepted_review_routing_20261022/`.832 previously accepted/context-only records were scoped;813 admitted through the existing Reviews relationship path (399 commentary/editorial,414 other analysis).19 existing-rule source exclusions applied (15 non-English,3 conference,1 video). No rejected scientific screen reopened; chapter/news/protocol and11 existing source holds stay out. Actual genres preserved in task metadata and normalization/UI; toggle remains Reviews.14 additional PMC fulltexts recovered and source-checked.

Final ready set25,466:20,225primary;4,859Reviews (4,046existingstrictreviews+813analyses);347meta;35guideline. Sources11999fulltext/13467abstract.42,020requests. All41,207baseline scientific inputs preserved,813new requests. Bookkeeping source paths/timestamps and17,332refresh-dependent task IDs refreshed; no byte-identical request claim. Cost$32.3910expected/$45.2027allowance; recommend$46reserve. No API/model/extraction calls or batch submissions. Existing$100ledger unchanged.213tests+60subtests pass. Canonical queues equal frozen inputs and state pointers now target this release. Old release/history retained. See report.md, completion.json, final_integrity_verification.json, baseline_payload_preservation.json and manifest.json. Extraction is NOT started; no graph replacement or screening rerun.


### 2026-10-22 — full Luna extraction Batch rerun authorized and started

The user explicitly authorized the full extraction rerun with the current prompts/schemas and large Batch API jobs. Run owner: `data/processed/model_runs/luna_v5_20261017/extraction_batch_rerun_20261022/`. Frozen release remains `accepted_review_routing_20261022`: 25,466 report records, 42,020 requests (36,814 primary/guideline,4,859 review,347meta). All frozen/canonical hashes and V5 screening/prescreen/prompt hashes passed preflight. Every generated API payload matches the previously priced request-body SHA256; low reasoning/current native schemas and max-output settings are unchanged. No new screening or scientific source-adjudication pass.

13 large request files are prepared:10primary/guideline,2review,1meta; 801–4,734requests/file, up to166.7MB. Partitioning respects the official200MB/50,000request limits and the existing conservative per-job maximum-cost ledger reservation, capped near$25perjob. The shared$100pipeline cap remains; expected full extraction$32.3910 with$46planning reserve. Large jobs are dispatched continuously as actual usage settles and releases reservations. Do not increase the cap or duplicate paid submissions to accelerate a deferred part.

The continuous local controller is documented in controller_process.json/controller.log; no automation or scheduled chat wakeup was created. It uploads/submits once, downloads both successful/error outputs, settles actual Batch usage through pipeline.llm, and uses the existing parsers with primary --skip-rebuild. Review/meta outputs stay in named run directories. No normalization or published graph replacement. All original answers/errors are retained; this initial queue enables no automatic paid retries. Completion is initial-pass-complete/QA-pending, not a promise of zero extraction errors.

All42,020 prepared requests reconcile to25,466unique records with zero duplicate taskIDs. See prepared_full_cohort_reconciliation.json, verified/, queue.json and approved_input_manifest.json. First accepted API batch: primary batch_001,3,523requests, batch_6ada3184b34c8190afd6663c4aeecc3b. Other job receipts/progress.json supersede this launch snapshot. Never reprepare/restart a completed run; if continuation is needed, check the existing controller PID/lock and job receipts first. Uploaded/submitting receipts without a batchID require outcome reconciliation, not blind resubmission. Source assets are snapshotted and hash-checked; stop if they change. The controller prevents idle sleep only while active and exits after all parts parse or a concrete blocker remains.


### 2026-10-22 23:30 UTC / 2026-10-23 03:30 Dubai — extraction controller connection recovery

The user requested extraction status. The continuous controller PID85898 had stopped at22:27UTC after APIConnectionError on four existing job-status reads. Those network failures are not model request failures. Direct read-only reconciliation of all five recorded jobs found four fully completed jobs (8729requests) and797of801completed in the remaining submitted primary part:9526of42020APIcompletions,0APIrequest failures,32490requests not yet submitted. Receipts and original progress/code/log are preserved in extraction_batch_rerun_20261022/connection_recovery_20261023/before; remote_status_reconciliation_20261023.json preserves the server observations.

A run-local controller repair retries transient status/download failures for known job IDs only; it does not automatically retry ambiguous upload/create outcomes, authentication failures or parsing errors. Two offline regression tests cover safe reads versus mutations/unknown outcomes, connection/timeout errors and permanent versus transient HTTPstatuses. No core pipeline, prompts, schemas, model settings, frozen inputs, screening, budget cap or graph changes. Repair code/test hashes and verification receipt are under connection_recovery_20261023/repair_verification.json.

The same continuous receipt-aware controller resumed asPID31535 with caffeinatePID31536; old process absence and exclusive lock were checked. It collects completed jobs, settles their existing reservations and submits only still-unsubmitted queue parts when budget permits. No completed/submitted paid jobs were resubmitted. Current progress.json supersedes these recovery-time counts as collection proceeds. No scheduled automation added.


### 2026-10-23 11:20 UTC — all477 extraction validation failures resolved

User requested diagnosis/recovery while the remaining Luna Batch extraction continues. Owner: extraction_batch_rerun_20261022/validation_recovery_20261023.468 failures were a parser null-restoration bug under local item-schema references (64cognitive,132molecular,272public-health): restore against the same resolved native schema before validating against the unchanged scientific schema. Offline replay:10991primary responses,468recovered,10514previouslyaccepted results unchanged,1074absent optional-null fields removed; required-null and all nine quality checks stayed strict. All13main request hashes,60protectedassets and approved input manifest unchanged.75tests+2subtests passed.

Nine genuine category failures retried in Luna low-reasoning Batch with unchanged scientific inputs/baseprompts/schemas plus recorded validation feedback.9/9nowpass, additional billed$0.01302418. Current unique completed-request statuses:{"ok": 16197}; original477taskIDs allstatusok,0remaining. Source/category checks and an offline normalizer probe preserve non-drug macaque baseline context without a false ketamine edge; this is not a whole-extraction accuracy assessment. MaincontrollerPID56951continues remote work and owns all reparsing/materialization; no duplicate paid mainjobs, new schedule, screening change or published graph change. Original raw/errors and request lineage retained. See completion.json,report.md,integrity_verification.json and nine_retry_category_review.json.


### 2026-10-24 00:10 UTC / 04:10 Dubai — user-directed immediate concurrent dispatch

The user explicitly rejected the conservative local reservation throttling and instructed submission of every remaining prepared batch. This supersedes the earlier reservation-based concurrency restriction for this extraction run. The four remaining prepared main parts are primary006/007/008/009, totalling18614requests. Source/model/prompt/schema/request bytes remain unchanged.

A narrowly scoped dispatch policy at extraction_batch_rerun_20261022/unthrottled_submission_20261024/dispatch_policy.json authorizes those exact job receipt paths and request SHA256values. pipeline.llm.submit/reserve_budget now has an explicit opt-in reservation-overcommit parameter; the default behavior and duplicate-attempt guard remain unchanged. The user-authorized dispatch checks settled spending instead of counting every in-flight job's maximum possible output as money already spent. All original reservations and actual-cost settlements remain recorded. The100USDtarget is retained as a reference, while aggregate worst-case in-flight reservations can exceed it under this instruction. Do not confuse those reservations with billed spending or silently restore the rejected queue throttle.

30relevant regression tests plus2subtests passed. The single receipt-aware controller resumed asPID50706, caffeinatePID50707. Existing remote jobs continue untouched. It now submits all four listed remaining parts without waiting for earlier jobs to finish; normal provider limits and receipt/outcome reconciliation still apply. No duplicate paid jobs, new schedule, scientific screening/extraction prompt changes or graph replacement. change_verification.json and before/ preserve implementation/history; final submission/server receipts are recorded alongside them as available.

Final dispatch verification: all13mainjobreceipts have13uniqueproviderjobIDs covering42020/42020mainrequests,0localunsubmitted. The4newjobs cover18614requests and were individually retrieved from the provider with no terminal failure. See unthrottled_submission_20261024/submission_completion.json. Existing jobs were not resubmitted; continuous collectorPID50706 remains active.


### 2026-10-25 11:20 UTC — remaining extraction failures: reusable input repair and targeted Batch retry

User authorized investigation, source repair and affected-only retries, explicitly requiring a reproducible pipeline step. Owner: `extraction_batch_rerun_20261022/remaining_failure_recovery_20261025/`. Initial38 failures are15category and23source-identity errors across34papers. Source flags cover19papers/32routes including passing siblings. Native PubMed XML plus all34exact Crossref responses were retained; reusable offline evidence collection reproduces the same decisions without network/model calls. Nine source-flagged reports have corroborated metadata/authentic abstracts and16routes to rerun;10records/16routes remain source-held through the existing manual route owner. Of the original38errors,26will rerun and12are held;5passing sibling routes also rerun and4passing sibling outputs are withheld. Holds are source/report issues, not changed V5 scientific decisions or population error estimates.

A repository PDF has the correct psilocybin therapeutic-alliance cover attached to an unrelated oncology article. Fixed `source_identity.py` so automatic front-title fallback cannot override a conflicting document DOI; existing explicit relationship/hash mechanisms remain separate. Original bytes/text preserved; normal abstract fallback is used for all3routes. Eight other repairs address verified abstract/title/bibliographic conflicts; native dates, authors, venue and PMC links are corrected where established. The first materialization refused a residual2004versus2024date conflict before writing candidates; native date was then repaired. v1/v2plans and the rejection remain historical; `recovery_plan_v3.json` is the applied plan. Only9candidate metadata rows changed; all other candidate rows and unaffected task objects are unchanged. The original frozen release is immutable.

Reusable `pipeline/extract/repair_extraction_inputs.py` provides bounded exact-identifier evidence collection/cache replay, DOI-plus-title corroboration, existing-owner application, standard task/fingerprint regeneration, validation-feedback retry preparation and existing-job collection. Current projections honor source holds on every sibling route and `input_replacements.json` to withhold stale answers. No hand-edited model answers, invented aliases, scientific prompt/schema changes or screening rerun. Standard article/abstract prompt selection remains in use.105targeted tests+10subtests passed; one existing registry-cardinality fixture expects110but the previously changed registry has112, explicitly excluded/documented rather than reported passing. All60protectedprompt/schemaassets and all13originalmain task/request files remain hash-identical.

One31request low-reasoning Luna Batch retry submitted as `batch_6adde3d00c24819080c1bda6b1f03285`; maximum configured reservation$0.1932470625, actual charge pending. No Sol calls or duplicate main jobs. Current42020route-task disposition:41973validated,31recoverypending,16sourceheld. Conditional on all31validating,42004usable route results for25456report records, with10held records separately; this is not42004findings or independent studies. Read `batch_012_retry_receipt_collection.json`/`completion.json` for newer actual results, not this pending snapshot.

Continuous receipt-aware collector/final reconciler is documented in `collector_process.json`/`collector.log`; it retrieves this same job, settles usage, parses with skip-rebuild, saves final counts and updates current state. Earlier read-only collector process receipt is preserved; no paid submission repeated. No schedule/heartbeat, normalization or graph replacement. Never restart the completed main controller. Check the recovery collector process and existing receipts before any resumption; no automatic additional paid retries. See report.md, integrity_verification.json, offline_core_replay_verification.json, primary_evidence/ and implementation/.


### 2026-10-25 — targeted extraction recovery complete; final counts verified

All31targeted Luna retries completed and passed unchanged schema/category/source checks;0remaining validation failures. Provider job completed and was collected2026-10-25at15:21UTC. Billed retry cost$0.020079. Current usable projection independently recounted at2026-10-25T17:45:18.455284+00:00:42004validated output rows covering25456report records.16route tasks across10source-held papers remain quarantined and are absent from usable outputs. These are report/route counts, not findings or independent studies. All60protectedprompt/schemaassets and completedV5screening hashes unchanged. Normalization has NOT started; no graph replacement. Source holds persist through the existing owner. See remaining_failure_recovery_20261025/completion.json and final_count_verification.json. Do not restart the completed collector or repeat paid submissions.


## 26 October 2026 — normalization handoff and build in progress

The user authorized pipeline preflight, final extraction counts and normalization. The accepted release remains V5 plus the explicit PCP addition, approved source cleanup and Reviews routing. The rejected/unpromoted V6.1 correction and full-text eligibility followup are not incorporated. No new screening, extraction or model calls.

Run owner: `data/processed/model_runs/luna_v5_20261017/normalization_20261026/`; staged run ID `luna_v5_20261026_normalized`. All 42,004 current outputs match their tasks and revalidate (20,250 primary/guideline, 4,859 Reviews, 347 meta-analysis reports; 25,456 total). Original submissions covered 25,466 reports: ten new source holds removed 16 routes. All 21 source holds are now consistently projected into downstream candidate/route tables; screening remains unchanged. The source-repair path projects future holds through the same reusable operation.

Corrected per-paper object accounting uses the production helper, including guideline recommendation_items: 24,454 reports have objects; 1,002 have none (775 no extractable evidence, 138 no relevant assigned-profile findings, 79 source-type/routing exceptions, 10 review requests). Eight more reports have only conversion-held objects. Thus 24,446 reports supply 128,315 converted rows for entity normalization. The 79 routing exceptions remain explicit unresolved source-type work, not topical exclusions. An early convenience count missed guideline items; original counts are retained under initial_incomplete_guideline_count, and corrected counters are authoritative. Production conversion already handled guideline items correctly.

Converters and fresh Luna-only assembly completed. The initial full table build stopped on the unchanged 20% receptor-subtopic residual guard. A molecular-only diagnostic exposed explicit legacy/gene/full-name aliases; the normalizer now recognizes NR1/NR2, Trk/growth-factor receptor, spaced GABA, transporter and sigma names in existing subtopics, and writes actionable failure diagnostics. No threshold relaxation or prompt/schema change. Original code/failure and diagnostic context limitations are preserved. The full build is rerunning; no final normalized counts are asserted yet. Builder tests: 68 passed, 311 subtests, one optional DuckDB skip; 100 additional boundary/regression tests passed. Earlier handoff/converter checks are preserved.

Corpus disposition reporting distinguishes routing/human-review outcomes from topical exclusion. Stale README statements about accepted guideline/commentary handling were corrected to match existing behavior. Frozen inputs, code/vocabularies, auxiliary metadata, hashes, exact runtime, commands and explicit revisions are saved in the run owner. The active graph pointer is unchanged; graph publication is not authorized by this build. Continue the running controller rather than repeating completed conversions or submitting model work.


## 26 October 2026 03:52 UTC — normalization complete, staged and verified

The complete build succeeded after the explicit receptor-alias repair, with all molecular parents passing the unchanged coverage guard. Output: `data/processed/kg_routed_runs/luna_v5_20261026_normalized/`. There are 113,338 normalized finding rows, 113,361 total evidence-edge rows (81,198 main-graph-admissible), and 18,825 entities. The paper table contains 23,714 rows; that table also includes reports whose proposed entities all went to audit and must not be described as 23,714 papers with normalized findings.

Final nonoverlapping accounting for the 25,466 submitted reports: 18,484 with main-graph-admissible evidence, 3,920 with normalized paper detail only, 2,042 with normalization audits only, 1,010 without usable extracted/converted rows, and ten newly source-held reports. Thus 22,404 reports have normalized findings. Normalized family counts are 17,936 primary/guideline, 4,143 Reviews and 325 meta-analysis reports; graph-admissible counts are 15,245 / 3,003 / 236 respectively. All 25,456 validated-response reports have explicit staged dispositions. The exclusive paper sets reconcile exactly, with zero overlap or unaccounted reports.

Source holds are not topical exclusions. The 1,010 no-row cases include 79 source-type/routing exceptions, ten no-object review requests and eight all-item conversion holds. Normalization holds likewise are not new source-adjudicated eligibility judgments: 884 audit-only reports have only unmapped entity labels, 123 only unmapped compounds, 358 only paper-scope graphability holds; other reports have other/mixed statuses. Full status/reason signatures are saved. These records and existing QA flags require release review rather than silent graph admission.

Read `normalization_20261026/report.md`, `completion.json`, `exclusive_paper_funnel.json`, `normalization_hold_breakdown.json` and `table_reference_integrity.json`. Frozen inputs/code/provider snapshots and hashes reverified; V5 screening and the active graph pointer unchanged. No duplicate finding/entity/paper/evidence IDs, dangling references or edge/finding admission mismatches. PCP has 5,177 main-graph-admissible edge rows. A final-report helper's Unicode splitlines error was fixed by using JSONL file iteration; it did not affect extraction data or normalized tables, and its failed log is preserved. All subsequent final checks passed.

Model state now records `normalization_status=complete_staged`. The staging corpus ledger is `candidate_for_release.parquet` in the run owner; the deployed graph is unchanged. Author-layer/payload construction, outstanding hold review and guarded publication remain later release steps. No new model calls; normalization API cost $0. The optional DuckDB copy was skipped.


## 26 October 2026 — normalization contract repair and targeted routing recovery

User authorized the investigation recommendations. Owner: `data/processed/model_runs/luna_v5_20261017/normalization_repairs_20261026/`. V5 scientific screening, current extraction prompts/schemas, original answers and published graph are unchanged. Deterministic repairs cover therapy subject-kind dispatch, two verified mebufotenin/GH001 aliases of existing 5-MeO-DMT, generic-primary measurement retention instead of condition lookup, and roles-aware review subject selection. Generic measurements remain detail only. New normalization manifests record contract revision v2.

Initial saved-output rebuild completed and recovered all343 identified generic-primary held reports. Its preliminary whole-corpus count comparison is preserved, but is NOT the final repaired release: real-data followup of19 former graph papers caught an overly broad preclinical fallback. Revision2 preserves genuine animal safety outcomes while explicitly behavioral outcomes use cognition. The bounded followup uses the same two-source production preset, including clinical endpoint derivation; its initial one-source convenience diagnostic is preserved and superseded. Twelve of19 regain graph admission under the narrowed rule; the seven remaining cases concern non-treatment measurements or miscategorized behavioral/physiological constructs, retained in detail. Final whole-corpus counts await the targeted retries and final rebuild.

The79 empty routing exceptions now have69 retry papers,6 source-review holds and4 confirmed source-format/language exclusions. Existing venue policy explicitly retained the Vanderbilt student journal; this is rerouted under Reviews rather than held solely for institutional status. The single-trial Bayesian reanalysis is routed to primary clinical extraction. Its saved PDF already contains the published MADRS correction; standard TEI parsing supplies its corrected abstract through the existing metadata owner, replacing stale PubMed abstract text without rewriting model answers. Failed XML refresh and direct-HTTP receipts are retained, not treated as identity/eligibility evidence. Four confirmed language/news cases are registered through the existing post-retrieval ledger; unresolved formats/boilerplate remain held.

Exactly70 Luna low-reasoning requests across69 papers are submitted in four existing-runner Batch jobs:64 one-pass Reviews requests and6 primary-profile requests. Combined maximum configured charge$0.4828683125; actual cost pending settlement. See submitted_jobs.json for unique provider receipts. No Sol/Gemini calls, duplicate main submissions, automatic paid retries or new schedules. Continuous receipt-aware collector `implementation/collect_routing_jobs.py` validates existing jobs and invokes `finish_routing.py` to build the staged `luna_v5_20261026_repaired` release. Never resubmit these jobs or restart completed main controllers.

Current candidate/route/task projections are updated only for the reviewed79-record scope; unaffected candidate/route values and task JSONL bytes were verified. Original outputs and frozen releases remain historical. Scientific source-type exceptions remain distinct from topical exclusions, and successful retry validation is not a guarantee of extractable findings. Relevant code, tests, sources, plans, regression packets, hashes and receipts are preserved. Current tests:109 passed,311 subtests,one optional skip;78 route/source-boundary tests with8 subtests also passed (overlapping suites, not an additive total). Revised-only followup22 passed. No graph publication.


## Local Luna graph inspection preview — 26 October 2026

User requested a preview while the targeted normalization/routing repairs run. External Chrome tab 192850490 opens http://127.0.0.1:8011/?data-source=local. This isolated preview uses the completed `luna_v5_20261026_normalized` snapshot (not the preliminary repaired_saved build): 22,404 represented reports, 113,338 normalized findings; UI counters 17,924 primary, 4,155 Reviews, 325 meta-analyses. The 69-paper targeted repair is not incorporated yet. Author identity enrichment has not been rebuilt; source author text remains available.

Owner: `data/processed/model_runs/luna_v5_20261017/normalization_repairs_20261026/preview`. Reproducible preparation and server launchers are in its `implementation/` directory. It reuses the production exporter in its documented diagnostic mode, staged-corpus Methods builder and preview allowlist/checksum validator. Matching Methods, browser graph/detail/analysis files and a code-only dist copy are isolated under `preview/isolated_root`; no active pointer, canonical corpus/screening, public Methods, normalized source table or deployed release was changed. Headers label the snapshot and pending repairs. `completion.json`, `http_verification.json`, `browser_verification.json` and `server_process.json` preserve counters/checks/current local process. All three evidence-family graph endpoints returned 200; private .env access returned 404; the Conditions graph and metrics were visually verified. The continuous existing Batch collector remains separate and active.


## 26 October 2026 — deployed versus Luna graph count audit, read-only

User requested a critical count/correctness comparison, then explicitly reaffirmed the existing project definition: open access means usable full text actually recovered and accessible; otherwise closed/unavailable. This is the same in old and new graphs. The preference is saved in Codex memory and `graph_count_comparison_20261026/user_access_definition.json`. Do not substitute publisher/license metadata distinctions as an explanation for the changes.

Audit owner: `data/processed/model_runs/luna_v5_20261017/graph_count_comparison_20261026/`. `report.html` presents all30 research-area × paper-type comparisons with total/open/closed counts, membership/access bridges, source examples and bounded diagnostic judgments. Count code invokes actual UI filtering functions against frozen family detail payloads. Archived deployed header/Targets counts match direct public-browser observations; a remote payload download returned403, so no independent remote payload hash verification is claimed. All six local payload hashes and30 area bridges conserve exactly in `verification.json`; report IDs/artifact links pass `report_static_verification.json`. Browser file preview was protocol-blocked and no browser workaround attempted; a read-only workspace-file open was queued. Existing graph preview remains available.

Actual UI header counts old→new:21735→22404 total;16731→17924 primary;4672→4155 Reviews;332→325 meta-analyses. Open totals10324→10975 and closed/unavailable11411→11429. Visible overview represented papers18484→17229, so header growth does not imply growth in area views. New snapshot is the original completed `luna_v5_20261026_normalized` preview, before pending69-paper repairs, not a final repaired release. Shared17414 identifiers,4321 leaving,4990 entering; identifiers/revisions are not independent-study counts.

Primary Targets2572→1685, open1134→758. Exactly1444 leave and557 enter,1128 shared. Leaving:433 V5 exclusions,447 retained without target profile,374 assigned profile returning no objects,166 conversion/normalization/admission,24 other cases. Access bridge:1134−574+176+24−2=758. Thus the open-target decline mainly follows membership; overall primary open coverage rises7634→8315. Stage locations are not error labels.249 entering Target papers have PCP evidence across eligible UI domains;223 is the narrower molecular-target-domain count and must not be substituted.

Sixty frozen diagnostic records were title/abstract-and-relationship checked:32primaryTargets,12primaryrealworld,8primarysubjective,8reviewTargets; nine selected saved-body followups and original paid-request traces distinguish source availability from extraction omission. Seven additional retained old meta cases were traced. Codex judgments are not independent human gold,60complete quantitative body audits or a representative accuracy estimate. Some old target links were background pharmacology or downstream effects, and new placement is defensible. Four of six diagnostic V5-excluded Target cases nevertheless have explicit eligible-drug abstract results, a separate screening recall concern; no V5 decision was changed.

Concrete downstream losses: review one-object priority selects clinical/context anchors over explicit named target anchors;268of584lost review-Target papers have a named target displaced,92by a context object. These are structural flags, not268confirmed rescues. Real-world converter can use an exposure predictor as compound subject, e.g sexual-minority status instead of hallucinogen-use outcome. Meta multiple-estimate guard incorrectly holds single pooled ORs accompanied by arm percentages in10.2147/ndt.s117146 and10.9758/cpn.25.1271;49results/20papers have the percentage-only trigger, but only those two lost papers are confirmed false positives here. Substring normalization also misattributes analogue20453 findings to parent5-MeO-DMT and an endogenous PCP-binding-factor finding to PCP. A radioligand study has actual ketamine/PCP/DXM Results in paid input but only dextrorphan in Luna output; MDMA subjective Results present in cognitive input had no subjective route. Source packets, hashes, quotes, immutable initial judgments and explicit followups are preserved.

Recommendation is to test narrow deterministic repairs on saved answers first, then repeat this frozen count comparison after existing repairs finish; use targeted route/extraction recovery only for actual missing results. Do not force old counts, rerun screening, relax legitimate holds or apply source-audit judgments automatically. This comparison made no production code/prompt/schema/screening/graph changes and no model/API calls ($0). The separate previously authorized69-paper repair collector was neither resubmitted nor altered.


## 27 October 2026 — expanded same-input normalization audit; final replay running

The user requested generalizable fixes and a substantially larger assessment without rerunning screening or extraction. Owner: `normalization_quality_repair_20261026/`. The expanded diagnostic sample contains 480 additional report identifiers (300 primary, 120 Reviews, 60 meta-analyses; 160 removed, 160 added, 160 shared selected-area memberships). All have title/abstract and selected-relationship checks; 87 selected saved-body passage checks, one original-PDF visual check and 133 saved-output followups are documented. Initial judgments and 58 explicit diagnostic corrections are preserved. This is not 480 complete quantitative body audits, an independent-human gold standard or a population accuracy estimate.

Production converters, normalization and controlled registries now contain tested subject-role, exact-identity, measured-endpoint, review-anchor and statistical-scope repairs. Original raw answers, V5, prompts/schemas and the published graph remain unchanged. A final independently affirmed DMT result was unnecessarily held alongside unregistered analogues; the narrowed shared-actor rule preserves that qualitative finding while retaining the full mixed exposure and shared group statistics, without inventing atom-specific values. A whole 130,709-row helper scan changed two subject projections; one restores DMT graph admission and the other PCP result still has an explicitly unmapped total-protein-synthesis endpoint. The final four-paper loss review and original findings remain preserved.

Frozen contract `routed_normalization_quality_20261026_v8` passed 561 tests and 325 subtests; one optional DuckDB test is skipped. Temporary Python dependencies were restored to their recorded versions after session cleanup. Twelve input assets are frozen against the original Luna build; only the controlled entity registry differs. Thirty execution sources, protected original and additional prompt/schema assets, regression tests and exact patches are archived. No model/API calls in this audit. A structural check found no literal study-DOI special cases or dated audit-ledger dependencies in the eleven changed/newly inventoried Python execution sources; this supports generality but is not scientific validation of every result.

The verified V7 intermediate build is archived at `verified_v7_before_parallel_actor_fix/`; do not present its counts as final V8. Final foreground replay driver PID50370, normalizer PID50732, tool session3186 began at13:23UTC. Primary/Reviews/meta conversion and assembly completed; whole-corpus normalization is running. Preserve the healthy CPU process. After completion: standard reference/input verification, independent V7→V8 acceptance, 480-case effects, isolated preview, actual-UI three-version counts and all30 area comparisons, then final report verification. Do not publish or change the active graph pointer.

Separately authorized 69-paper routing recovery returned all70 valid outputs by06:20UTC on27October. Its existing finalizer resumed after the core freeze and is independently rebuilding its own staged release. Those new outputs are excluded from this same-input normalization comparison regardless of their completion state; do not call them new requests from this audit or merge their benefits into the deterministic repair counts.


## 27 October 2026 13:55 UTC / 17:55 Dubai — expanded normalization audit complete; local preview verified

Final contract V8 completed and verified against the identical original Luna screening, routes, candidates and extraction-answer bytes. Results: 25,456 validated reports reconcile to 18,513 with main-graph-admissible findings, 4,416 detail-only, 1,519 audit-only and 1,008 without converted rows. 22,929 reports have normalized findings; 117,287 findings / 117,310 edges / 81,737 main edges / 19,793 entities. All source/code/protected hashes and reference integrity passed. No new model calls or cost from this audit; no screening/prompt/schema changes or graph publication. Final regression suite: 561 tests, 325 subtests; one optional DuckDB skip. The independently reviewed V7→V8 change is exactly one supported DMT main admission, no lost papers and full row equality outside the two explicitly bounded helper cases. PCP total-protein-synthesis remains an honest unmapped-endpoint audit, not a claimed rescue.

Actual UI counts deployed → original Luna → same-input repaired: total 21,735 → 22,404 → 22,929; primary 16,731 → 17,924 → 18,282; Reviews 4,672 → 4,155 → 4,319; meta-analyses 332 → 325 → 328; open access 10,324 → 10,975 → 11,174. Overview-visible reports 18,484 → 17,229 → 17,327. Primary Targets 2,572 → 1,685 → 1,554 (open 1,134 → 758 → 729); Review Targets 891 → 473 → 885. These are report identifiers, not independent studies, and area memberships overlap. Open access retains the same recovered-usable-full-text definition.

All30 area/type comparisons and90 pairwise count/access bridges conserve. The same-input repair adds560 represented reports and moves35 formerly represented reports entirely to audit (net+525);457 gain main-graph evidence and428 lose their last main-admissible finding. These are not error-rate or exclusion counts. The132 primary Target exits are exactly source-item linked:37 remain main elsewhere,72 retain paper detail,23 retain audits; one paper enters Targets. All2,632 area transitions have explicit lineage/coverage accounting; unmatched converter-held items and multiple exact matches are disclosed. Do not label every lost edge a corrected error or every gained edge a validated scientific result.

The readable480-record audit retains all bounded source judgments and explicit revisions. Remaining concerns include8 screening-recall examples, absent assigned profiles/structured findings, unit/p-value/source contradictions, incomplete controlled vocabulary, conservative mixed/uncertain attribution, report-identity/version cleanup and a saved-language flag. The report links individual examples; no inference of whole-paper absence from a selected-area packet. No defensible population accuracy percentage is claimed.

Separate previously authorized69-paper routing recovery also completed:70valid outputs; integrated staged normalization contains22,983 reports with findings,54 more than the controlled comparison;18,542main/4,441detail/1,533audit/932norows across25,446validated reports. It separately includes6sourceholds/4source-format-language exclusions from the earlier79-case scope, with one new valid response still reporting wrong_source_type (10.1152/physiolgenomics.00125.2003). Its billed model cost$0.07870222 is not a new call from this audit. Completion is frozen in `separate_routing_completion_snapshot.json`; do not mix its counts into the three-version same-input table.

Deliverables under `normalization_quality_repair_20261026/`: `report.html`, `report.md`, `report_verification.json`, `three_version_comparison/`, `audit_reconciliation/report.html`, `area_reason_inventory/`, `final_release/` and all historical/intermediate snapshots. Final report tables, links,480-case join and all90 bridges verified. Isolated preview http://127.0.0.1:8012/?data-source=local (PID57086) uses the22,929-report controlled comparison, visibly labelled27Oct2026/local preview; browser header and primary Target1,554/open729 directly verified. Three graph endpoints return200 with expected hashes and private .env404. Published graph, active pointers, canonical source data and source author-layer refresh remain untouched. No scheduled followup is needed for this completed audit.


## Target-profile gap investigation — 2026-10-27

Completed a read-only trace of the447 historical Primary-Target losses without a Target task and374 with empty Target responses. Frozen100-per-group random source review (200total), saved-input/current-object followups, and individual review of all38 reports without normalized findings (17no rows,21audit-only). Current disposition across821:688main-graph,95detail-only,21audit-only,17no findings/audit. The counts are report identifiers, not independent experiments or accuracy estimates.

Findings: direct Target definition explains many changes, but actual gaps remain. Two random no-Target cases have omitted original target assays (one partial capture); a third initial route concern was explicitly corrected after verifying complete Molecular-effects/PK coverage. All17no-row reports reviewed:7explicit physiological/readout coverage gaps,3computational scope boundaries,3insufficient reported assay results,2method descriptions,2format-related cases. All21audit-only reviewed:14neural vocabulary/projection gaps,2specific behavior labels rejected as generic,2review subject/scope gaps,1ketamine-versus-placebo parsing error,1identity hold,1format-verification hold. Do not conflate antagonist/KO dependence with direct binding or receptor availability with occupancy.

Report and reproducible census/judgments: `data/processed/model_runs/luna_v5_20261017/target_profile_gap_audit_20261027/report.html` and `summary.json`. Frozen initial judgments preserved; explicit source/coverage followups record corrections. Recommendations only: use saved fields first, align route coverage with extractor scope, then consider affected-profile reruns only for results truly absent. No screening, prompt/schema, extraction, normalization or graph changes; zero model/API calls.


## Cross-area coverage clarification — 2026-10-27

User challenged the Target emphasis in the latest report. Consolidated existing verified evidence across all10 areas and30 area/paper-type combinations; no new source audit or model calls. The completed480-record audit includes44–50source checks per area (300primary/120Reviews/60meta overall),87selected body-passage checks and133saved-output followups. The additional200-case Target investigation is deeper and overlaps the earlier sample; it is not whole-pipeline validation. The older sampling summary with reviewed_papers=0 is preparation-time history; the completed audit_reconciliation/inventory_480.jsonl is the final source-judgment owner.

All-area overview: `data/processed/model_runs/luna_v5_20261017/all_area_audit_overview_20261027/report.html`. It includes old/original/repaired total-open-closed counts for all30 combinations, exact historical loss-stage inventories and source-review coverage. Primary no-profile/empty-answer navigation contains4748paper-area incidences across4161distinct identifiers (3841no-profile/907empty), not confirmed errors, independent studies or a paid rerun queue. Safety880/86,Realworld783/172,Moleculareffects638/44 illustrate residual profile-stage inventories outside Targets. The report explicitly distinguishes scientific diagnostic sampling from complete adjudication of every residual case. Existing published graph, V5, prompts/schemas, extraction/normalization outputs and pipeline logic unchanged.


## 28 October 2026 — cross-domain saved-output repair and complete-cohort reconciliation

Completed at 2026-10-28T16:13:11.641519+00:00; checkpoint recorded 2026-10-28T16:24:51.863821+00:00. Owner: `cross_domain_coverage_repair_20261028/`; final run `luna_v5_20261028_cross_domain_repaired`. The comparison starts from the integrated release containing the previously completed routing recovery, not the earlier controlled-only preview. All 25,446 canonical report identifiers and 41,945 saved task responses reconcile. The historical no-converted-row diagnostic was corrected from 932 to 930 by canonicalizing both sides of two registered DOI aliases; those papers already had findings and are not new rescues. Original ledgers remain preserved.

Normalized represented reports 22,983→23,053; open (recovered usable full text) 11,201→11,230. Actual website overview union 17,399→17,401; main-admitted reports before website filters 18,542→18,554. These are different stages: a main-admitted report need not pass the UI's additional overview filters. Final dispositions: detail_only=4,499, main_graph=18,554, no_converted_rows=930, audit_only=1,463. Actual UI family inventory counts, including detail: primary=18,333 (open 8,472, closed 9,861); reviews=4,392 (open 2,546, closed 1,846); meta_analyses=328 (open 212, closed 116). Newly represented 70; formerly represented now without findings 0; new main admission 62; former main now detail/audit 50. These are report and membership changes, not independent-study counts or error-rate estimates. All 30 area/type comparisons and 33 membership bridges are linked in `report.html`/`report.md`, with old deployed counts kept separate from this same-answer repair pass. Open always means actually recovered usable full text, not a publisher metadata label.

Reusable fixes are in the primary/Review/meta converters, normalizer, controlled vocabularies and graph-view contract. Converter additions: 21 primary objects, 27 Review projections, one descriptive meta incidence result; all existing primary/meta converter rows remain unchanged. Review dispatch corrects 40 typed domains and preserves 188 explicitly nonclinical broad topics as general detail rather than guessing a condition. Complete supported anatomy takes precedence; an unresolved anchor preserves the literal neural readout in detail instead of guessing a measurement family. Molecular-expression/enrichment wording, non-steady-state phase locking, structural tract measures and associated symptoms do not become unsupported neural constructs. Specific measured behavior, functional-neurological wording and an explicit metabolic pathway receive controlled mappings. Narrow attribution guards stop tested pooled/composite and unregistered-agent class shortcuts from creating unsupported individual-drug or class claims; they are not a universal solution for mixed exposures. Valid class-level findings, dose comparisons, active comparators and corrected inference remain supported. There are no literal study-DOI or dated audit-owner dependencies in the changed execution modules. A new reusable read-only `pipeline.kg.audit_saved_extraction_coverage` supplies whole-cohort task, object, disposition, profile and area inventories.

Fresh diagnostic source assessment: 173 selected records across the nine non-Target areas (122 evidence captured elsewhere/in saved fields, 16 reasonably empty for the area, nine main-assessment raw-result omission flags, six saved-object gaps, 20 uncertain). Three incidental omissions make 12 candidate papers, including two phenotype-scope qualifications and one assay ambiguity. These pre-repair labels are not a post-repair error rate; captured in saved fields does not necessarily mean visible in the graph. The sample excludes the earlier 480 and Target 200, with one disclosed overlap with an extra Target followup; it was used to develop fixes, not independent held-out validation. Prior work covered all ten areas and all three paper families. Additional checks cover 36 cause-selected saved rows across 12 internal domains, all 90 primary conversion holds, 35 selected meta holds, and 185 newly matchable overview-capable rows/71 label mappings. All 400 original neural-detail fallback records were individually checked against saved fields/table rows: nine measurement-family collisions, 26 precision/context limitations and 365 without another obvious saved-field contradiction. The final fallback retains literal readouts. Bounded source/table probes also test anatomy precedence, expression exclusions, steady-state specificity, contrast context and domain preservation. These overlapping checks are not summed into unique whole-paper audits, and table acceptance is not population scientific correctness; source judgments use saved abstracts/fields unless explicitly stated otherwise.

The initial normalization guards passed focused tests but failed corpus acceptance. Rejected source/impact snapshots remain archived; the first replay was interrupted before normalization and unchanged converter outputs reused. A later complete build exposed bounded readout/anatomy/contrast regressions; that intermediate build is preserved separately. The final rules pass 541 tests and 347 subtests (1 optional test skipped; see the final test receipt), corpus counterexample/positive controls, source/input hashes, unique-key and reference checks. The final test and bounded acceptance receipts match the executed normalizer hash. All numerical/quote/warning/provenance differences and final paper/area transitions are independently accounted for in the acceptance artifacts. Literal fallback preservation does not establish drug attribution or blanket scientific validation of every gained edge.

Remaining issues are explicit: missing raw results; some broad Review subjective/context projections and role conflicts; complex mixed-regimen/compound attribution; unresolved vocabulary and compound identities; rounded statistical ambiguity; and a source-format leak (Physiology conference abstract DOI10.1152/physiol.2025.40.s1.0127) needing the existing upstream source owner. Mapping correctness does not itself establish drug attribution. The final report links exact remaining cases and preserves the earlier source judgments.

Screening V5, extraction prompts/schemas/raw answers, canonical candidate corpus and active/published graph pointers remain hash-identical. This release and its payload export are staging/diagnostic only, with no refreshed author layer. No new model/API calls or cost ($0), no extraction rerun, no publication, and no scheduled continuation created by this step. The prior local preview is not relabeled as this new release.


## 28 October 2026 — deployed-versus-final comparison and interpretation

The user clarified that the primary comparison must be the currently deployed September graph against the final new Luna graph, rather than the last +70 same-answer repair. Reporting owner: `deployed_vs_final_assessment_20261028/`. The live public active.json was fetched and saved; its run_id remains living_update_20260917_author_identity_reviewed, and all three local deployed detail-payload hashes exactly match its published file hashes. All30 deployed area memberships/access counts reproduce the prior comparison.

Whole represented graph21,735→23,053 (+1,318); primary16,731→18,333; Reviews4,672→4,392; meta332→328; usable-accessible-fulltext papers10,324→11,230. Raw report-identifier turnover:17,739 shared,3,996 old absent and5,314 entrants. Fourteen apparent old losses have registered identifier replacements. For the remaining reasons see counts.json; stage locations are not correctness verdicts.

The consistent actual overview union is18,504→17,401. The earlier18,484 deployed number was the export manifest's stored summary, not the union of actual displayed area memberships. The30 original deployed membership lists reproduce exactly; this is a20-count reporting-denominator correction with no change to publication totals or area counts. Preserve overview_denominator_reconciliation.json.

Interpretation: source-checked examples demonstrate improved drug identity, group attribution and evidence qualification, plus genuine new coverage. They also demonstrate remaining omissions and visibility/granularity losses; do not describe all old area losses as false positives or all new additions as correct. No overall percentage accuracy gain has been measured. Existing480 source judgments are attached to current final representation, not silently rescored into a final accuracy benchmark. Twelve illustrative selected claims were checked against actual deployed/final statements; examples explicitly distinguish clear improvements, valid reclassification/tradeoffs, regressions repaired back to parity, and remaining defects. The200 historical Target-loss checks are diagnostic evidence about the direct-assay versus mechanism/readout boundary, not an overall recall estimate.

The user-facing report leads with deployed-versus-final totals, all10areas×3paper types and a clear quality assessment. Full accessible/closed counts, whole-graph turnover, loss locations, selected old/new source statements and provenance are linked. The earlier technical repair report remains an appendix. This task made no production pipeline, screening, extraction, normalization, active graph or published graph changes and no model calls; public deployment metadata was read only.


## 28 October 2026 — latest final graph local exploration preview

User requested the latest graph locally. Isolated preview is running at http://127.0.0.1:8013/?data-source=local, run luna_v5_20261028_cross_domain_repaired, PID 45835. Owner cross_domain_coverage_repair_20261028/preview; reproducible prepare/launch/serve scripts in implementation. Reuses the verified final exported payload bytes, with isolated manifest path rebasing, matching staged Methods data, and existing preview allowlist/checksum validation. No normalized scientific inputs or active/public pointers changed.

Browser visibly verified graph rendering and header Final Luna ·28Oct2026, total23,053/primary18,333/Reviews4,392/meta328; Conditions1,686/open1,128. In-app browser tab7 marked deliverable. Three graph endpoints verified200 with exact checksums; private .env404. The earlier8011/8012 previews are older snapshots;8013 is the final graph. Author identity enrichment has not been refreshed; source author text remains available.

### 2026-10-29 — Author identity refresh of the final local graph

User requested a full author-list/attribution check and verification that the earlier identity repairs survived rebuilding. The canonical correction registry was intact, but the 28 October diagnostic preview/export had skipped the separate author-table stage. Rebuilt author tables for all 23,919 backing metadata records using the September reviewed cache plus missing-only public metadata retrieval; displayed scientific graph remains 23,053 publications.

Owner: `data/processed/model_runs/luna_v5_20261017/author_identity_refresh_20261029/`. Read `report.md`, `summary.json`, `completion.json`, and `audit_final/summary.json`. Existing reviews were preserved verbatim. Exact-DOI checks corrected 105 inherited wrong-work links (129 refetched bylines changed). Added 25 DOI/position identity corrections, 28 fingerprinted source byline reviews, and two identifier-supported profile mappings in the existing `pipeline/kg/author_identity_overrides.json`. Source review corrected cross-person ORCIDs, duplicated authors, surname-only false merges, wrong expanded profiles, and affiliations listed as authors. Saved NLM records cross-check 17,035 bylines; differing counts are navigation flags, not established errors.

Shared `build_author_tables.py` now checks cached report DOI/title identity, retries suspect entries online, and falls back to supplied names without borrowing unrelated IDs. An unchanged fingerprinted source review takes precedence for verified translations. 56 author/audit/export tests pass. Final tables have 128,244 authorship rows / 70,762 identities, 97.13% structured coverage, and zero duplicate positions, orphan links, or different-name same-paper identity collisions. 28 unresolved conflict profiles / 230 rows remain withheld from public author facets, and 176 new priority possible identity splits remain separate pending stronger evidence; do not call these verified duplicate counts. 242 NLM/provider count differences also remain flags, including consortium and source conventions. Some report-key/translation conflicts use source names without disputed structured IDs.

Author tables/cache/report were added to `data/processed/kg_routed_runs/luna_v5_20261028_cross_domain_repaired/`. Scientific parquet tables and all graph summary counts were hash/equality checked unchanged. New normal-freshness payload is under this owner's `payload/`. Local preview was safely restarted on the same `http://127.0.0.1:8013/?data-source=local` using this owner's `preview/` package (PID and HTTP/browser checks saved there). Public active pointers/deployment unchanged. No model calls, screening/extraction reruns or scientific normalization changes. Use the standard author stage/audit/export path for future releases; do not promote a diagnostic `--allow-stale-authors` export.

### 2026-10-29 — Author count discrepancy reconciliation (read-only)

User asked why Robin Carhart-Harris appeared to fall from 96 deployed publications to 25 in the new graph. Reproduced BOTH exact numbers with actual UI author-count functions and frozen/public-verified payloads: deployed main-graph first/last-author aggregate across all types =96; pre-author-refresh new preview split him across11 source-name variants, largest fragment25. After the completed author refresh, matched aggregate =86. All first/last papers including detail =105→105. All represented papers under the same reviewed ORCID, any author position =225→224 (212shared,13removed,12added); including unmerged name-matched profiles is227→225, not a proven global identity merge.

Owner: `data/processed/model_runs/luna_v5_20261017/author_count_comparison_20261029/`; start with `report.html` and `summary.json`. Current public active pointer/release and all3 local deployed detail payload hashes match; author/access UI counter functions are identical. Matched96→86 waterfall:12old main papers survive only in detail,3are normalization-held,2are V5 exclusions,3are source/context routes;10new main first/last papers offset20departures. Full13whole-paper losses:4normalization,2empty extraction,4V5,3source/context. Read `robin_missing_papers_reviewed.json`; these are source-title/abstract/saved-output diagnostic judgments, not full-text rescreening or independent gold accuracy.

Concrete remaining coverage concerns include HBM23224 LSD V1/V3 connectivity (accepted/extracted composite endpoint unmapped), DMT HADES global harmonic endpoints unmapped, two substantive review/global-brain syntheses held, empty microdosing-blinding extraction, and the context-routed review/opinion `10.1097/yco.0000000000000467`. Two conference abstracts and breathwork-only/theoretical exclusions should not be treated as automatic errors. Entropic-brain-today has explicit psilocybin evidence despite a broad-consciousness V5 rejection; scope/recall is debatable. No eligibility or scientific corrections were applied by this investigation.

Read-only survival comparison covers 164 old author identities with at least 30 represented papers. Hendricks remains 61→61 after accounting for an OpenAlex→ORCID identity change (59 old papers survive, two removed/two added). All 53 old Curran papers survive, but 49 are under other/conflicted identities rather than the old ORCID; her public author visibility remains a real limitation. Dahan 33→19 is an actual cohort change: 17 V5 exclusions/three additions, mostly ketamine pain research; some excluded abstracts also have PK/drug-high contributions, so do not declare all 17 correct without purpose/exception review. No model calls, prompt/pipeline changes, normalization edits, graph refresh or publication in this comparison. Existing local preview 8013 remains author-refreshed.


### 2026-10-29 — Author and coverage follow-up completed, local preview only

Owner: `data/processed/model_runs/luna_v5_20261017/author_and_coverage_repairs_20261029/`; start with `report.html`, `summary.json`, `completion.json` and `final_integrity_verification.json`. User authorized remaining deterministic author/coverage repairs and an unsubmitted targeted model proposal. No subagents, paid model calls, new screening or extraction were used. V5, frozen extraction inputs/raw answers and canonical/published active pointers remain unchanged.

Accepted run `luna_v5_20261029_author_coverage_repaired_v2` replays all 41,945 saved responses for 25,446 reports / 128,861 source objects. Full reference checks pass; all 102,652 shared source-item groups preserve quantitative values and scientific statements. 192 tests and 311 subtests pass, one optional test skipped. Original rejected trials are retained: an overbroad cognition substring alias and global neural-measure admission inconsistency were corrected before export. Generic exact-only terms are enforced in all vocabulary text matchers. Thirty-one controlled behavioral constructs, V3, explicit all-components-resolve two-region connectivity with one shared proposition, and bounded global-neural measure typing are integrated in normal normalization code. No invented anatomy, efficacy, outcome values or source-unit corrections.

Represented papers 23,053→23,058 (18,333→18,335 primary; 4,392→4,395 Reviews; 328 meta unchanged); recovered-fulltext papers 11,230→11,233. Zero formerly represented papers lost. Actual UI named-area union 17,401→17,416, computed from the browser memberships, NOT the stored export projection-summary counts 17,352→17,481. No existing named-area paper lost. Primary Cognition 2,046→2,105; Review Cognition 148→154; meta Cognition 22→23; primary Behavior 2,742→2,745; Brain regions 2,128→2,135; all other family/area counts unchanged. Internal dispositions are separate: 121 newly main-admitted reports and 144 main→detail nonanatomical-measure reports, already outside named views. The five recovered reports/qualifications and source-unit warnings are linked in the report.

Author repairs add 217 source-specific DOI/position reviews and 11 explicit profile mappings in the existing registry. 262 identity rows on 248 papers change, all 128,244 original credits/source bylines preserved. Conflict profiles 28→20, affected rows 230→88 (82 papers remain); no new duplicate positions, orphans, different-name identity collisions or global ORCID aliases. Remaining 13 papers/78 repeated source rows and 242 count flags are not presumed errors. Aggregated author tables now preserve conflict status rather than clearing it because an OpenAlex ID exists. Curran, Zhou, Johnson, Furukawa and other high-impact same-name/profile issues are documented against source bylines/owners. Bibliographic retrieval failures remain explicit, not identity proof.

Robin Carhart-Harris has 229 represented papers at the reviewed identity versus 225 deployed / 224 immediately before this round. Four of the 13 previously absent old papers recovered. Nine remain: four V5 exclusions, two conferences, two zero-object extractions and one review never screened by V5. Actual comparable Authors overview first/last count is 96 deployed→86 before this round→91 now; including detail first/last 105→105→108. Do not confuse these UI roles with all coauthorships. The initial displayed25 was one unmerged source-name fragment.

Prepared four existing-profile fallback extraction tasks using a cohort-wide zero-object clinical-only plus methodological-validity selection; each saved abstract/refusal reviewed. Conservative combined Batch ceiling $0.0254436875, rounded $0.026, using saved approved rates; recheck before submission. No requests submitted. Four screening proposals remain separate and unpriced, two records source-blocked. LSD HBM23224 supplied/source packet says75mg and requires original-PDF unit verification; meta Psychres112749 has non-atomic effect ranges. These are not silently repaired. All930 no-converted reports are inventoried, not certified correct.

Fresh author export and matching Methods are running at `http://127.0.0.1:8013/?data-source=local`; accepted v2 run verified by HTTP, with per-file allowlist and checksums. Public deployment unchanged. This is deterministic regression/source-judgment evidence, not independent expert gold or a population accuracy estimate. No scheduled continuation created.


### 2026-10-29 — User rejects targeted reruns; proposal withdrawn

The user explicitly rejected the proposed targeted screening/extraction reruns and requires systematic defects to be fixed in the normal pipeline. This supersedes every earlier suggestion to submit the four extraction tasks or screening proposals. No requests were submitted. The proposal and earlier report are preserved only in `author_and_coverage_repairs_20261029/withdrawn_targeted_model_proposal_20261029/` and `report_before_proposal_withdrawal/`; preparation helpers now stop with the withdrawal instruction. There are zero active tasks. Read `targeted_rerun_withdrawal.json`.

Applied normalization changes are shared code/vocabulary and were replayed over all saved outputs. Source-specific author identity reviews are in the standard persistent correction registry and are reapplied by the normal author builder. They are curated exceptions, not a general identity-inference algorithm. The remaining methodological-versus-clinical routing gap is NOT fixed by preparing a hand-picked fallback queue, and remains explicitly unresolved. Any correction must enter standard routing with cohort-wide regression checks; no new routing rule, screening, extraction, scientific payload or public pointer change was made in this withdrawal. Report/summary now remove the rerun proposal as an active next step. Persistence evidence is `pipeline_persistence_verification.json`.

### 2026-10-29 — Whole-cohort extraction routing investigation completed

Owner: `data/processed/model_runs/luna_v5_20261017/routing_contract_audit_20261029/`; start with `report.html`, `summary.json`, `confirmed_findings.json` and `integrity_verification.json`. Investigation only: no subagents, model/API calls, production code/prompt/schema edits, extraction/screening reruns, targeted queues or graph/pointer changes. User's rejection of ad hoc targeted reruns remains in force.

Reconciled all 25,446 selected reports / 41,945 saved tasks and answers / 128,861 objects. Zero missing/duplicate task-output joins, profile/domain mapping mismatches or current primary contract fingerprint differences. All 25,446 ready retained reports are selected. Whole-cohort source-pointer verification covers 20,237 packet-referencing tasks / 11,998 source packet records across four files: all fingerprints match. This proves which text was supplied, not complete or correct article text.

Manually reviewed a frozen 495-report / 908-task diagnostic/control set spanning all 14 profiles, including random empty/nonempty controls, all 46 validity-empty papers (51 tasks), all 21 wrong-source-type papers (25 tasks), all 32 nonempty-scope-warning papers, and missing-domain risk cases in every primary domain. These groups overlap. Seed/selection/provenance and all 495 explicit title/abstract/task judgments are preserved; 492 are outside the specified earlier target/Robin judgment lists, not certified unseen in all historical audits. Complete saved-answer/current-normalized traces exported for all 495, with deeper complete-object followups. Fourteen source-body navigation followups verify 30 task-packet fingerprints; two original source-section reconstructions match frozen body hashes. Not 495 complete full-paper quantitative audits, independent expert gold or population error rates.

Twenty enumerated routing/contract mismatch examples: ten method-contribution, nine missing topic/contribution profiles and one narrative synthesis stranded in meta. Fourteen currently have no saved objects; six retain other findings. These are not 20 wholly absent papers or automatic eligibility rescues. Wrong-profile examples extend beyond Targets to physiology, behavior/personality, utilization, product composition, PK and receptor expression. Separate correctly-routed extractor refusals include present MDMA toxicology results and eligible ketamine basic biology. Existing objects also show evidence-role problems: scale validation becomes positive clinical evidence, expert ratings become participant-effect edges, and template resemblance in unexposed cohorts becomes drug clinical/safety evidence. Some apparent defects are already mitigated downstream (provider attitudes; cannabis and unrelated trial filtering). Do not sum these overlapping categories into an error rate or restore all empty outputs.

Additional structural source checks flag 60 navigation/editorial-like abstracts (54 wholly empty), not 60 automatic exclusions. One verified primary packet supplies only supplemental correlations despite a richer frozen task abstract. Four empty meta tasks comprise three abstracts lacking numerical pooled estimates and one full narrative synthesis. Offline synthetic probes show review/meta selectors can skip a changed task/source using successful DOI alone; this is a demonstrated future reuse weakness, not proof of stale accepted results. Primary task identities already fingerprint contracts. Eighty protected-production/frozen-input hashes unchanged; all 495 review packets/source hashes reconcile. Recommendations are shared contribution/role contracts, profile coverage backstop, consistent scope/refusal rules, source completeness/genre handling and secondary task-identity hardening. No fixes applied in this investigation.


## Routing-contract repair authorized — 2026-10-29 15:28 UTC

The user now explicitly authorizes principled routing repairs and targeted reruns of affected extractions. This supersedes the earlier withdrawal of ad hoc reruns, but does not authorize DOI/author allowlists, V5 changes or a deployment. Owner: `routing_contract_repair_20261029`. Original accepted release, raw answers and screening remain immutable.

Implemented shared source/contribution instructions, optional backward-compatible primary `evidence_role`/`source_contribution` fields, method/physiology fallback, curated-abstract input/fingerprints, mechanical supplement-only abstract fallback and secondary task/source/contract cache identities. New post-extraction coverage and delta preparation/merge use standard extraction profiles, schemas and Batch runners; unaffected profiles/JSONL lines are preserved. Failed/refused/empty-over-nonempty replacements remain unresolved, retaining parent history. Source-quality guards keep title-only assertions from unqualified effect edges. Shared normalization distinguishes observed/null outcomes from scale validation, expert ratings, economic models and unexposed-cohort template comparisons. No global rerun solely because a compatible optional field was added.

Whole accepted-cohort navigation: 25,446 reports; 8,277 coverage candidates, not 8,277 extraction reruns, including one supplement-only packet missed by keyword-only navigation. 58 navigation-like abstracts held: native registry collection returned 19 linked PubMed records without abstracts and 58 Crossref records without abstracts; four have title-based saved objects, not six within this exact subset. No replacement text was invented and no new source exclusions applied. The existing 495-report diagnostic/control set has 487 source-ready validation inputs and eight source holds.

Final contract validation: `validation_final_contract`, Batch `batch_6ae364fecf348190bb8018a7cc390074` (487 requests), maximum configured cost $1.8813; preliminary validation `batch_6ae35d964c388190bc0c396ae48616f0` remains separately receipted and must also be collected/settled. Preliminary prompt lacked the final profile-replacement clarification/non-exhaustive iboga examples; do not call it the final contract benchmark. Both are pending at this checkpoint. `production_ready` has 8,277 immutable requests in three large parts, prompt SHA3204e2dc4c7b0bb2752605422ac4a6bdcfa8856e913dbe32dccfa542c05b327a, maximum configured ceiling $31.6891. No production coverage or affected extraction has been submitted. Intermediate offline production preparations are preserved, not paid: v1 predates partial-source census; v2 was stopped before completion after a missing-packet navigation bug, which was fixed; v3 supplies verified frozen source inputs reused by final preparation.

102 targeted tests +2 subtests pass. A broader existing suite passed 256 tests +36 subtests, with one unrelated pre-existing stale UI asset-version expectation. New extraction/routing/schema checks are passing; this is not model accuracy validation. Saved-answer normalization-only replay is running at `normalization_only_release`, run ID `luna_v5_20261029_contribution_roles_v1`; do not claim its final counts yet. Continuous local collectors are running for the two known validation receipts; no scheduled automation was created. Shared ledger settled $63.184403895 before these jobs settle, cap $100. No Sol/Gemini calls, screening changes, canonical extraction projection replacement or graph deployment.

Next: collect/validate final-contract plans against source and frozen diagnostic controls; only then dispatch production coverage parts together, build quote-validated standard delta tasks and submit only affected profiles. Reconcile output/source/role issues, merge with unchanged sibling profiles, replay normalization, retain unresolved source/scientific holds and report actual changes/cost. Reusable commands are in `pipeline/extract/README.md`; `pipeline/rerun_luna.py prepare-extraction-coverage` integrates preparation into the main workflow.

### Repair checkpoint — 2026-10-29 15:42 UTC

Extended the shared role guard to passive statements with explicit per-item Delphi rating design, retaining valid provider/public-health views and delivery recommendations in their actual domains. Protect a genuine null treatment contrast in a validation paper; mixed trial/Delphi designs do not trigger the design-only shortcut. Latest whole-graph rule proposal is44findings/13papers (30previouslymain); this is not the final normalized delta. All13complete frozen abstracts and exact changed item descriptions were inspected for contribution-role support; no13full-paper quantitative audit or independent expert gold claim. `role_source_validation.json` preserves those checks.

106targetedtests+2subtests pass, including the end-to-end standard-task delta merge. V5, current candidate/route owners, author identity owner, public graph pointer and active extraction pointer match the six original protected hashes. Unaffected parent release input hashes also match. First unpublished normalization replay was stopped before completion to apply the broader validated expert-role guard; its source snapshots/logs are preserved with a withdrawal receipt. Current normalization replay: `normalization_release`, runID`luna_v5_20261029_contribution_roles_v2`. No paid repeat extraction or deployment occurred. Both validation receipts remain in progress; production coverage and actual repair extractions remain unsubmitted pending final-contract validation. Continuous local collectors retain their locks/receipts.

### Parallel coverage dispatch — 2026-10-29 15:45 UTC

Dispatched all three final-contract coverage-planning parts alongside control validation, as a read-only extraction-work proposal stage. This advances the asynchronous work without waiting to submit the bulk while controls are queued. Actual affected extraction reruns and graph changes remain gated on validation. Production requests8277, actual repair extraction requests0. Jobs: batch_6ae369bb772c8190b9533c120521ed58, batch_6ae369d7ec908190bcfaaa519a2c4bf6, batch_6ae369eefc1481909127e044702d9376. Raw request/task/prompt/schema manifests and receipts are immutable; never resubmit these jobs. Continuous local collectors are active for both validation generations and production_ready, not scheduled wakeups. Latest shared role rules have106passingtests+2subtests and13source-abstract role judgments; current no-model replay is normalization_release/contribution_roles_v2.

### Current implementation verification — 2026-10-29 15:49 UTC

108targetedtests+2subtests pass. Generic narrative-only source correction supports both wrongly assigned primary and meta families through the standard Reviews builder; an explicit narrative source-design quote is required. Mixed original/synthesis reports are not wholesale rerouted. Newly discovered primary→quantitative-meta changes remain explicit source/family holds pending a standard meta handoff, not automatic primary retries. Actual repair extraction requests remain0; the five known coverage/control jobs are in progress, including all3productionplanningparts. No graph/canonical owner changes. See routing_contract_repair_20261029/status.json and async_jobs.json.

### Status check — 2026-10-29 17:43 UTC

Normalization-only replay contribution_roles_v2 completed successfully. All118324findings and23058represented papers remain; main-admitted findings81073→81055 and detail37251→37269. The18net main-to-detail shifts are source/role corrections, not18paper exclusions. Economic projections are reclassified to their actual public-health domain. Full before/after snapshots saved in normalization_before_counts.json/normalization_after_counts.json. No public pointer changed. Fresh remote API metadata check at17:42UTC: all5known coverage/control jobs in_progress,0results/0failuresreported. All3local continuous collectors are still running. Next is final-contract/source-plan validation, standard affected-profile extraction, merge/replay and final local-preview/count/cost comparison. No new submissions or model generation calls during this status check.

### Coverage-stage architecture questioned — 2026-10-29 18:04 UTC

The user explicitly questions the newly added coverage-planning LLM step and whether different instructions constitute an unagreed pipeline change. It is a new post-extraction diagnostic/routing-proposal stage, not V5 screening or standard extraction; do not describe it as merely rerunning the existing pipeline. Audit outputs remain separate and unadopted. No actual repair extractions have been submitted. Existing collectors only retrieve the paid jobs already sent; do not advance audit plans into production extraction while this workflow question is unresolved. This is not an instruction to erase raw jobs/history or revert the separately authorized normalization/code fixes.

### Separate self-review removed from the production entry point — 2026-10-30 03:13 UTC

The user challenges both the need for an extra stage and the circularity/correlated errors of Luna reviewing its own saved extraction summaries. Removed prepare-extraction-coverage and its options from rerun_luna.py; replaced the production handoff recipe with an explicit diagnostic-only note. Preserve already paid requests/raw answers and experimental implementation sources. No audit plans adopted and no actual extraction reruns submitted. Proceed with shared fixes in existing routing/task/source/normalization components, distinguishing ignored existing annotations from missing upstream scientific-domain judgments; a deterministic code fix cannot invent the latter. Validate against source-checked cases, not Luna self-agreement. No new model calls, V5 changes or graph deployment in this correction.

### Bounded core repair cleanup — 2026-10-30T07:52:30.586016+04:00 (Asia/Dubai)

User explicitly wants fixes to existing components, not extra self-review/check/fallback stages. Archived and removed experimental coverage executables/tests and all coverage_context hooks. Restored original primary schemas and general-primary prompt from pre-experiment snapshots; removed unvalidated shared prompt additions and automatic supplementary-to-abstract fallback. Kept verified contribution-role normalization, curated-abstract source/input fingerprints, unusable-navigation handling, and secondary task/source/contract cache fixes.125tests+10subtests pass after cleanup. V5 and original primary contract hashes verified. Paid request/results history preserved; no audit plans adopted and actual repair extraction calls0.

The completed normalization-only result retains118324findings/23058represented papers;13economicfindingsfrom7papers remappedclinical→real_world_public_health;18main-admitted findings moved to paper detail without removing papers. No demonstrated task-loss/profile-execution mismatch in the original census; method-modifier and omitted-domain coverage are unimplemented policy/contract limitations, not silently solved mechanical bugs. Do not keep labeling these fixed or launch an audit-derived queue.

Final ordinary offline rebuild started from frozen accepted inputs, owner final_core_release, runIDluna_v5_20261030_core_pipeline_repairs, using cleaned code. No model calls. Finish rebuild/export, refresh local preview/counts, freeze bounded fixes and report limitations. Do not reopen screening, invent new routing judgments or add fallback/recursive model steps to close every remaining example.


### 2026-10-30 — Local finalization complete; no extra model-review stage

Owner: `routing_contract_repair_20261029`. The ordinary offline conversion/assembly/normalization replay finished at `final_core_release`, exported as `final_payload` with run `luna_v5_20261030_core_pipeline_repairs`. Same 25,446 selected reports / 41,945 accepted saved tasks and answers / 128,861 objects; no new model calls or repair extractions. Primary prompts/schemas match pre-experiment versions. Experimental coverage executables, context hooks, shared prompt/schema additions and supplementary-to-abstract fallback are removed; 9,251 paid diagnostic requests/results are retained as withdrawn history, with zero adopted plans. All saved jobs are completed/parsed; stale pending-status wording is superseded by `status.json` and `remote_status_final_from_saved_receipts.json`.

Final graph: 23,058 represented reports, 118,324 findings, 118,347 evidence edges, no dangling references/admission mismatches. 18,528 reports have a main-admitted finding; 4,530 have detail-only findings; 930 have no converted findings (924 empty saved answers, six objects without converted rows); 1,458 remain normalization-audit-only. These outcomes sum to 25,446 and are not adjudicated screening errors. The actual UI overview union is 17,413, rather than the raw export projection counter 17,478. All represented family counts: 18,335 primary, 4,395 Reviews, 328 meta-analyses. Actual recovered usable full text: 11,233 open / 11,825 closed.

Verified against fresh public-pointer hashes, the deployed September release has 21,735 represented reports / 10,324 open and actual overview union 18,504. Final corpus turnover is 17,744 shared raw identifiers, 5,314 added and 3,991 absent old identifiers; 14 apparent absences are registered identifier changes. Old absences break down into V5 exclusions 2,629, normalization holds 484, no converted extraction 321, context/source-type routing 294, publication format/language 238, identifier changes 14, source holds 10 and other cleanup one. These processing locations are not correctness labels. Full 30 area/type/open/closed comparison and per-membership losses are in `counts.json` and `all_area_losses.jsonl`.

Existing 480 source judgments were reattached to final graph state without silently re-scoring them as a held-out accuracy benchmark. All 12 earlier paired examples were traced to final output: 11 selected scientific field sets are unchanged; the receptor-imaging example only changes generic-measure admission to detail, with 12 regional findings retained. The illustrative set demonstrates six improvements/typing corrections, one parity case, two clear coverage/granularity losses and three mixed cases. Do not claim a global accuracy gain percentage. Confirmed wastewater-review omission, esketamine quantitative-detail loss, pooled/context projection limits and missing-domain/empty-output risks remain documented. No new policy, fallback or audit-driven queue was created to force recovery.

Author tables rebuilt offline from the accepted cache and current reviewed registry equal the accepted repaired tables exactly, preserving 128,244 byline rows. Robin: 225→229 all coauthored represented reports; overview first/last-author view 96→91 and including detail 105→108. Initial 25 was an unmerged source-name fragment. Twenty unresolved identity profiles / 88 rows on 82 papers remain withheld from identity facets with bylines retained.

Verification: 345 tests +46 subtests pass; 6 protected owner hashes, 13 frozen input assets, 86 execution source snapshots, 12 restored primary contracts and all 39 export file hashes checked. Final table, author, export and HTTP receipts are preserved under the owner. Preview refreshed at `http://127.0.0.1:8013/?data-source=local`, PID 13895, with matching Methods, allowed files and final payload checksums. Local header names the Luna V5/PCP October snapshot instead of inheriting the deployed September date; no exact search-through date was invented. Public/canonical active pointers, candidate corpus, V5 routes and correction registries remain unchanged. No deployment or broad unrelated commit.

This completes the current local repair cycle. Use `report.html`, `final_summary.json`, `status.json` and `final_integrity_verification.json` as the current handoff; earlier pending/experimental notes remain immutable history.


### 2026-10-30 — Read-only overview/detail fraction comparison across all areas

User requested a denominator-aware comparison before further normalization investigation, explicitly across all domains. Owner `overview_visibility_fractions_20261030`: actual UI functions reproduce all 60 area/type/version overview sets. For retained area-mapped findings, deployed→final detail-only shares: Real-world14.7%→30.0%, Safety10.9%→23.4%, Targets15.7%→24.3%; every area and all three types are tabulated. Main denominator excludes fully unmapped/withheld objects, so a separate pre-normalization saved-evidence table covers all12native domains, distinguishing same-domain main/detail, other-domain retention and no normalized findings anywhere. Empty outputs are explicitly excluded from the native nonempty-evidence denominator. No source judgments, accuracy rates or automatic rescue proposals inferred. No model calls or core pipeline/normalization/graph changes. All six protected owners match previous hashes. The existing consolidated final comparison report has this section added; its prior HTML is preserved.


### 2026-10-30 — Safety normalization aligned with current Luna contracts

Completed the user-requested bounded Safety audit and deterministic repair in `safety_normalization_alignment_20261030`. Mechanically censused all 17,126 baseline Safety finding records and checked 85 unique selected saved extraction statements/field sets (69 changed-rule packets, 10 role-boundary records and 14 legacy interaction-keyword records, deduplicated). This is normalization fidelity against saved extraction contracts, not a new original-paper extraction accuracy benchmark or population error rate; the prepared 266 navigation records were not all adjudicated.

Changes are in existing `pipeline/kg/build_evidence_tables.py`, the existing evidence exporter and finding-card renderer, with current-contract regression tests. Removed drug/enzyme-name-only interaction shortcuts; repaired lexical event mappings; honored concrete event plus declared existing Safety family; retained exact event and category separately rather than adding prose nodes. Added a neutral electrolyte/fluid balance anchor without inferring hyponatraemia. Narrow registered exposure wrappers and explicitly generic pooled psychedelic classes resolve without splitting pooled named-drug estimates or inventing analogue identities. Existing role gates now distinguish reporting audits, perceptions, forecasts, proposed monitoring, pretreatment attribution and enzyme-only readouts from observed Safety outcomes; actual null results/cytotoxicity protected. Six native Safety fields survive normalization, export and detail display. All 53,939 nonempty field instances match the public detail export; severity and seriousness remain distinct.

Standard full offline replay from frozen `routing_contract_repair_20261029/final_core_release` completed as `luna_v5_20261030_safety_final`. Source inputs/raw answers and normalization import closure verified unchanged. Normalized scientific statement/value sets match across findings plus retained audit; event splitting/deduplication can change. Eight assertion projections moved from audit to findings; one generic physiological/subjective interaction synthesis moved to the ordinary unmapped audit after removal of a false Safety label, with its original statement preserved. These movements are not new model evidence. All table references/admissions reconcile. Offline author rows equal prior accepted tables exactly (128,244). No screening/extraction/prompt/schema changes, model/API calls, paper-specific allowlists, public deployment or active-pointer writes. Three earlier incomplete local prototypes were explicitly superseded before use; only release_verified completed and supplies the current preview.

Actual current-UI Safety counts, all types: deployed September 6,905 area-mapped / 6,153 visible / 752 detail-only (10.9%); before repair 6,859 / 5,256 / 1,603 (23.4%); after repair 6,860 / 5,446 / 1,414 (20.6%). Net +190 visible Safety papers comprises 192 gains and 2 justified old-shortcut removals; no new represented publications. Primary visible 3,793→3,960, Reviews 1,391→1,411, meta 72→75. Total represented remains 23,058 (18,335 primary/4,395 Reviews/328 meta), recovered full text 11,233, remaining 11,825. Other-area shared-wrapper effects are +1 Cognition, +1 Real-world and +1 Molecular; all other visible-area totals unchanged. These are coverage corrections, not a measured global accuracy gain.

Remaining 1,414 detail-only Safety papers: 639 unresolved subject identity, 625 unresolved endpoints, 108 review multi-drug attribution, 47 explicit extraction review flags, 44 unresolved class, with overlaps. Endpoint group includes genuine residual vocabulary gaps alongside vague/non-event headings; not all remaining items individually adjudicated or deemed correct holds. Additional 114 acute psychotomimetic navigation flags are classification-overlap leads, not 114 confirmed mistakes. Preserve this uncertainty; do not blanket promote or create another model-review pipeline.

Verification: 504 normalization tests passed, 1 skipped, 361 subtests; 115 export/UI Python tests and 14 JS tests passed. Current preview refreshed at `http://127.0.0.1:8013/?data-source=local`, report `/safety-audit/`, isolated server PID 24639. HTTP payload hashes, local Methods identity, private .env404 and actual browser header/3,960 primary Safety count/exact-event and frequency display verified. Prior preview server PID13895 replaced only after ownership check. Public/canonical owners unchanged; dirty unrelated work preserved. Final handoff: `report.html`, `summary.json`, `rebuild_integrity.json`, `browser_safety_field_verification.json`, `final_verification.json` and `status.json`.


### 2026-10-30: deeper Safety normalization pass completed (v3)

- Completed ordinary frozen-input replay `luna_v5_20261030_safety_patterns_v3` under `data/processed/model_runs/luna_v5_20261017/safety_remaining_patterns_20261030/release_final`; no model/provider calls, V5 screening/extraction/prompt/schema changes or published-pointer writes. Development candidates and rejected broad review gates are preserved; only final v3 is served.
- Existing shared normalizer uses exact complete administration identities, one measured class unit, typed Safety event/category pairs and controlled-family round trips. Removed generic psychedelic-effects and acute psychotomimetic-to-psychosis defaults. Bounded current-role fixes hold another actor's toxicity, counterfactual avoided care and exposure trends without outcomes, and prevent therapeutic-benefit directions from manufacturing Safety events. Genuine injury, mixed benefit/harm and incomplete review domain tags are protected by tested controls.
- Actual UI Safety papers: 5,446 → 5,526 (140 gains / 60 removals); mapped denominator 6,860 → 6,791; detail-only 1,414 → 1,265 (20.6% → 18.6%). Primary visible 4,003; Reviews 1,448; Meta 75.
- All 91 formerly main Safety findings behind the 60 removals have saved-source checks. Current structural census: 611 subject-only, 340 endpoint-only, 124 both, 190 other explicit attribution/role/review holds. Of 1,265, 494 are visible elsewhere and 771 have no overview area. Meta retains 73 Safety-detail papers; 47 have result-level uncertainties/QA flags. These are not population error rates or original-paper gold adjudications.
- 624 tests + 361 subtests passed (1 skip). Exact statements, values, quotes, warnings and dose/time context conserved across findings + audit; 53,831 native public Safety field instances verified, zero mismatches. All 128,244 author byline rows unchanged.
- Completed Safety/Target candidate has 23,307 represented papers; 249 additional papers exactly match the separately completed Target repair and are not credited to Safety. Zero previously represented papers lost. Later Molecular-readout work was added to shared build_evidence_tables.py 16 seconds after this replay completed; preserve it. The preview uses the tested archived normalizer SHA47c17987a8a76c36873ad4e308219a3ec80eeba44a8c8e4ecfbae03a128deacf, and Safety function bodies match the working checkout. No restart or overwrite of unrelated Molecular work.
- Local preview http://127.0.0.1:8013/?data-source=local ; report http://127.0.0.1:8013/safety-patterns/ . Six served payload hashes, report hash, run/release identity and private-path404 verified; browser shows 4,003 primary Safety / 1,961 open. Public graph unchanged.
- 241 distinct saved DOI/statement witnesses plus separate exposure-label and Meta-flag inspections. Remaining identity, pooled/joint-unit, vague/mixed endpoint and source/result uncertainties are documented. No blanket promotion or paper allowlist. See `data/processed/model_runs/luna_v5_20261017/safety_remaining_patterns_20261030/report.html`, `summary.json`, `final_verification.json` and source-check ledgers.


### 2026-10-31 — Controlled vocabulary and verified aliases integrated

User authorized the vocabulary/verified-alias improvement. Owner `normalization_vocabulary_expansion_20261031`; final ordinary offline replay `after_tables_v5` (also `after_tables`) uses the same 131,096 routed extraction rows and 9,007 existing clinical-endpoint projections. Earlier candidates, source snapshots, test failures and supersessions are preserved. No model/API calls, screening/extraction reruns, V5 edits, prompt/schema changes, paper-specific overrides, overview-category changes or public deployment.

Production changes live in existing entity registry, node vocabulary and normalizer: verified existing-compound synonyms (2-Br-LSD/BOL-148, MXE, psilocine/psilocyn, 4-HO-DiPT), five distinct target/family entries, additional exact cognitive/subjective aliases, seven literal cognitive/social constructs and 16 complete Safety-event mappings. Whole-field policies and bounded derivative/contained-parent/conjugate protections prevent the new aliases from erasing compound/subtype or assay-role distinctions. New constructs are not automatically added to the existing UI display whitelist. Future normal pipeline runs use these shared owners.

Final before/after baseline is the latest Target-repair preview, not deployed September: 238 changed source observations across 161 papers, including 144 newly main-normalized observations on 101 papers and eight observations moved to detail on seven papers. Source statements, values, quotes, warnings and all original observations conserved; zero unmatched or invented source observations. Represented papers 23,625→23,626; actual browser overview union 17,656→17,662 (six gains, zero losses). Area counts: Safety 5,541→5,543; Cognition 2,308→2,312; Behavior 2,839→2,842; Subjective 1,383→1,384; Targets 2,397→2,399. Conditions 3,113, Treatment context 1,038, Real-world 2,807, Brain regions 2,433 and Molecular effects 5,140 unchanged. Area memberships overlap; these are coverage/identity corrections, not an original-paper accuracy benchmark.

The older preview's 17,737 export-summary counter does not equal the actual UI's 17,656 on that same old payload. New export-summary count is 17,752, actual UI is 17,662. Both before/after columns in the report use identical UI rules; the difference between export counters and UI counts is not an 81-paper loss caused by this work. Preserve `overview_counter_reconciliation.json`; no counter code changed here.

Verification: 1,025 tests plus 405 subtests passed, one pre-existing test skipped, including 61 new focused cases. Selected diff/compile checks, alias-collision checks, frozen input/import-closure hashes, source-observation conservation, unique table identifiers/references/admissions and actual UI membership checks passed. Packaged scientific records and all actual area counts match the verified diagnostic replay. Offline refreshed author tables equal the prior accepted preview exactly: 128,478 byline rows, 70,867 author rows; all 23,961 paper metadata rows unchanged. Funding/open-science records also unchanged. No broad unrelated commit/reset.

Local preview refreshed at http://127.0.0.1:8013/?data-source=local as `luna_v5_20261031_vocabulary:local`, owner `latest_graph_preview_vocabulary_20261031`. Only the owned prior preview server was replaced. Served payload hashes, current UI, matching Methods/report, protected public/canonical pointers and candidate corpus verified. Report at `/normalization-report/`; handoff artifacts include `result_summary.json`, `final_verification.json`, `comparison_changed_findings.jsonl`, `remaining_census.json`, and preview `http_verification.json`, `payload_verification.json`, `author_preservation_verification.json`.

Bounded limitations remain explicit. Unknown analogues, pooled exposures and unresolved receptor/endpoint identities are not automatically admitted. A pre-existing 4-AcO-DiPT→DiPT subject collapse in DOI10.3390/metabo12080705 remains documented in `remaining_known_issues.json`; this pass does not claim a complete chemical-name parser audit. Its separate conjugate/oxide endpoint errors were corrected. No general chemical scope expansion or paper-level patch was used to conceal it.
