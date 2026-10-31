> **19 October update:** the complete browser queue has been reviewed. Usable article text is now available for **10,855 / 22,451** eligible papers; **1,563** entries remain for manual recovery. Current provisional extraction inputs contain **37,506 tasks**, estimated at **$28.99 Batch** with a **$40.49 planning allowance**. No extraction jobs submitted. [Current recovery report](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/docs/evaluation/luna_fulltext_recovery_2026-10-18.md).

# Refreshed Luna extraction inputs and cost — 18 October 2026

**PROVISIONAL — superseded readiness claim:** this snapshot reused existing local files and did not complete open-access recovery after Luna screening. Extraction is on hold pending that recovery and a new input/cost freeze. The figures below describe the earlier local-only snapshot.

**Local-only scope: 37,584 calls across 22,496 papers. Estimated Batch API cost: $27.35; allow approximately $38.12 for cache-write charges and variation/retries.** The current project budget has $79.91 available after logged spend and held reservations. No extraction jobs were submitted and no new model calls were made for this refresh.

| Extraction lane | Papers | Calls | Expected Batch cost |
|---|---:|---:|---:|
| Primary studies | 18,058 | 33,146 | $20.88 |
| Guidelines/consensus | 35 | 35 | $0.05 |
| Reviews | 4,053 | 4,053 | $5.70 |
| Meta-analyses | 350 | 350 | $0.72 |
| **Total** | **22,496** | **37,584** | **$27.35** |

Primary papers can have several assigned domain extractions; the other lanes use one paper-level task each. All tasks are ready and have unique identities. There are 16,035 article-text calls and 21,549 abstract calls. The model remains GPT-6 Luna, low reasoning, with the current production prompts and schemas. The rejected prompt candidate is not used.

## What the refresh changed

- Rebuilt the article packets from the current verified source artifacts using the existing primary-study versus full-article section-selection methods. The old shared packet file dated from September. There are now 9,253 selected article packets, each with source identity and content hashes.
- Fixed a task-builder metadata lookup that silently skipped **2,102 tasks for 1,516 papers**: their abstracts existed in the canonical candidate table but were absent or blank in the enrichment cache. Task construction now follows routing's existing precedence: populated candidate metadata wins, and enrichment fills gaps. Explicit custom inputs remain isolated unless a candidate input is supplied.
- Made another 330 primary/guideline article tasks, 64 review tasks and six meta-analysis tasks ready through the packet refresh. Two earlier abstract tasks were removed by confirmed conference-format exclusions. Relative to the previously prepared inventory, ready calls rise from 35,084 to **37,584**.
- Preserved the completed Luna screening table byte for byte. Only the two newly applicable conference-format decisions were projected from the post-retrieval ledger into downstream selection; earlier topic decisions were not reused to screen this generation.
- Froze the task files, article packets, bibliography inputs and current prompt/schema files. Previous input files are backed up alongside the refresh. The large raw and frozen input files remain in the project's local data store.

All 23,620 raw Luna inclusions reconcile to the following downstream dispositions:

| Current disposition | Papers |
|---|---:|
| Ready for extraction | 22,496 |
| Context-only / no extraction under existing profiles | 894 |
| Excluded by confirmed post-retrieval eligibility decisions | 168 |
| Duplicate DOI aliases | 62 |
| **Total Luna inclusions** | **23,620** |

## How the cost was calculated

Official GPT-6 Luna Batch rates are **$0.05 input and $0.25 output per million tokens** at short context; above 272,000 input tokens they become **$0.10 input and $0.375 output** for the full request. Cache writes are 1.25 times the input rate. The estimate applies Batch rates directly, with no second discount. [Official pricing](https://developers.openai.com/api/docs/pricing) · [Luna pricing and context notes](https://developers.openai.com/api/docs/models/gpt-6-luna).

Input estimates use the actual refreshed production request contents, instructions and native schemas. Local tokenization uses `o200k_base`, calibrated against 360 metered current-prompt Luna calls. The mean schema/envelope adjustment is approximately −112 tokens, with residuals from −135 to −88 before that adjustment. These are calibrated local estimates, not exact server-side token counts. Production request bodies were independently reconstructed and matched against the cost manifest for every primary contract/depth combination and both synthesis depths.

Output estimates include reasoning tokens. Primary estimates use observed output length by domain and text depth from those 360 current-prompt calls; reviews and meta-analyses use the existing 40-call family pilots. Guidelines use review output length as a proxy and account for about five cents. Current input lengths are priced individually, including the one long-context meta-analysis request. No estimated input exceeds Luna's 922,000-token input limit.

| Cost component | Estimate |
|---|---:|
| Uncached input | $12.61 |
| Output, including reasoning | $14.74 |
| **Expected extraction cost** | **$27.35** |
| **Planning allowance** | **$38.12** |

The allowance first applies a 25% premium to input for possible cache writes, then adds a further 25% to the combined input/output cost for variation and retries. It is a budgeting assumption, not a confidence interval or guaranteed ceiling. Cache-read savings are not assumed. If every request consumed its entire configured output allowance, the theoretical total would be much higher (about $168); actual submission remains subject to the shared $100 budget guard and per-job reservations.

The logged project ledger currently shows $19.45 settled token-based spend and $0.64 held for unreconciled attempts, leaving **$79.91 of the authorized $100**. Adding the extraction planning allowance puts the project at approximately **$58.21 including those held reservations**, below the budget. These figures describe the project ledger, not the API account's prepaid credit balance or a reconciled invoice.

## Submission plan and checks

The local plan uses **10 substantial batches**, balanced by request size: seven primary/guideline batches of approximately 4,740 requests each, two review batches of approximately 2,027 each, and one 350-paper meta-analysis batch. Each plan stays below 5,000 requests and 148 MB estimated JSONL, leaving headroom below the 150 MB local target. Exact prepared bytes and budget reservations must pass the submission checks. No remote jobs were created.

Verification confirms unique task IDs; current Luna screening provenance for every ready paper; no retired-provider model provenance; nonempty, ready sources; unchanged screening and contract hashes; and matched production request reconstruction. The metadata fix and existing route/transport behavior pass **82 targeted tests**. Remaining scientific normalization limitations from the previous audit still apply; this refresh does not claim to resolve them.

[Versioned summary and verification](luna_extraction_ready_costs_2026-10-18/README.md) · [Frozen input manifest](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/model_runs/luna_v5_20261017/extraction_refresh_20261018/input_freeze.json) · [Cost calculation](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/model_runs/luna_v5_20261017/extraction_refresh_20261018/cost_projection.json) · [Task-level cost manifest](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/model_runs/luna_v5_20261017/extraction_refresh_20261018/cost_records.jsonl) · [Local batch plan](/Users/frank/Library/CloudStorage/Dropbox/projects/psychedelics_knowledge_graph/data/processed/model_runs/luna_v5_20261017/extraction_refresh_20261018/batch_plan.json).
