# Analyze workflows

Explore remains the interactive graph and its path to findings and papers. Analyze has three tasks that share research area, topic, publication type, source-text depth, years, and evidence filters:

| Task | Purpose | Main interactions |
| --- | --- | --- |
| Landscape | Understand activity and research coverage | Existing overview, entity profiles, publication trends, and coverage |
| Compare | Compare the composition of research literatures | Choose up to four compounds, authors, journals, areas, topics, or pinned evidence sets; compare counts or shares; inspect contributing reports |
| Evidence | Examine methods, results, and limitations | Filter findings, inspect publication characteristics or individual results, explore coverage, and open source findings |

## Scope and counting

- Analysis uses the normalized findings admitted to the main graph. It does not claim to cover every result in every source paper.
- Evidence filters apply together to each finding before publication aggregation. A design recorded on one finding and an outcome recorded on another do not satisfy a combined finding-level filter.
- A source report is one publication under the existing publication identity rules. It is not necessarily an independent trial, dataset, or participant sample.
- Study characteristics group matching findings by publication. Results and limitations retain one row per indexed finding; a result may appear in more than one graph projection.
- Samples are displayed as extracted, never summed. The minimum-sample filter uses primary-study sample metadata and excludes unknown sizes and secondary-literature totals.
- A report counts once in each profile category it covers. Categories and comparison groups can overlap, so shares need not sum to 100%.
- Coverage cells count reports containing both selected characteristics across their matching findings. Co-coverage does not establish an association, paired measurement, or treatment comparison. Clicking a cell shows all matching findings within those reports.
- “Not recorded” means missing metadata. A zero cell means no matching indexed reports in the chosen scope. Neither establishes an absence of research outside this corpus.
- “Full-text extraction” describes the text used by the extraction pipeline. It is not a legal open-access or licensing classification. Analyze defaults to all source text.
- Author profiles use the first/last-author metadata currently provided by the corpus; they are not a complete coauthorship analysis.

Pinned evidence sets keep their own scope, dates, evidence filters, and coverage selection. Shared Compare controls can narrow every set further. Adding sets with different dates expands the shared date range to encompass their saved ranges. Comparison profiles describe separate literatures; they do not pool effects or establish comparative efficacy.

## Results and appraisal

Results show extracted support, estimates, population/system, exact comparator, timepoint, and source locator. Source risk-of-bias, certainty, heterogeneity, and subgroup information appears when recorded. Extracted notes and uncertainty remain separate from source appraisal. Missing appraisal is explicit; the UI does not calculate a quality score or infer certainty from sample size, citations, publication counts, or reporting signals.

The reporting and reproducibility panel remains available as a disclosure below the evidence table. Study rows, comparison cells, and overlap actions open the existing Findings and Bibliography surfaces, preserving source-paper links.

## Explore handoff

“Analyze this graph scope” opens Evidence with the graph subject, research area/topic, dates, paper type, and source-text scope. Generic graph subjects remain valid filters even when they are not individual compounds in the Analyze entity list. A detail-chart selection is not silently approximated with inferred facets: the UI explains that Evidence filters can refine the transferred graph scope.

Switching between Explore and Analyze retains each workspace. Analysis tasks share the year range instead of resetting it when changing entity type or publication type. A selected area/topic with no matches stays selected and displays zero instead of widening the query automatically.

## Saved questions and links

The page URL carries the analysis task, scope, evidence filters, comparison selections, and selected coverage cell. “Copy question link” shares this query against the recipient's current corpus; it does not freeze the dataset.

Up to ten questions can be saved in browser local storage. Each stores a query and a compact baseline fingerprint per matching publication. Reopening a question compares the current matching evidence with the saved baseline and reports:

- publications newly matching the question;
- publications whose matching extracted content changed;
- publications no longer matching the question.

New and changed reports can be inspected, and the user can accept the current evidence as a new baseline. Changes may reflect indexing, corrections, extraction updates, or a different available corpus. Removed reports are counted but cannot be opened from the current dataset. Baselines do not store full historical findings.

Saving requires no account or backend. Questions remain in that browser and origin; clearing browser data removes them. Checks run when a question is reopened. There are no scheduled checks, cross-device synchronization, or background notifications.

## Implementation and verification

- `ui/research-model.js`: publication aggregation, finding filters, report co-coverage, and snapshot comparison; browser and CommonJS export.
- `ui/research-analysis.js`: integration with existing domain labelers, task rendering, scope transfer, comparisons, and saved questions.
- `ui/research-analysis.css`: workspace styling, responsive controls, and scrollable tables.
- `scripts/public_site_files.txt`: includes the three new assets in the static site.

Run the focused model tests with `node --test tests/test_research_model.cjs`. They cover same-finding filter conjunction, report deduplication, overlapping categories, missing metadata, sample thresholds, coverage selection, saved-state validation and restoration, pinned date/type scope, and change baselines.

Build and preview with `bash scripts/preview_site.sh public`, which serves the local UI against the published data. No corpus regeneration or schema migration is needed.
