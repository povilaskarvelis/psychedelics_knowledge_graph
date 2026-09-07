# Analyze workflows

Explore remains the interactive graph and its path to findings and papers. Analyze is one continuous view: existing publication profiles, trends, entities and overlap charts, followed by a finer-grained Evidence coverage heat map.

There are no Landscape/Compare/Evidence task tabs, comparison builder, saved-question controls, or study-characteristics/results tables. The experimental workspace remains available on `codex/analyze-workspace-experiment`.

## Scope and coverage

The heat map follows the main Analyze controls: entity and focus, research area, topic, publication type, access availability, and years. The Open access option uses accessible full text as the project’s operational proxy for open access. All three paper types remain included when All papers is selected. Dates remain stable when switching to a paper type or entity with fewer publication years.

Rows and columns can represent populations/models, study design, outcomes/measures, comparators, follow-up, experimental systems, assays/methods, topics, research areas, or compounds. The two axes must differ. Each axis has a category search that narrows the displayed labels without filtering the main charts or changing the heat-map counts. Up to 18 rows and 12 columns appear at once; category search makes less common categories accessible. Selected cells from shared links remain visible outside those leading categories.

Cells count unique publications containing both characteristics across their matching findings. Multiple findings in one publication do not multiply its count. This is report-level co-coverage, not an association between characteristics or a pooled treatment comparison. Missing metadata is shown as Not recorded; zero means no indexed reports match that cell in the current scope. The graph corpus does not include every finding in every source paper.

Clicking a nonzero cell opens the matching findings and bibliography using the existing source-paper workflow. Clearing a cell or changing its axes/category search clears that drill-down. No separate evidence table is added.

## Sharing

The workspace header keeps the Explore/Analyze choice together on the left and a quieter Share view action on the right. The action is available in both modes without reading as a third workspace tab. Explore links preserve the category, paper/access filters, date range, and selected graph node or relationship. Analyze links preserve the section, entity focus, research-area/topic scope, paper/access filters, date range, chart configuration, coverage axes/searches, and selected result or coverage cell. Reopening a link restores that state without automatically scrolling away from the main view.

Major navigation creates browser-history entries, while filter tuning updates the current entry. Back and Forward therefore move between meaningful views without adding an entry for every small adjustment. Copied URLs use the canonical public address and include a schema version and graph release; ordinary browsing preserves local preview parameters. Links query the current corpus rather than freezing a historical dataset, and an older-release link displays a notice when it is rendered against newer data.

Older task links resolve to the single Analyze view. Old comparison selections and detailed evidence filters are ignored rather than silently narrowing the overview. Existing browser-local saved-question data is not deleted, but the simplified view does not expose it.

## Verification

Run `node --test tests/test_research_model.cjs tests/test_view_state.cjs` for counting, category-search behavior, scope filtering, shared-state validation and restoration, legacy-link handling, and cell drill-down. Build the preview with `bash scripts/build_site.sh`; no corpus regeneration or schema migration is needed.
