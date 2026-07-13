from pathlib import Path


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
