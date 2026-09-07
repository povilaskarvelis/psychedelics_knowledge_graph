(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.PKGViewState = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const VERSION = "1";
  const VIEW_PARAMETERS = Object.freeze([
    "v", "mode", "section", "view", "papers", "access", "from", "to",
    "focus", "area", "scope-area", "concept", "coverage", "graph",
    "compound", "target", "result", "network", "relationship", "timeline", "momentum",
    "publication", "publication-compound", "publication-area", "release",
    // Retired parameters are removed whenever a canonical view URL is written.
    "task", "research", "compare", "lens",
  ]);
  const PAPER_VIEWS = new Set(["all", "primary", "meta_analyses", "reviews"]);
  const ACCESS_VIEWS = new Set(["all", "open"]);
  const GRAPH_KINDS = new Set(["compound", "target", "edge"]);
  const NETWORK_ORDERS = new Set(["areas", "relationships"]);
  const FOCUS_TIMELINE_VIEWS = new Set(["areas", "compounds"]);
  const PUBLICATION_MODES = new Set(["volume", "mix"]);
  const RESULT_TYPES = new Set(["publication_history", "evidence", "compounds"]);

  function bounded(value, maximum = 200) {
    return typeof value === "string" ? value.trim().slice(0, maximum) : "";
  }

  function year(value) {
    const parsed = Number(value);
    if (!Number.isInteger(parsed) || parsed < 1800 || parsed > 3000) return "";
    return String(parsed);
  }

  function positiveInteger(value, minimum, maximum) {
    const parsed = Math.round(Number(value));
    return Number.isInteger(parsed) && parsed >= minimum && parsed <= maximum ? parsed : null;
  }

  function parseJson(value, maximum = 16000) {
    const text = bounded(value, maximum);
    if (!text) return null;
    try {
      const parsed = JSON.parse(text);
      return parsed && typeof parsed === "object" ? parsed : null;
    } catch (_) {
      return null;
    }
  }

  function validateGraphSelection(raw) {
    if (!raw || !GRAPH_KINDS.has(raw.kind)) return null;
    const compound = bounded(raw.compound, 300);
    const target = bounded(raw.target, 500);
    if (raw.kind === "compound" && compound) return { kind: "compound", compound };
    if (raw.kind === "target" && target) return { kind: "target", target };
    if (raw.kind === "edge" && compound && target) return { kind: "edge", compound, target };
    return null;
  }

  function validateResult(raw) {
    if (!raw || !RESULT_TYPES.has(raw.type)) return null;
    if (raw.type === "publication_history") {
      const selectedYear = positiveInteger(raw.year, 1800, 3000);
      return selectedYear ? { type: raw.type, year: selectedYear } : null;
    }
    if (raw.type === "evidence") {
      const sourceKey = bounded(raw.sourceKey, 40);
      const areaKey = bounded(raw.areaKey, 120);
      return sourceKey && areaKey ? { type: raw.type, sourceKey, areaKey } : null;
    }
    const leftKey = bounded(raw.leftKey, 300);
    const rightKey = bounded(raw.rightKey, 300);
    return leftKey
      ? { type: raw.type, leftKey, ...(rightKey && rightKey !== leftKey ? { rightKey } : {}) }
      : null;
  }

  function read(input) {
    const params = input instanceof URLSearchParams ? input : new URL(input, "https://example.invalid/").searchParams;
    const warnings = [];
    const rawVersion = bounded(params.get("v"), 8);
    if (rawVersion && rawVersion !== VERSION) warnings.push("unsupported-version");

    const rawMode = bounded(params.get("mode"), 20);
    let mode = rawMode === "analysis" ? "analysis" : "overview";
    // `mode=explore` used to mean the old Analyze workspace. Versioned links use
    // it for the current Explore workspace without breaking those older links.
    if (["explore", "compare"].includes(rawMode) && !rawVersion) mode = "analysis";
    const legacyLens = bounded(params.get("lens"), 40);
    const section = rawMode === "compare"
      ? "compound"
      : bounded(params.get("section"), 40) || legacyLens;

    const rawPapers = bounded(params.get("papers"), 40);
    const rawAccess = bounded(params.get("access"), 20);
    if (rawPapers && !PAPER_VIEWS.has(rawPapers)) warnings.push("papers");
    if (rawAccess && !ACCESS_VIEWS.has(rawAccess)) warnings.push("access");

    const graphKind = bounded(params.get("graph"), 20);
    const graphSelection = validateGraphSelection({
      kind: graphKind,
      compound: params.get("compound"),
      target: params.get("target"),
    });
    if (graphKind && !graphSelection) warnings.push("graph");

    const rawResult = params.get("result");
    const result = validateResult(parseJson(rawResult, 2000));
    if (rawResult && !result) warnings.push("result");

    const rawCoverage = params.get("coverage") || params.get("research");
    const coverage = parseJson(rawCoverage, 16000);
    if (rawCoverage && !coverage) warnings.push("coverage");

    const rawNetwork = bounded(params.get("network"), 30);
    const rawTimeline = bounded(params.get("timeline"), 30);
    const rawPublication = bounded(params.get("publication"), 30);
    const rawMomentum = params.get("momentum");
    const momentum = rawMomentum ? positiveInteger(rawMomentum, 2, 15) : null;
    if (rawNetwork && !NETWORK_ORDERS.has(rawNetwork)) warnings.push("network");
    if (rawTimeline && !FOCUS_TIMELINE_VIEWS.has(rawTimeline)) warnings.push("timeline");
    if (rawPublication && !PUBLICATION_MODES.has(rawPublication)) warnings.push("publication");
    if (rawMomentum && momentum === null) warnings.push("momentum");

    return {
      version: rawVersion,
      mode,
      section,
      view: bounded(params.get("view"), 120),
      papers: PAPER_VIEWS.has(rawPapers) ? rawPapers : "",
      access: ACCESS_VIEWS.has(rawAccess) ? rawAccess : "",
      from: year(params.get("from")),
      to: year(params.get("to")),
      focus: bounded(params.get("focus"), 300),
      area: bounded(params.get("area"), 120),
      scopeArea: bounded(params.get("scope-area"), 120),
      concept: bounded(params.get("concept"), 300),
      coverage,
      graphSelection,
      result,
      networkOrder: NETWORK_ORDERS.has(rawNetwork) ? rawNetwork : "",
      relationship: bounded(params.get("relationship"), 500),
      focusTimelineView: FOCUS_TIMELINE_VIEWS.has(rawTimeline) ? rawTimeline : "",
      momentum,
      publicationMode: PUBLICATION_MODES.has(rawPublication) ? rawPublication : "",
      publicationCompound: bounded(params.get("publication-compound"), 300),
      publicationArea: bounded(params.get("publication-area"), 120),
      release: bounded(params.get("release"), 100),
      warnings,
    };
  }

  function clear(url) {
    VIEW_PARAMETERS.forEach((key) => url.searchParams.delete(key));
    return url;
  }

  function set(url, key, value) {
    if (value !== "" && value !== null && value !== undefined) url.searchParams.set(key, String(value));
  }

  function write(input, state) {
    const url = input instanceof URL ? new URL(input.href) : new URL(input);
    clear(url);
    const hasViewState = Boolean(state && state.mode);
    if (!hasViewState) return url;

    set(url, "v", VERSION);
    set(url, "mode", state.mode === "analysis" ? "analysis" : "explore");
    set(url, "section", state.section);
    set(url, "view", state.view);
    set(url, "papers", state.papers);
    set(url, "access", state.access);
    set(url, "from", year(state.from));
    set(url, "to", year(state.to));
    set(url, "focus", bounded(state.focus, 300));
    set(url, "area", bounded(state.area, 120));
    set(url, "scope-area", bounded(state.scopeArea, 120));
    set(url, "concept", bounded(state.concept, 300));
    if (state.coverage && typeof state.coverage === "object") set(url, "coverage", JSON.stringify(state.coverage));

    const graph = validateGraphSelection(state.graphSelection);
    if (graph) {
      set(url, "graph", graph.kind);
      set(url, "compound", graph.compound);
      set(url, "target", graph.target);
    }
    const result = validateResult(state.result);
    if (result) set(url, "result", JSON.stringify(result));
    if (NETWORK_ORDERS.has(state.networkOrder)) set(url, "network", state.networkOrder);
    set(url, "relationship", bounded(state.relationship, 500));
    if (FOCUS_TIMELINE_VIEWS.has(state.focusTimelineView)) set(url, "timeline", state.focusTimelineView);
    const momentum = positiveInteger(state.momentum, 2, 15);
    if (momentum !== null) set(url, "momentum", momentum);
    if (PUBLICATION_MODES.has(state.publicationMode)) set(url, "publication", state.publicationMode);
    set(url, "publication-compound", bounded(state.publicationCompound, 300));
    set(url, "publication-area", bounded(state.publicationArea, 120));
    set(url, "release", bounded(state.release, 100));
    return url;
  }

  return { VERSION, VIEW_PARAMETERS, clear, read, write, validateGraphSelection, validateResult };
});
