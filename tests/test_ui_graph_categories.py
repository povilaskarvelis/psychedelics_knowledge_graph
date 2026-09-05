from colorsys import rgb_to_hls
import json
from pathlib import Path
import re
import tomllib


ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "ui" / "app.js"
INDEX_HTML = ROOT / "index.html"
STYLES_CSS = ROOT / "ui" / "styles.css"
ANALYSIS_WORKER_JS = ROOT / "ui" / "analysis-worker.js"
NETLIFY_TOML = ROOT / "netlify.toml"
GRAPH_VIEW_CONTRACT = ROOT / "schema" / "graph_view_contract.json"


def test_payload_derived_labels_are_escaped_before_html_insertion() -> None:
    source = APP_JS.read_text(encoding="utf-8")

    assert '${escapeHtml(label)}</span>`' in source
    assert "<h3>${escapeHtml(relation)}</h3>" in source
    assert "<strong>${escapeHtml(compound)} → ${escapeHtml(target)}</strong>" in source
    assert "<strong>${escapeHtml(compound)}</strong>" in source
    assert "<strong>${escapeHtml(target)}</strong>" in source


def test_public_site_has_non_disruptive_browser_security_headers() -> None:
    config = tomllib.loads(NETLIFY_TOML.read_text(encoding="utf-8"))
    wildcard = next(header for header in config["headers"] if header["for"] == "/*")
    values = wildcard["values"]

    assert values["X-Content-Type-Options"] == "nosniff"
    assert values["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in values["Content-Security-Policy"]


def test_real_world_use_contains_exposure_contexts_without_a_separate_graph_view() -> None:
    contract = json.loads(GRAPH_VIEW_CONTRACT.read_text(encoding="utf-8"))
    views = {view["id"]: view for view in contract["views"]}

    assert views["public_health_measure"]["object_kinds"] == [
        "public_health_measure",
        "exposure_context",
    ]
    assert all(view["label"] != "Use contexts" for view in views.values())


def test_real_world_topic_facets_include_social_context_without_a_catch_all() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    topic_order = source.split("const PUBLIC_HEALTH_TOPIC_ORDER = [", 1)[1].split("];", 1)[0]
    facet_labeler = source.split("function publicHealthTopicFacetLabel", 1)[1].split(
        "function publicHealthUseContextFacetLabels",
        1,
    )[0]

    assert '"Culture, religion & social context"' in topic_order
    assert '"Other real-world topics"' not in topic_order
    assert 'return canonical || "";' in facet_labeler


def test_molecular_effects_category_is_kind_based_across_source_domains() -> None:
    contract = json.loads(GRAPH_VIEW_CONTRACT.read_text(encoding="utf-8"))
    molecular = next(
        view for view in contract["views"] if view["id"] == "pathway_readout"
    )

    assert molecular["object_kinds"] == ["pathway_process", "biomarker_readout"]
    assert "domains" not in molecular


def test_graph_categories_load_from_the_versioned_shared_contract() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    init = source.split("async function init()", 1)[1].split("if (yearMinFilter)", 1)[0]

    assert 'GRAPH_VIEW_CONTRACT_PATH = "schema/graph_view_contract.json"' in source
    assert "await loadGraphViewContract()" in init
    assert init.index("await loadGraphViewContract()") < init.index(
        "loadGraphManifestStats()"
    )


def test_category_matching_reuses_precompiled_sets() -> None:
    source = APP_JS.read_text(encoding="utf-8")

    matcher = source.split("function claimMatchesEntityViewOption", 1)[1].split("function rightEntityLabel", 1)[0]
    assert "ENTITY_CATEGORY_OPTION_SPECS.get" in matcher
    assert "new Set(" not in matcher


def test_graph_bootstrap_does_not_wait_for_detail_payload() -> None:
    source = APP_JS.read_text(encoding="utf-8")

    bootstrap = source.split("async function renderCurrentGraphBootstrap", 1)[1].split(
        "async function loadCurrentClaimsAndRender", 1
    )[0]
    assert "await loadGraphBootstrapClaims(sourceKey)" in bootstrap
    assert "loadDetailBootstrapClaims" not in bootstrap


def test_graph_payload_uses_r2_by_default_without_silent_local_fallback() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    loader = source.split("function graphPayloadPointerCandidates", 1)[1].split(
        "function graphPayloadCandidates", 1
    )[0]
    config_loader = source.split("async function loadGraphPayloadConfig", 1)[1].split(
        "function loadGraphManifestStats", 1
    )[0]

    assert "https://data.psychedelicskg.com/browser/active.json" in source
    assert "if (localDataSourceRequested())" in loader
    assert "return [GRAPH_PAYLOAD_LOCAL_POINTER_URL]" in loader
    assert "return [GRAPH_PAYLOAD_PUBLIC_PREVIEW_POINTER_URL]" in loader
    assert "return [GRAPH_PAYLOAD_REMOTE_POINTER_URL]" in loader
    assert ".catch(() => ({}))" not in config_loader


def test_unpublished_local_graph_data_requires_an_explicit_localhost_query() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    selector = source.split("function localDataSourceRequested", 1)[1].split(
        "function graphPayloadPointerCandidates", 1
    )[0]

    assert "LOCAL_GRAPH_DATA_HOSTS.has(window.location.hostname)" in selector
    assert 'LOCAL_DATA_SOURCE_QUERY_PARAMETER = "data-source"' in source
    assert '=== "local"' in selector


def test_graph_payload_failures_are_not_converted_to_empty_datasets() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    loaders = source.split("async function loadGraphBootstrapClaims", 1)[1].split(
        "function routeNativeSourceKey", 1
    )[0]

    assert ".catch(() => [])" not in loaders
    assert "graphPayloadCandidates(config, path)" in loaders


def test_initial_load_shows_the_fast_graph_bootstrap() -> None:
    source = APP_JS.read_text(encoding="utf-8")

    init = source.split("async function init()", 1)[1].split("if (yearMinFilter)", 1)[0]
    assert "showGraphBootstrap: true" in init


def test_initial_dashboard_bootstrap_renders_before_full_detail_payload() -> None:
    source = APP_JS.read_text(encoding="utf-8")

    dashboard = source.split("async function renderCurrentDashboardBootstrap", 1)[1].split(
        "function canonicalOverviewBootstrapClaims", 1
    )[0]
    loader = source.split("async function loadCurrentClaimsAndRender", 1)[1].split(
        "function scheduleIdleTask", 1
    )[0]

    assert 'currentEntityViewKey() !== "condition_indication"' in dashboard
    assert "syncYearFilterControls(activeClaimsForMode(), true)" in dashboard
    assert "renderOverviewDetail(graphFiltered, allAccessGraphFiltered)" in dashboard
    assert loader.index("loadDashboardBootstrapClaims(sourceKey)") < loader.index(
        "renderCurrentGraphBootstrap"
    )
    assert loader.index("renderCurrentDashboardBootstrap") < loader.index(
        "ensureClaimsForCurrentView"
    )


def test_unfiltered_overview_always_uses_the_canonical_graph_bootstrap() -> None:
    source = APP_JS.read_text(encoding="utf-8")

    helper = source.split("function canonicalOverviewBootstrapClaims", 1)[1].split(
        "async function loadCurrentClaimsAndRender", 1
    )[0]
    render = source.split("function render()", 1)[1].split("function refreshMainViews", 1)[0]

    assert "graphBootstrapClaimsBySource.get(currentSourceKey())" in helper
    assert "if (yearRange.constrained) return null" in helper
    assert "claimLayer !== \"normalized\" || selected || detailGraphFilter" in helper
    assert "canonicalOverviewBootstrapClaims()" in render
    assert "buildGraph(canonicalBootstrap)" in render


def test_evidence_view_round_trip_renders_the_same_canonical_bootstrap() -> None:
    source = APP_JS.read_text(encoding="utf-8")

    switch = source.split("function switchEvidenceView", 1)[1].split(
        "function switchEntityView", 1
    )[0]
    bootstrap = source.split("async function renderCurrentGraphBootstrap", 1)[1].split(
        "function canonicalOverviewBootstrapClaims", 1
    )[0]

    assert 'showGraphBootstrap: claimLayer === "normalized"' in switch
    assert "cloneGraphSelection(selected || evidenceSelectionIntent)" in switch
    assert "evidenceSelectionRestorePending = Boolean(selected)" in switch
    assert "if (selected) requestGraphCenterAfterRender()" in switch
    assert "selected = null" not in switch
    assert "if (!filtered.length) return false" in bootstrap
    assert "normalizedCurrentSourceLoaded()) return false" not in bootstrap


def test_missing_cross_literature_focus_falls_back_with_an_explanation() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    html_source = INDEX_HTML.read_text(encoding="utf-8")
    styles = STYLES_CSS.read_text(encoding="utf-8")

    reconcile = source.split("function reconcileGraphSelection", 1)[1].split(
        "function disconnectCardsLoadObserver", 1
    )[0]
    fallback = source.split("function showGraphFocusFallback", 1)[1].split(
        "function rememberGraphSelection", 1
    )[0]

    assert "evidenceSelectionRestorePending && evidenceSelectionIntent" in reconcile
    assert "showGraphFocusFallback(evidenceSelectionIntent)" in reconcile
    assert "within the current filters" in fallback
    assert 'id="graphFocusNotice"' in html_source
    assert 'aria-live="polite"' in html_source
    assert ".graph-focus-notice[hidden]" in styles


def test_graph_selection_always_aligns_controls_below_the_sticky_header() -> None:
    source = APP_JS.read_text(encoding="utf-8")

    request = source.split("function requestGraphCenterAfterRender", 1)[1].split(
        "function runPendingGraphCenter", 1
    )[0]
    alignment = source.split("function centerGraphInViewport", 1)[1].split(
        "function updateSearchPlaceholder", 1
    )[0]

    assert "centerGraphAfterRender = true" in request
    assert "graphTopIsVisibleInViewport" not in source
    assert "graphScrollPositionAfterRender" not in source
    assert 'querySelector(".graph-toolbar")' in alignment
    assert 'querySelector("[data-site-header]")' in alignment
    assert "const controlsGap = 34" in alignment
    assert "graphToolbarTop - siteHeaderHeight - controlsGap" in alignment
    assert 'behavior: "smooth"' in alignment


def test_canonical_overview_svg_is_cached_across_background_detail_loading() -> None:
    source = APP_JS.read_text(encoding="utf-8")

    cache_key = source.split("function graphDomCacheKey", 1)[1].split(
        "function clearGraphDomCacheForSource", 1
    )[0]
    cache_clear = source.split("function clearGraphDomCacheForSource", 1)[1].split(
        "function rememberGraphDom", 1
    )[0]
    loader = source.split("async function loadRouteNativeEvidenceSource", 1)[1].split(
        "function currentSourceKey", 1
    )[0]

    assert 'graphStage === "bootstrap" ? "canonical" : claimArrayId(claims)' in cache_key
    assert "data.some((claim) => claim?.__graph_bootstrap)" in cache_key
    assert "preserveBootstrap && key.startsWith" in cache_clear
    assert "clearGraphDomCacheForSource(sourceKey, { preserveBootstrap: true })" in loader


def test_overview_dashboard_is_restored_from_prebuilt_dom_before_async_render() -> None:
    source = APP_JS.read_text(encoding="utf-8")

    cache = source.split("function overviewDetailCacheKeyForContext", 1)[1].split(
        "function renderOverviewDetail", 1
    )[0]
    switch = source.split("function switchEntityView", 1)[1].split(
        "async function fetchJsonFromCandidates", 1
    )[0]

    assert "createOverviewDetailCacheEntry" in cache
    assert "entry.container.replaceChildren" in source
    assert "detailBody.replaceChildren(...Array.from(entry.container.childNodes))" in cache
    assert "const detailRestored = restoreCachedOverviewDetail()" in switch
    assert "resetDetail: !detailRestored" in switch


def test_overview_dashboards_are_precomputed_only_for_an_intended_view() -> None:
    source = APP_JS.read_text(encoding="utf-8")

    prewarm = source.split("function scheduleOverviewDetailPrewarmForView", 1)[1].split(
        "function normalizedCurrentSourceLoaded", 1
    )[0]
    init = source.split("async function init()", 1)[1].split("if (yearMinFilter)", 1)[0]

    assert "scheduleIdleTask(" in prewarm
    assert "prewarmOverviewDetailEntry" in prewarm
    assert "ENTITY_CATEGORY_OPTIONS.forEach" not in prewarm
    assert "scheduleOverviewDetailPrewarm" not in init
    assert "preloadLikelyNextData" not in source


def test_dashboard_paints_before_findings_and_bibliography_render() -> None:
    source = APP_JS.read_text(encoding="utf-8")

    deferred = source.split("function scheduleDeferredSurfaceRender", 1)[1].split(
        "function scheduleRender", 1
    )[0]

    assert deferred.count("window.requestAnimationFrame") == 2
    assert deferred.index("renderOverviewDetail") < deferred.rindex("window.requestAnimationFrame")
    assert deferred.rindex("window.requestAnimationFrame") < deferred.index("renderCards")
    assert deferred.index("renderCards") < deferred.index("renderBibliography")


def test_route_native_detail_rows_are_not_legacy_deduplicated() -> None:
    source = APP_JS.read_text(encoding="utf-8")

    loader = source.split("async function loadRouteNativeEvidenceSource", 1)[1].split(
        "function currentSourceKey", 1
    )[0]

    assert "claimIdentity" not in source
    assert "dedupeClaims" not in source
    assert "claimStores.normalized.bySource[sourceKey] = enrichedItems" in loader


def test_initial_card_distribution_does_not_force_layout_per_card() -> None:
    source = APP_JS.read_text(encoding="utf-8")

    append_card = source.split("function appendCardToMasonryColumn", 1)[1].split("function renderCards", 1)[0]
    assert "index % columns.length" in append_card
    assert "getBoundingClientRect" not in append_card
    assert "updateCardsMasonryColumnHeight" not in source


def test_findings_search_does_not_rerender_the_graph_or_dashboard() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    html_source = INDEX_HTML.read_text(encoding="utf-8")
    styles = STYLES_CSS.read_text(encoding="utf-8")
    search_render = source.split("function scheduleFindingSearchRender", 1)[1].split(
        "function requestGraphCenterAfterRender", 1
    )[0]
    search_listener = source.split('if (searchInput) {', 1)[1].split('if (bibliographySearchInput)', 1)[0]

    assert "scheduleFindingSearchRender()" in search_listener
    assert "scheduleRender()" not in search_listener
    assert "renderCards(" in search_render
    assert "buildGraph(" not in search_render
    assert "renderBibliography(" not in search_render
    assert 'aria-controls="findingSearchOptions"' in html_source
    assert 'id="findingSearchOptions" role="listbox"' in html_source
    assert "renderFindingSearchOptions()" in search_listener
    assert "FINDING_SEARCH_DEBOUNCE_MS = 180" in source
    assert 'input[type="search"]:focus-visible' in styles
    assert "box-shadow: none" in styles.split('input[type="search"]:focus-visible', 1)[1].split("}", 1)[0]


def test_analysis_entity_search_is_browseable_before_typing() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    matches = source.split("function explorerSearchMatches", 1)[1].split(
        "function explorerSearchOptionMarkup", 1
    )[0]
    options = source.split("function renderExplorerSearchOptions", 1)[1].split(
        "function selectExplorerSearchEntry", 1
    )[0]
    listeners = source.split('if (explorerSearchInput) {', 1)[1].split(
        'window.addEventListener("resize"', 1
    )[0]

    assert "if (!normalizedQuery)" in matches
    assert "right.studyCount - left.studyCount" in matches
    assert "EXPLORER_SEARCH_OPTION_BATCH_SIZE = 80" in source
    assert "appendExplorerSearchOptionBatch();" in options
    assert 'explorerSearchInput.addEventListener("focus"' in listeners
    assert 'explorerSearchOptions.addEventListener("scroll"' in listeners


def test_explore_and_analyze_keep_separate_dashboard_and_filter_state() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    html_source = INDEX_HTML.read_text(encoding="utf-8")
    cache_key = source.split("function currentOverviewDetailCacheKey", 1)[1].split(
        "function overviewDetailSnapshot", 1
    )[0]
    detail_header = source.split("function setDetailHeader", 1)[1].split(
        "function clearDetailForTransition", 1
    )[0]
    mode_switch = source.split("function switchExplorerMode", 1)[1].split(
        "function switchCompareKind", 1
    )[0]

    assert 'explorerMode !== "overview"' in cache_key
    assert 'explorerMode === "overview"' in detail_header
    assert "overviewWorkspaceFilterState = { evidenceView, accessView }" in mode_switch
    assert "accessView = state.accessView" in source
    assert "deferredSurfaceRenderToken += 1" in source
    assert "syncYearFilterControls(activeClaimsForMode(), false)" in mode_switch
    assert 'id="explorerScopeClear" type="button">Reset</button>' in html_source
    assert "explorerScopeClear.hidden = false" in source


def test_analysis_defaults_to_year_2000_through_latest_available_year() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    defaults = source.split("function defaultYearFilterRange", 1)[1].split(
        "function syncYearFilterControls", 1
    )[0]
    sync = source.split("function syncYearFilterControls", 1)[1].split(
        "function rememberYearFilterControls", 1
    )[0]
    reset = source.split('explorerScopeClear.addEventListener("click"', 1)[1].split(
        "if (explorerFocusBack)", 1
    )[0]

    assert "ANALYSIS_DEFAULT_START_YEAR = 2000" in source
    assert 'explorerMode === "analysis"' in defaults
    assert "clampNumber(ANALYSIS_DEFAULT_START_YEAR, bounds.min, bounds.max)" in defaults
    assert "max: bounds.max" in defaults
    assert "defaultYearFilterRange(bounds)" in sync
    assert "refreshAnalysisScope({ resetYears: true })" in reset


def test_analysis_dropdown_menus_use_the_site_dark_theme() -> None:
    source = STYLES_CSS.read_text(encoding="utf-8")
    root = source.split(":root {", 1)[1].split("}", 1)[0]
    options = source.split(
        ".analysis-query-field select option,", 1
    )[1].split("}", 1)[0]

    assert "color-scheme: dark;" in root
    assert ".analysis-publication-field select option" in source
    assert "color: var(--fg);" in options
    assert "background: var(--bg-2);" in options


def test_analysis_section_headings_do_not_render_redundant_meta_copy() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    renderer = source.split("function renderAnalyticsPanel", 1)[1].split(
        "function analysisExperimentalSystemFacetLabel", 1
    )[0]
    momentum = source.split("function renderExplorerMomentumPanel", 1)[1].split(
        "function updateExplorerMomentumPanel", 1
    )[0]
    focused_dashboard = source.split("function renderExplorerFocused", 1)[1].split(
        "function renderExplorerSurface", 1
    )[0]
    focused_section_order = focused_dashboard.split("const dashboardSections", 1)[1].split(
        "dashboard.append", 1
    )[0]

    assert "${meta" not in renderer
    assert "<span>" not in renderer
    assert "data-explorer-momentum-meta" not in momentum
    assert "<h3>Connections</h3><span>" not in focused_dashboard
    assert focused_section_order.index("overlapWrap.firstElementChild") < focused_section_order.index(
        "dashboardSections.push(networkPanel)"
    )


def test_analysis_chart_titles_and_axis_labels_have_safe_insets() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    styles = STYLES_CSS.read_text(encoding="utf-8")
    landscape = source.split("function renderExplorerLandscape", 1)[1].split(
        "function renderExplorerMomentum", 1
    )[0]
    grouped_history = source.split("function renderAnalyticsGroupedYearHistogram", 1)[1].split(
        "function analyticsSparkline", 1
    )[0]
    publication_history = source.split("function renderEvidenceTrajectory", 1)[1].split(
        "function renderSynthesisGap", 1
    )[0]
    evidence_coverage = source.split("function renderSynthesisGap", 1)[1].split(
        "function renderEvidenceComparison", 1
    )[0]

    assert 'renderAnalyticsPanel("Research-area evidence coverage"' in source
    assert 'renderAnalyticsPanel("Evidence maturity"' not in source
    assert "const width = 788;" in landscape
    assert "const height = 348;" in landscape
    assert "bottom: 72, left: 76" in landscape
    assert 'y="${baselineY + 18}"' in landscape
    assert 'y="${height - 36}"' in landscape
    assert 'x="34"' in landscape
    assert 'y="${height - 20}"' in grouped_history
    assert 'y="${height - 20}"' in publication_history
    assert "const height = 348;" in evidence_coverage
    assert "bottom: 64" in evidence_coverage
    assert 'y="${baselineY + 12}"' in evidence_coverage
    assert 'y="${height - 36}"' in evidence_coverage
    assert "\n.graph > svg {\n" in styles
    assert "\n.graph svg {\n" not in styles


def test_cross_domain_overlap_uses_consistent_labels_and_edge_markers() -> None:
    source = STYLES_CSS.read_text(encoding="utf-8")
    grid = source.split(".analytics-overlap-grid {", 1)[1].split("}", 1)[0]
    column_label = source.split(".analytics-overlap-column span {", 1)[1].split("}", 1)[0]
    row_label = source.split(".analytics-overlap-row-label {", 1)[1].split("}", 1)[0]

    assert "grid-template-rows: 170px;" in grid
    assert "padding-right: 120px;" in grid
    assert "writing-mode: horizontal-tb;" in column_label
    assert "transform: rotate(-45deg);" in column_label
    assert "transform-origin: left bottom;" in column_label
    assert "text-align: left;" in column_label
    assert "color: color-mix(in srgb, var(--area-color) 60%, #e8ece8);" in column_label
    assert "text-shadow: none;" in column_label
    assert "color: color-mix(in srgb, var(--area-color) 60%, #e8ece8);" in row_label
    assert "justify-content: flex-end;" in row_label
    assert "border-right: 2px solid var(--area-color);" in row_label
    assert "border-left" not in row_label
    assert "text-align: right;" in row_label
    assert "text-shadow: none;" in row_label


def test_bibliography_search_reuses_the_rendered_rows_and_cached_index() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    rows_from_claims = source.split("function bibliographyRowsFromClaims", 1)[1].split(
        "function currentBibliographyYearRange", 1
    )[0]
    search_index = source.split("function bibliographyHaystack", 1)[1].split(
        "function bibliographyCitationHtml", 1
    )[0]
    search_render = source.split("function scheduleBibliographySearchIndexWarmup", 1)[1].split(
        "function summarizeConnections", 1
    )[0]
    search_listener = source.split('if (bibliographySearchInput) {', 1)[1].split(
        'if (detailBody)', 1
    )[0]

    assert "claimSearchHaystack" not in rows_from_claims
    assert "bibliographySearchTextCache.get(entry)" in search_index
    assert "bibliographySearchTextCache.set(entry, searchText)" in search_index
    assert "scheduleBibliographySearchIndexWarmup(rows)" in search_render
    assert "started < 8" in search_render
    assert "BIBLIOGRAPHY_SEARCH_DEBOUNCE_MS" in search_render
    assert "renderBibliography()" in search_render
    assert "scheduleBibliographySearchRender()" in search_listener
    assert "applyFilters(" not in search_listener


def test_full_graph_does_not_promote_detail_only_findings() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    admission = source.split("function isMainGraphAdmitted", 1)[1].split("function unique", 1)[0]
    graph_build = source.split("function buildGraph", 1)[1].split("function render()", 1)[0]

    assert 'admission === "main_graph"' in admission
    assert "data.filter(isMainGraphAdmitted)" in graph_build


def test_single_study_node_suppression_applies_only_to_primary_evidence() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    eligibility = source.split("function findingsWithEligibleGraphNodes", 1)[1].split(
        "function graphRelationshipKeyForClaim", 1
    )[0]

    assert "if (isSecondaryEvidenceView()) return data;" in eligibility
    assert 'evidenceView === "meta_analyses"' not in eligibility


def test_graph_selection_details_match_the_admitted_graph_projection() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    filtering = source.split("function applyFiltersToClaims", 1)[1].split(
        "function applyGlobalFindingSearchFilters", 1
    )[0]
    detail = source.split("function renderSelectedDetailFromData", 1)[1].split(
        "function renderSelectedDetail", 1
    )[0]

    assert "detailFiltered.filter(isMainGraphAdmitted)" in filtering
    assert "uniqueGraphPropositionClaims(" in filtering
    assert "data.filter(isMainGraphAdmitted)" in detail
    assert "allAccessData.filter(isMainGraphAdmitted)" in detail
    assert detail.count("uniqueGraphPropositionClaims(") >= 2


def test_main_browse_surfaces_exclude_detail_only_findings_but_search_can_retrieve_them() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    cards = source.split("function findingCardResults", 1)[1].split("function selectionIsValid", 1)[0]
    render = source.split("function render()", 1)[1].split("function refreshMainViews", 1)[0]
    global_search = source.split("function globalFindingSearchClaims", 1)[1].split(
        "function hasFindingSearchQuery", 1
    )[0]

    assert "graphFiltered.filter(isMainGraphAdmitted)" in cards
    assert "applyGlobalFindingSearchFilters()" in cards
    assert "applyFilters({ ignoreSearch: true }).filter(isMainGraphAdmitted)" in render
    assert "filter(isMainGraphAdmitted)" not in global_search


def test_review_panel_omits_report_coverage_summary() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    review_panel = source.split("function renderReviewContextCharts", 1)[1].split(
        "function isNetworkMetaAnalysisClaim", 1
    )[0]

    assert '"Review approaches"' in review_panel
    assert '"Overall review focus"' in review_panel
    assert '"Evidence base"' in review_panel
    assert "Relationship types" not in review_panel
    assert "Coverage within each report" not in review_panel
    assert "relationshipEntries" not in review_panel
    assert "review_relationship_type_facet" not in review_panel
    assert "coverageFocusEntries" not in review_panel
    assert "review_coverage_focus_facet" not in review_panel


def test_findings_search_index_is_cached_and_warmed_in_small_idle_chunks() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    raw_index = source.split("function rawSearchTextForClaim", 1)[1].split(
        "function claimDerivedSearchParts", 1
    )[0]
    warmup = source.split("function scheduleFindingSearchIndexWarmup", 1)[1].split(
        "function requestGraphCenterAfterRender", 1
    )[0]

    assert "rawClaimSearchTextCache.get" in raw_index
    assert "collectSearchTextParts" not in raw_index
    assert "scheduleIdleTask(warmChunk" in warmup
    assert "started < 8" in warmup


def test_bibliography_enrichment_preserves_the_warmed_findings_index() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    enrichment = source.split("function enrichClaimsWithBibliographyMetadata", 1)[1].split(
        "function addBibliographyContext", 1
    )[0]

    assert "rawClaimSearchTextCache.get(claim)" in enrichment
    assert "rawClaimSearchTextCache.set(" in enrichment
    assert "claimSearchTextCache.get(claim)" in enrichment
    assert "claimSearchTextCache.set(enriched" in enrichment


def test_card_intrinsic_size_does_not_override_column_width() -> None:
    source = STYLES_CSS.read_text(encoding="utf-8")
    card_rule = source.split(".card {", 1)[1].split(".card-header", 1)[0]

    assert "contain-intrinsic-inline-size: none" in card_rule
    assert "contain-intrinsic-block-size: auto 320px" in card_rule
    assert "contain-intrinsic-size: 320px" not in card_rule


def test_initial_graph_detail_panel_is_blank() -> None:
    source = INDEX_HTML.read_text(encoding="utf-8")

    assert "Graph Detail" not in source
    assert "No selection yet." not in source


def test_initial_page_has_no_blocking_loading_screen() -> None:
    html_source = INDEX_HTML.read_text(encoding="utf-8")
    app_source = APP_JS.read_text(encoding="utf-8")
    style_source = STYLES_CSS.read_text(encoding="utf-8")

    assert "site-loader" not in html_source
    assert "app-booting" not in html_source
    assert "finishInitialBoot" not in app_source
    assert ".site-loader" not in style_source


def test_header_uses_graph_counts_without_awaiting_queue_labels() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    stats_source = source.split("function heroStatsFromGraphManifest", 1)[1].split(
        "function completeHeroStats", 1
    )[0]
    render_source = source.split("function setHeroStatValues", 1)[1].split("function updateStats", 1)[0]
    html_source = INDEX_HTML.read_text(encoding="utf-8")

    assert "paper_counts" in stats_source
    assert "awaiting_graph_inclusion" not in stats_source
    assert "awaiting" not in render_source.lower()
    assert "data-stat-detail" not in html_source


def test_initial_page_uses_swap_fonts_without_hiding_content() -> None:
    source = INDEX_HTML.read_text(encoding="utf-8")
    head = source.split("<body>", 1)[0]

    assert "display=swap" in head
    assert 'classList.add("fonts-pending")' not in head
    assert "html.fonts-pending body" not in head
    assert "visibility: hidden" not in head
    assert "document.fonts.load" not in head


def test_initial_dashboard_becomes_an_interactive_browse_surface() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    dashboard = source.split("async function renderCurrentDashboardBootstrap", 1)[1].split(
        "function canonicalOverviewBootstrapClaims", 1
    )[0]
    loader = source.split("async function loadCurrentClaimsAndRender", 1)[1].split(
        "function scheduleIdleTask", 1
    )[0]
    graph = source.split("function prepareBootstrapInteraction", 1)[1].split(
        "edgeEntries.forEach", 1
    )[0]

    assert "dashboardSourceReady[sourceKey] = true" in dashboard
    assert "scheduleDeferredSurfaceRender(graphFiltered, allAccessGraphFiltered, false)" in dashboard
    assert "scheduleFindingSearchIndexWarmup()" in dashboard
    assert "if (dashboardRendered && !hasFindingSearchQuery())" in loader
    assert loader.index("if (dashboardRendered && !hasFindingSearchQuery())") < loader.index(
        "ensureClaimsForCurrentView"
    )
    assert "currentViewClaimsReady()" in graph


def test_detail_bootstrap_is_decoded_and_normalized_once() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    decoder = source.split("function columnarBootstrapClaimsFromPayload", 1)[1].split(
        "function dashboardBootstrapClaimsFromPayload", 1
    )[0]
    loader = source.split("async function loadRouteNativeEvidenceSource", 1)[1].split(
        "function currentSourceKey", 1
    )[0]

    assert decoder.count("routeNativeFindingForCurrentUi") == 1
    assert "item[bootstrapMarker] = true" in decoder
    assert "routeNativeFindingForCurrentUi" not in loader
    assert "claimStores.normalized.bySource[sourceKey] = enrichedItems" in loader


def test_entity_navigation_prefers_category_shards_and_keeps_full_search_fallback() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    view_loader = source.split("async function loadNormalizedClaimView", 1)[1].split(
        "async function ensureClaimsForCurrentView", 1
    )[0]
    search = source.split("function scheduleFindingSearchRender", 1)[1].split(
        "function scheduleFindingSearchIndexWarmup", 1
    )[0]
    listeners = source.split("if (entityKindToggle)", 1)[1].split(
        'window.addEventListener("resize"', 1
    )[0]

    assert "loadRouteNativeEvidenceView(sourceKey, viewKey)" in view_loader
    assert "loadNormalizedClaimSource(sourceKey)" in view_loader
    assert "loadNormalizedClaimSource(currentSourceKey())" in search
    assert "preloadClaimsForEntityView(viewKey)" in listeners
    assert "preloadFullClaimsForCurrentSource" not in source
    assert 'searchInput.addEventListener("focus"' in source
    assert "scheduleFindingSearchIndexWarmup()" in listeners


def test_card_progressive_rendering_uses_a_real_scroll_root() -> None:
    app_source = APP_JS.read_text(encoding="utf-8")
    style_source = STYLES_CSS.read_text(encoding="utf-8")
    cards = app_source.split("function renderCards", 1)[1].split(
        "function bibliographyEntryId", 1
    )[0]
    panel = style_source.split(".cards-panel {", 1)[1].split("}", 1)[0]

    assert "cardsEl.scrollHeight > cardsEl.clientHeight + 1" in cards
    assert "root: observerRoot" in cards
    assert "height: min(78vh, 960px)" in panel


def test_manifest_stats_do_not_block_the_initial_graph() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    init = source.split("async function init()", 1)[1].split("if (yearMinFilter)", 1)[0]

    assert "loadGraphManifestStats();" in init
    assert "await loadGraphManifestStats()" not in init
    assert "await loadCurrentClaimsAndRender" in init


def test_versioned_static_assets_are_browser_immutable() -> None:
    config = tomllib.loads(NETLIFY_TOML.read_text(encoding="utf-8"))
    headers = {entry["for"]: entry["values"] for entry in config["headers"]}
    html_source = INDEX_HTML.read_text(encoding="utf-8")

    assert headers["/ui/*.js"]["Cache-Control"] == "public, max-age=31536000, immutable"
    assert headers["/ui/*.css"]["Cache-Control"] == "public, max-age=31536000, immutable"
    assert 'styles.css?v=20260905-research-workspace-v61' in html_source
    assert 'app.js?v=20260905-research-workspace-v53' in html_source
    for asset in ("research-model.js", "research-analysis.js", "research-analysis.css"):
        assert f'{asset}?v=20260905-v1' in html_source
    assert 'rel="canonical" href="https://psychedelicskg.com/"' in html_source
    assert '"@type": "Dataset"' in html_source


def test_lower_level_research_areas_are_labeled_as_topics() -> None:
    app_source = APP_JS.read_text(encoding="utf-8")
    html_source = INDEX_HTML.read_text(encoding="utf-8")

    assert 'aria-label="Filter analysis by topic"' in html_source
    for label in (
        "Research topic",
        "All topics",
        "topic breadth",
        "Topic profile",
        "Topic momentum",
    ):
        assert label in app_source
    for old_label in (
        "Research concept",
        "All concepts",
        "concept breadth",
        "Concept profile",
        "Concept momentum",
    ):
        assert old_label not in app_source

    # The wording changes without breaking stored data or existing links.
    assert 'data-analysis-scope-concept' in app_source
    assert 'column.type === "concept"' in app_source


def test_analysis_legends_use_large_square_color_swatches() -> None:
    source = STYLES_CSS.read_text(encoding="utf-8")
    swatches = source.split(
        ".analytics-chart-legend i,\n.compare-composition-legend i {", 1
    )[1].split("}", 1)[0]

    assert "width: 12px;" in swatches
    assert "height: 12px;" in swatches
    assert "border-radius: 3px;" in swatches


def test_topic_overlap_has_room_for_diagonal_column_labels() -> None:
    source = STYLES_CSS.read_text(encoding="utf-8")
    grid = source.split(".analysis-concept-overlap-grid {", 1)[1].split("}", 1)[0]
    labels = source.split(
        ".analysis-concept-overlap-grid .analytics-overlap-column span {", 1
    )[1].split("}", 1)[0]

    assert "--overlap-label-width: 220px;" in grid
    assert "grid-template-rows: 190px;" in grid
    assert "padding-right: 140px;" in grid
    assert "width: 190px;" in labels


def test_analysis_scope_counts_follow_the_selected_entity() -> None:
    app_source = APP_JS.read_text(encoding="utf-8")
    worker_source = ANALYSIS_WORKER_JS.read_text(encoding="utf-8")
    scope_controls = app_source.split("function syncAnalysisScopeControls()", 1)[1].split(
        "function explorerSourceClaims()", 1
    )[0]
    base_mask = worker_source.split("function baseStudyMask", 1)[1].split(
        "function idsFromMask", 1
    )[0]

    assert "analysisClaimsForFocusedEntity(" in scope_controls
    assert "explorerBaseFilteredClaims" in scope_controls
    assert "entityByLensAndKey.get(params.lens)?.get(params.focusKey)" in base_mask
    assert "params.focusKey && !focus?.membership.has(study.id)" in base_mask
    assert 'analysis-worker.js?v=20260904-contextual-scope-v4' in app_source


def test_desktop_header_and_home_content_share_the_same_horizontal_gutter() -> None:
    source = STYLES_CSS.read_text(encoding="utf-8")
    header = source.split(".site-header-inner {", 1)[1].split("}", 1)[0]
    content = source.split(".content {", 1)[1].split("}", 1)[0]

    assert "width: calc(100% - 16vw);" in header
    assert "1500px" not in header
    assert "padding: 16px 8vw 32px;" in content


def test_api_code_examples_wrap_long_commands_without_horizontal_scrolling() -> None:
    style_source = STYLES_CSS.read_text(encoding="utf-8")
    api_source = (ROOT / "api" / "index.html").read_text(encoding="utf-8")
    pre_styles = style_source.split(".access-code-card pre {", 1)[1].split("}", 1)[0]

    assert "overflow: hidden;" in pre_styles
    assert "overflow-wrap: anywhere;" in pre_styles
    assert "white-space: pre-wrap;" in pre_styles
    assert "curl -sS --get" in api_source
    assert '--data-urlencode "q=psilocybin"' in api_source
    assert '--data-urlencode "limit=5"' in api_source
    assert "/ui/styles.css?v=20260729-api-code-wrap-v1" in api_source


def test_stacked_bar_full_views_restart_palette_and_filtered_categories_keep_their_color() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    color_helper = source.split("function compositionCategoryColorKey", 1)[1].split(
        "function compositionFilterAttrs", 1
    )[0]
    chart = source.split("function renderFacetCompositionChart", 1)[1].split(
        "function hasRegisteredTrial", 1
    )[0]
    detail = source.split("function renderFieldValueDetail", 1)[1].split(
        "function renderPublicationYearDetail", 1
    )[0]

    assert "compositionCategoryColors" not in source
    assert "compositionCategoryColorKey(entry, field)" in color_helper
    assert "const color = palette[index % palette.length]" in color_helper
    assert "detailGraphFilter?.compositionColor" in color_helper
    assert "filteredColor?.key === key ? filteredColor.color : color" in color_helper
    assert "colorForEntry(entry, index, palette, filterField)" in chart
    assert 'data-palette-color="${escapeHtml(colors.color)}"' in chart
    assert 'paletteColor = ""' in detail
    assert "compositionFilterColor(field, value, paletteColor)" in detail
    assert source.count('target.dataset.paletteColor || ""') >= 2


def test_analysis_hides_redundant_study_characteristics_and_transparency_panels() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    matrix_view = source.split("function renderExplorerMatrix", 1)[1].split(
        "function explorerSvgElement", 1
    )[0]
    focused_view = source.split("function renderExplorerFocused", 1)[1].split(
        "function renderExplorerSurface", 1
    )[0]
    all_view = source.split("function renderAllAnalysis", 1)[1].split(
        "function compareCombinedItems", 1
    )[0]

    assert "renderAnalysisStudyDetailSections(" not in matrix_view
    assert "renderAnalysisStudyDetailSections(" not in focused_view
    assert "renderAnalysisStudyDetailSections(" not in all_view
    assert source.count("renderAnalysisStudyDetailSections(") == 1
    assert "autosizeExplorerWorkspace(dashboard);" in focused_view
    assert "autosizeExplorerWorkspace(graphEl.firstElementChild);" in all_view


def test_analysis_study_detail_charts_drill_into_matching_records() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    click_handler = source.split('graphEl.addEventListener("click"', 1)[1].split(
        'graphEl.addEventListener("mouseover"', 1
    )[0]

    assert 'data-analysis-study-filter="facet"' in source
    assert 'data-analysis-study-filter="sample-size"' in source
    assert "function renderAnalysisStudyFilterDetail" in source
    assert "claimsForFieldValue(field, value, items)" in source
    assert "claimsForAnalysisSampleSizeRange(sampleItems, min, max)" in source
    assert "renderExplorerSelectionDetail(fieldValueDetailTitle(field, label)" in source
    assert 'event.target.closest?.("[data-analysis-study-filter]")' in click_handler


def test_stacked_bar_palette_starts_with_blue_and_nudges_teal_toward_green() -> None:
    source = APP_JS.read_text(encoding="utf-8")

    assert 'const CATEGORY_COLORS = [\n  "#708aa7",\n  "#b89a5b",\n  "#a96f7e",\n  "#69a196",' in source
    assert 'const PUBLICATION_YEAR_COLOR = "#69a196";' in source
    assert "const GRAPH_COLOR_STOPS = [\n  { r: 67, g: 187, b: 166 }," in source
    assert 'node.style.setProperty("--node-glow", rgbaString(color, 0.29));' in source


def test_publication_year_hover_regions_do_not_overlap_at_chart_edges() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    chart_source = source.split("function renderAnnualPublicationChart", 1)[1].split(
        "function sampleSizeStudyEntries", 1
    )[0]

    assert "const barCenter = x + barWidth / 2" in chart_source
    assert "barCenter - step / 2" in chart_source
    assert "barCenter + step / 2" in chart_source
    assert "index === buckets.length - 1" in chart_source
    assert "? width - margin.right" in chart_source
    assert "clampNumber(x - (hitWidth - barWidth) / 2" not in chart_source


def test_right_detail_panel_exposes_expandable_funders_without_coverage_subtitle() -> None:
    source = APP_JS.read_text(encoding="utf-8")

    assert "function renderFundingCharts(items)" in source
    assert 'renderHorizontalBarChart(funders, "Funders"' in source
    assert 'filterField: "funding_funder_facet"' in source
    assert "renderFundingCharts(items)" in source
    assert "funding-summary-grid" not in source
    assert '"funding_status_facet"' not in source
    assert "Funding metadata found for ${formatCompactNumber(metadataFound)} of" not in source
    assert 'expandKey: "funders"' in source


def test_journal_and_funder_bars_use_the_thin_variant() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    styles = STYLES_CSS.read_text(encoding="utf-8")

    assert 'extraClass: "bar-tone-gray bar-thin funding-funders-card"' in source
    assert 'extraClass: "bar-tone-stone bar-thin"' in source
    assert ".trend-card.bar-thin .trend-bar-track" in styles
    assert "height: 5px;" in styles.split(".trend-card.bar-thin .trend-bar-track", 1)[1].split("}", 1)[0]


def test_ranked_detail_lists_offer_incremental_expansion_only() -> None:
    source = APP_JS.read_text(encoding="utf-8")

    assert "function renderRankedChartExpansionControls" in source
    assert 'data-chart-expand-action="more"' in source
    assert "Show ${formatCompactNumber(increment)} more" in source
    assert 'data-chart-expand-action="all"' not in source
    assert 'data-chart-expand-action="collapse"' not in source
    assert "Show top ${formatCompactNumber(initialCount)}" not in source
    assert 'rankedChartVisibleCount("authors"' in source
    assert 'if (key === "funders") chartCard.outerHTML = renderFundingCharts(activeDetailItems);' in source


def test_in_text_and_doi_links_share_one_muted_teal_family() -> None:
    source = STYLES_CSS.read_text(encoding="utf-8")
    app_source = APP_JS.read_text(encoding="utf-8")
    methods_source = (ROOT / "ui" / "methods.js").read_text(encoding="utf-8")

    assert "--link-color: #65bdad;" in source
    assert "--link-color-hover: #84ccbf;" in source
    assert "--doi-link-color: #91ded5;" in source
    assert "--doi-link-color-hover: #b2efe8;" in source
    assert source.count("color: var(--link-color);") >= 9
    assert source.count("color: var(--link-color-hover);") >= 9
    assert "color: var(--doi-link-color);" in source
    assert "color: var(--doi-link-color-hover);" in source
    assert app_source.count('class="doi-link"') >= 2
    assert 'class="doi-link"' in methods_source
    assert "#b8fff7" not in source
    assert "#a9f7ef" not in source


def test_stacked_bar_palette_becomes_progressively_more_muted_after_fifth_color() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    palette_source = source.split("const CATEGORY_COLORS = [", 1)[1].split("];", 1)[0]
    colors = re.findall(r'"(#[0-9a-f]{6})"', palette_source)

    def saturation(hex_color: str) -> float:
        channels = [int(hex_color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        return rgb_to_hls(*channels)[2]

    def lightness(hex_color: str) -> float:
        channels = [int(hex_color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        return rgb_to_hls(*channels)[1]

    tail_saturations = [saturation(color) for color in colors[5:]]
    tail_lightness = [lightness(color) for color in colors[5:]]
    assert len(colors) == 25
    assert tail_saturations[0] <= 0.21
    assert tail_saturations[-1] <= 0.07
    assert all(current > following for current, following in zip(tail_saturations, tail_saturations[1:]))
    assert all(current > following for current, following in zip(tail_lightness, tail_lightness[1:]))


def test_early_stacked_bar_colors_do_not_repeat_the_same_hue_families() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    palette_source = source.split("const CATEGORY_COLORS = [", 1)[1].split("];", 1)[0]
    colors = re.findall(r'"(#[0-9a-f]{6})"', palette_source)

    def hue(hex_color: str) -> float:
        channels = [int(hex_color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        return rgb_to_hls(*channels)[0] * 360

    def hue_distance(first: str, second: str) -> float:
        difference = abs(hue(first) - hue(second))
        return min(difference, 360 - difference)

    assert hue_distance(colors[6], colors[0]) > 45
    assert hue_distance(colors[6], colors[9]) > 45
    assert hue_distance(colors[8], colors[2]) > 45
    assert hue_distance(colors[10], colors[2]) > 45


def test_brain_relationship_types_use_brain_specific_assignments_and_one_other_bucket() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    relationship_source = source.split("const MECHANISTIC_RELATIONSHIP_TYPE_ORDER", 1)[1].split(
        "function assayFamilyText", 1
    )[0]

    assert 'other_or_mixed: "Other"' in relationship_source
    assert '"Other/mixed relationship"' not in relationship_source
    assert '"Activity change"' in relationship_source
    assert '"Structural change"' in relationship_source
    assert '"Metabolic/perfusion change"' in relationship_source
    assert '"Neurochemical change"' in relationship_source
    assert "if (isBrainRelationshipClaim(claim))" in relationship_source
    assert '"functional connectivity": "Connectivity change"' in relationship_source
    assert '"brain structure": "Structural change"' in relationship_source
    assert '"receptor occupancy": "Binding/affinity"' in relationship_source


def test_administration_facets_are_separate_single_value_dimensions() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    administration_source = source.split("const ADMINISTRATION_ROUTE_ORDER", 1)[1].split(
        "function normalizedAdministrationRouteText", 1
    )[0]
    chart_source = source.split("function renderAdministrationContextCharts", 1)[1].split(
        "function renderClinicalComparatorChart", 1
    )[0]

    assert "function administrationRouteFacetLabel" in administration_source
    assert "function dosingScheduleFacetLabel" in administration_source
    assert "function sessionContextFacetLabel" in administration_source
    assert 'return "Multiple routes"' in administration_source
    assert '"Preclinical experiment"' in administration_source
    assert '"Administration route", "administration_route_facet"' in chart_source
    assert '"Dosing schedule", "dosing_schedule_facet"' in chart_source
    assert '"Session context", "session_context_facet"' in chart_source
    assert "dose_route_session_facet" not in source


def test_cached_graph_reset_removes_stale_crossfade_state() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    graph_source = source.split("function buildGraph", 1)[1].split("function render()", 1)[0]

    cached_branch = graph_source.split("if (cached)", 1)[1].split("if (!crossfadeFromBootstrap)", 1)[0]
    reset_branch = graph_source.split("reset: () =>", 1)[1].split("applyFocusState", 1)[0]
    assert "graphSwapToken += 1" in cached_branch
    assert 'svg.classList.remove("graph-swap-layer", "graph-swap-out", "graph-swap-in", "graph-swap-active")' in reset_branch


def test_filtered_graph_is_committed_without_resizing_the_full_graph_first() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    graph_source = source.split("function buildGraph", 1)[1].split("function render()", 1)[0]
    uncached_setup = graph_source.split("if (!crossfadeFromBootstrap)", 1)[1].split(
        "const allowedRelationships", 1
    )[0]
    commit = graph_source.rsplit("if (crossfadeFromBootstrap && previousSvg)", 1)[1].split(
        "rememberGraphDom", 1
    )[0]

    assert 'graphEl.innerHTML = ""' not in uncached_setup
    assert "graphEl.replaceChildren(svg)" in commit
    assert commit.index("graphEl.replaceChildren(svg)") < commit.index(
        'graphEl.style.setProperty("--kg-graph-height"'
    )


def test_selected_graph_skips_the_bootstrap_completion_crossfade() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    graph_source = source.split("function buildGraph", 1)[1].split("const width", 1)[0]

    assert 'previousSvg?.dataset.graphStage === "bootstrap"' in graph_source
    assert 'graphStage === "full"' in graph_source
    assert "!selected" in graph_source
    assert "!detailGraphFilter" in graph_source


def test_graph_allocates_more_label_space_to_the_right_side() -> None:
    source = APP_JS.read_text(encoding="utf-8")

    assert "const GRAPH_LEFT_LABEL_MAX_WIDTH_PX = 180;" in source
    assert "const GRAPH_RIGHT_LABEL_MAX_WIDTH_PX = 210;" in source
    assert "GRAPH_LEFT_LABEL_MAX_WIDTH_PX + GRAPH_LABEL_MARGIN_BUFFER_PX" in source
    assert "GRAPH_RIGHT_LABEL_MAX_WIDTH_PX + GRAPH_LABEL_MARGIN_BUFFER_PX + GRAPH_RIGHT_LABEL_GUTTER_PX" in source


def test_constrained_graph_uses_a_scrollable_canvas_instead_of_scaling_its_contents() -> None:
    app_source = APP_JS.read_text(encoding="utf-8")
    style_source = STYLES_CSS.read_text(encoding="utf-8")
    graph_source = app_source.split("function buildGraph", 1)[1].split("function render()", 1)[0]

    assert "const GRAPH_MIN_LAYOUT_WIDTH_PX = 720;" in app_source
    assert "viewportWidth < GRAPH_MIN_LAYOUT_WIDTH_PX" in graph_source
    assert "Math.max(viewportWidth, GRAPH_MIN_LAYOUT_WIDTH_PX)" in graph_source
    assert 'svg.dataset.horizontalScrollable = horizontallyScrollableGraph ? "true" : "false";' in graph_source
    assert '.graph svg[data-horizontal-scrollable="true"]' in style_source
    assert "min-width: var(--kg-graph-layout-width);" in style_source


def test_constrained_graph_preserves_all_nodes_and_vertical_spacing() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    graph_source = source.split("function buildGraph", 1)[1].split("function render()", 1)[0]

    assert "maxMobileNodes" not in graph_source
    assert "GRAPH_COMPACT_BASE_HEIGHT_PX" not in source
    assert "GRAPH_COMPACT_MIN_NODE_SPACING_PX" not in source
    assert "maxNodeCount * GRAPH_MIN_NODE_SPACING_PX" in graph_source


def test_graph_edge_control_points_stay_between_the_node_columns() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    graph_source = source.split("function buildGraph", 1)[1].split("function render()", 1)[0]
    edge_source = graph_source.split("edgeEntries.forEach", 1)[1].split(
        "path.setAttribute", 1
    )[0]

    assert "const horizontalSpan = Math.max(0, tPos.x - cPos.x);" in edge_source
    assert "const controlOffset = horizontalSpan * 0.4;" in edge_source
    assert "const firstControlX = cPos.x + controlOffset;" in edge_source
    assert "const secondControlX = tPos.x - controlOffset;" in edge_source
    assert "const curve = 80;" not in edge_source


def test_constrained_graph_category_tabs_are_a_single_horizontal_scroll_row() -> None:
    source = STYLES_CSS.read_text(encoding="utf-8")
    constrained_styles = source.split(
        "@container graph-column (max-width: 1000px)", 1
    )[1].split("@container graph-column (max-width: 820px)", 1)[0]
    category_styles = constrained_styles.split(".category-toggle {", 1)[1].split("}", 1)[0]

    assert "flex-wrap: nowrap;" in category_styles
    assert "justify-content: flex-start;" in category_styles
    assert "overflow-x: auto;" in category_styles
    assert "border-radius: 999px;" in category_styles
    assert "width: calc(100% - 16px);" in category_styles
    assert "margin-inline: 0 16px;" in category_styles


def test_year_controls_stack_when_the_graph_column_is_constrained() -> None:
    source = STYLES_CSS.read_text(encoding="utf-8")
    graph_column_styles = source.split(".graph-column {", 1)[1].split("}", 1)[0]
    constrained_styles = source.split(
        "@container graph-column (max-width: 820px)", 1
    )[1].split(".panel h2", 1)[0]

    assert "container-type: inline-size;" in graph_column_styles
    assert "container-name: graph-column;" in graph_column_styles
    assert "grid-template-columns: minmax(0, 1fr);" in constrained_styles
    assert ".evidence-view-toggle," in constrained_styles
    assert ".year-range-inline" in constrained_styles
    assert "grid-column: 1;" in constrained_styles
    assert "justify-self: center;" in constrained_styles


def test_graph_labels_use_two_lines_without_unspecified_therapy_special_case() -> None:
    source = APP_JS.read_text(encoding="utf-8")

    assert '"psychedelic-assisted therapy (unspecified compounds)"' not in source
    assert "GRAPH_THREE_LINE_LABELS" not in source
    assert source.count("pos.y, 2);") >= 2


def test_slash_separated_graph_labels_wrap_without_an_inserted_hyphen() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    helper = source.split("function wrapUnbrokenLabelToLines", 1)[1].split(
        "function wrapLabelToLines", 1
    )[0]

    assert "const naturalBreak = /[-/]$/.test(prefix);" in helper
    assert "const firstLine = naturalBreak ? prefix : `${prefix}-`;" in helper
    assert "naturalBreak," in helper


def test_each_edge_uses_a_gradient_between_its_endpoint_colors() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    edge_render = source.split('edgeEntries.forEach(([key, edge], index)', 1)[1].split(
        "compoundPositions.forEach", 1
    )[0]

    assert 'start.setAttribute("stop-color", rgbString(compoundColor))' in edge_render
    assert 'end.setAttribute("stop-color", rgbString(targetColor))' in edge_render
    assert "path.style.stroke = `url(#${gradientId})`" in edge_render


def test_graph_elements_are_not_revealed_in_separate_waves() -> None:
    app_source = APP_JS.read_text(encoding="utf-8")
    style_source = STYLES_CSS.read_text(encoding="utf-8")

    assert "graph-enter" not in app_source
    assert ".graph svg.graph-enter" not in style_source


def test_homepage_uses_central_release_metadata_for_version_and_literature_date() -> None:
    source = INDEX_HTML.read_text(encoding="utf-8")

    assert "Graph version: v{{RELEASE_VERSION}}" in source
    assert "Literature updated: {{RELEASE_LITERATURE_UPDATED}}" in source
    assert "Graph version: v0.0.1" not in source
    assert "Literature search through: 2026-05-28" not in source
