from colorsys import rgb_to_hls
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "ui" / "app.js"
INDEX_HTML = ROOT / "index.html"
STYLES_CSS = ROOT / "ui" / "styles.css"


def test_real_world_use_contains_exposure_contexts_without_a_separate_graph_view() -> None:
    source = APP_JS.read_text(encoding="utf-8")

    assert 'key: "public_health_measure",\n    kinds: ["public_health_measure", "exposure_context"]' in source
    assert 'label: "Use contexts"' not in source


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
        "function loadBibliographyPayloadsInBackground", 1
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
    assert "normalizedCurrentSourceLoaded()) return false" not in bootstrap


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


def test_overview_dashboards_are_precomputed_in_idle_chunks() -> None:
    source = APP_JS.read_text(encoding="utf-8")

    prewarm = source.split("function scheduleOverviewDetailPrewarmForSource", 1)[1].split(
        "function normalizedCurrentSourceLoaded", 1
    )[0]
    init = source.split("async function init()", 1)[1].split("if (yearMinFilter)", 1)[0]

    assert "ENTITY_CATEGORY_OPTIONS.forEach" in prewarm
    assert "scheduleIdleTask(" in prewarm
    assert "prewarmOverviewDetailEntry" in prewarm
    assert "scheduleOverviewDetailPrewarmForSource(currentSourceKey())" in init


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
    search_render = source.split("function scheduleFindingSearchRender", 1)[1].split(
        "function requestGraphCenterAfterRender", 1
    )[0]
    search_listener = source.split('if (searchInput) {', 1)[1].split('if (bibliographySearchInput)', 1)[0]

    assert "scheduleFindingSearchRender()" in search_listener
    assert "scheduleRender()" not in search_listener
    assert "renderCards(" in search_render
    assert "buildGraph(" not in search_render
    assert "renderBibliography(" not in search_render


def test_full_graph_does_not_promote_detail_only_findings() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    admission = source.split("function isMainGraphAdmitted", 1)[1].split("function unique", 1)[0]
    graph_build = source.split("function buildGraph", 1)[1].split("function render()", 1)[0]

    assert 'admission === "main_graph"' in admission
    assert "data.filter(isMainGraphAdmitted)" in graph_build


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


def test_initial_page_reveals_only_after_required_fonts_are_ready() -> None:
    source = INDEX_HTML.read_text(encoding="utf-8")
    head = source.split("<body>", 1)[0]

    assert 'classList.add("fonts-pending")' in head
    assert "html.fonts-pending body" in head
    assert "visibility: hidden" in head
    assert 'document.fonts.load(\'400 1em "IBM Plex Sans"\')' in head
    assert 'document.fonts.load(\'700 1em "Space Grotesk"\')' in head
    assert "document.fonts.ready" in head
    assert "display=swap" in head
    assert "setTimeout(revealStyledPage, 1600)" in head


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


def test_stacked_bar_palette_starts_with_blue_and_nudges_teal_toward_green() -> None:
    source = APP_JS.read_text(encoding="utf-8")

    assert 'const CATEGORY_COLORS = [\n  "#708aa7",\n  "#b89a5b",\n  "#a96f7e",\n  "#69a196",' in source
    assert 'const PUBLICATION_YEAR_COLOR = "#69a196";' in source
    assert "const GRAPH_COLOR_STOPS = [\n  { r: 70, g: 197, b: 181 }," in source
    assert 'node.style.setProperty("--node-glow", rgbaString(color, 0.29));' in source


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
    assert app_source.count('class="doi-link"') >= 3
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
