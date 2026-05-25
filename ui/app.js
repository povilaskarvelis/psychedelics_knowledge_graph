const graphEl = document.getElementById("graph");
const cardsEl = document.getElementById("cards");
const yearMinFilter = document.getElementById("yearMinFilter");
const yearMaxFilter = document.getElementById("yearMaxFilter");
const yearStepButtons = document.querySelectorAll(".year-step");
const searchInput = document.getElementById("searchInput");
const bibliographySearchInput = document.getElementById("bibliographySearchInput");
const fullTextOnlyToggle = document.getElementById("fullTextOnlyToggle");
const tooltip = document.getElementById("tooltip");
const detailTitle = document.querySelector("#graphDetail h3");
const detailBody = document.getElementById("detailBody");
const modeButtons = document.querySelectorAll("[data-mode]");
const claimLayerButtons = document.querySelectorAll("[data-claim-layer]");
const evidenceViewButtons = document.querySelectorAll("[data-evidence-view]");
const entityKindToggle = document.querySelector("[data-entity-kind-toggle]");
const studiesStatCard = document.getElementById("studiesStatCard");
const bibliographyPanel = document.getElementById("bibliographyPanel");
const studyListEl = document.getElementById("studyList");

if (tooltip && tooltip.parentElement !== document.body) {
  document.body.appendChild(tooltip);
}

const stats = {
  compounds: document.querySelector('[data-stat="compounds"]'),
  indications: document.querySelector('[data-stat="indications"]'),
  targets: document.querySelector('[data-stat="targets"]'),
  studies: document.querySelector('[data-stat="studies"]'),
};

const evidenceRank = { low: 1, medium: 2, high: 3 };
const MAX_GRAPH_EDGES = 500;
/** Chunk size for progressive rendering (IntersectionObserver loads more while scrolling). */
const LIST_CHUNK_SIZE = 120;

let cardsLoadObserver = null;
let bibliographyLoadObserver = null;
const GRAPH_COLOR_STOPS = [
  { r: 73, g: 214, b: 200 },
  { r: 119, g: 217, b: 141 },
  { r: 216, g: 210, b: 111 },
  { r: 241, g: 166, b: 106 },
  { r: 232, g: 117, b: 141 },
];
const CATEGORY_COLORS = [
  "#49d6c8",
  "#f1b74b",
  "#ef6c9a",
  "#90baff",
  "#77d98d",
  "#cda7ff",
  "#f6a66a",
  "#9aa4bf",
];
const DIRECTION_COLORS = {
  positive: "#90baff",
  mixed: "#ef6c9a",
  null: "#94a3b8",
  negative: "#fb7185",
  unclear: "#64748b",
};
const SYSTEM_COLORS = {
  clinical: "#49d6c8",
  preclinical: "#f1b74b",
  in_vitro: "#90baff",
  in_vivo: "#ef6c9a",
  ex_vivo: "#cda7ff",
  observational: "#ef6c9a",
  unknown: "#9aa4bf",
};
const ENTITY_VIEW_OPTIONS = {
  disorders: [
    { key: "condition_indication", label: "Conditions", singular: "Condition", lowerPlural: "conditions", lowerSingular: "condition" },
    { key: "symptom_problem", label: "Symptoms", singular: "Symptom", lowerPlural: "symptoms", lowerSingular: "symptom" },
    {
      key: "safety_adverse_event",
      label: "Safety",
      singular: "Safety/adverse event",
      lowerPlural: "safety/adverse events",
      lowerSingular: "safety/adverse event",
    },
    { key: "outcome_scale", label: "Scales", singular: "Outcome scale", lowerPlural: "outcome scales", lowerSingular: "outcome scale" },
  ],
  mechanistic: [
    { key: "target", label: "Targets", singular: "Target", lowerPlural: "targets", lowerSingular: "target" },
    { key: "pathway_process", label: "Pathways", singular: "Pathway", lowerPlural: "pathways", lowerSingular: "pathway" },
    {
      key: "biomarker_readout",
      label: "Biomarkers",
      singular: "Biomarker/readout",
      lowerPlural: "biomarkers/readouts",
      lowerSingular: "biomarker/readout",
    },
    { key: "system_family", label: "Systems", singular: "System/family", lowerPlural: "systems/families", lowerSingular: "system/family" },
  ],
};

let claims = [];
let disorderClaims = [];
const claimStores = {
  normalized: { mechanistic: [], disorders: [] },
  extracted: { mechanistic: [], disorders: [] },
};
let bibliographyByMode = {
  mechanistic: [],
  disorders: [],
};
let selected = null;
let isolateSelection = false;
let mode = "disorders";
let claimLayer = "normalized";
let evidenceView = "primary";
let entityView = {
  disorders: "condition_indication",
  mechanistic: "target",
};
let renderScheduled = false;
let activeDetailItems = [];
let detailGraphFilter = null;
const yearFilterState = {
  mechanistic: { min: "", max: "" },
  disorders: { min: "", max: "" },
};

const defaultDetail = {
  title: "Graph Detail",
};

const COMPOUND_CLASS_LABEL_RE =
  /\b(classic(?:al)? psychedelics?|serotonergic psychedelics?|psychedelic(?: assisted)? (?:medicines?|drugs?|substances?|compounds?|therap(?:y|ies))|psychedelics?|hallucinogenic drugs?|hallucinogens?|arylcyclohexylamines?|synthetic cathinones?|iboga alkaloids?|nbome drugs?|5[- ]*ht2a?r? agonists?)\b/;
const COMPOUND_LIST_LABEL_RE = /\b(?:and|or)\b|[;&]/;
const REFERENCE_COMPOUND_LABEL_RE =
  /\b(5 ht|5 hydroxytryptamine|8 oh dpat|clozapine|d serine|ifenprodil|ketanserin|m100907|memantine|methysergide|mk 801|pcp|phencyclidine|ritanserin|serotonin|way100635)\b/;
const SAMPLE_SIZE_BINS = [
  { label: "1", min: 1, max: 1 },
  { label: "2-10", min: 2, max: 10 },
  { label: "11-25", min: 11, max: 25 },
  { label: "26-50", min: 26, max: 50 },
  { label: "51-100", min: 51, max: 100 },
  { label: "101-250", min: 101, max: 250 },
  { label: "251-500", min: 251, max: 500 },
  { label: ">500", min: 501, max: Number.POSITIVE_INFINITY },
];
const GRAPH_LABEL_MAX_WIDTH_PX = 190;
const GRAPH_RIGHT_LABEL_GUTTER_PX = 42;

function normalizeValue(value) {
  return (value || "").toString().trim().toLowerCase();
}

function cleanDisplayText(value) {
  return (value ?? "")
    .toString()
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function unique(values) {
  return Array.from(new Set(values)).sort();
}

function graphLabel(value) {
  return meaningfulText(value);
}

function compoundGraphLabel(value) {
  const text = meaningfulText(value);
  if (!text) return "";
  const normalized = normalizeValue(text).replace(/[-_]+/g, " ");
  if (COMPOUND_CLASS_LABEL_RE.test(normalized)) return "";
  if (REFERENCE_COMPOUND_LABEL_RE.test(normalized)) return "";
  if (COMPOUND_LIST_LABEL_RE.test(normalized)) return "";
  return text;
}

function rightEntityKey() {
  return mode === "mechanistic" ? "target" : "disorder";
}

function entityViewOptionsForMode() {
  return ENTITY_VIEW_OPTIONS[mode] || [];
}

function currentEntityViewKey() {
  const options = entityViewOptionsForMode();
  const selectedKey = entityView[mode];
  if (options.some((option) => option.key === selectedKey)) return selectedKey;
  return options[0]?.key || "";
}

function currentEntityViewOption() {
  const key = currentEntityViewKey();
  return entityViewOptionsForMode().find((option) => option.key === key) || null;
}

function rightEntityLabel(plural = true) {
  if (claimLayer !== "normalized") {
    return mode === "mechanistic"
      ? plural
        ? "Mechanistic nodes"
        : "Mechanistic node"
      : plural
        ? "Clinical nodes"
        : "Clinical node";
  }
  const option = currentEntityViewOption();
  if (!option) return mode === "mechanistic" ? (plural ? "Targets" : "Target") : plural ? "Conditions" : "Condition";
  return plural ? option.label : option.singular;
}

function lowerRightEntityLabel(plural = true) {
  if (claimLayer !== "normalized") {
    return mode === "mechanistic"
      ? plural
        ? "mechanistic nodes"
        : "mechanistic node"
      : plural
        ? "clinical nodes"
        : "clinical node";
  }
  const option = currentEntityViewOption();
  if (!option) return mode === "mechanistic" ? (plural ? "targets" : "target") : plural ? "conditions" : "condition";
  return plural ? option.lowerPlural : option.lowerSingular;
}

function entityKindForClaim(claim) {
  return normalizeValue(claim.kg_entity_kind || claim.entity_kind);
}

function claimsForEntityView(baseClaims) {
  if (claimLayer !== "normalized") return baseClaims;
  const activeKind = currentEntityViewKey();
  if (!activeKind) return baseClaims;
  return baseClaims.filter((claim) => entityKindForClaim(claim) === activeKind);
}

function activeClaimsForMode() {
  const baseClaims = mode === "mechanistic" ? claims : disorderClaims;
  return graphViewClaims(claimsForEntityView(baseClaims));
}

function passesAccessAndYearFilters(claim, yearRange) {
  if (fullTextOnlyToggle?.checked && claimSourceAccessLevel(claim) !== "full_text_seen") {
    return false;
  }
  if (yearRange?.constrained) {
    const year = parseYearValue(claim.study_year);
    if (year === null) return false;
    if (year < yearRange.min || year > yearRange.max) return false;
  }
  return true;
}

function activeOutcomeScaleClaims() {
  if (mode !== "disorders" || evidenceView !== "primary") return [];
  const yearRange = activeYearRange(activeClaimsForMode());
  return graphViewClaims(disorderClaims)
    .filter((claim) => isOutcomeScaleClaim(claim))
    .filter((claim) => passesAccessAndYearFilters(claim, yearRange));
}

function studyJoinKey(claim) {
  const doi = normalizeDoi(claim.study_doi);
  if (doi) return `doi:${doi}`;
  const openalex = normalizeValue(claim.openalex_id);
  if (openalex) return `openalex:${openalex}`;
  const title = normalizeValue(claim.study_title);
  const year = parseYearValue(claim.study_year);
  if (title || year !== null) return `title:${title}|${year || ""}`;
  return "";
}

function evidenceScopeKey(claim) {
  const study = studyJoinKey(claim);
  const compound = normalizeValue(claim.compound);
  if (!study || !compound) return "";
  return `${study}|compound:${compound}`;
}

function outcomeScaleClaimsForChart(items) {
  const scaleItems = items.filter((claim) => isOutcomeScaleClaim(claim));
  if (scaleItems.length) return scaleItems;

  const activeScaleClaims = activeOutcomeScaleClaims();
  const scopeKeys = new Set(items.map(evidenceScopeKey).filter(Boolean));
  if (!scopeKeys.size) return activeScaleClaims;
  return activeScaleClaims.filter((claim) => scopeKeys.has(evidenceScopeKey(claim)));
}

function setDetailGraphFilter(items) {
  detailGraphFilter = {
    items: new Set(items),
  };
  refreshMainViews();
}

function clearDetailGraphFilter() {
  detailGraphFilter = null;
}

function claimSourceAccessLevel(claim) {
  const sourceAccess = normalizeValue(claim.source_access_level);
  if (sourceAccess) return sourceAccess;
  const accessLevel = normalizeValue(claim.access_level);
  return accessLevel === "secondary_summary" ? "" : accessLevel;
}

function applyClaimLayerStore() {
  const store = claimStores[claimLayer] || claimStores.normalized;
  claims = store.mechanistic || [];
  disorderClaims = store.disorders || [];
}

function primaryEvidenceClaims(baseClaims) {
  return baseClaims.filter(
    (claim) =>
      (normalizeValue(claim.paper_assessment_route) === "primary_evidence" ||
        (normalizeValue(claim.paper_type) === "primary_results" &&
          normalizeValue(claim.source_type) === "primary_study")) &&
      normalizeValue(claim.access_level) !== "secondary_summary",
  );
}

function secondaryLiteratureClaims(baseClaims) {
  return baseClaims.filter((claim) => {
    const route = normalizeValue(claim.paper_assessment_route);
    const accessLevel = normalizeValue(claim.access_level);
    if (route === "secondary_literature" || accessLevel === "secondary_summary") return true;
    if (route === "primary_evidence") return false;
    const sourceFamily = normalizeValue(claim.source_family);
    const sourceType = normalizeValue(claim.source_type);
    const paperType = normalizeValue(claim.paper_type);
    return (
      sourceFamily === "evidence_synthesis" ||
      ["secondary_evidence", "review", "meta_analysis"].includes(sourceType) ||
      ["systematic_review", "meta_analysis", "review"].includes(paperType)
    );
  });
}

function claimIdentity(claim, index) {
  const rightKey = claim.target !== undefined ? "target" : "disorder";
  const parts = [
    claim.compound || "",
    claim[rightKey] || "",
    claim.study_doi || "",
    claim.openalex_id || "",
    claim.mechanism_type || "",
    claim.assay_type || "",
    claim.assay_family || "",
    claim.action_type || "",
    claim.affinity_type || "",
    claim.affinity_value || "",
    claim.outcome_type || "",
    claim.outcome_measure || "",
    claim.sample_size_total || "",
    claim.timepoint || "",
    claim.comparator || "",
    claim.evidence_locator || "",
    claim.supporting_quote || "",
  ];
  const key = parts.join("|");
  return key.replace(/\|/g, "") ? key : `claim-${index}`;
}

function dedupeClaims(items) {
  const seen = new Set();
  const out = [];
  items.forEach((claim, index) => {
    const key = claimIdentity(claim, index);
    if (seen.has(key)) return;
    seen.add(key);
    out.push(claim);
  });
  return out;
}

function graphViewClaims(baseClaims) {
  if (evidenceView === "secondary") return secondaryLiteratureClaims(baseClaims);
  return primaryEvidenceClaims(baseClaims);
}

function parseYearValue(raw) {
  const text = (raw || "").toString().trim();
  if (!text) return null;

  const yearMatch = text.match(/\b(18|19|20)\d{2}\b/);
  if (yearMatch) return Number(yearMatch[0]);

  const numeric = Number(text);
  if (!Number.isFinite(numeric)) return null;
  const year = Math.trunc(numeric);
  if (year < 1800 || year > 3000) return null;
  return year;
}

function yearBoundsFromClaims(data) {
  let minYear = Number.POSITIVE_INFINITY;
  let maxYear = Number.NEGATIVE_INFINITY;

  data.forEach((claim) => {
    const year = parseYearValue(claim.study_year);
    if (year === null) return;
    if (year < minYear) minYear = year;
    if (year > maxYear) maxYear = year;
  });

  if (!Number.isFinite(minYear) || !Number.isFinite(maxYear)) return null;
  return { min: minYear, max: maxYear };
}

function syncYearFilterControls(data, forceReset = false) {
  if (!yearMinFilter || !yearMaxFilter) return;

  const bounds = yearBoundsFromClaims(data);
  if (!bounds) {
    yearMinFilter.value = "";
    yearMaxFilter.value = "";
    yearMinFilter.disabled = true;
    yearMaxFilter.disabled = true;
    yearFilterState[mode] = { min: "", max: "" };
    return;
  }

  yearMinFilter.disabled = false;
  yearMaxFilter.disabled = false;
  yearMinFilter.min = String(bounds.min);
  yearMinFilter.max = String(bounds.max);
  yearMaxFilter.min = String(bounds.min);
  yearMaxFilter.max = String(bounds.max);

  const state = yearFilterState[mode] || { min: "", max: "" };
  let minYear = parseYearValue(forceReset ? "" : state.min);
  let maxYear = parseYearValue(forceReset ? "" : state.max);

  if (minYear === null) minYear = bounds.min;
  if (maxYear === null) maxYear = bounds.max;

  minYear = clampNumber(minYear, bounds.min, bounds.max);
  maxYear = clampNumber(maxYear, bounds.min, bounds.max);
  if (minYear > maxYear) {
    [minYear, maxYear] = [maxYear, minYear];
  }

  yearFilterState[mode] = { min: String(minYear), max: String(maxYear) };
  yearMinFilter.value = String(minYear);
  yearMaxFilter.value = String(maxYear);
}

function activeYearRange(data) {
  if (!yearMinFilter || !yearMaxFilter) {
    return { constrained: false, min: null, max: null };
  }

  const bounds = yearBoundsFromClaims(data);
  if (!bounds) {
    return { constrained: false, min: null, max: null };
  }

  let minYear = parseYearValue(yearMinFilter.value);
  let maxYear = parseYearValue(yearMaxFilter.value);
  if (minYear === null) minYear = bounds.min;
  if (maxYear === null) maxYear = bounds.max;

  minYear = clampNumber(minYear, bounds.min, bounds.max);
  maxYear = clampNumber(maxYear, bounds.min, bounds.max);
  if (minYear > maxYear) {
    [minYear, maxYear] = [maxYear, minYear];
  }

  yearMinFilter.value = String(minYear);
  yearMaxFilter.value = String(maxYear);
  yearFilterState[mode] = { min: String(minYear), max: String(maxYear) };

  const constrained = minYear > bounds.min || maxYear < bounds.max;
  return {
    constrained,
    min: minYear,
    max: maxYear,
  };
}

const textMeasureCanvas = document.createElement("canvas");
const textMeasureContext = textMeasureCanvas.getContext("2d");

function clampNumber(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function edgeWidthForCount(count, maxCount) {
  const minWidth = 1.5;
  const maxWidth = 10.5;
  const safeCount = Math.max(1, Number(count) || 1);
  const safeMax = Math.max(1, Number(maxCount) || 1);
  if (safeMax <= 1) return 3.0;
  const normalized = (Math.sqrt(safeCount) - 1) / (Math.sqrt(safeMax) - 1);
  return minWidth + normalized * (maxWidth - minWidth);
}

function interpolateNumber(start, end, ratio) {
  return Math.round(start + (end - start) * ratio);
}

function graphColorForIndex(index, total) {
  if (total <= 1) return GRAPH_COLOR_STOPS[0];
  const clampedIndex = clampNumber(index, 0, total - 1);
  const position = (clampedIndex / (total - 1)) * (GRAPH_COLOR_STOPS.length - 1);
  const lower = Math.floor(position);
  const upper = Math.min(GRAPH_COLOR_STOPS.length - 1, lower + 1);
  const ratio = position - lower;
  const start = GRAPH_COLOR_STOPS[lower];
  const end = GRAPH_COLOR_STOPS[upper];
  return {
    r: interpolateNumber(start.r, end.r, ratio),
    g: interpolateNumber(start.g, end.g, ratio),
    b: interpolateNumber(start.b, end.b, ratio),
  };
}

function rgbString(color) {
  return `rgb(${color.r}, ${color.g}, ${color.b})`;
}

function rgbaString(color, alpha) {
  return `rgba(${color.r}, ${color.g}, ${color.b}, ${alpha})`;
}

function applyGraphNodeColor(node, color) {
  node.style.setProperty("--node-color", rgbString(color));
  node.style.setProperty("--node-fill", rgbaString(color, 0.2));
  node.style.setProperty("--node-glow", rgbaString(color, 0.44));
}

function estimateLabelWidth(label) {
  const text = (label || "").toString();
  return Math.max(40, Math.ceil(text.length * 6.8));
}

function estimateGraphLabelWidth(label) {
  return Math.min(GRAPH_LABEL_MAX_WIDTH_PX, estimateLabelWidth(label));
}

function truncateLabel(label, maxChars) {
  const text = (label || "").toString();
  if (text.length <= maxChars) return text;
  if (maxChars <= 1) return text.slice(0, 1);
  return `${text.slice(0, Math.max(1, maxChars - 3))}...`;
}

function measureLabelWidth(text) {
  if (!textMeasureContext) {
    return estimateLabelWidth(text);
  }
  textMeasureContext.font = '16px "IBM Plex Sans", sans-serif';
  return textMeasureContext.measureText((text || "").toString()).width;
}

function fitLabelToWidth(label, maxWidthPx) {
  const text = (label || "").toString();
  if (maxWidthPx <= 18) return "";
  if (measureLabelWidth(text) <= maxWidthPx) return text;

  const suffix = "...";
  const suffixWidth = measureLabelWidth(suffix);
  let low = 0;
  let high = text.length;
  let best = "";

  while (low <= high) {
    const mid = Math.floor((low + high) / 2);
    const candidate = `${text.slice(0, mid)}${suffix}`;
    if (measureLabelWidth(candidate) <= maxWidthPx) {
      best = candidate;
      low = mid + 1;
    } else {
      high = mid - 1;
    }
  }

  if (best) return best;
  if (suffixWidth <= maxWidthPx) return suffix;
  return "";
}

function wrapLabelToLines(label, maxWidthPx, maxLines = 2) {
  const rawText = (label || "").toString().trim();
  if (!rawText) return [""];
  if (measureLabelWidth(rawText) <= maxWidthPx) return [rawText];

  const words = rawText.split(/\s+/).filter(Boolean);
  if (words.length === 1) {
    return [fitLabelToWidth(rawText, maxWidthPx)];
  }

  const lines = [];
  let current = "";

  for (let i = 0; i < words.length; i += 1) {
    const word = words[i];
    const candidate = current ? `${current} ${word}` : word;

    if (measureLabelWidth(candidate) <= maxWidthPx) {
      current = candidate;
      continue;
    }

    if (!current) {
      current = fitLabelToWidth(word, maxWidthPx);
    }

    lines.push(current);
    current = word;

    if (lines.length === maxLines - 1) {
      const remainder = [current, ...words.slice(i + 1)].join(" ");
      lines.push(fitLabelToWidth(remainder, maxWidthPx));
      return lines.slice(0, maxLines);
    }
  }

  if (current) {
    lines.push(fitLabelToWidth(current, maxWidthPx));
  }

  return lines.slice(0, maxLines);
}

function setWrappedSvgLabel(textNode, fullLabel, maxWidthPx, x, centerY) {
  const lines = wrapLabelToLines(fullLabel, maxWidthPx, 2);
  const lineHeight = 17;
  const startY = centerY - ((lines.length - 1) * lineHeight) / 2 + 4;
  textNode.textContent = "";

  lines.forEach((line, index) => {
    const tspan = document.createElementNS("http://www.w3.org/2000/svg", "tspan");
    tspan.setAttribute("x", x);
    tspan.setAttribute("y", startY + index * lineHeight);
    tspan.textContent = line;
    textNode.appendChild(tspan);
  });
}

function studyId(claim) {
  return claim.study_doi || claim.openalex_id || "unknown";
}

function countStudies(items) {
  return new Set(items.map(studyId)).size;
}

function labelFromSlug(value) {
  return (value || "")
    .toString()
    .split(/[_\s]+/)
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function paperTypeLabel(paperType) {
  const normalized = normalizeValue(paperType);
  if (normalized === "primary_results") return "primary results";
  if (normalized === "conference_or_poster_abstract") return "conference/poster";
  if (!normalized) return "paper type unknown";
  return labelFromSlug(normalized);
}

function resultDirectionLabel(direction) {
  const normalized = normalizeValue(direction);
  if (!normalized) return "unclear";
  if (normalized === "null") return "null finding";
  return labelFromSlug(normalized);
}

function studyDesignLabel(design) {
  const normalized = normalizeValue(design);
  if (
    !normalized ||
    ["unknown", "pending_curation", "not_reported", "not_applicable", "not reported", "not applicable"].includes(
      normalized
    )
  ) {
    return "";
  }

  const text = normalized.replace(/[_/()-]+/g, " ").replace(/\s+/g, " ").trim();
  if (/phase\s*3/.test(text) && /randomi[sz]ed|controlled|trial/.test(text)) return "phase 3 rct";
  if (/phase\s*2/.test(text) && /randomi[sz]ed|controlled|trial/.test(text)) return "phase 2 rct";
  if (/randomi[sz]ed|randomised|double blind|controlled trial|placebo controlled|crossover/.test(text)) return "rct";
  if (/open label/.test(text)) return "open label";
  if (/dose finding|dose response|rising tolerance/.test(text)) return "dose finding";
  if (/post hoc/.test(text)) return "post-hoc";
  if (/follow up|followup/.test(text)) return "follow-up";
  if (/case control|cross sectional|observational|naturalistic|survey|internet survey|prospective/.test(text)) {
    return "observational";
  }
  if (/qualitative|ethnographic|user generated|reddit|interview/.test(text)) return "qualitative";
  if (/retrospective|chart review|case series|single arm effectiveness/.test(text)) return "retrospective";
  if (/case report/.test(text)) return "case report";
  if (/case series/.test(text)) return "case series";
  if (/preclinical|animal|mouse|mice|rat|rats|in vivo/.test(text)) return "preclinical";
  if (/clinical trial/.test(text)) return "clinical trial";
  if (/binding|radioligand|competition/.test(text)) return "binding assay";
  if (/functional receptor|potency|uptake/.test(text)) return "functional assay";
  if (/in vitro|enzyme assay|pharmacology study|microdialysis|correlation study/.test(text)) return "in vitro";
  if (/computational|in silico|modeling|modelling|admet/.test(text)) return "computational";
  if (/pka|pk a|pka determination|chemical/.test(text)) return "chemical assay";
  if (/experimental|within subject|pretreatment/.test(text)) return "experimental";
  return "";
}

function accessLevelLabel(accessLevel) {
  const normalized = normalizeValue(accessLevel);
  const labels = {
    full_text_seen: "full text",
    abstract_only: "abstract only",
    secondary_summary: "secondary summary",
  };
  return labels[normalized] || labelFromSlug(normalized);
}

function classToken(value) {
  return normalizeValue(value).replace(/_/g, "-").replace(/[^a-z0-9-]+/g, "-") || "unknown";
}

function chipHtml(kind, label, token = label) {
  if (!label) return "";
  return `<span class="badge ${kind} ${classToken(token)}">${label}</span>`;
}

function paperTypeBadgeHtml(paperType) {
  const normalized = normalizeValue(paperType) || "other";
  const label =
    normalized === "primary_results" ? "primary research" : paperTypeLabel(normalized);
  return chipHtml("paper-type", label, normalized);
}

function studyDesignBadgeHtml(design) {
  const label = studyDesignLabel(design);
  return chipHtml("study-design", label, label);
}

function accessLevelBadgeHtml(accessLevel) {
  return chipHtml("access-level", accessLevelLabel(accessLevel), accessLevel);
}

function resultDirectionBadgeHtml(direction) {
  const normalized = normalizeValue(direction);
  if (!normalized || normalized === "not_applicable") return "";
  return chipHtml("result-direction", resultDirectionLabel(normalized), normalized);
}

function systemBadgeHtml(system) {
  const normalized = normalizeValue(system);
  if (!normalized || ["unknown", "not_applicable", "not applicable"].includes(normalized)) return "";
  return chipHtml("system", displayFieldLabel(normalized), normalized);
}

function supportLabel(support) {
  const normalized = normalizeValue(support);
  if (normalized === "not_supported") return "not supported";
  if (!normalized) return "support unknown";
  return labelFromSlug(normalized);
}

function supportBadgeHtml(support) {
  return chipHtml("support", supportLabel(support), support || "unknown");
}

function reviewBadgeHtml(claim) {
  return claim.needs_human_review ? chipHtml("review", "needs review", "needs_review") : "";
}

function claimBadgeHtml(claim) {
  return [
    reviewBadgeHtml(claim),
    systemBadgeHtml(claim.system),
    mode === "disorders" ? studyDesignBadgeHtml(claim.study_design) : "",
    accessLevelBadgeHtml(claim.access_level),
    paperTypeBadgeHtml(claim.paper_type),
  ]
    .filter(Boolean)
    .join("");
}

function setDetailHeader(title) {
  detailTitle.textContent = title;
}

function renderDetailEmpty() {
  detailBody.innerHTML = '<div class="detail-empty">No selection yet.</div>';
}

function clearSelectedStyles() {
  graphEl.querySelectorAll(".selected").forEach((el) => el.classList.remove("selected"));
}

function clearSelection() {
  selected = null;
  isolateSelection = false;
  detailGraphFilter = null;
  clearSelectedStyles();
  setDetailHeader(defaultDetail.title);
  renderDetailEmpty();
  hideTooltip();
  scheduleRender();
}

function showTooltip(content, event) {
  tooltip.innerHTML = content;
  tooltip.style.opacity = "1";
  tooltip.style.transform = "translateY(0)";
  positionTooltip(event);
}

function moveTooltip(event) {
  positionTooltip(event);
}

function hideTooltip() {
  tooltip.style.opacity = "0";
  tooltip.style.transform = "translateY(6px)";
}

function showTooltipForElement(content, element) {
  const rect = element.getBoundingClientRect();
  showTooltip(content, {
    clientX: rect.left + rect.width / 2,
    clientY: rect.top + rect.height / 2,
  });
}

function positionTooltip(event) {
  const gap = 25;
  const padding = 8;
  const rect = tooltip.getBoundingClientRect();
  const maxLeft = Math.max(padding, window.innerWidth - rect.width - padding);
  const maxTop = Math.max(padding, window.innerHeight - rect.height - padding);
  const centeredLeft = event.clientX - rect.width / 2;
  const desiredTop = event.clientY + gap;

  tooltip.style.left = `${clampNumber(centeredLeft, padding, maxLeft)}px`;
  tooltip.style.top = `${clampNumber(desiredTop, padding, maxTop)}px`;
}

function openAlexUrl(openalexId) {
  const id = (openalexId || "").toString().trim();
  if (!id) return "";
  if (id.startsWith("http://") || id.startsWith("https://")) return id;
  return `https://openalex.org/${id}`;
}

function doiUrl(doiValue) {
  const raw = (doiValue || "").toString().trim();
  if (!raw) return "";
  if (raw.startsWith("http://") || raw.startsWith("https://")) return raw;
  const normalized = raw.replace(/^doi:\s*/i, "").replace(/^https?:\/\/doi\.org\//i, "");
  if (!normalized) return "";
  return `https://doi.org/${encodeURI(normalized)}`;
}

function normalizeAuthors(value) {
  if (Array.isArray(value)) {
    return value
      .map((item) => (item || "").toString().trim())
      .filter(Boolean)
      .join(", ");
  }
  if (value && typeof value === "object") {
    const candidates = [];
    if (value.name) candidates.push(value.name);
    if (value.display_name) candidates.push(value.display_name);
    if (value.author) candidates.push(value.author);
    if (candidates.length) {
      return candidates
        .map((item) => (item || "").toString().trim())
        .filter(Boolean)
        .join(", ");
    }
  }
  return (value || "").toString().trim();
}

function claimAuthors(claim) {
  const authorFields = [
    claim.authors,
    claim.author_list,
    claim.study_authors,
    claim.author,
    claim.first_author,
  ];
  for (const field of authorFields) {
    const normalized = normalizeAuthors(field);
    if (normalized) return normalized;
  }
  return "";
}

function normalizeDoi(value) {
  return (value || "")
    .toString()
    .trim()
    .replace(/^doi:\s*/i, "")
    .replace(/^https?:\/\/doi\.org\//i, "");
}

function splitAuthorNames(value) {
  const text = cleanDisplayText(normalizeAuthors(value));
  if (!text) return [];
  if (text.includes(";")) {
    return text
      .split(";")
      .map((part) => cleanDisplayText(part))
      .filter(Boolean);
  }
  return [text];
}

function citationAuthors(value) {
  const authors = splitAuthorNames(value);
  if (!authors.length) return "Unknown authors";
  if (authors.length <= 3) return authors.join(", ");
  return `${authors.slice(0, 3).join(", ")}, et al.`;
}

function sentencePart(value) {
  const text = cleanDisplayText(value);
  if (!text) return "";
  return /[.!?]$/.test(text) ? text : `${text}.`;
}

function normalizedKgClaims() {
  return [...claimStores.normalized.disorders, ...claimStores.normalized.mechanistic];
}

function updateStats() {
  const rightLabelEl = stats.indications?.previousElementSibling;
  const targetLabelEl = stats.targets?.previousElementSibling;
  if (rightLabelEl) rightLabelEl.textContent = "Indications";
  if (targetLabelEl) targetLabelEl.textContent = "Targets";

  const totalClaims = normalizedKgClaims();
  stats.compounds.textContent = formatCompactNumber(
    unique(totalClaims.map((claim) => compoundGraphLabel(claim.compound)).filter(Boolean)).length
  );
  stats.indications.textContent = formatCompactNumber(
    unique(
      claimStores.normalized.disorders
        .filter((claim) => entityKindForClaim(claim) === "condition_indication")
        .map((claim) => graphLabel(claim.disorder))
        .filter(Boolean)
    ).length
  );
  stats.targets.textContent = formatCompactNumber(
    unique(
      claimStores.normalized.mechanistic
        .filter((claim) => entityKindForClaim(claim) === "target")
        .map((claim) => graphLabel(claim.target))
        .filter(Boolean)
    ).length
  );
  stats.studies.textContent = formatCompactNumber(uniqueStudyCount(totalClaims));
}

function applyFilters() {
  const rightKey = rightEntityKey();
  const activeClaims = activeClaimsForMode();
  const yearRange = activeYearRange(activeClaims);
  const fullTextOnly = Boolean(fullTextOnlyToggle?.checked);

  const baseFiltered = activeClaims.filter((claim) => {
    if (fullTextOnly && claimSourceAccessLevel(claim) !== "full_text_seen") {
      return false;
    }

    if (yearRange.constrained) {
      const year = parseYearValue(claim.study_year);
      if (year === null) return false;
      if (year < yearRange.min || year > yearRange.max) return false;
    }

    return true;
  });

  const detailFiltered = detailGraphFilter?.items
    ? baseFiltered.filter((claim) => detailGraphFilter.items.has(claim))
    : baseFiltered;

  if (!selected || !isolateSelection) return detailFiltered;

  if (selected.type === "edge") {
    return detailFiltered.filter(
      (claim) => claim.compound === selected.compound && claim[rightKey] === selected.target
    );
  }
  if (selected.type === "compound") {
    return detailFiltered.filter((claim) => claim.compound === selected.name);
  }
  if (selected.type === "target") {
    return detailFiltered.filter((claim) => claim[rightKey] === selected.name);
  }
  return detailFiltered;
}

function selectionIsValid(data) {
  if (!selected) return true;
  const rightKey = rightEntityKey();
  if (selected.type === "edge") {
    return data.some((claim) => claim.compound === selected.compound && claim[rightKey] === selected.target);
  }
  if (selected.type === "compound") {
    return data.some((claim) => claim.compound === selected.name);
  }
  if (selected.type === "target") {
    return data.some((claim) => claim[rightKey] === selected.name);
  }
  return false;
}

function disconnectCardsLoadObserver() {
  if (cardsLoadObserver) {
    cardsLoadObserver.disconnect();
    cardsLoadObserver = null;
  }
}

function disconnectBibliographyLoadObserver() {
  if (bibliographyLoadObserver) {
    bibliographyLoadObserver.disconnect();
    bibliographyLoadObserver = null;
  }
}

function createClaimCardElement(claim) {
  const card = document.createElement("div");
  card.className = "card";

  const badges = claimBadgeHtml(claim);

  const doiValue = meaningfulText(claim.study_doi);
  const openAlexId = meaningfulText(claim.openalex_id);
  const doiHref = doiUrl(doiValue);
  const sourceLine = doiHref
    ? claimFieldLine(
        "DOI",
        `<a href="${doiHref}" target="_blank" rel="noopener noreferrer">${escapeHtml(
          doiValue
        )}</a>`
      )
    : openAlexId
      ? claimFieldLine("OpenAlex", escapeHtml(String(openAlexId)))
      : "";

  const relation = claimRelationText(claim);
  const authors = claimAuthors(claim);
  const journal = meaningfulText(claim.study_journal || claim.journal);

  const mechanismSummary = [
    cleanDisplayText(claim.mechanism_type),
    cleanDisplayText(claim.action_type),
  ]
    .filter(Boolean)
    .filter((part, index, parts) => parts.indexOf(part) === index)
    .join(" • ");
  const assaySummary = [
    cleanDisplayText(claim.assay_type),
    cleanDisplayText(claim.assay_family),
    cleanDisplayText(claim.model_or_system),
  ]
    .filter(Boolean)
    .filter((part, index, parts) => parts.indexOf(part) === index)
    .join(" • ");
  const mainFinding = claimMainFindingText(claim);
  const mainFindingLine = mainFinding
    ? `<div class="card-main-finding"><span class="card-field-label">${
        mode === "mechanistic" ? "Finding" : "Outcome"
      }:</span> ${escapeHtml(mainFinding)}</div>`
    : "";

  const evidenceLines =
    mode === "disorders"
      ? [
          claimFieldLineFromValue("Scale", claim.outcome_measure_normalized),
          claimFieldLineFromValue("Sample", sampleSizeText(claim)),
          claimFieldLineFromValue("Context", claim.clinical_context_condition),
          claimFieldLineFromValue("Population", claim.population),
        ].join("")
      : [
          claimFieldLineFromValue("Mechanism", mechanismSummary),
          claimFieldLineFromValue("Assay", assaySummary),
          claimFieldLineFromValue("Species", claim.species),
        ].join("")
  const studyTitle = cleanDisplayText(claim.study_title);
  const studyLine = studyTitle
    ? `${escapeHtml(studyTitle)}${
        claim.study_year != null && String(claim.study_year) !== ""
          ? ` (${escapeHtml(String(claim.study_year))})`
          : ""
      }`
    : "not available";

  card.innerHTML = `
      <div class="card-header">
        <h3>${relation}</h3>
        <div class="badge-row">${badges}</div>
      </div>
      <div class="meta">
        ${mainFindingLine}
        ${claimFieldLine("Study", studyLine)}
        ${claimFieldLine("Authors", escapeHtml(authors || "not available"))}
        ${sourceLine ? sourceLine : ""}
        ${claimFieldLine("Journal", escapeHtml(journal || "not available"))}
        ${claimFieldLineFromValue("Trial registry", claim.trial_registry_ids)}
        ${evidenceLines}
      </div>
    `;

  return card;
}

function renderCards(data) {
  const searchValue = normalizeValue(searchInput?.value);
  const rightKey = rightEntityKey();
  const cardData = !searchValue
    ? data
    : data.filter((claim) => {
        const haystack = [
          claim.compound,
          claim[rightKey],
          claim.mechanism_type,
          claim.assay_type,
          claim.assay_family,
          claim.action_type,
          claim.study_title,
          claim.affinity_type,
          claim.outcome_type,
          claim.outcome_domain,
          claim.outcome_measure_normalized,
          claim.result_direction,
          claim.sample_size_total,
          claim.sample_size_by_arm,
          claim.population,
          claim.intervention_or_exposure,
          claim.comparator,
          claim.dose,
          claim.timepoint,
          claim.adverse_events,
          claim.support,
          claim.supporting_quote,
          claim.raw_entity_label,
          claim.entity_role,
          claim.clinical_context_condition,
          claim.graph_entity_label,
          claim.graph_exclusion_reason,
          claim.normalization_status,
          claim.normalization_notes,
          claim.canonical_compound,
          claim.canonical_entity,
          claim.paper_assessment_route,
          claim.paper_type,
          claim.source_family,
          claim.source_type,
          claimAuthors(claim),
          claim.study_doi,
          claim.openalex_id,
        ]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        return haystack.includes(searchValue);
      });

  disconnectCardsLoadObserver();
  cardsEl.innerHTML = "";

  if (!cardData.length) {
    return;
  }

  let rendered = 0;

  function appendCardsChunk() {
    const end = Math.min(rendered + LIST_CHUNK_SIZE, cardData.length);
    for (let i = rendered; i < end; i += 1) {
      cardsEl.appendChild(createClaimCardElement(cardData[i]));
    }
    rendered = end;
  }

  function removeCardsSentinel() {
    cardsEl.querySelector(".cards-load-sentinel")?.remove();
  }

  function attachCardsSentinelIfNeeded() {
    disconnectCardsLoadObserver();
    removeCardsSentinel();
    if (rendered >= cardData.length) return;

    const sentinel = document.createElement("div");
    sentinel.className = "cards-load-sentinel";
    sentinel.setAttribute("aria-hidden", "true");
    cardsEl.appendChild(sentinel);

    cardsLoadObserver = new IntersectionObserver(
      (entries) => {
        if (!entries[0]?.isIntersecting) return;
        disconnectCardsLoadObserver();
        appendCardsChunk();
        attachCardsSentinelIfNeeded();
      },
      { root: cardsEl, rootMargin: "360px", threshold: 0 }
    );
    cardsLoadObserver.observe(sentinel);
  }

  appendCardsChunk();
  attachCardsSentinelIfNeeded();
}

function bibliographyEntryId(entry, index = 0) {
  if (entry.id) return entry.id;
  if (entry.doi) return `doi:${normalizeValue(entry.doi)}`;
  if (entry.openalexId) return `openalex:${normalizeValue(entry.openalexId)}`;
  const titleKey = normalizeValue(entry.title);
  if (titleKey || entry.year) return `title:${titleKey}|${entry.year || ""}`;
  return `bibliography-entry-${index}`;
}

function normalizeBibliographyPaper(item, index = 0) {
  const year = parseYearValue(item?.year ?? item?.study_year ?? item?.publication_date);
  const entry = {
    id: cleanDisplayText(item?.id),
    doi: normalizeDoi(item?.doi ?? item?.study_doi),
    openalexId: cleanDisplayText(item?.openalex_id ?? item?.openalexId),
    title: cleanDisplayText(item?.title ?? item?.study_title) || "Untitled study",
    authors: cleanDisplayText(item?.authors ?? item?.author_list ?? item?.author ?? item?.first_author),
    year: year ?? "",
    journal: cleanDisplayText(item?.journal ?? item?.study_journal),
    publicationDate: cleanDisplayText(item?.publication_date ?? item?.publicationDate),
    publicationType: cleanDisplayText(item?.publication_type ?? item?.publicationType),
    publisher: cleanDisplayText(item?.publisher),
    trialRegistryIds: cleanDisplayText(item?.trial_registry_ids ?? item?.trialRegistryIds),
    keywords: cleanDisplayText(item?.keywords),
    meshTerms: cleanDisplayText(item?.mesh_terms ?? item?.meshTerms),
    contexts: Array.isArray(item?.contexts)
      ? item.contexts
          .map((context) => ({
            compound: cleanDisplayText(context?.compound),
            entity: cleanDisplayText(context?.entity ?? context?.target ?? context?.disorder),
          }))
          .filter((context) => context.compound || context.entity)
      : [],
  };
  entry.id = bibliographyEntryId(entry, index);
  return entry;
}

function bibliographyFromPayload(payload) {
  const papers = Array.isArray(payload?.papers) ? payload.papers : [];
  return papers.map((paper, index) => normalizeBibliographyPaper(paper, index));
}

function bibliographyLookup(modeKey) {
  const rows = bibliographyByMode[modeKey] || [];
  const byDoi = new Map();
  const byOpenAlex = new Map();
  rows.forEach((entry) => {
    const doiKey = normalizeValue(normalizeDoi(entry.doi));
    if (doiKey && !byDoi.has(doiKey)) byDoi.set(doiKey, entry);
    const openAlexKey = normalizeValue(entry.openalexId);
    if (openAlexKey && !byOpenAlex.has(openAlexKey)) byOpenAlex.set(openAlexKey, entry);
  });
  return { byDoi, byOpenAlex };
}

function enrichClaimsWithBibliographyMetadata(items, modeKey) {
  const lookup = bibliographyLookup(modeKey);
  return items.map((claim) => {
    const doiKey = normalizeValue(normalizeDoi(claim.study_doi));
    const openAlexKey = normalizeValue(claim.openalex_id);
    const entry = (doiKey && lookup.byDoi.get(doiKey)) || (openAlexKey && lookup.byOpenAlex.get(openAlexKey));
    if (!entry) return claim;
    return {
      ...claim,
      study_journal: claim.study_journal || entry.journal,
      publication_type: claim.publication_type || entry.publicationType,
      publication_date: claim.publication_date || entry.publicationDate,
      publisher: claim.publisher || entry.publisher,
      trial_registry_ids: claim.trial_registry_ids || entry.trialRegistryIds,
      authors: claimAuthors(claim) ? claim.authors : entry.authors,
    };
  });
}

function addBibliographyContext(entry, compound, entity) {
  const compoundText = cleanDisplayText(compound);
  const entityText = cleanDisplayText(entity);
  if (!compoundText && !entityText) return;
  const key = `${normalizeValue(compoundText)}|${normalizeValue(entityText)}`;
  const exists = entry.contexts.some(
    (context) => `${normalizeValue(context.compound)}|${normalizeValue(context.entity)}` === key
  );
  if (!exists) entry.contexts.push({ compound: compoundText, entity: entityText });
}

function bibliographyRowsFromClaims(data) {
  const rightKey = rightEntityKey();
  const studies = new Map();

  data.forEach((claim, index) => {
    const baseEntry = normalizeBibliographyPaper(
      {
        id: studyKey(claim, index),
        doi: claim.study_doi,
        openalex_id: claim.openalex_id,
        title: claim.study_title,
        authors: claimAuthors(claim),
        year: claim.study_year,
        journal: claim.study_journal ?? claim.journal,
        publication_type: claim.publication_type,
        publication_date: claim.publication_date,
        publisher: claim.publisher,
        trial_registry_ids: claim.trial_registry_ids,
      },
      index
    );
    addBibliographyContext(baseEntry, claim.compound, claim[rightKey]);
    const id = bibliographyEntryId(baseEntry, index);
    const existing = studies.get(id);
    if (!existing) {
      studies.set(id, baseEntry);
      return;
    }

    ["doi", "openalexId", "title", "authors", "year", "journal", "publicationDate", "publicationType", "publisher", "trialRegistryIds"].forEach(
      (field) => {
        if (!existing[field] && baseEntry[field]) existing[field] = baseEntry[field];
      }
    );
    baseEntry.contexts.forEach((context) => addBibliographyContext(existing, context.compound, context.entity));
  });

  return Array.from(studies.values()).sort((a, b) => {
    const yearDiff = (Number(b.year) || 0) - (Number(a.year) || 0);
    if (yearDiff !== 0) return yearDiff;
    return (a.title || "").localeCompare(b.title || "");
  });
}

function currentBibliographyYearRange() {
  if (!yearMinFilter || !yearMaxFilter) return { constrained: false, min: null, max: null };
  const bounds = yearBoundsFromClaims(activeClaimsForMode());
  if (!bounds) return { constrained: false, min: null, max: null };
  const minYear = parseYearValue(yearMinFilter.value) ?? bounds.min;
  const maxYear = parseYearValue(yearMaxFilter.value) ?? bounds.max;
  return {
    constrained: minYear > bounds.min || maxYear < bounds.max,
    min: Math.min(minYear, maxYear),
    max: Math.max(minYear, maxYear),
  };
}

function bibliographyPaperMatchesSelection(entry) {
  if (!selected || !isolateSelection) return true;
  const contexts = entry.contexts || [];
  if (!contexts.length) return false;

  if (selected.type === "edge") {
    return contexts.some(
      (context) =>
        normalizeValue(context.compound) === normalizeValue(selected.compound) &&
        normalizeValue(context.entity) === normalizeValue(selected.target)
    );
  }
  if (selected.type === "compound") {
    return contexts.some((context) => normalizeValue(context.compound) === normalizeValue(selected.name));
  }
  if (selected.type === "target") {
    return contexts.some((context) => normalizeValue(context.entity) === normalizeValue(selected.name));
  }
  return true;
}

function bibliographyRowsForCurrentView(data) {
  const payloadRows = bibliographyByMode[mode] || [];
  const rows = payloadRows.length ? payloadRows : bibliographyRowsFromClaims(data);
  const yearRange = payloadRows.length ? currentBibliographyYearRange() : { constrained: false };
  return rows.filter((entry) => {
    if (yearRange.constrained) {
      const year = parseYearValue(entry.year || entry.publicationDate);
      if (year === null) return false;
      if (year < yearRange.min || year > yearRange.max) return false;
    }
    return bibliographyPaperMatchesSelection(entry);
  });
}

function bibliographyHaystack(entry) {
  const contextText = (entry.contexts || [])
    .map((context) => `${context.compound} ${context.entity}`)
    .join(" ");
  return normalizeValue(
    [
      entry.title,
      entry.authors,
      entry.journal,
      entry.year,
      entry.publicationDate,
      entry.publicationType,
      entry.publisher,
      entry.trialRegistryIds,
      entry.keywords,
      entry.meshTerms,
      entry.doi,
      entry.openalexId,
      contextText,
    ].join(" ")
  );
}

function bibliographyCitationHtml(entry) {
  const authors = citationAuthors(entry.authors);
  const year = parseYearValue(entry.year || entry.publicationDate) ?? "n.d.";
  const title = sentencePart(entry.title || "Untitled study");
  const journal = sentencePart(entry.journal);
  const doiHref = doiUrl(entry.doi);
  const openAlexHref = !doiHref && entry.openalexId ? openAlexUrl(entry.openalexId) : "";
  const yearHtml = `<span>(${escapeHtml(String(year))}).</span>`;
  const titleHtml = `<span>${escapeHtml(title)}</span>`;

  return `
    <p class="study-citation">
      <span>${escapeHtml(authors)}</span>
      ${yearHtml}
      ${titleHtml}
      ${journal ? `<em>${escapeHtml(journal)}</em>` : ""}
      ${doiHref ? `<a href="${doiHref}" target="_blank" rel="noopener noreferrer">${escapeHtml(doiHref)}</a>` : ""}
      ${openAlexHref ? `<a href="${openAlexHref}" target="_blank" rel="noopener noreferrer">OpenAlex</a>` : ""}
    </p>
  `;
}

function renderBibliography(data) {
  if (!studyListEl) return;

  const rows = bibliographyRowsForCurrentView(data);
  const bibliographyQuery = normalizeValue(bibliographySearchInput?.value);
  const filteredRows = !bibliographyQuery
    ? rows
    : rows.filter((entry) => bibliographyHaystack(entry).includes(bibliographyQuery));

  if (!filteredRows.length) {
    disconnectBibliographyLoadObserver();
    studyListEl.innerHTML = '<div class="detail-empty">No bibliography entries in the current view.</div>';
    return;
  }

  disconnectBibliographyLoadObserver();
  studyListEl.innerHTML = "";

  function studyArticleHtml(entry) {
    return `
        <article class="study-item">
          ${bibliographyCitationHtml(entry)}
        </article>
      `;
  }

  let bibliographyRendered = 0;

  function appendBibliographyChunk() {
    const end = Math.min(bibliographyRendered + LIST_CHUNK_SIZE, filteredRows.length);
    const slice = filteredRows.slice(bibliographyRendered, end);
    bibliographyRendered = end;
    const html = slice.map((entry) => studyArticleHtml(entry)).join("");
    studyListEl.insertAdjacentHTML("beforeend", html);
  }

  function removeBibliographySentinel() {
    studyListEl.querySelector(".bibliography-load-sentinel")?.remove();
  }

  function attachBibliographySentinelIfNeeded() {
    disconnectBibliographyLoadObserver();
    removeBibliographySentinel();
    if (bibliographyRendered >= filteredRows.length) return;

    const sentinel = document.createElement("div");
    sentinel.className = "bibliography-load-sentinel";
    sentinel.setAttribute("aria-hidden", "true");
    studyListEl.appendChild(sentinel);

    bibliographyLoadObserver = new IntersectionObserver(
      (entries) => {
        if (!entries[0]?.isIntersecting) return;
        disconnectBibliographyLoadObserver();
        appendBibliographyChunk();
        attachBibliographySentinelIfNeeded();
      },
      { root: studyListEl, rootMargin: "360px", threshold: 0 }
    );
    bibliographyLoadObserver.observe(sentinel);
  }

  appendBibliographyChunk();
  attachBibliographySentinelIfNeeded();
}

function focusBibliography() {
  if (!bibliographyPanel) return;
  bibliographyPanel.scrollIntoView({ behavior: "smooth", block: "start" });
  bibliographyPanel.classList.add("focused");
  setTimeout(() => bibliographyPanel.classList.remove("focused"), 700);
}

function summarizeConnections(items, key) {
  const map = new Map();
  items.forEach((item) => {
    const label = key === "compound" ? compoundGraphLabel(item[key]) : graphLabel(item[key]);
    if (!label) return;
    const entry = map.get(label) || { count: 0 };
    entry.count += 1;
    map.set(label, entry);
  });
  return Array.from(map.entries())
    .map(([label, entry]) => ({ label, ...entry }))
    .sort((a, b) => b.count - a.count);
}

function escapeHtml(value) {
  return (value ?? "")
    .toString()
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/** Label ends with colon; bold styling comes from `.card-field-label` in CSS. */
function claimFieldLine(label, valueHtml) {
  return `<div><span class="card-field-label">${escapeHtml(label)}:</span> ${valueHtml}</div>`;
}

function formatCompactNumber(value) {
  const number = Number(value) || 0;
  return number.toLocaleString("en-US");
}

function displayFieldLabel(value, fallback = "Unknown") {
  const normalized = normalizeValue(value);
  if (!normalized) return fallback;
  if (normalized === "null") return "Null";
  return labelFromSlug(normalized).replace(/\b\w/g, (char) => char.toUpperCase());
}

const EMPTY_FIELD_VALUES = new Set([
  "",
  "not_reported",
  "not reported",
  "not_applicable",
  "not applicable",
  "unknown",
  "none",
  "n/a",
  "na",
]);

function meaningfulText(value) {
  const text = cleanDisplayText(value);
  if (EMPTY_FIELD_VALUES.has(normalizeValue(text))) return "";
  return text;
}

function claimFieldLineFromValue(label, value) {
  const text = meaningfulText(value);
  return text ? claimFieldLine(label, escapeHtml(text)) : "";
}

function claimRelationText(claim) {
  const rightKey = rightEntityKey();
  const compound = meaningfulText(claim.compound) || "Unknown compound";
  const graphEntity =
    meaningfulText(claim[rightKey]) ||
    meaningfulText(claim.raw_entity_label) ||
    meaningfulText(claim.graph_entity_label) ||
    `Non-graph ${lowerRightEntityLabel(false)}`;
  return `${compound} → ${graphEntity}`;
}

function sampleSizeText(claim) {
  return meaningfulText(claim.sample_size_total) || meaningfulText(claim.sample_size_by_arm);
}

function compactUniqueParts(values) {
  const seen = new Set();
  return values
    .map((value) => meaningfulText(value))
    .filter(Boolean)
    .filter((value) => {
      const key = normalizeValue(value);
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
}

function displayOutcomeType(value) {
  const text = meaningfulText(value);
  return text ? labelFromSlug(text) : "";
}

function displayResultDirection(value) {
  const normalized = normalizeValue(value);
  if (!normalized || normalized === "not_applicable") return "";
  return resultDirectionLabel(normalized);
}

function claimMainFindingText(claim) {
  if (mode === "mechanistic") {
    const value = [
      meaningfulText(claim.affinity_value),
      meaningfulText(claim.affinity_unit),
    ]
      .filter(Boolean)
      .join(" ");
    if (value) {
      return compactUniqueParts([claim.affinity_type || "Measure", value]).join(" · ");
    }
    return compactUniqueParts([claim.mechanism_type, claim.action_type, claim.assay_type]).join(" · ");
  }

  const outcome = meaningfulText(claim.outcome_measure) || displayOutcomeType(claim.outcome_type);
  const direction = displayResultDirection(claim.result_direction);
  const scale = meaningfulText(claim.outcome_measure_normalized);
  const parts = compactUniqueParts([outcome, scale, direction]);
  return parts.join(" · ");
}

function parseSampleSize(value) {
  const text = meaningfulText(value);
  if (!text) return null;
  const matches = text.match(/\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?/g) || [];
  const numbers = matches
    .map((match) => Number(match.replace(/,/g, "")))
    .filter((number) => Number.isFinite(number) && number >= 1);
  if (!numbers.length) return null;
  return Math.round(Math.max(...numbers));
}

function sampleSizeBucket(value) {
  const size = parseSampleSize(value);
  if (size === null) return "";
  return SAMPLE_SIZE_BINS.find((bin) => size >= bin.min && size <= bin.max)?.label || "";
}

function sampleSizeBinForSize(size) {
  if (!Number.isFinite(size) || size < 1) return null;
  return SAMPLE_SIZE_BINS.find((bin) => size >= bin.min && size <= bin.max) || null;
}

function splitNormalizedOutcomeMeasures(value) {
  return meaningfulText(value)
    .split(/\s*;\s*/)
    .map((part) => meaningfulText(part))
    .filter(Boolean);
}

function isOutcomeScaleClaim(claim) {
  return entityKindForClaim(claim) === "outcome_scale";
}

function outcomeScaleLabelsForClaim(claim) {
  if (isOutcomeScaleClaim(claim)) {
    return [graphLabel(claim.disorder)].filter(Boolean);
  }
  return splitNormalizedOutcomeMeasures(claim.outcome_measure_normalized);
}

function studyKey(claim, index) {
  const id = studyId(claim);
  if (id && id !== "unknown") return id;

  const title = normalizeValue(claim.study_title);
  const year = parseYearValue(claim.study_year);
  if (title || year !== null) return `${title}|${year || ""}`;

  return `claim-${index}`;
}

function uniqueStudyEntries(items) {
  const seen = new Set();
  const entries = [];

  items.forEach((claim, index) => {
    const key = studyKey(claim, index);
    if (seen.has(key)) return;
    seen.add(key);
    entries.push({
      key,
      year: parseYearValue(claim.study_year),
      claim,
    });
  });

  return entries;
}

function uniqueStudyCount(items) {
  return uniqueStudyEntries(items).length;
}

function yearStats(items) {
  const years = uniqueStudyEntries(items)
    .map((entry) => entry.year)
    .filter((year) => year !== null)
    .sort((a, b) => a - b);

  if (!years.length) {
    return { first: null, last: null, spanLabel: "No publication years" };
  }

  const first = years[0];
  const last = years[years.length - 1];
  return {
    first,
    last,
    spanLabel: first === last ? String(first) : `${first}-${last}`,
  };
}

function buildYearBuckets(items) {
  const entries = uniqueStudyEntries(items).filter((entry) => entry.year !== null);
  if (!entries.length) return [];

  const years = entries.map((entry) => entry.year);
  const minYear = Math.min(...years);
  const maxYear = Math.max(...years);
  const step = 1;
  const startYear = Math.floor(minYear / step) * step;
  const buckets = [];

  for (let start = startYear; start <= maxYear; start += step) {
    buckets.push({
      start,
      end: Math.min(start + step - 1, maxYear),
      count: 0,
      claims: 0,
    });
  }

  entries.forEach((entry) => {
    const index = Math.floor((entry.year - startYear) / step);
    if (buckets[index]) buckets[index].count += 1;
  });
  items.forEach((claim) => {
    const year = parseYearValue(claim.study_year);
    if (year === null) return;
    const index = Math.floor((year - startYear) / step);
    if (buckets[index]) buckets[index].claims += 1;
  });

  return buckets.map((bucket) => ({
    ...bucket,
    label: bucket.start === bucket.end ? String(bucket.start) : `${bucket.start}-${bucket.end}`,
  }));
}

function summarizeConnectionEvidence(items, key) {
  const map = new Map();

  items.forEach((claim, index) => {
    const label = key === "compound" ? compoundGraphLabel(claim[key]) : graphLabel(claim[key]);
    if (!label) return;
    const entry = map.get(label) || { label, claims: 0, studies: new Set() };
    entry.claims += 1;
    entry.studies.add(studyKey(claim, index));
    map.set(label, entry);
  });

  return Array.from(map.values())
    .map((entry) => ({
      label: entry.label,
      claims: entry.claims,
      studies: entry.studies.size,
    }))
    .sort((a, b) => {
      const byStudies = b.studies - a.studies;
      if (byStudies !== 0) return byStudies;
      const byClaims = b.claims - a.claims;
      if (byClaims !== 0) return byClaims;
      return a.label.localeCompare(b.label);
    });
}

function summarizeFieldEvidence(items, field, options = {}) {
  const map = new Map();
  const seen = new Set();

  items.forEach((claim, index) => {
    const labels = options.splitValues
      ? splitNormalizedOutcomeMeasures(claim[field])
      : [meaningfulText(claim[field])].filter(Boolean);
    if (!labels.length) return;
    const study = studyKey(claim, index);
    labels.forEach((label) => {
      const seenKey = options.uniqueStudies ? `${study}|${label}` : "";
      if (seenKey) {
        if (seen.has(seenKey)) return;
        seen.add(seenKey);
      }
      const entry = map.get(label) || { label, count: 0, studies: new Set() };
      entry.count += 1;
      entry.studies.add(study);
      map.set(label, entry);
    });
  });

  return Array.from(map.values())
    .map((entry) => ({
      label: entry.label,
      count: entry.count,
      studies: entry.studies.size,
    }))
    .sort((a, b) => {
      const byCount = b.count - a.count;
      if (byCount !== 0) return byCount;
      const byStudies = b.studies - a.studies;
      if (byStudies !== 0) return byStudies;
      return a.label.localeCompare(b.label);
    });
}

function summarizeOutcomeScaleEvidence(items) {
  const map = new Map();

  items.forEach((claim, index) => {
    const labels = outcomeScaleLabelsForClaim(claim);
    if (!labels.length) return;
    const study = studyKey(claim, index);
    labels.forEach((label) => {
      const entry = map.get(label) || { label, count: 0, studies: new Set() };
      entry.count += 1;
      entry.studies.add(study);
      map.set(label, entry);
    });
  });

  return Array.from(map.values())
    .map((entry) => ({
      label: entry.label,
      count: entry.count,
      studies: entry.studies.size,
    }))
    .sort((a, b) => {
      const byCount = b.count - a.count;
      if (byCount !== 0) return byCount;
      const byStudies = b.studies - a.studies;
      if (byStudies !== 0) return byStudies;
      return a.label.localeCompare(b.label);
    });
}

function summarizeSampleSizeBuckets(items) {
  const bucketOrder = SAMPLE_SIZE_BINS.map((bin) => bin.label);
  const buckets = new Map(bucketOrder.map((label) => [label, new Set()]));

  items.forEach((claim, index) => {
    const bucket = sampleSizeBucket(claim.sample_size_total);
    if (!bucket) return;
    buckets.get(bucket)?.add(studyKey(claim, index));
  });

  return bucketOrder
    .map((label) => ({ label, count: buckets.get(label)?.size || 0 }))
    .filter((entry) => entry.count > 0);
}

function sampleSizeStudyEntries(items) {
  const byStudy = new Map();
  items.forEach((claim, index) => {
    const sampleSize = parseSampleSize(sampleSizeText(claim));
    const year = parseYearValue(claim.study_year);
    if (sampleSize === null || year === null) return;
    const key = studyKey(claim, index);
    const existing = byStudy.get(key);
    const direction = normalizeValue(claim.result_direction) || "unknown";
    const relation = `${claim.compound || "Unknown"} -> ${claim.disorder || "Unknown"}`;

    if (!existing) {
      byStudy.set(key, {
        key,
        sampleSize,
        sampleText: sampleSizeText(claim) || String(sampleSize),
        year,
        direction,
        label: relation,
        studyTitle: cleanDisplayText(claim.study_title) || "Unknown study",
        claimCount: 1,
        relations: new Set([relation]),
      });
      return;
    }

    existing.claimCount += 1;
    existing.relations.add(relation);
    if (existing.sampleSize < sampleSize) {
      existing.sampleSize = sampleSize;
      existing.sampleText = sampleSizeText(claim) || String(sampleSize);
      existing.direction = direction;
      existing.label = relation;
    }
  });
  return Array.from(byStudy.values())
    .map((entry) => ({
      ...entry,
      relationSummary: Array.from(entry.relations).slice(0, 3).join("; "),
    }))
    .sort((a, b) => {
      const byYear = a.year - b.year;
      if (byYear !== 0) return byYear;
      const bySampleSize = b.sampleSize - a.sampleSize;
      if (bySampleSize !== 0) return bySampleSize;
      return a.label.localeCompare(b.label);
    });
}

function sampleYearBucketStep(minYear, maxYear) {
  const span = maxYear - minYear + 1;
  if (span <= 18) return 1;
  if (span <= 36) return 2;
  if (span <= 80) return 5;
  return 10;
}

function sampleYearBuckets(minYear, maxYear) {
  const step = sampleYearBucketStep(minYear, maxYear);
  const startYear = Math.floor(minYear / step) * step;
  const buckets = [];
  for (let start = startYear; start <= maxYear; start += step) {
    const end = Math.min(start + step - 1, maxYear);
    buckets.push({
      start,
      end,
      label: start === end ? String(start) : `${start}-${end}`,
    });
  }
  return buckets;
}

function countByField(items, field, options = {}) {
  const counts = new Map();
  const studySeen = new Set();
  const studiesByValue = new Map();

  items.forEach((claim, index) => {
    const value = normalizeValue(claim[field]) || "unknown";
    const study = studyKey(claim, index);
    if (options.uniqueStudies) {
      const key = `${study}|${value}`;
      if (studySeen.has(key)) return;
      studySeen.add(key);
    }
    if (!studiesByValue.has(value)) studiesByValue.set(value, new Set());
    studiesByValue.get(value).add(study);
    counts.set(value, (counts.get(value) || 0) + 1);
  });

  return Array.from(counts.entries()).map(([label, count]) => ({
    label,
    count,
    studies: studiesByValue.get(label)?.size || count,
  }));
}

function sortCompositionEntries(entries, field) {
  const orders = {
    result_direction: ["positive", "mixed", "null", "negative", "unclear", "unknown"],
    system: ["clinical", "preclinical", "in_vitro", "in_vivo", "ex_vivo", "observational", "unknown"],
  };
  const order = orders[field] || [];

  return [...entries].sort((a, b) => {
    const aIndex = order.indexOf(a.label);
    const bIndex = order.indexOf(b.label);
    if (aIndex !== -1 || bIndex !== -1) {
      return (aIndex === -1 ? 999 : aIndex) - (bIndex === -1 ? 999 : bIndex);
    }
    const byCount = b.count - a.count;
    if (byCount !== 0) return byCount;
    return a.label.localeCompare(b.label);
  });
}

function limitCompositionEntries(entries, maxEntries = 5) {
  if (entries.length <= maxEntries) return entries;
  const visible = entries.slice(0, maxEntries - 1);
  const otherCount = entries.slice(maxEntries - 1).reduce((sum, entry) => sum + entry.count, 0);
  const otherStudies = entries.slice(maxEntries - 1).reduce((sum, entry) => sum + (entry.studies || 0), 0);
  return [...visible, { label: "other", count: otherCount, studies: otherStudies, isAggregate: true }];
}

function colorForCategory(label, index, field = "") {
  const normalized = normalizeValue(label) || "unknown";
  if (field === "result_direction" && DIRECTION_COLORS[normalized]) return DIRECTION_COLORS[normalized];
  if (field === "system" && SYSTEM_COLORS[normalized]) return SYSTEM_COLORS[normalized];
  return CATEGORY_COLORS[index % CATEGORY_COLORS.length];
}

function compositionFilterAttrs(entry, field) {
  if (!field || !entry?.label || entry.isAggregate) return "";
  const label = displayFieldLabel(entry.label);
  const studies = Number(entry.studies ?? entry.count ?? 0) || 0;
  const claims = Number(entry.count ?? studies) || 0;
  return `role="button" tabindex="0" data-filter-field="${escapeHtml(field)}" data-filter-value="${escapeHtml(
    entry.label
  )}" data-filter-label="${escapeHtml(label)}" data-study-count="${escapeHtml(String(studies))}" data-claim-count="${escapeHtml(
    String(claims)
  )}" aria-label="${escapeHtml(`${label}: ${studies} studies, ${claims} claims`)}"`;
}

function compositionTargetClass(entry) {
  return entry?.isAggregate ? "" : " composition-filter-target";
}

/** Overview trend charts (#rrggbb only): soften fills slightly; alpha near 1 so colors stay saturated. */
function chartFillSoft(hexColor, alpha = 0.96) {
  const s = (hexColor || "").trim();
  if (!s.startsWith("#")) return s;
  const hex = s.slice(1);
  let r;
  let g;
  let b;
  if (hex.length === 6) {
    r = parseInt(hex.slice(0, 2), 16);
    g = parseInt(hex.slice(2, 4), 16);
    b = parseInt(hex.slice(4, 6), 16);
  } else if (hex.length === 3) {
    r = parseInt(hex.slice(0, 1).repeat(2), 16);
    g = parseInt(hex.slice(1, 2).repeat(2), 16);
    b = parseInt(hex.slice(2, 3).repeat(2), 16);
  } else {
    return s;
  }
  if ([r, g, b].some((n) => Number.isNaN(n))) return s;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function trendCardHtml(title, subtitle, body, extraClass = "") {
  const className = ["trend-card", extraClass].filter(Boolean).join(" ");
  return `
    <section class="${escapeHtml(className)}">
      <div class="trend-card-header">
        <h4>${escapeHtml(title)}</h4>
        ${subtitle ? `<span>${escapeHtml(subtitle)}</span>` : ""}
      </div>
      ${body}
    </section>
  `;
}

function renderTrendStats(items, extraStats = []) {
  const stats = [
    { label: "Claims", value: formatCompactNumber(items.length) },
    { label: "Studies", value: formatCompactNumber(uniqueStudyCount(items)) },
    ...extraStats,
  ];

  return `
    <div class="trend-summary-grid">
      ${stats
        .map(
          (stat) => `
            <div class="trend-stat">
              <span>${escapeHtml(stat.label)}</span>
              <strong>${escapeHtml(stat.value)}</strong>
            </div>
          `
        )
        .join("")}
    </div>
  `;
}

function renderAnnualPublicationChart(items) {
  const buckets = buildYearBuckets(items);
  if (!buckets.length) {
    return trendCardHtml("Publications per year", "", '<div class="trend-empty">No publication years available.</div>');
  }

  const width = 280;
  const height = 132;
  const margin = { top: 12, right: 10, bottom: 24, left: 10 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const maxCount = Math.max(1, ...buckets.map((bucket) => bucket.count));
  const slotWidth = plotWidth / buckets.length;
  const barWidth = Math.max(3, Math.min(16, slotWidth * 0.68));
  const step = buckets.length > 1 ? (plotWidth - barWidth) / (buckets.length - 1) : 0;
  const bars = buckets
    .map((bucket, index) => {
      if (!bucket.count) return "";
      const x = buckets.length > 1 ? margin.left + index * step : margin.left + (plotWidth - barWidth) / 2;
      const barHeight = (bucket.count / maxCount) * plotHeight;
      const y = margin.top + plotHeight - barHeight;
      const hitWidth = Math.max(12, Math.min(step, barWidth + 10));
      const hitX = clampNumber(x - (hitWidth - barWidth) / 2, margin.left, width - margin.right - hitWidth);
      const aria = `${bucket.label}. ${bucket.count} studies. Open ${bucket.claims} claims.`;
      return `
        <g class="publication-year-target" tabindex="0" role="button" focusable="true"
          aria-label="${escapeHtml(aria)}"
          data-year-start="${escapeHtml(String(bucket.start))}"
          data-year-end="${escapeHtml(String(bucket.end))}"
          data-year-label="${escapeHtml(bucket.label)}"
          data-study-count="${escapeHtml(String(bucket.count))}"
          data-claim-count="${escapeHtml(String(bucket.claims))}">
          <rect class="publication-year-hit" x="${hitX.toFixed(2)}" y="${margin.top}" width="${hitWidth.toFixed(2)}" height="${plotHeight}" rx="3"></rect>
          <rect class="publication-year-bar" x="${x.toFixed(2)}" y="${y.toFixed(2)}" width="${barWidth.toFixed(2)}" height="${barHeight.toFixed(2)}" rx="2" fill="${chartFillSoft(
            "#49d6c8"
          )}"></rect>
        </g>
      `;
    })
    .join("");
  const firstLabel = buckets[0].label;
  const lastLabel = buckets[buckets.length - 1].label;

  return trendCardHtml(
    "Publications per year",
    "",
    `
      <svg class="trend-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Publications per year">
        <line x1="${margin.left}" y1="${margin.top + plotHeight}" x2="${width - margin.right}" y2="${margin.top + plotHeight}" class="trend-axis-line" />
        ${bars}
        <text x="${margin.left}" y="${height - 5}" class="trend-axis-label" text-anchor="start">${escapeHtml(firstLabel)}</text>
        <text x="${width - margin.right}" y="${height - 5}" class="trend-axis-label" text-anchor="end">${escapeHtml(lastLabel)}</text>
      </svg>
    `
  );
}

function renderHorizontalBarChart(entries, title, subtitle, options = {}) {
  if (!entries.length) {
    return trendCardHtml(
      title,
      subtitle,
      `<div class="trend-empty">${escapeHtml(options.emptyText || "No connected evidence in this selection.")}</div>`
    );
  }

  const valueKey = options.valueKey || "studies";
  const maxValue = Math.max(1, ...entries.map((entry) => Number(entry[valueKey]) || 0));
  const body = `
    <div class="trend-bars">
      ${entries
        .map((entry, index) => {
          const value = Number(entry[valueKey]) || 0;
          const width = Math.max(4, (value / maxValue) * 100);
          const claims = Number(entry.claims ?? entry.count ?? value) || 0;
          const studies = Number(entry.studies ?? value) || 0;
          const isInteractive = Boolean(options.filterField && entry.label);
          const rowClass = ["trend-bar-row", isInteractive ? "interactive-bar" : ""].filter(Boolean).join(" ");
          const interactiveAttrs = isInteractive
            ? `role="button" tabindex="0" data-filter-field="${escapeHtml(options.filterField)}" data-filter-value="${escapeHtml(
                entry.label
              )}" data-filter-label="${escapeHtml(entry.label)}" data-study-count="${escapeHtml(
                String(studies)
              )}" data-claim-count="${escapeHtml(String(claims))}"`
            : "";
          return `
            <div class="${escapeHtml(rowClass)}" style="--bar-width: ${width.toFixed(2)}%" ${interactiveAttrs}>
              <div class="trend-bar-topline">
                <span title="${escapeHtml(entry.label)}">${escapeHtml(entry.label)}</span>
                <strong>${formatCompactNumber(value)}</strong>
              </div>
              <div class="trend-bar-track"><span></span></div>
            </div>
          `;
        })
        .join("")}
    </div>
  `;

  return trendCardHtml(title, subtitle, body);
}

function renderOutcomeMeasureChart(items) {
  if (evidenceView !== "primary") return "";
  if (mode !== "disorders") return "";
  const scaleItems = outcomeScaleClaimsForChart(items);
  const entries = summarizeOutcomeScaleEvidence(scaleItems);
  if (!entries.length) {
    return trendCardHtml(
      "Outcome scales",
      "",
      '<div class="trend-empty">No named outcome scales available.</div>',
      "evidence-card"
    );
  }

  const chips = entries
    .map(
      (entry) => `
        <button class="scale-chip" type="button"
          data-outcome-scale="${escapeHtml(entry.label)}"
          title="${escapeHtml(entry.label)}: ${entry.count} claims"
          aria-label="Show ${escapeHtml(entry.count)} claims using ${escapeHtml(entry.label)}">
          <strong>${escapeHtml(entry.label)}</strong>
          <em>${formatCompactNumber(entry.count)}</em>
        </button>
      `
    )
    .join("");

  return trendCardHtml(
    "Outcome scales",
    "",
    `<div class="scale-chip-grid">${chips}</div>`,
    "evidence-card"
  );
}

function renderSampleSizePlotBody(items) {
  const entries = sampleSizeStudyEntries(items);
  if (!entries.length) {
    return '<div class="trend-empty">No sample sizes with publication years available.</div>';
  }

  const width = 280;
  const height = 156;
  const margin = { top: 8, right: 8, bottom: 19, left: 48 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const minYear = Math.min(...entries.map((entry) => entry.year));
  const maxYear = Math.max(...entries.map((entry) => entry.year));
  const yearBuckets = sampleYearBuckets(minYear, maxYear);
  const sizeBins = [...SAMPLE_SIZE_BINS].reverse();
  const gap = 2;
  const cellWidth = Math.max(4, (plotWidth - gap * (yearBuckets.length - 1)) / yearBuckets.length);
  const cellHeight = Math.max(7, (plotHeight - gap * (sizeBins.length - 1)) / sizeBins.length);
  const cells = new Map();

  entries.forEach((entry) => {
    const yearIndex = yearBuckets.findIndex((bucket) => entry.year >= bucket.start && entry.year <= bucket.end);
    const sizeBin = sampleSizeBinForSize(entry.sampleSize);
    if (yearIndex < 0 || !sizeBin) return;
    const key = `${yearIndex}|${sizeBin.label}`;
    const cell =
      cells.get(key) ||
      {
        yearIndex,
        yearBucket: yearBuckets[yearIndex],
        sizeBin,
        count: 0,
        claims: 0,
      };
    cell.count += 1;
    cell.claims += entry.claimCount;
    cells.set(key, cell);
  });

  const maxCount = Math.max(1, ...Array.from(cells.values()).map((cell) => cell.count));
  const heatmapCells = yearBuckets
    .flatMap((yearBucket, yearIndex) =>
      sizeBins.map((sizeBin, sizeIndex) => {
        const x = margin.left + yearIndex * (cellWidth + gap);
        const y = margin.top + sizeIndex * (cellHeight + gap);
        const cell = cells.get(`${yearIndex}|${sizeBin.label}`);
        if (!cell) {
          return `<rect class="sample-heatmap-cell empty" x="${x.toFixed(2)}" y="${y.toFixed(2)}" width="${cellWidth.toFixed(
            2
          )}" height="${cellHeight.toFixed(2)}" rx="2"></rect>`;
        }
        const alpha = 0.16 + 0.76 * Math.sqrt(cell.count / maxCount);
        const maxValue = Number.isFinite(sizeBin.max) ? String(sizeBin.max) : "";
        const aria = `${yearBucket.label}, sample size ${sizeBin.label}: ${cell.count} studies, ${cell.claims} claims.`;
        return `
          <g class="sample-heatmap-target" tabindex="0" role="button" focusable="true"
            aria-label="${escapeHtml(aria)}"
            data-year-start="${escapeHtml(String(yearBucket.start))}"
            data-year-end="${escapeHtml(String(yearBucket.end))}"
            data-year-label="${escapeHtml(yearBucket.label)}"
            data-sample-min="${escapeHtml(String(sizeBin.min))}"
            data-sample-max="${escapeHtml(maxValue)}"
            data-sample-label="${escapeHtml(sizeBin.label)}"
            data-study-count="${escapeHtml(String(cell.count))}"
            data-claim-count="${escapeHtml(String(cell.claims))}">
            <rect class="sample-heatmap-hit" x="${x.toFixed(2)}" y="${y.toFixed(2)}" width="${cellWidth.toFixed(
              2
            )}" height="${cellHeight.toFixed(2)}" rx="2"></rect>
            <rect class="sample-heatmap-cell" x="${x.toFixed(2)}" y="${y.toFixed(2)}" width="${cellWidth.toFixed(
              2
            )}" height="${cellHeight.toFixed(2)}" rx="2" fill="${chartFillSoft("#49d6c8", alpha)}"></rect>
          </g>
        `;
      })
    )
    .join("");
  const yLabels = sizeBins
    .map((bin, index) => {
      const y = margin.top + index * (cellHeight + gap) + cellHeight / 2 + 3;
      return `<text x="${margin.left - 7}" y="${y.toFixed(2)}" class="trend-axis-label" text-anchor="end">${escapeHtml(
        bin.label
      )}</text>`;
    })
    .join("");
  const firstYear = yearBuckets[0].label;
  const lastYear = yearBuckets[yearBuckets.length - 1].label;

  return `
    <svg class="sample-heatmap-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Sample sizes by publication year">
      ${yLabels}
      ${heatmapCells}
      <text x="${margin.left}" y="${height - 5}" class="trend-axis-label" text-anchor="start">${escapeHtml(firstYear)}</text>
      <text x="${width - margin.right}" y="${height - 5}" class="trend-axis-label" text-anchor="end">${escapeHtml(lastYear)}</text>
    </svg>
  `;
}

function renderResultDirectionBody(items) {
  let entries = sortCompositionEntries(countByField(items, "result_direction"), "result_direction");
  if (!entries.length) {
    return '<div class="trend-empty">No result directions available.</div>';
  }
  entries = limitCompositionEntries(entries, 6);

  const total = entries.reduce((sum, entry) => sum + entry.count, 0);
  const segments = entries
    .map((entry, index) => {
      const width = total ? (entry.count / total) * 100 : 0;
      return `<span class="trend-stack-segment${compositionTargetClass(entry)}" ${compositionFilterAttrs(
        entry,
        "result_direction"
      )} style="width: ${width.toFixed(2)}%; background: ${chartFillSoft(
        colorForCategory(entry.label, index, "result_direction")
      )}" title="${escapeHtml(displayFieldLabel(entry.label))}: ${entry.count}"></span>`;
    })
    .join("");
  const legend = entries
    .map(
      (entry, index) => `
        <span class="trend-legend-item${compositionTargetClass(entry)}" ${compositionFilterAttrs(entry, "result_direction")}>
          <i style="background: ${chartFillSoft(colorForCategory(entry.label, index, "result_direction"))}"></i>
          ${escapeHtml(displayFieldLabel(entry.label))} <strong>${formatCompactNumber(entry.count)}</strong>
        </span>
      `
    )
    .join("");

  return `
    <div class="result-direction-composition">
      <div class="trend-stack">${segments}</div>
      <div class="trend-legend">${legend}</div>
    </div>
  `;
}

function renderSampleSizeHeatmap(items) {
  if (evidenceView !== "primary") return "";
  if (mode !== "disorders") return "";
  return trendCardHtml(
    "Sample sizes",
    "",
    renderSampleSizePlotBody(items),
    "evidence-card sample-card"
  );
}

function renderResultDirectionChart(items) {
  if (evidenceView !== "primary") return "";
  if (mode !== "disorders") return "";
  return trendCardHtml(
    "Result direction",
    "",
    renderResultDirectionBody(items),
    "evidence-card result-direction-card"
  );
}

function renderEvidenceDetailGroup(items) {
  if (evidenceView !== "primary") return "";
  if (mode !== "disorders") return "";
  return `
    ${renderSampleSizeHeatmap(items)}
    ${renderResultDirectionChart(items)}
    ${renderOutcomeMeasureChart(items)}
  `;
}

function renderCompositionChart(items, field, title, options = {}) {
  let entries = sortCompositionEntries(countByField(items, field, options), field);
  if (!entries.length) {
    const emptySubtitle = field === "result_direction" ? "" : "Claim composition";
    return trendCardHtml(title, emptySubtitle, '<div class="trend-empty">No categorized evidence.</div>');
  }
  entries = limitCompositionEntries(entries, options.maxEntries || 6);

  const total = entries.reduce((sum, entry) => sum + entry.count, 0);
  const segments = entries
    .map((entry, index) => {
      const width = total ? (entry.count / total) * 100 : 0;
      return `<span class="trend-stack-segment${compositionTargetClass(entry)}" ${compositionFilterAttrs(
        entry,
        field
      )} style="width: ${width.toFixed(2)}%; background: ${chartFillSoft(
        colorForCategory(entry.label, index, field)
      )}" title="${escapeHtml(displayFieldLabel(entry.label))}: ${entry.count}"></span>`;
    })
    .join("");
  const legend = entries
    .map(
      (entry, index) => `
        <span class="trend-legend-item${compositionTargetClass(entry)}" ${compositionFilterAttrs(entry, field)}>
          <i style="background: ${chartFillSoft(colorForCategory(entry.label, index, field))}"></i>
          ${escapeHtml(displayFieldLabel(entry.label))} <strong>${formatCompactNumber(entry.count)}</strong>
        </span>
      `
    )
    .join("");

  const compositionSubtitle =
    options.subtitle !== undefined
      ? options.subtitle
      : field === "result_direction"
        ? ""
        : "Claims";
  return trendCardHtml(
    title,
    compositionSubtitle,
    `
      <div class="trend-stack">${segments}</div>
      <div class="trend-legend">${legend}</div>
    `
  );
}

function renderExperimentalSystemChart(items) {
  if (evidenceView !== "primary") return "";
  if (mode === "disorders") return "";
  return renderCompositionChart(items, "system", "Experimental system");
}

function renderDetailClaimCards(items) {
  if (!items.length) {
    return trendCardHtml("Claims", "", '<div class="trend-empty">No claims in this selection.</div>');
  }

  const sortedClaims = [...items].sort((a, b) => {
    const yearDiff = (parseYearValue(b.study_year) || 0) - (parseYearValue(a.study_year) || 0);
    if (yearDiff !== 0) return yearDiff;
    return (a.study_title || "").localeCompare(b.study_title || "");
  });

  const rightKey = rightEntityKey();
  const body = `
    <div class="detail-claim-cards">
      ${sortedClaims
        .map((claim) => {
          const relation = claimRelationText(claim);
          const doiHref = doiUrl(claim.study_doi);
          const source = doiHref
            ? `<a href="${doiHref}" target="_blank" rel="noopener noreferrer">${escapeHtml(claim.study_doi)}</a>`
            : claim.openalex_id
            ? `<a href="${openAlexUrl(claim.openalex_id)}" target="_blank" rel="noopener noreferrer">${escapeHtml(claim.openalex_id)}</a>`
            : "";
          const mainLine =
            mode === "mechanistic"
              ? `${claim.affinity_value ? claim.affinity_type || "Measure" : claim.mechanism_type || "Mechanism"} ${
                  claim.affinity_value || claim.action_type || claim.assay_type || "reported"
                } ${claim.affinity_unit || ""}`.trim()
              : `${meaningfulText(claim.outcome_type) || "Outcome"}${
                  meaningfulText(claim.outcome_measure_normalized)
                    ? ` · ${meaningfulText(claim.outcome_measure_normalized)}`
                    : meaningfulText(claim.outcome_measure)
                      ? ` · ${meaningfulText(claim.outcome_measure)}`
                      : ""
                }`;
          const contextLine =
            mode === "mechanistic"
              ? `System: ${claim.system || "unknown"} · Species: ${claim.species || "unknown"}`
              : `Direction: ${resultDirectionLabel(claim.result_direction)} · Population: ${claim.population || "unknown"}`;
          const sampleLine =
            mode === "disorders"
              ? [
                  sampleSizeText(claim) ? `Sample: ${sampleSizeText(claim)}` : "",
                  meaningfulText(claim.timepoint) ? `Timepoint: ${meaningfulText(claim.timepoint)}` : "",
                  meaningfulText(claim.comparator) ? `Comparator: ${meaningfulText(claim.comparator)}` : "",
                ]
                  .filter(Boolean)
                  .join(" · ")
              : "";
          const journalLine = [claim.study_journal, claim.publication_type]
            .map(cleanDisplayText)
            .filter(Boolean)
            .join(" · ");

          return `
            <article class="detail-claim-card">
              <h5>${escapeHtml(relation)}</h5>
              <div class="detail-claim-meta">
                <div>${escapeHtml(mainLine)}</div>
                <div>${escapeHtml(contextLine)}</div>
                ${sampleLine ? `<div>${escapeHtml(sampleLine)}</div>` : ""}
                <div>${escapeHtml(cleanDisplayText(claim.study_title) || "Unknown study")}${claim.study_year ? ` (${escapeHtml(claim.study_year)})` : ""}</div>
                ${journalLine ? `<div>${escapeHtml(journalLine)}</div>` : ""}
                ${source ? `<div>${source}</div>` : ""}
              </div>
              <div class="badge-row">${claimBadgeHtml(claim)}</div>
            </article>
          `;
        })
        .join("")}
    </div>
  `;

  return trendCardHtml("Claims", "", body);
}

function sampleHeatmapTooltipHtml(target) {
  const studyCount = Number(target.dataset.studyCount || 0);
  const claimCount = Number(target.dataset.claimCount || 0);
  return `
    <strong class="tooltip-title">${escapeHtml(target.dataset.yearLabel || "Unknown years")}</strong>
    <span class="tooltip-meta">N=${escapeHtml(target.dataset.sampleLabel || "unknown")} · ${formatCompactNumber(
      studyCount
    )} stud${studyCount === 1 ? "y" : "ies"} · ${formatCompactNumber(claimCount)} claim${
      claimCount === 1 ? "" : "s"
    }</span>
  `;
}

function publicationYearTooltipHtml(target) {
  const studyCount = Number(target.dataset.studyCount || 0);
  const claimCount = Number(target.dataset.claimCount || 0);
  return `
    <strong class="tooltip-title">${escapeHtml(target.dataset.yearLabel || "Unknown year")}</strong>
    <span class="tooltip-meta">${formatCompactNumber(studyCount)} stud${
      studyCount === 1 ? "y" : "ies"
    } · ${formatCompactNumber(claimCount)} claim${claimCount === 1 ? "" : "s"}</span>
  `;
}

function horizontalBarTooltipHtml(target) {
  const studyCount = Number(target.dataset.studyCount || 0);
  const claimCount = Number(target.dataset.claimCount || 0);
  return `
    <strong class="tooltip-title">${escapeHtml(target.dataset.filterLabel || "Unknown")}</strong>
    <span class="tooltip-meta">${formatCompactNumber(studyCount)} stud${
      studyCount === 1 ? "y" : "ies"
    } · ${formatCompactNumber(claimCount)} claim${claimCount === 1 ? "" : "s"}</span>
  `;
}

function claimsForStudyKey(studyKeyValue) {
  return activeDetailItems.filter((claim, index) => studyKey(claim, index) === studyKeyValue);
}

function claimsForFieldValue(field, value) {
  if (!field || !value) return [];
  const normalizedValue = normalizeValue(value);
  return activeDetailItems.filter((claim) => normalizeValue(cleanDisplayText(claim[field])) === normalizedValue);
}

function fieldValueDetailTitle(field, value) {
  if (field === "compound") return `Compound: ${value}`;
  if (field === "disorder" || field === "target") return `${rightEntityLabel(false)}: ${value}`;
  return `${displayFieldLabel(field)}: ${value}`;
}

function claimsForPublicationYearRange(startValue, endValue) {
  const start = Number(startValue);
  const end = Number(endValue || startValue);
  if (!Number.isFinite(start) || !Number.isFinite(end)) return [];
  return activeDetailItems.filter((claim) => {
    const year = parseYearValue(claim.study_year);
    return year !== null && year >= start && year <= end;
  });
}

function claimsForSampleHeatmapCell(startValue, endValue, minValue, maxValue) {
  const start = Number(startValue);
  const end = Number(endValue || startValue);
  const min = Number(minValue);
  const parsedMax = maxValue === "" ? Number.POSITIVE_INFINITY : Number(maxValue);
  const max = Number.isFinite(parsedMax) ? parsedMax : Number.POSITIVE_INFINITY;
  if (!Number.isFinite(start) || !Number.isFinite(end) || !Number.isFinite(min)) return [];

  const matchingStudies = new Set();
  activeDetailItems.forEach((claim, index) => {
    const year = parseYearValue(claim.study_year);
    const sampleSize = parseSampleSize(sampleSizeText(claim));
    if (year === null || sampleSize === null) return;
    if (year < start || year > end || sampleSize < min || sampleSize > max) return;
    matchingStudies.add(studyKey(claim, index));
  });
  if (!matchingStudies.size) return [];
  return activeDetailItems.filter((claim, index) => matchingStudies.has(studyKey(claim, index)));
}

function claimsForOutcomeScale(scaleValue) {
  const scaleKey = normalizeValue(scaleValue);
  if (!scaleKey) return [];
  return outcomeScaleClaimsForChart(activeDetailItems).filter((claim) =>
    outcomeScaleLabelsForClaim(claim).some((scale) => normalizeValue(scale) === scaleKey)
  );
}

function restoreCurrentDetailPanel() {
  clearDetailGraphFilter();
  const filtered = applyFilters();
  refreshMainViews();
  if (selected) {
    renderSelectedDetailFromData(filtered);
    return;
  }
  renderOverviewDetail(filtered);
}

function renderStudyDetail(studyKeyValue) {
  const studyClaims = claimsForStudyKey(studyKeyValue);
  if (!studyClaims.length) return;

  activeDetailItems = studyClaims;
  setDetailGraphFilter(studyClaims);
  const firstClaim = studyClaims[0];
  const rightKey = rightEntityKey();
  const title = cleanDisplayText(firstClaim.study_title) || "Study detail";
  const year = parseYearValue(firstClaim.study_year);
  const doiHref = doiUrl(firstClaim.study_doi);
  const source = doiHref
    ? `<a href="${doiHref}" target="_blank" rel="noopener noreferrer">${escapeHtml(firstClaim.study_doi)}</a>`
    : firstClaim.openalex_id
      ? `<a href="${openAlexUrl(firstClaim.openalex_id)}" target="_blank" rel="noopener noreferrer">${escapeHtml(
          firstClaim.openalex_id
        )}</a>`
      : "";
  const context = [
    year ? String(year) : "",
    cleanDisplayText(firstClaim.study_journal),
    cleanDisplayText(firstClaim.study_design),
  ]
    .filter(Boolean)
    .join(" · ");
  const sample = sampleSizeText(firstClaim);

  setDetailHeader(title);
  detailBody.innerHTML = `
    <div class="trend-dashboard">
      <div class="study-detail-actions">
        <button class="ghost small" type="button" data-detail-action="restore">Back</button>
      </div>
      ${renderTrendStats(studyClaims, [
        {
          label: "Compounds",
          value: formatCompactNumber(unique(studyClaims.map((claim) => compoundGraphLabel(claim.compound)).filter(Boolean)).length),
        },
        {
          label: rightEntityLabel(true),
          value: formatCompactNumber(unique(studyClaims.map((claim) => graphLabel(claim[rightKey])).filter(Boolean)).length),
        },
      ])}
      <section class="study-detail-note">
        ${context ? `<div>${escapeHtml(context)}</div>` : ""}
        ${sample ? `<div>Sample: ${escapeHtml(sample)}</div>` : ""}
        ${source ? `<div>${source}</div>` : ""}
      </section>
      ${renderDetailClaimCards(studyClaims)}
    </div>
  `;
}

function renderFieldValueDetail(field, value, labelValue = value) {
  const fieldClaims = claimsForFieldValue(field, value);
  if (!fieldClaims.length) return;

  const rightKey = rightEntityKey();
  const rightLabel = rightEntityLabel(true);
  const compoundEntries = summarizeConnectionEvidence(fieldClaims, "compound");
  const rightEntries = summarizeConnectionEvidence(fieldClaims, rightKey);
  const composition =
    mode === "disorders"
      ? `${renderSampleSizeHeatmap(fieldClaims)}${renderResultDirectionChart(fieldClaims)}`
      : renderExperimentalSystemChart(fieldClaims);

  activeDetailItems = fieldClaims;
  setDetailGraphFilter(fieldClaims);
  setDetailHeader(fieldValueDetailTitle(field, labelValue));
  detailBody.innerHTML = `
    <div class="trend-dashboard">
      <div class="study-detail-actions">
        <button class="ghost small" type="button" data-detail-action="restore">Back</button>
      </div>
      ${renderTrendStats(fieldClaims, [
        { label: "Compounds", value: formatCompactNumber(compoundEntries.length) },
        { label: rightLabel, value: formatCompactNumber(rightEntries.length) },
      ])}
      ${renderAnnualPublicationChart(fieldClaims)}
      ${composition}
      ${mode === "disorders" ? renderOutcomeMeasureChart(fieldClaims) : ""}
      ${field === "compound" ? "" : renderHorizontalBarChart(compoundEntries, "Compounds", "Ranked by unique studies", { filterField: "compound" })}
      ${
        field === rightKey
          ? ""
          : renderHorizontalBarChart(rightEntries, rightLabel, "Ranked by unique studies", { filterField: rightKey })
      }
      ${renderDetailClaimCards(fieldClaims)}
    </div>
  `;
}

function renderPublicationYearDetail(startValue, endValue, labelValue) {
  const yearClaims = claimsForPublicationYearRange(startValue, endValue);
  if (!yearClaims.length) return;

  const rightKey = rightEntityKey();
  const rightLabel = rightEntityLabel(true);
  const compoundEntries = summarizeConnectionEvidence(yearClaims, "compound");
  const rightEntries = summarizeConnectionEvidence(yearClaims, rightKey);
  const composition =
    mode === "disorders"
      ? `${renderSampleSizeHeatmap(yearClaims)}${renderResultDirectionChart(yearClaims)}`
      : renderExperimentalSystemChart(yearClaims);

  activeDetailItems = yearClaims;
  setDetailGraphFilter(yearClaims);
  setDetailHeader(`Publications: ${labelValue}`);
  detailBody.innerHTML = `
    <div class="trend-dashboard">
      <div class="study-detail-actions">
        <button class="ghost small" type="button" data-detail-action="restore">Back</button>
      </div>
      ${renderTrendStats(yearClaims, [
        { label: "Compounds", value: formatCompactNumber(compoundEntries.length) },
        { label: rightLabel, value: formatCompactNumber(rightEntries.length) },
      ])}
      ${composition}
      ${mode === "disorders" ? renderOutcomeMeasureChart(yearClaims) : ""}
      ${renderHorizontalBarChart(compoundEntries, "Compounds", "Ranked by unique studies", { filterField: "compound" })}
      ${renderHorizontalBarChart(rightEntries, rightLabel, "Ranked by unique studies", { filterField: rightKey })}
      ${renderDetailClaimCards(yearClaims)}
    </div>
  `;
}

function renderSampleHeatmapDetail(startValue, endValue, minValue, maxValue, labelValue) {
  const sampleClaims = claimsForSampleHeatmapCell(startValue, endValue, minValue, maxValue);
  if (!sampleClaims.length) return;

  const rightKey = rightEntityKey();
  const rightLabel = rightEntityLabel(true);
  const compoundEntries = summarizeConnectionEvidence(sampleClaims, "compound");
  const rightEntries = summarizeConnectionEvidence(sampleClaims, rightKey);

  activeDetailItems = sampleClaims;
  setDetailGraphFilter(sampleClaims);
  setDetailHeader(`Sample sizes: ${labelValue}`);
  detailBody.innerHTML = `
    <div class="trend-dashboard">
      <div class="study-detail-actions">
        <button class="ghost small" type="button" data-detail-action="restore">Back</button>
      </div>
      ${renderTrendStats(sampleClaims, [
        { label: "Compounds", value: formatCompactNumber(compoundEntries.length) },
        { label: rightLabel, value: formatCompactNumber(rightEntries.length) },
      ])}
      ${renderSampleSizeHeatmap(sampleClaims)}
      ${renderResultDirectionChart(sampleClaims)}
      ${mode === "disorders" ? renderOutcomeMeasureChart(sampleClaims) : ""}
      ${renderHorizontalBarChart(compoundEntries, "Compounds", "Ranked by unique studies", { filterField: "compound" })}
      ${renderHorizontalBarChart(rightEntries, rightLabel, "Ranked by unique studies", { filterField: rightKey })}
      ${renderDetailClaimCards(sampleClaims)}
    </div>
  `;
}

function renderOutcomeScaleDetail(scaleValue) {
  const scaleClaims = claimsForOutcomeScale(scaleValue);
  if (!scaleClaims.length) return;

  const scopeKeys = new Set(scaleClaims.map(evidenceScopeKey).filter(Boolean));
  const sourceItems = activeDetailItems.length ? activeDetailItems : applyFilters();
  const scopedViewClaims =
    currentEntityViewKey() === "outcome_scale"
      ? scaleClaims
      : sourceItems.filter((claim) => !isOutcomeScaleClaim(claim) && scopeKeys.has(evidenceScopeKey(claim)));
  const detailClaims = scopedViewClaims.length ? scopedViewClaims : scaleClaims;
  const rightKey = rightEntityKey();
  const compoundEntries = summarizeConnectionEvidence(detailClaims, "compound");
  const rightEntries = summarizeConnectionEvidence(detailClaims, rightKey);

  activeDetailItems = detailClaims;
  setDetailGraphFilter(detailClaims);
  setDetailHeader(`Outcome scale: ${scaleValue}`);
  detailBody.innerHTML = `
    <div class="trend-dashboard">
      <div class="study-detail-actions">
        <button class="ghost small" type="button" data-detail-action="restore">Back</button>
      </div>
      ${renderTrendStats(detailClaims, [
        { label: "Compounds", value: formatCompactNumber(compoundEntries.length) },
        { label: rightEntityLabel(true), value: formatCompactNumber(rightEntries.length) },
      ])}
      ${renderSampleSizeHeatmap(detailClaims)}
      ${renderResultDirectionChart(detailClaims)}
      ${renderOutcomeMeasureChart(detailClaims)}
      ${renderHorizontalBarChart(compoundEntries, "Compounds", "Ranked by unique studies", { filterField: "compound" })}
      ${renderHorizontalBarChart(rightEntries, rightEntityLabel(true), "Ranked by unique studies", { filterField: rightKey })}
      ${renderDetailClaimCards(detailClaims)}
    </div>
  `;
}

function renderEdgeDetail(compound, target, edgeClaims) {
  const studies = uniqueStudyCount(edgeClaims);
  activeDetailItems = edgeClaims;
  setDetailHeader(`${compound} → ${target}`);

  const primaryComposition = renderExperimentalSystemChart(edgeClaims);

  detailBody.innerHTML = `
    <div class="trend-dashboard">
      ${renderTrendStats(edgeClaims)}
      ${renderAnnualPublicationChart(edgeClaims)}
      ${primaryComposition}
      ${renderEvidenceDetailGroup(edgeClaims)}
      ${renderDetailClaimCards(edgeClaims)}
    </div>
  `;
}

function renderNodeDetail(type, name, nodeClaims) {
  const rightKey = rightEntityKey();
  const connectionKey = type === "compound" ? rightKey : "compound";
  const connections = summarizeConnectionEvidence(nodeClaims, connectionKey);
  const connectionLabel = type === "compound" ? lowerRightEntityLabel(true) : "compounds";

  activeDetailItems = nodeClaims;
  setDetailHeader(name);

  const composition = renderExperimentalSystemChart(nodeClaims);

  detailBody.innerHTML = `
    <div class="trend-dashboard">
      ${renderTrendStats(nodeClaims, [{ label: "Connections", value: formatCompactNumber(connections.length) }])}
      ${renderAnnualPublicationChart(nodeClaims)}
      ${composition}
      ${renderEvidenceDetailGroup(nodeClaims)}
      ${renderHorizontalBarChart(connections, displayFieldLabel(connectionLabel), "Ranked by unique studies", { filterField: connectionKey })}
      ${renderDetailClaimCards(nodeClaims)}
    </div>
  `;
}

function renderOverviewDetail(data) {
  const rightKey = rightEntityKey();
  const rightLabel = rightEntityLabel(true);
  const compoundEntries = summarizeConnectionEvidence(data, "compound");
  const rightEntries = summarizeConnectionEvidence(data, rightKey);

  activeDetailItems = data;
  setDetailHeader(`All ${lowerRightEntityLabel(true)}`);

  if (!data.length) {
    detailBody.innerHTML = '<div class="detail-empty">No claims match the current filters.</div>';
    return;
  }

  const composition = renderExperimentalSystemChart(data);

  detailBody.innerHTML = `
    <div class="trend-dashboard">
      ${renderTrendStats(data, [
        { label: "Compounds", value: formatCompactNumber(compoundEntries.length) },
        { label: rightLabel, value: formatCompactNumber(rightEntries.length) },
      ])}
      ${renderAnnualPublicationChart(data)}
      ${composition}
      ${renderEvidenceDetailGroup(data)}
      ${renderHorizontalBarChart(compoundEntries, "Compounds", "Ranked by unique studies", { filterField: "compound" })}
      ${renderHorizontalBarChart(rightEntries, rightLabel, "Ranked by unique studies", { filterField: rightKey })}
    </div>
  `;
}

function renderSelectedDetailFromData(data) {
  if (!selected) return;

  const rightKey = rightEntityKey();
  if (selected.type === "edge") {
    const edgeClaims = data.filter(
      (claim) => claim.compound === selected.compound && claim[rightKey] === selected.target
    );
    renderEdgeDetail(selected.compound, selected.target, edgeClaims);
    return;
  }

  if (selected.type === "compound") {
    const nodeClaims = data.filter((claim) => claim.compound === selected.name);
    renderNodeDetail("compound", selected.name, nodeClaims);
    return;
  }

  if (selected.type === "target") {
    const nodeClaims = data.filter((claim) => claim[rightKey] === selected.name);
    renderNodeDetail("target", selected.name, nodeClaims);
  }
}

function buildGraph(data) {
  graphEl.innerHTML = "";

  const rightKey = rightEntityKey();
  const compoundCounts = new Map();
  const rightCounts = new Map();
  const compoundConnections = new Map();
  const rightConnections = new Map();
  const incidentEdgeKeysByCompound = new Map();
  const incidentEdgeKeysByRight = new Map();

  data.forEach((claim) => {
    const compound = compoundGraphLabel(claim.compound);
    const right = graphLabel(claim[rightKey]);
    if (!compound || !right) return;

    compoundCounts.set(compound, (compoundCounts.get(compound) || 0) + 1);
    rightCounts.set(right, (rightCounts.get(right) || 0) + 1);

    const compoundSet = compoundConnections.get(compound) || new Set();
    compoundSet.add(right);
    compoundConnections.set(compound, compoundSet);

    const rightSet = rightConnections.get(right) || new Set();
    rightSet.add(compound);
    rightConnections.set(right, rightSet);

    const edgeKey = `${compound}|${right}`;
    const byCompound = incidentEdgeKeysByCompound.get(compound) || new Set();
    byCompound.add(edgeKey);
    incidentEdgeKeysByCompound.set(compound, byCompound);
    const byRight = incidentEdgeKeysByRight.get(right) || new Set();
    byRight.add(edgeKey);
    incidentEdgeKeysByRight.set(right, byRight);
  });

  const compounds = Array.from(compoundCounts.keys()).sort((a, b) => {
    const byClaims = (compoundCounts.get(b) || 0) - (compoundCounts.get(a) || 0);
    if (byClaims !== 0) return byClaims;
    const byDegree = (compoundConnections.get(b)?.size || 0) - (compoundConnections.get(a)?.size || 0);
    if (byDegree !== 0) return byDegree;
    return a.localeCompare(b);
  });

  const targets = Array.from(rightCounts.keys()).sort((a, b) => {
    const byClaims = (rightCounts.get(b) || 0) - (rightCounts.get(a) || 0);
    if (byClaims !== 0) return byClaims;
    const byDegree = (rightConnections.get(b)?.size || 0) - (rightConnections.get(a)?.size || 0);
    if (byDegree !== 0) return byDegree;
    return a.localeCompare(b);
  });

  const width = graphEl.clientWidth || 800;
  const height = graphEl.clientHeight || 420;

  const longestLeftLabelPx = Math.max(80, ...compounds.map(estimateGraphLabelWidth));
  const longestRightLabelPx = Math.max(80, ...targets.map(estimateGraphLabelWidth));
  const baseSideMargin = clampNumber(Math.floor(width * 0.18), 110, 220);
  let leftMargin = Math.max(baseSideMargin, longestLeftLabelPx + 28);
  let rightMargin = Math.max(baseSideMargin, longestRightLabelPx + 28 + GRAPH_RIGHT_LABEL_GUTTER_PX);
  const minCenterWidth = 120;
  const maxMarginBudget = Math.max(220, width - minCenterWidth);
  const combinedMargins = leftMargin + rightMargin;
  if (combinedMargins > maxMarginBudget) {
    const scale = maxMarginBudget / combinedMargins;
    leftMargin = Math.floor(leftMargin * scale);
    rightMargin = Math.floor(rightMargin * scale);
  }

  const margin = { top: 40, right: rightMargin, bottom: 40, left: leftMargin };
  const compoundX = margin.left;
  const targetX = width - margin.right;
  const labelOffset = 22;
  const leftLabelMaxWidth = Math.min(GRAPH_LABEL_MAX_WIDTH_PX, Math.max(20, compoundX - labelOffset - 10));
  const rightLabelMaxWidth = Math.min(
    GRAPH_LABEL_MAX_WIDTH_PX,
    Math.max(20, width - (targetX + labelOffset) - GRAPH_RIGHT_LABEL_GUTTER_PX - 10)
  );

  const compoundStep = (height - margin.top - margin.bottom) / Math.max(compounds.length, 1);
  const targetStep = (height - margin.top - margin.bottom) / Math.max(targets.length, 1);

  const compoundPositions = new Map();
  const targetPositions = new Map();

  compounds.forEach((compound, index) => {
    compoundPositions.set(compound, {
      x: compoundX,
      y: margin.top + index * compoundStep + compoundStep / 2,
    });
  });

  targets.forEach((target, index) => {
    targetPositions.set(target, {
      x: targetX,
      y: margin.top + index * targetStep + targetStep / 2,
    });
  });

  const edges = new Map();
  const claimsByCompound = new Map();
  const claimsByRight = new Map();
  data.forEach((claim) => {
    const compound = compoundGraphLabel(claim.compound);
    const right = graphLabel(claim[rightKey]);
    if (compound) {
      const list = claimsByCompound.get(compound) || [];
      list.push(claim);
      claimsByCompound.set(compound, list);
    }
    if (right) {
      const list = claimsByRight.get(right) || [];
      list.push(claim);
      claimsByRight.set(right, list);
    }

    if (!compound || !right) return;

    const key = `${compound}|${right}`;
    const existing = edges.get(key) || {
      count: 0,
      rank: 0,
      claims: [],
    };
    const rank = evidenceRank[claim.evidence_level] || 1;
    existing.count += 1;
    existing.claims.push(claim);
    if (rank > existing.rank) {
      existing.rank = rank;
    }
    edges.set(key, existing);
  });
  let edgeEntries = Array.from(edges.entries());
  if (edgeEntries.length > MAX_GRAPH_EDGES) {
    edgeEntries = edgeEntries
      .sort((a, b) => {
        const edgeA = a[1];
        const edgeB = b[1];
        const byCount = (edgeB.count || 0) - (edgeA.count || 0);
        if (byCount !== 0) return byCount;
        return (edgeB.rank || 0) - (edgeA.rank || 0);
      })
      .slice(0, MAX_GRAPH_EDGES);
  }

  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
  svg.appendChild(defs);
  const compoundColors = new Map(compounds.map((compound, index) => [compound, graphColorForIndex(index, compounds.length)]));
  const targetColors = new Map(targets.map((target, index) => [target, graphColorForIndex(index, targets.length)]));
  const maxEdgeCount = Math.max(
    1,
    ...edgeEntries.map((entry) => entry[1].count || 0)
  );
  const edgeElementByKey = new Map();
  const compoundNodeElements = new Map();
  const rightNodeElements = new Map();
  const interactiveElements = [];

  function registerInteractive(el) {
    interactiveElements.push(el);
  }

  function clearFocusState() {
    interactiveElements.forEach((el) => {
      el.classList.remove("muted", "focus-primary", "focus-related");
    });
  }

  function muteAll() {
    interactiveElements.forEach((el) => el.classList.add("muted"));
  }

  function markNode(elementMap, name, focusClass) {
    const pair = elementMap.get(name);
    if (!pair) return;
    pair.node.classList.add(focusClass);
    pair.label.classList.add(focusClass);
    pair.node.classList.remove("muted");
    pair.label.classList.remove("muted");
  }

  function markEdge(edgeKey, focusClass) {
    const edge = edgeElementByKey.get(edgeKey);
    if (!edge) return;
    edge.classList.add(focusClass);
    edge.classList.remove("muted");
  }

  function applyFocusForNode(nodeType, nodeName) {
    clearFocusState();
    muteAll();

    const edgeKeys =
      nodeType === "compound"
        ? incidentEdgeKeysByCompound.get(nodeName)
        : incidentEdgeKeysByRight.get(nodeName);

    if (edgeKeys) {
      edgeKeys.forEach((edgeKey) => {
        markEdge(edgeKey, "focus-related");
        const [compound, right] = edgeKey.split("|");
        markNode(compoundNodeElements, compound, "focus-related");
        markNode(rightNodeElements, right, "focus-related");
      });
    }

    if (nodeType === "compound") {
      markNode(compoundNodeElements, nodeName, "focus-primary");
    } else {
      markNode(rightNodeElements, nodeName, "focus-primary");
    }
  }

  function applyFocusForEdge(edgeKey) {
    clearFocusState();
    muteAll();
    markEdge(edgeKey, "focus-primary");
    const [compound, right] = edgeKey.split("|");
    markNode(compoundNodeElements, compound, "focus-related");
    markNode(rightNodeElements, right, "focus-related");
  }

  function applyFocusFromSelection() {
    if (!selected) {
      clearFocusState();
      return;
    }
    if (selected.type === "edge") {
      applyFocusForEdge(`${selected.compound}|${selected.target}`);
      return;
    }
    if (selected.type === "compound") {
      applyFocusForNode("compound", selected.name);
      return;
    }
    if (selected.type === "target") {
      applyFocusForNode("target", selected.name);
      return;
    }
    clearFocusState();
  }

  edgeEntries.forEach(([key, edge], index) => {
    const [compound, target] = key.split("|");
    const cPos = compoundPositions.get(compound);
    const tPos = targetPositions.get(target);
    if (!cPos || !tPos) return;

    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    const midX = (cPos.x + tPos.x) / 2;
    const curve = 80;
    const d = `M ${cPos.x} ${cPos.y} C ${midX - curve} ${cPos.y}, ${midX + curve} ${tPos.y}, ${tPos.x} ${tPos.y}`;
    path.setAttribute("d", d);
    path.setAttribute("class", "edge");
    const edgeWidth = edgeWidthForCount(edge.count, maxEdgeCount);
    path.style.setProperty("--edge-width", `${edgeWidth.toFixed(2)}px`);
    const compoundColor = compoundColors.get(compound) || graphColorForIndex(0, 1);
    const targetColor = targetColors.get(target) || graphColorForIndex(0, 1);
    const gradientId = `edge-gradient-${index}`;
    const gradient = document.createElementNS("http://www.w3.org/2000/svg", "linearGradient");
    gradient.setAttribute("id", gradientId);
    gradient.setAttribute("gradientUnits", "userSpaceOnUse");
    gradient.setAttribute("x1", `${cPos.x}`);
    gradient.setAttribute("y1", `${cPos.y}`);
    gradient.setAttribute("x2", `${tPos.x}`);
    gradient.setAttribute("y2", `${tPos.y}`);
    const start = document.createElementNS("http://www.w3.org/2000/svg", "stop");
    start.setAttribute("offset", "0%");
    start.setAttribute("stop-color", rgbString(compoundColor));
    start.setAttribute("stop-opacity", "0.78");
    const end = document.createElementNS("http://www.w3.org/2000/svg", "stop");
    end.setAttribute("offset", "100%");
    end.setAttribute("stop-color", rgbString(targetColor));
    end.setAttribute("stop-opacity", "0.72");
    gradient.appendChild(start);
    gradient.appendChild(end);
    defs.appendChild(gradient);
    path.style.stroke = `url(#${gradientId})`;
    path.style.setProperty("--edge-glow", rgbaString(compoundColor, 0.36));
    path.dataset.compound = compound;
    path.dataset.target = target;
    path.dataset.claimCount = `${edge.count}`;
    path.dataset.edgeKey = key;
    if (selected?.type === "edge" && selected.compound === compound && selected.target === target) {
      path.classList.add("selected");
    }
    edgeElementByKey.set(key, path);
    registerInteractive(path);

    path.addEventListener("mouseenter", (event) => {
      path.classList.add("hovered");
      applyFocusForEdge(key);
      showTooltip(
        `<strong>${compound} → ${target}</strong><br/>claims: ${edge.count}`,
        event
      );
    });
    path.addEventListener("mousemove", moveTooltip);
    path.addEventListener("mouseleave", () => {
      path.classList.remove("hovered");
      hideTooltip();
      applyFocusFromSelection();
    });
    path.addEventListener("click", (event) => {
      event.stopPropagation();
      const sameSelection =
        selected?.type === "edge" && selected.compound === compound && selected.target === target;
      if (sameSelection) {
        if (!isolateSelection) {
          isolateSelection = true;
          scheduleRender();
          return;
        }
        clearSelection();
        return;
      }

      selected = { type: "edge", compound, target };
      isolateSelection = false;
      clearSelectedStyles();
      path.classList.add("selected");
      renderEdgeDetail(compound, target, edge.claims);
      applyFocusFromSelection();
      scheduleRender();
    });
    svg.appendChild(path);
  });

  compoundPositions.forEach((pos, compound) => {
    const node = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    node.setAttribute("cx", pos.x);
    node.setAttribute("cy", pos.y);
    node.setAttribute("r", 12);
    node.setAttribute("class", "node compound");
    applyGraphNodeColor(node, compoundColors.get(compound) || graphColorForIndex(0, 1));
    if (selected?.type === "compound" && selected.name === compound) {
      node.classList.add("selected");
    }
    svg.appendChild(node);
    registerInteractive(node);

    const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
    label.setAttribute("x", pos.x - labelOffset);
    label.setAttribute("class", "node-label");
    label.setAttribute("text-anchor", "end");
    setWrappedSvgLabel(label, compound, leftLabelMaxWidth, pos.x - labelOffset, pos.y);
    if (selected?.type === "compound" && selected.name === compound) {
      label.classList.add("selected");
    }
    svg.appendChild(label);
    registerInteractive(label);
    compoundNodeElements.set(compound, { node, label });

    const nodeClaims = claimsByCompound.get(compound) || [];
    const enter = (event) => {
      node.classList.add("hovered");
      label.classList.add("hovered");
      applyFocusForNode("compound", compound);
      showTooltip(
        `<strong>${compound}</strong><br/>Claims: ${nodeClaims.length}<br/>Connections: ${
          summarizeConnections(nodeClaims, rightKey).length
        }`,
        event
      );
    };
    const leave = () => {
      node.classList.remove("hovered");
      label.classList.remove("hovered");
      hideTooltip();
      applyFocusFromSelection();
    };
    const click = (event) => {
      event.stopPropagation();
      const sameSelection = selected?.type === "compound" && selected.name === compound;
      if (sameSelection) {
        if (!isolateSelection) {
          isolateSelection = true;
          scheduleRender();
          return;
        }
        clearSelection();
        return;
      }

      selected = { type: "compound", name: compound };
      isolateSelection = false;
      clearSelectedStyles();
      node.classList.add("selected");
      label.classList.add("selected");
      renderNodeDetail("compound", compound, nodeClaims);
      applyFocusFromSelection();
      scheduleRender();
    };
    node.addEventListener("mouseenter", enter);
    node.addEventListener("mousemove", moveTooltip);
    node.addEventListener("mouseleave", leave);
    node.addEventListener("click", click);
    label.addEventListener("mouseenter", enter);
    label.addEventListener("mousemove", moveTooltip);
    label.addEventListener("mouseleave", leave);
    label.addEventListener("click", click);
  });

  targetPositions.forEach((pos, target) => {
    const node = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    node.setAttribute("cx", pos.x);
    node.setAttribute("cy", pos.y);
    node.setAttribute("r", 12);
    node.setAttribute("class", "node target");
    applyGraphNodeColor(node, targetColors.get(target) || graphColorForIndex(0, 1));
    if (selected?.type === "target" && selected.name === target) {
      node.classList.add("selected");
    }
    svg.appendChild(node);
    registerInteractive(node);

    const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
    label.setAttribute("x", pos.x + labelOffset);
    label.setAttribute("class", "node-label");
    setWrappedSvgLabel(label, target, rightLabelMaxWidth, pos.x + labelOffset, pos.y);
    if (selected?.type === "target" && selected.name === target) {
      label.classList.add("selected");
    }
    svg.appendChild(label);
    registerInteractive(label);
    rightNodeElements.set(target, { node, label });

    const nodeClaims = claimsByRight.get(target) || [];
    const enter = (event) => {
      node.classList.add("hovered");
      label.classList.add("hovered");
      applyFocusForNode("target", target);
      showTooltip(
        `<strong>${target}</strong><br/>Claims: ${nodeClaims.length}<br/>Compounds: ${
          summarizeConnections(nodeClaims, "compound").length
        }`,
        event
      );
    };
    const leave = () => {
      node.classList.remove("hovered");
      label.classList.remove("hovered");
      hideTooltip();
      applyFocusFromSelection();
    };
    const click = (event) => {
      event.stopPropagation();
      const sameSelection = selected?.type === "target" && selected.name === target;
      if (sameSelection) {
        if (!isolateSelection) {
          isolateSelection = true;
          scheduleRender();
          return;
        }
        clearSelection();
        return;
      }

      selected = { type: "target", name: target };
      isolateSelection = false;
      clearSelectedStyles();
      node.classList.add("selected");
      label.classList.add("selected");
      renderNodeDetail("target", target, nodeClaims);
      applyFocusFromSelection();
      scheduleRender();
    };
    node.addEventListener("mouseenter", enter);
    node.addEventListener("mousemove", moveTooltip);
    node.addEventListener("mouseleave", leave);
    node.addEventListener("click", click);
    label.addEventListener("mouseenter", enter);
    label.addEventListener("mousemove", moveTooltip);
    label.addEventListener("mouseleave", leave);
    label.addEventListener("click", click);
  });

  graphEl.appendChild(svg);
  if (edges.size > edgeEntries.length) {
    const note = document.createElement("div");
    note.className = "graph-truncation-note";
    note.textContent = `Showing top ${edgeEntries.length} of ${edges.size} edges (ranked by claim count).`;
    graphEl.appendChild(note);
  }

  applyFocusFromSelection();
}

function render() {
  const filtered = applyFilters();
  if (selected && !selectionIsValid(filtered)) {
    selected = null;
    isolateSelection = false;
  }
  if (detailGraphFilter) {
    // Keep the current right-panel drilldown visible while refreshing the graph.
  } else if (selected) {
    renderSelectedDetailFromData(filtered);
  } else {
    renderOverviewDetail(filtered);
  }
  updateStats();
  renderCards(filtered);
  buildGraph(filtered);
  renderBibliography(filtered);
}

function refreshMainViews() {
  const filtered = applyFilters();
  if (selected && !selectionIsValid(filtered)) {
    selected = null;
    isolateSelection = false;
    clearSelectedStyles();
  }
  updateStats();
  renderCards(filtered);
  buildGraph(filtered);
  renderBibliography(filtered);
}

function scheduleRender() {
  if (renderScheduled) return;
  renderScheduled = true;
  window.requestAnimationFrame(() => {
    renderScheduled = false;
    render();
  });
}

function updateSearchPlaceholder() {
  if (!searchInput) return;
  if (mode === "mechanistic") {
    searchInput.placeholder = `Search compounds, ${lowerRightEntityLabel(true)}, or assays`;
  } else {
    searchInput.placeholder = `Search compounds, ${lowerRightEntityLabel(true)}, or outcomes`;
  }
}

function updateEntityKindToggle() {
  if (!entityKindToggle) return;
  const isAvailable = claimLayer === "normalized";
  entityKindToggle.hidden = !isAvailable;
  if (!isAvailable) {
    entityKindToggle.innerHTML = "";
    return;
  }

  const scopedClaims = graphViewClaims(mode === "mechanistic" ? claims : disorderClaims);
  const counts = new Map();
  scopedClaims.forEach((claim) => {
    const kind = entityKindForClaim(claim);
    if (!kind) return;
    counts.set(kind, (counts.get(kind) || 0) + 1);
  });

  let options = entityViewOptionsForMode().filter((option) => (counts.get(option.key) || 0) > 0);
  if (!options.length) options = entityViewOptionsForMode();
  const activeKey = options.some((option) => option.key === currentEntityViewKey())
    ? currentEntityViewKey()
    : options[0]?.key || "";
  if (activeKey && entityView[mode] !== activeKey) {
    entityView = { ...entityView, [mode]: activeKey };
  }

  entityKindToggle.innerHTML = options
    .map((option) => {
      const isActive = option.key === activeKey;
      return `
        <button
          class="ghost small ${isActive ? "active" : ""}"
          data-entity-view="${escapeHtml(option.key)}"
          role="tab"
          aria-selected="${isActive ? "true" : "false"}"
          type="button"
        >
          ${escapeHtml(option.label)}
        </button>
      `;
    })
    .join("");
}

function updateModeUI() {
  modeButtons.forEach((btn) => {
    const isActive = btn.dataset.mode === mode;
    btn.classList.toggle("active", isActive);
    btn.setAttribute("aria-selected", isActive ? "true" : "false");
  });
  claimLayerButtons.forEach((btn) => {
    const isActive = btn.dataset.claimLayer === claimLayer;
    btn.classList.toggle("active", isActive);
    btn.setAttribute("aria-selected", isActive ? "true" : "false");
  });
  evidenceViewButtons.forEach((btn) => {
    const isActive = btn.dataset.evidenceView === evidenceView;
    btn.classList.toggle("active", isActive);
    btn.setAttribute("aria-selected", isActive ? "true" : "false");
  });
  updateEntityKindToggle();
  updateSearchPlaceholder();
  if (fullTextOnlyToggle) fullTextOnlyToggle.disabled = false;
  fullTextOnlyToggle?.closest(".access-toggle")?.classList.remove("disabled");
}

function switchMode(nextMode) {
  if (mode === nextMode) return;
  mode = nextMode;
  selected = null;
  isolateSelection = false;
  detailGraphFilter = null;
  clearSelectedStyles();
  updateModeUI();
  syncYearFilterControls(activeClaimsForMode());
  setDetailHeader(defaultDetail.title);
  renderDetailEmpty();
  scheduleRender();
}

function switchClaimLayer(nextLayer) {
  if (!claimStores[nextLayer] || claimLayer === nextLayer) return;
  claimLayer = nextLayer;
  applyClaimLayerStore();
  selected = null;
  isolateSelection = false;
  detailGraphFilter = null;
  clearSelectedStyles();
  updateModeUI();
  syncYearFilterControls(activeClaimsForMode(), true);
  setDetailHeader(defaultDetail.title);
  renderDetailEmpty();
  scheduleRender();
}

function switchEvidenceView(nextView) {
  if (!["primary", "secondary"].includes(nextView) || evidenceView === nextView) return;
  evidenceView = nextView;
  selected = null;
  isolateSelection = false;
  detailGraphFilter = null;
  clearSelectedStyles();
  updateModeUI();
  syncYearFilterControls(activeClaimsForMode(), true);
  setDetailHeader(defaultDetail.title);
  renderDetailEmpty();
  scheduleRender();
}

function switchEntityView(nextView) {
  const options = entityViewOptionsForMode();
  if (!options.some((option) => option.key === nextView) || currentEntityViewKey() === nextView) return;
  entityView = { ...entityView, [mode]: nextView };
  selected = null;
  isolateSelection = false;
  detailGraphFilter = null;
  clearSelectedStyles();
  updateModeUI();
  syncYearFilterControls(activeClaimsForMode(), true);
  setDetailHeader(defaultDetail.title);
  renderDetailEmpty();
  scheduleRender();
}

async function fetchJsonFromCandidates(candidates) {
  const errors = [];
  for (const url of candidates) {
    try {
      const response = await fetch(url, { cache: "no-store" });
      if (!response.ok) {
        errors.push(`${url} -> HTTP ${response.status}`);
        continue;
      }
      const data = await response.json();
      return { data, url };
    } catch (error) {
      errors.push(`${url} -> ${error.message}`);
    }
  }
  throw new Error(errors.join("; "));
}

function dataCandidates(path) {
  return [`../${path}`, `/${path}`, path];
}

async function loadClaimArray({ arrayPath, payloadPaths = [], payloadMapper }) {
  const errors = [];
  if (arrayPath) {
    try {
      const { data } = await fetchJsonFromCandidates(dataCandidates(arrayPath));
      if (Array.isArray(data)) return data;
      errors.push(`${arrayPath} -> expected JSON array`);
    } catch (error) {
      errors.push(error.message);
    }
  }
  for (const payloadPath of payloadPaths) {
    try {
      const { data } = await fetchJsonFromCandidates(dataCandidates(payloadPath));
      return payloadMapper(data);
    } catch (error) {
      errors.push(error.message);
    }
  }
  throw new Error(errors.join("; "));
}

async function loadOptionalClaimArray(options) {
  try {
    return await loadClaimArray(options);
  } catch (_error) {
    return [];
  }
}

function mechanisticFromPayload(payload) {
  const contributions = Array.isArray(payload?.contributions) ? payload.contributions : [];
  return contributions.map((item) => ({
    claim_type: item?.properties?.claim_type || "",
    compound: item?.resources?.compound || "",
    target: item?.resources?.target || "",
    raw_entity_label: item?.properties?.raw_entity_label || "",
    entity_role: item?.properties?.entity_role || "",
    clinical_context_condition: item?.properties?.clinical_context_condition || "",
    graph_entity_label: item?.properties?.graph_entity_label || "",
    graph_entity_type: item?.properties?.graph_entity_type || "",
    graph_include_candidate: item?.properties?.graph_include_candidate === true,
    graph_exclusion_reason: item?.properties?.graph_exclusion_reason || "",
    mechanism_type: item?.properties?.mechanism_type || "",
    assay_type: item?.properties?.assay_type || "",
    assay_family: item?.properties?.assay_family || "",
    action_type: item?.properties?.action_type || "",
    affinity_type: item?.properties?.affinity_type || "",
    affinity_value: item?.properties?.affinity_value ?? "",
    affinity_unit: item?.properties?.affinity_unit || "",
    result_direction: item?.properties?.result_direction || "",
    species: item?.properties?.species || "",
    model_or_system: item?.properties?.model_or_system || "",
    system: item?.properties?.system || "",
    study_doi: item?.paper?.doi || "",
    openalex_id: item?.paper?.openalex_id || "",
    study_title: item?.paper?.title || "",
    study_year: item?.paper?.year ?? "",
    study_journal: String(item?.paper?.journal ?? item?.paper?.study_journal ?? "").trim(),
    publication_type: item?.paper?.publication_type || "",
    publication_date: item?.paper?.publication_date || "",
    publisher: item?.paper?.publisher || "",
    trial_registry_ids: item?.paper?.trial_registry_ids || "",
    authors:
      item?.paper?.authors ??
      item?.paper?.author_list ??
      item?.paper?.author ??
      item?.paper?.first_author ??
      "",
    evidence_level: item?.properties?.evidence_level || "low",
    support: item?.properties?.support || "",
    confidence: item?.properties?.confidence ?? "",
    needs_human_review: item?.properties?.needs_human_review === true,
    source: item?.properties?.source || "",
    kg_domain: item?.properties?.kg_domain || item?.extracted_variables?.kg_domain || "",
    kg_entity_kind:
      item?.properties?.kg_entity_kind || item?.properties?.entity_kind || item?.extracted_variables?.kg_entity_kind || "",
    entity_kind: item?.properties?.entity_kind || item?.properties?.kg_entity_kind || item?.extracted_variables?.kg_entity_kind || "",
    kg_evidence_type: item?.properties?.kg_evidence_type || item?.extracted_variables?.kg_evidence_type || "",
    kg_relation_type: item?.properties?.kg_relation_type || item?.extracted_variables?.kg_relation_type || "",
    kg_source_name: item?.properties?.kg_source_name || item?.extracted_variables?.kg_source_name || "",
    paper_type: item?.provenance?.paper_type || "",
    source_type: item?.provenance?.source_type || "",
    source_family: item?.provenance?.source_family || "",
    paper_assessment_route: item?.provenance?.paper_assessment_route || "",
    access_level: item?.provenance?.access_level || "",
    source_access_level: item?.provenance?.source_access_level || item?.provenance?.access_level || "",
    evidence_location: item?.provenance?.evidence_location || "",
    evidence_locator: item?.provenance?.evidence_locator || "",
    study_design: item?.provenance?.study_design || "",
    notes: item?.provenance?.notes || "",
    supporting_quote: item?.extracted_variables?.supporting_quote || "",
    normalization_status: item?.extracted_variables?.normalization_status || "",
    normalization_notes: item?.extracted_variables?.normalization_notes || "",
    canonical_compound: item?.extracted_variables?.canonical_compound || "",
    canonical_entity: item?.extracted_variables?.canonical_entity || "",
  }));
}

function disorderFromPayload(payload) {
  const contributions = Array.isArray(payload?.contributions) ? payload.contributions : [];
  return contributions.map((item) => ({
    claim_type: item?.properties?.claim_type || "",
    compound: item?.resources?.compound || "",
    disorder: item?.resources?.disorder || "",
    raw_entity_label: item?.properties?.raw_entity_label || "",
    entity_role: item?.properties?.entity_role || "",
    clinical_context_condition: item?.properties?.clinical_context_condition || "",
    graph_entity_label: item?.properties?.graph_entity_label || "",
    graph_entity_type: item?.properties?.graph_entity_type || "",
    graph_include_candidate: item?.properties?.graph_include_candidate === true,
    graph_exclusion_reason: item?.properties?.graph_exclusion_reason || "",
    outcome_type: item?.properties?.outcome_type || "",
    outcome_domain: item?.properties?.outcome_domain || "",
    result_direction: item?.properties?.result_direction || "",
    outcome_measure: item?.properties?.outcome_measure || "",
    outcome_measure_normalized:
      item?.properties?.outcome_measure_normalized || item?.extracted_variables?.outcome_measure_normalized || "",
    sample_size_total: item?.extracted_variables?.sample_size_total || item?.properties?.sample_size_total || "",
    sample_size_by_arm: item?.extracted_variables?.sample_size_by_arm || item?.properties?.sample_size_by_arm || "",
    population: item?.properties?.population || "",
    intervention_or_exposure:
      item?.extracted_variables?.intervention_or_exposure || item?.properties?.intervention_or_exposure || "",
    comparator: item?.extracted_variables?.comparator || item?.properties?.comparator || "",
    dose: item?.extracted_variables?.dose || item?.properties?.dose || "",
    timepoint: item?.extracted_variables?.timepoint || item?.properties?.timepoint || "",
    adverse_events: item?.extracted_variables?.adverse_events || item?.properties?.adverse_events || "",
    system: item?.properties?.system || "",
    study_doi: item?.paper?.doi || "",
    openalex_id: item?.paper?.openalex_id || "",
    study_title: item?.paper?.title || "",
    study_year: item?.paper?.year ?? "",
    study_journal: String(item?.paper?.journal ?? item?.paper?.study_journal ?? "").trim(),
    publication_type: item?.paper?.publication_type || "",
    publication_date: item?.paper?.publication_date || "",
    publisher: item?.paper?.publisher || "",
    trial_registry_ids: item?.paper?.trial_registry_ids || "",
    authors:
      item?.paper?.authors ??
      item?.paper?.author_list ??
      item?.paper?.author ??
      item?.paper?.first_author ??
      "",
    evidence_level: item?.properties?.evidence_level || "low",
    support: item?.properties?.support || "",
    confidence: item?.properties?.confidence ?? "",
    needs_human_review: item?.properties?.needs_human_review === true,
    source: item?.properties?.source || "",
    kg_domain: item?.properties?.kg_domain || item?.extracted_variables?.kg_domain || "",
    kg_entity_kind:
      item?.properties?.kg_entity_kind || item?.properties?.entity_kind || item?.extracted_variables?.kg_entity_kind || "",
    entity_kind: item?.properties?.entity_kind || item?.properties?.kg_entity_kind || item?.extracted_variables?.kg_entity_kind || "",
    kg_evidence_type: item?.properties?.kg_evidence_type || item?.extracted_variables?.kg_evidence_type || "",
    kg_relation_type: item?.properties?.kg_relation_type || item?.extracted_variables?.kg_relation_type || "",
    kg_source_name: item?.properties?.kg_source_name || item?.extracted_variables?.kg_source_name || "",
    paper_type: item?.provenance?.paper_type || "",
    source_type: item?.provenance?.source_type || "",
    source_family: item?.provenance?.source_family || "",
    paper_assessment_route: item?.provenance?.paper_assessment_route || "",
    access_level: item?.provenance?.access_level || "",
    source_access_level: item?.provenance?.source_access_level || item?.provenance?.access_level || "",
    evidence_location: item?.provenance?.evidence_location || "",
    evidence_locator: item?.provenance?.evidence_locator || "",
    study_design: item?.provenance?.study_design || "",
    notes: item?.provenance?.notes || "",
    supporting_quote: item?.extracted_variables?.supporting_quote || "",
    normalization_status: item?.extracted_variables?.normalization_status || "",
    normalization_notes: item?.extracted_variables?.normalization_notes || "",
    canonical_compound: item?.extracted_variables?.canonical_compound || "",
    canonical_entity: item?.extracted_variables?.canonical_entity || "",
  }));
}

function renderLoadError(messages) {
  setDetailHeader("Data Load Error");
  detailBody.innerHTML = `
    <div class="detail-empty">
      Start a local static server from the project root (for example: <code>python3 -m http.server</code>), then open <code>/ui/</code>.
    </div>
    <div class="detail-list">
      ${messages.map((msg) => `<div class="detail-item"><div class="meta">${msg}</div></div>`).join("")}
    </div>
  `;
  cardsEl.innerHTML = `<div class="detail-empty">No claims loaded.</div>`;
  graphEl.innerHTML = "";
  if (studyListEl) {
    studyListEl.innerHTML = `<div class="detail-empty">No studies loaded.</div>`;
  }
}

async function loadBibliographyPayloads() {
  const payloads = [
    {
      key: "mechanistic",
      candidates: [
        "../data/processed/bibliography_payload_mechanistic.json",
        "/data/processed/bibliography_payload_mechanistic.json",
        "data/processed/bibliography_payload_mechanistic.json",
      ],
    },
    {
      key: "disorders",
      candidates: [
        "../data/processed/bibliography_payload_disorder.json",
        "/data/processed/bibliography_payload_disorder.json",
        "data/processed/bibliography_payload_disorder.json",
      ],
    },
  ];

  await Promise.all(
    payloads.map(async ({ key, candidates }) => {
      try {
        const { data } = await fetchJsonFromCandidates(candidates);
        bibliographyByMode[key] = bibliographyFromPayload(data);
      } catch (_error) {
        bibliographyByMode[key] = [];
      }
    })
  );
}

async function init() {
  const loadErrors = [];

  try {
    const primary = await loadClaimArray({
      payloadPaths: ["data/processed/graph_payload_mechanistic.json"],
      payloadMapper: mechanisticFromPayload,
    });
    const secondary = await loadOptionalClaimArray({
      payloadPaths: ["data/processed/graph_payload_mechanistic_secondary_sources.json"],
      payloadMapper: mechanisticFromPayload,
    });
    claimStores.normalized.mechanistic = dedupeClaims([...primary, ...secondary]);
  } catch (error) {
    loadErrors.push(`normalized mechanistic claims: ${error.message}`);
  }

  try {
    const primary = await loadClaimArray({
      payloadPaths: ["data/processed/graph_payload_disorder.json"],
      payloadMapper: disorderFromPayload,
    });
    const secondary = await loadOptionalClaimArray({
      payloadPaths: ["data/processed/graph_payload_disorder_secondary_sources.json"],
      payloadMapper: disorderFromPayload,
    });
    claimStores.normalized.disorders = dedupeClaims([...primary, ...secondary]);
  } catch (error) {
    loadErrors.push(`normalized disorder claims: ${error.message}`);
  }

  try {
    const primary = await loadClaimArray({
      arrayPath: "data/processed/extraction/mechanistic_claims.json",
      payloadPaths: [
        "data/processed/graph_payload_mechanistic_primary_with_secondary.json",
        "data/processed/graph_payload_mechanistic.json",
      ],
      payloadMapper: mechanisticFromPayload,
    });
    const secondary = await loadOptionalClaimArray({
      arrayPath: "data/processed/extraction/mechanistic_secondary_claims.json",
      payloadMapper: mechanisticFromPayload,
    });
    claimStores.extracted.mechanistic = dedupeClaims([...primary, ...secondary]);
  } catch (error) {
    loadErrors.push(`full mechanistic claims: ${error.message}`);
  }

  try {
    const primary = await loadClaimArray({
      arrayPath: "data/processed/extraction/disorder_claims.json",
      payloadPaths: [
        "data/processed/graph_payload_disorder_primary_with_secondary.json",
        "data/processed/graph_payload_disorder.json",
      ],
      payloadMapper: disorderFromPayload,
    });
    const secondary = await loadOptionalClaimArray({
      arrayPath: "data/processed/extraction/disorder_secondary_claims.json",
      payloadMapper: disorderFromPayload,
    });
    claimStores.extracted.disorders = dedupeClaims([...primary, ...secondary]);
  } catch (error) {
    loadErrors.push(`full disorder claims: ${error.message}`);
  }

  applyClaimLayerStore();

  const totalLoadedClaims = Object.values(claimStores).reduce(
    (sum, store) => sum + store.mechanistic.length + store.disorders.length,
    0
  );
  if (!totalLoadedClaims) {
    renderLoadError(loadErrors);
    return;
  }

  await loadBibliographyPayloads();
  Object.keys(claimStores).forEach((layer) => {
    claimStores[layer].mechanistic = enrichClaimsWithBibliographyMetadata(
      claimStores[layer].mechanistic,
      "mechanistic"
    );
    claimStores[layer].disorders = enrichClaimsWithBibliographyMetadata(claimStores[layer].disorders, "disorders");
  });
  applyClaimLayerStore();
  updateModeUI();
  syncYearFilterControls(activeClaimsForMode(), true);
  setDetailHeader(defaultDetail.title);
  renderDetailEmpty();
  scheduleRender();
}

if (yearMinFilter) {
  yearMinFilter.addEventListener("change", scheduleRender);
}
if (yearMaxFilter) {
  yearMaxFilter.addEventListener("change", scheduleRender);
}
if (yearStepButtons.length) {
  yearStepButtons.forEach((btn) => {
    btn.addEventListener("click", (event) => {
      event.preventDefault();
      const targetId = btn.dataset.target || "";
      const dir = btn.dataset.dir || "";
      const input = document.getElementById(targetId);
      if (!(input instanceof HTMLInputElement) || input.disabled) return;
      if (dir === "up") input.stepUp();
      if (dir === "down") input.stepDown();
      input.dispatchEvent(new Event("change", { bubbles: true }));
      input.focus({ preventScroll: true });
    });
  });
}
if (searchInput) {
  searchInput.addEventListener("input", () => {
    renderCards(applyFilters());
  });
}
if (bibliographySearchInput) {
  bibliographySearchInput.addEventListener("input", () => {
    renderBibliography(applyFilters());
  });
}
if (fullTextOnlyToggle) {
  fullTextOnlyToggle.addEventListener("change", scheduleRender);
}
if (studiesStatCard) {
  studiesStatCard.addEventListener("click", focusBibliography);
  studiesStatCard.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      focusBibliography();
    }
  });
}
if (detailBody) {
  detailBody.addEventListener("mouseover", (event) => {
    const target = event.target.closest?.(".sample-heatmap-target");
    if (!target || !detailBody.contains(target)) return;
    if (event.relatedTarget && target.contains(event.relatedTarget)) return;
    target.classList.add("hovered");
    showTooltip(sampleHeatmapTooltipHtml(target), event);
  });
  detailBody.addEventListener("mouseover", (event) => {
    const target = event.target.closest?.(".publication-year-target");
    if (!target || !detailBody.contains(target)) return;
    if (event.relatedTarget && target.contains(event.relatedTarget)) return;
    target.classList.add("hovered");
    showTooltip(publicationYearTooltipHtml(target), event);
  });
  detailBody.addEventListener("mouseover", (event) => {
    const target = event.target.closest?.(".interactive-bar, .composition-filter-target");
    if (!target || !detailBody.contains(target)) return;
    if (event.relatedTarget && target.contains(event.relatedTarget)) return;
    target.classList.add("hovered");
    showTooltip(horizontalBarTooltipHtml(target), event);
  });
  detailBody.addEventListener("mousemove", (event) => {
    const target = event.target.closest?.(".sample-heatmap-target");
    if (!target || !detailBody.contains(target)) return;
    moveTooltip(event);
  });
  detailBody.addEventListener("mousemove", (event) => {
    const target = event.target.closest?.(".publication-year-target");
    if (!target || !detailBody.contains(target)) return;
    moveTooltip(event);
  });
  detailBody.addEventListener("mousemove", (event) => {
    const target = event.target.closest?.(".interactive-bar, .composition-filter-target");
    if (!target || !detailBody.contains(target)) return;
    moveTooltip(event);
  });
  detailBody.addEventListener("mouseout", (event) => {
    const target = event.target.closest?.(".sample-heatmap-target");
    if (!target || !detailBody.contains(target)) return;
    if (event.relatedTarget && target.contains(event.relatedTarget)) return;
    target.classList.remove("hovered");
    hideTooltip();
  });
  detailBody.addEventListener("mouseout", (event) => {
    const target = event.target.closest?.(".publication-year-target");
    if (!target || !detailBody.contains(target)) return;
    if (event.relatedTarget && target.contains(event.relatedTarget)) return;
    target.classList.remove("hovered");
    hideTooltip();
  });
  detailBody.addEventListener("mouseout", (event) => {
    const target = event.target.closest?.(".interactive-bar, .composition-filter-target");
    if (!target || !detailBody.contains(target)) return;
    if (event.relatedTarget && target.contains(event.relatedTarget)) return;
    target.classList.remove("hovered");
    hideTooltip();
  });
  detailBody.addEventListener("focusin", (event) => {
    const target = event.target.closest?.(".sample-heatmap-target");
    if (!target || !detailBody.contains(target)) return;
    target.classList.add("hovered");
    showTooltipForElement(sampleHeatmapTooltipHtml(target), target);
  });
  detailBody.addEventListener("focusin", (event) => {
    const target = event.target.closest?.(".publication-year-target");
    if (!target || !detailBody.contains(target)) return;
    target.classList.add("hovered");
    showTooltipForElement(publicationYearTooltipHtml(target), target);
  });
  detailBody.addEventListener("focusin", (event) => {
    const target = event.target.closest?.(".interactive-bar, .composition-filter-target");
    if (!target || !detailBody.contains(target)) return;
    target.classList.add("hovered");
    showTooltipForElement(horizontalBarTooltipHtml(target), target);
  });
  detailBody.addEventListener("focusout", (event) => {
    const target = event.target.closest?.(".sample-heatmap-target");
    if (!target || !detailBody.contains(target)) return;
    target.classList.remove("hovered");
    hideTooltip();
  });
  detailBody.addEventListener("focusout", (event) => {
    const target = event.target.closest?.(".publication-year-target");
    if (!target || !detailBody.contains(target)) return;
    target.classList.remove("hovered");
    hideTooltip();
  });
  detailBody.addEventListener("focusout", (event) => {
    const target = event.target.closest?.(".interactive-bar, .composition-filter-target");
    if (!target || !detailBody.contains(target)) return;
    target.classList.remove("hovered");
    hideTooltip();
  });
  detailBody.addEventListener("click", (event) => {
    const restoreButton = event.target.closest?.("[data-detail-action='restore']");
    if (restoreButton && detailBody.contains(restoreButton)) {
      restoreCurrentDetailPanel();
      return;
    }

    const target = event.target.closest?.(".sample-heatmap-target");
    if (!target || !detailBody.contains(target)) return;
    event.preventDefault();
    hideTooltip();
    renderSampleHeatmapDetail(
      target.dataset.yearStart || "",
      target.dataset.yearEnd || "",
      target.dataset.sampleMin || "",
      target.dataset.sampleMax || "",
      `${target.dataset.yearLabel || ""}, N=${target.dataset.sampleLabel || ""}`
    );
  });
  detailBody.addEventListener("click", (event) => {
    const target = event.target.closest?.(".publication-year-target");
    if (!target || !detailBody.contains(target)) return;
    event.preventDefault();
    hideTooltip();
    renderPublicationYearDetail(target.dataset.yearStart || "", target.dataset.yearEnd || "", target.dataset.yearLabel || "");
  });
  detailBody.addEventListener("click", (event) => {
    const target = event.target.closest?.(".interactive-bar, .composition-filter-target");
    if (!target || !detailBody.contains(target)) return;
    event.preventDefault();
    hideTooltip();
    renderFieldValueDetail(target.dataset.filterField || "", target.dataset.filterValue || "", target.dataset.filterLabel || "");
  });
  detailBody.addEventListener("keydown", (event) => {
    const target = event.target.closest?.(".sample-heatmap-target");
    if (!target || !detailBody.contains(target)) return;
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    hideTooltip();
    renderSampleHeatmapDetail(
      target.dataset.yearStart || "",
      target.dataset.yearEnd || "",
      target.dataset.sampleMin || "",
      target.dataset.sampleMax || "",
      `${target.dataset.yearLabel || ""}, N=${target.dataset.sampleLabel || ""}`
    );
  });
  detailBody.addEventListener("keydown", (event) => {
    const target = event.target.closest?.(".publication-year-target");
    if (!target || !detailBody.contains(target)) return;
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    hideTooltip();
    renderPublicationYearDetail(target.dataset.yearStart || "", target.dataset.yearEnd || "", target.dataset.yearLabel || "");
  });
  detailBody.addEventListener("keydown", (event) => {
    const target = event.target.closest?.(".interactive-bar, .composition-filter-target");
    if (!target || !detailBody.contains(target)) return;
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    hideTooltip();
    renderFieldValueDetail(target.dataset.filterField || "", target.dataset.filterValue || "", target.dataset.filterLabel || "");
  });
  detailBody.addEventListener("click", (event) => {
    const target = event.target.closest?.(".scale-chip[data-outcome-scale]");
    if (!target || !detailBody.contains(target)) return;
    event.preventDefault();
    renderOutcomeScaleDetail(target.dataset.outcomeScale || "");
  });
}
graphEl.addEventListener("click", (event) => {
  if (event.target === graphEl || event.target.tagName?.toLowerCase() === "svg") {
    clearSelection();
  }
});
modeButtons.forEach((button) => {
  button.addEventListener("click", () => {
    switchMode(button.dataset.mode);
  });
});
claimLayerButtons.forEach((button) => {
  button.addEventListener("click", () => {
    switchClaimLayer(button.dataset.claimLayer);
  });
});
evidenceViewButtons.forEach((button) => {
  button.addEventListener("click", () => {
    switchEvidenceView(button.dataset.evidenceView);
  });
});
if (entityKindToggle) {
  entityKindToggle.addEventListener("click", (event) => {
    const button = event.target.closest?.("[data-entity-view]");
    if (!button || !entityKindToggle.contains(button)) return;
    switchEntityView(button.dataset.entityView || "");
  });
}
window.addEventListener("resize", scheduleRender);

init();
