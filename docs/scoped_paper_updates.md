# Updating selected papers without rerunning the whole extraction

Use `pipeline/update/run_scoped_paper_update.py` whenever an upstream fix changes
one paper or a DOI list. Typical reasons include:

- a wrong full-text artifact was replaced;
- a paper changed from full-text to abstract-only, or the reverse;
- a record is now excluded by prescreening;
- metadata, an abstract, a prompt, or a schema changed; or
- selected papers should be re-extracted after a correction.

The workflow has one rule: every DOI in the update list is removed from the
previous active raw outputs and converted evidence before current replacements
are added. Therefore:

- newly excluded records leave no stale extraction or KG rows;
- re-extracted records overwrite all of their previous extraction/evidence rows;
- an abstract-only replacement cannot retain claims from an old full-text route;
- a failed or incomplete replacement cannot be promoted; and
- every DOI outside the list is preserved unchanged.

There is one active extraction pointer and one active graph pointer. Temporary
batch files and the versioned candidate directory are staging artifacts, not a
second active history layer.

## 1. Make the upstream correction

Edit the canonical source for the decision. Examples are the candidate corpus,
prescreen rules/curation, full-text artifact store, manual access overrides, or
extraction prompt/schema. Do not patch KG rows directly.

Create a newline-delimited DOI file:

```text
10.1000/example-one
10.1000/example-two
```

## 2. Prepare the scoped update

```bash
UPDATE_ID=paper_fix_YYYYMMDD
DOI_FILE=path/to/update_dois.txt

python pipeline/update/run_scoped_paper_update.py prepare \
  --update-id "$UPDATE_ID" \
  --doi-file "$DOI_FILE" \
  --refresh-derived
```

`--refresh-derived` does not call a model. It runs, in order:

1. DOI-scoped deterministic prescreening, merged into the canonical decision table;
2. a full deterministic route-table rebuild, which also refreshes route status in
   `candidate_papers.parquet`;
3. a full article-text-input rebuild; and
4. a full extraction-task rebuild.

The route/article/task rebuilds are intentionally global because they are cheap
and deterministic. Only the expensive model extraction is scoped.

Prepared files are written under
`data/processed/paper_updates/$UPDATE_ID/`, including:

- `update_manifest.json`: counts, source hashes, and replacement audit;
- `scope_dois.txt`: the exact tombstone/replacement boundary;
- `ready_tasks.jsonl`: every runnable current task in the scope;
- `ready_tasks_primary.jsonl`, `ready_tasks_reviews.jsonl`, and
  `ready_tasks_meta_analyses.jsonl`: optional batch splits;
- `no_current_task_dois.txt`: records now absent from the retained route/task set;
- `no_runnable_task_dois.txt`: records that get no model replacement.
- `scope_status.csv`: one row per DOI showing replacement versus deletion-only
  disposition, current task families/text modes, and old output/evidence counts.

Review `update_manifest.json` before spending model calls. `prepare` does not
change the active extraction or KG.

If the deterministic layers were already rebuilt and verified, omit
`--refresh-derived`. Use `--overwrite` only to regenerate the same prepared
update after checking that no needed batch output lives in its update directory.

To run one literature family now while explicitly deferring the others, filter
the effective DOI scope during preparation. For example, this keeps primary
papers plus deletion-only records, while leaving review and meta-analysis DOIs
untouched:

```bash
python pipeline/update/run_scoped_paper_update.py prepare \
  --update-id primary_fix_YYYYMMDD \
  --doi-file path/to/all_affected_dois.txt \
  --only-task-group primary \
  --include-no-runnable
```

The command refuses a DOI that has runnable tasks in both the selected family
and another family, because replacement is DOI-wide.

## 3. Extract only the prepared tasks

The synchronous runner can use `ready_tasks.jsonl` directly. For the Gemini
Batch API, keep batch work in a separate patch run and prepare one non-empty
family file at a time:

```bash
PATCH_RUN="${UPDATE_ID}_extraction"
UPDATE_DIR="data/processed/paper_updates/${UPDATE_ID}"

python pipeline/extract/run_route_extraction_batch_api.py prepare \
  --run-id "$PATCH_RUN" \
  --batch-id primary \
  --input-jsonl "$UPDATE_DIR/ready_tasks_primary.jsonl" \
  --batch-size 100000

python pipeline/extract/run_route_extraction_batch_api.py submit \
  --run-id "$PATCH_RUN" \
  --batch-id primary
```

Repeat `prepare` and `submit` with batch IDs `reviews` and `meta_analyses` for
their non-empty task files. For each submitted batch:

```bash
python pipeline/extract/run_route_extraction_batch_api.py status \
  --run-id "$PATCH_RUN" --batch-id primary

python pipeline/extract/run_route_extraction_batch_api.py download \
  --run-id "$PATCH_RUN" --batch-id primary

python pipeline/extract/run_route_extraction_batch_api.py parse \
  --run-id "$PATCH_RUN" --batch-id primary --skip-rebuild
```

`--skip-rebuild` is important here: downstream replacement happens only after
all scoped task families are complete and validated by the updater.

## 4. Finalize a candidate replacement

After all prepared tasks have a successful current output:

```bash
python pipeline/update/run_scoped_paper_update.py finalize \
  --update-id "$UPDATE_ID" \
  --patch-outputs \
    "data/processed/extraction/routed_runs/${PATCH_RUN}/route_extraction_outputs.jsonl"
```

Finalize refuses to proceed if:

- any prepared runnable task lacks a successful output;
- a task ID, route ID, DOI, input fingerprint, domain, task manifest, route
  table, or active base snapshot changed since preparation;
- a successful output is not one of the prepared current tasks; or
- a non-runnable scoped DOI would retain a stale output.

On success it creates a versioned candidate at
`data/processed/extraction/routed_runs/$UPDATE_ID/`:

```text
candidate outputs = active outputs outside DOI scope + current patch outputs
candidate evidence = active evidence outside DOI scope + evidence converted from current patch outputs
```

The active KG still has not changed at this point. Inspect
`data/processed/paper_updates/$UPDATE_ID/finalize_report.json` if desired.

For an update containing only exclusions and no runnable tasks, omit
`--patch-outputs`; finalize will produce the correctly reduced candidate.

## 5. Promote the validated candidate

```bash
python pipeline/update/run_scoped_paper_update.py promote \
  --update-id "$UPDATE_ID"
```

Use `--offline` if author resolution should use only the existing OpenAlex
cache. Promotion:

1. rebuilds the normalized KG and author tables from the candidate evidence;
2. builds graph/detail payloads without activating them early;
3. activates the new graph pointer;
4. rebuilds the Methods projection and `dist/` public-site bundle; and
5. writes `data/processed/extraction/active_routed_run.json` only after success.

If a downstream build fails, the previous active graph pointer is restored and
the active extraction pointer is not changed. Re-run the failed promotion after
fixing the cause; do not edit candidate rows by hand.

## Important operational boundaries

- Put every DOI whose old output may be stale in the update list, including
  newly excluded records. The DOI list is both the deletion and replacement
  boundary.
- Never finalize only one domain or paper-type family for an affected paper.
  Finalize requires the full current runnable task set for the entire DOI scope.
- Do not use `build_extraction_routes.py --doi-file ...` with the canonical
  route output. Its scoped mode produces a scoped table; the updater deliberately
  performs the full deterministic route rebuild instead.
- Prompt and schema file contents are part of the task input fingerprint. A
  prompt/schema change generates new task IDs and cannot silently reuse an old
  output.
- Raw provider response logs may remain for debugging, but they are never an
  active pipeline input. Active outputs and evidence are determined solely by
  `active_routed_run.json` and `graph_payload_active.json`.
