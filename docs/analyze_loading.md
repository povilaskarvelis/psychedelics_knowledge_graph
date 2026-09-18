# Analyze loading

Analyze has a separate finding-level dataset. It retains the fields used by the
current charts, entity scopes, bibliography, and coverage axes, but omits detailed
quotations, estimates, doses, locators, funding metadata, and proposition IDs.
Structured author records retain their identity and display-name aliases.
Filtering still runs on individual findings; no findings are merged or sampled.

`build_analysis_payload.py` builds three run-length column payloads, the study
index, and full-evidence chunks of 512 original rows. Every filename contains a
content hash. A compact row's original position identifies its exact detailed
finding. The local preview and R2 publisher use the same builder. The publisher
uploads and verifies the new objects before replacing the active pointer.

The browser keeps compact Analyze data separate from Explore's complete-source
flags and stores. Opening Analyze fetches the three compact payloads and the
worker's study index. Decoding yields between batches. Background preloading
starts after Explore's initial data load and respects the existing data-saver
policy; hover/focus can start it earlier. Coverage calculates only its selected
axes and caches calculated fields.

Finding cards request full evidence when they approach the viewport. Requests
for the same chunk are shared, at most four chunks load concurrently, and the
in-memory cache retains at most 24 chunks. A failed request can be retried.
The bibliography needs no evidence-chunk request. Explicit full-text finding
search keeps its existing full-source loading behavior so search coverage is not
silently reduced. Old releases without compact payloads use the original loading
path. Skeleton panels and status messages reserve space during first load;
reduced-motion preferences disable the loading animation.

## Validation on 2026-09-17

Release: `living_update_20260916_fulltext_recovery_complete`.

| Data | Original detail payloads | Compact Analyze payloads |
| --- | ---: | ---: |
| Uncompressed JSON | 80,466,333 bytes | 30,111,547 bytes |
| Local gzip estimate | 18,204,860 bytes | 8,186,491 bytes |

The unchanged analysis index is approximately 10.6 MB uncompressed. Including it,
the initial Analyze data volume is about 55% smaller. These are payload sizes,
not a claim about end-to-end load time or the CDN's negotiated compression.

All 99,100 original findings were checked against decoded compact records using
the browser's actual labelers: all ten coverage axes, paper identity, author
identities, compound membership, hidden/admitted state, and relation labels match.
Browser checks found identical rendered Overview, Compounds, Authors, and Journals
charts. Opening a coverage cell showed complete quotations and citations while
fetching one evidence chunk. The initial Analyze request log contained no full
detail datasets. Shared coverage state and Explore/Analyze navigation were checked.

To repeat parity checking, start a local preview and save its `/__preview__/active.json`
response to a file, then run from the repository root:

```sh
node scripts/check_analysis_parity.cjs data/processed/graph_payload_runs/RUN_ID /tmp/analysis-pointer.json
```

Run the focused tests:

```sh
node --test tests/test_analysis_loading.cjs tests/test_analysis_payload.cjs tests/test_research_model.cjs tests/test_evidence_facets.cjs tests/test_view_state.cjs
python -m pytest tests/test_build_analysis_payload.py tests/test_build_analysis_index.py tests/test_publish_browser_payload_r2.py tests/test_preview_server.py tests/test_ui_graph_categories.py
```

The approach follows established guidance on
[off-main-thread work](https://web.dev/articles/off-main-thread),
[reducing startup payloads](https://web.dev/learn/performance/code-split-javascript),
and [breaking up long tasks](https://web.dev/articles/optimize-long-tasks).
