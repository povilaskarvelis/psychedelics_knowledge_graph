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
const MAX_CARDS_RENDER = 250;
const MAX_BIBLIOGRAPHY_RENDER = 300;
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

let claims = [];
let disorderClaims = [];
let selected = null;
let isolateSelection = false;
let mode = "disorders";
let renderScheduled = false;
const yearFilterState = {
  mechanistic: { min: "", max: "" },
  disorders: { min: "", max: "" },
};

const defaultDetail = {
  title: "Graph Detail",
};

function normalizeValue(value) {
  return (value || "").toString().trim().toLowerCase();
}

function unique(values) {
  return Array.from(new Set(values)).sort();
}

function activeClaimsForMode() {
  const baseClaims = mode === "mechanistic" ? claims : disorderClaims;
  return primaryEvidenceClaims(baseClaims);
}

function primaryEvidenceClaims(baseClaims) {
  return baseClaims.filter(
    (claim) =>
      normalizeValue(claim.paper_type) === "primary_results" &&
      normalizeValue(claim.source_type) === "primary_study" &&
      normalizeValue(claim.access_level) !== "secondary_summary",
  );
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
  const labels = {
    randomized_controlled_trial: "rct",
    phase_3_randomized_controlled_trial: "phase 3 rct",
    phase_3_trial: "phase 3",
    phase_2_trial: "phase 2",
    clinical_trial: "clinical trial",
    open_label_trial: "open label",
    pilot_trial: "pilot",
    observational_follow_up: "follow-up",
    observational_study: "observational",
    preclinical_study: "preclinical",
    case_report: "case report",
    in_vitro_binding_assay: "binding assay",
    in_vitro_uptake_assay: "uptake assay",
  };
  if (labels[normalized]) return labels[normalized];
  if (!normalized || normalized === "unknown" || normalized === "pending_curation") return "";
  return labelFromSlug(normalized);
}

function accessLevelLabel(accessLevel) {
  const normalized = normalizeValue(accessLevel);
  const labels = {
    full_text_seen: "full text",
    abstract_only: "abstract",
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
  return chipHtml("study-design", studyDesignLabel(design), design);
}

function accessLevelBadgeHtml(accessLevel) {
  return chipHtml("access-level", accessLevelLabel(accessLevel), accessLevel);
}

function claimBadgeHtml(claim) {
  return [
    studyDesignBadgeHtml(claim.study_design),
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

function updateStats() {
  const disorderPrimary = primaryEvidenceClaims(disorderClaims);
  const mechanisticPrimary = primaryEvidenceClaims(claims);
  const totalClaims = [...disorderPrimary, ...mechanisticPrimary];

  stats.compounds.textContent = formatCompactNumber(
    unique(totalClaims.map((claim) => claim.compound).filter(Boolean)).length
  );
  stats.indications.textContent = formatCompactNumber(
    unique(disorderPrimary.map((claim) => claim.disorder).filter(Boolean)).length
  );
  stats.targets.textContent = formatCompactNumber(
    unique(mechanisticPrimary.map((claim) => claim.target).filter(Boolean)).length
  );
  stats.studies.textContent = formatCompactNumber(uniqueStudyCount(totalClaims));
}

function applyFilters() {
  const rightKey = mode === "mechanistic" ? "target" : "disorder";
  const activeClaims = activeClaimsForMode();
  const yearRange = activeYearRange(activeClaims);
  const fullTextOnly = Boolean(fullTextOnlyToggle?.checked);

  const baseFiltered = activeClaims.filter((claim) => {
    if (fullTextOnly && normalizeValue(claim.access_level) !== "full_text_seen") {
      return false;
    }

    if (yearRange.constrained) {
      const year = parseYearValue(claim.study_year);
      if (year === null) return false;
      if (year < yearRange.min || year > yearRange.max) return false;
    }

    return true;
  });

  if (!selected || !isolateSelection) return baseFiltered;

  if (selected.type === "edge") {
    return baseFiltered.filter(
      (claim) => claim.compound === selected.compound && claim[rightKey] === selected.target
    );
  }
  if (selected.type === "compound") {
    return baseFiltered.filter((claim) => claim.compound === selected.name);
  }
  if (selected.type === "target") {
    return baseFiltered.filter((claim) => claim[rightKey] === selected.name);
  }
  return baseFiltered;
}

function selectionIsValid(data) {
  if (!selected) return true;
  const rightKey = mode === "mechanistic" ? "target" : "disorder";
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

function renderCards(data) {
  const searchValue = normalizeValue(searchInput?.value);
  const rightKey = mode === "mechanistic" ? "target" : "disorder";
  const cardData = !searchValue
    ? data
    : data.filter((claim) => {
        const haystack = [
          claim.compound,
          claim[rightKey],
          claim.assay_type,
          claim.study_title,
          claim.affinity_type,
          claim.outcome_type,
          claim.result_direction,
          claim.paper_type,
          claimAuthors(claim),
          claim.study_doi,
          claim.openalex_id,
        ]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        return haystack.includes(searchValue);
      });

  cardsEl.innerHTML = "";

  const rows = cardData.slice(0, MAX_CARDS_RENDER);
  rows.forEach((claim) => {
    const card = document.createElement("div");
    card.className = "card";

    const badges = claimBadgeHtml(claim);

    const doiHref = doiUrl(claim.study_doi);
    const sourceLine = doiHref
      ? claimFieldLine(
          "DOI",
          `<a href="${doiHref}" target="_blank" rel="noopener noreferrer">${escapeHtml(
            claim.study_doi
          )}</a>`
        )
      : claim.openalex_id
        ? claimFieldLine("OpenAlex", escapeHtml(String(claim.openalex_id)))
        : "";

    const relation = mode === "mechanistic" ? `${claim.compound} → ${claim.target}` : `${claim.compound} → ${claim.disorder}`;
    const authors = claimAuthors(claim);

    const affinityValueInner = [
      claim.affinity_value != null && String(claim.affinity_value).trim() !== ""
        ? escapeHtml(String(claim.affinity_value))
        : "",
      claim.affinity_unit ? escapeHtml(String(claim.affinity_unit)) : "",
    ]
      .filter(Boolean)
      .join(" ");

    const outcomeLine =
      mode === "disorders"
        ? claimFieldLine(
            "Outcome",
            `${escapeHtml(claim.outcome_type || "reported")}${
              claim.outcome_measure ? ` • ${escapeHtml(claim.outcome_measure)}` : ""
            }`
          )
        : "";
    const directionLine =
      mode === "disorders"
        ? claimFieldLine("Direction", escapeHtml(resultDirectionLabel(claim.result_direction)))
        : "";

    card.innerHTML = `
      <div class="card-header">
        <h3>${relation}</h3>
        <div class="badge-row">${badges}</div>
      </div>
      <div class="meta">
        ${
          mode === "mechanistic"
            ? `${claimFieldLine(claim.affinity_type || "Measure", affinityValueInner)}
        ${claimFieldLine("Assay", escapeHtml(claim.assay_type || ""))}`
            : `${outcomeLine}
        ${directionLine}`
        }
        ${claimFieldLine("System", escapeHtml(claim.system || "unknown"))}
        ${claimFieldLine(mode === "mechanistic" ? "Species" : "Population", escapeHtml((mode === "mechanistic" ? claim.species : claim.population) || "unknown"))}
        ${claimFieldLine(
          "Study",
          `${escapeHtml(claim.study_title || "")}${
            claim.study_year != null && String(claim.study_year) !== ""
              ? ` (${escapeHtml(String(claim.study_year))})`
              : ""
          }`
        )}
        ${claimFieldLine("Authors", escapeHtml(authors || "not available"))}
        ${sourceLine ? sourceLine : ""}
      </div>
    `;

    cardsEl.appendChild(card);
  });

  if (cardData.length > rows.length) {
    const note = document.createElement("div");
    note.className = "detail-empty";
    note.textContent = `Showing ${rows.length} of ${cardData.length} claim cards. Filter to narrow further.`;
    cardsEl.appendChild(note);
  }
}

function renderBibliography(data) {
  if (!studyListEl) return;

  const rightKey = mode === "mechanistic" ? "target" : "disorder";
  const rightLabel = mode === "mechanistic" ? "Targets" : "Indications";
  const studies = new Map();

  data.forEach((claim) => {
    const id = studyId(claim);
    if (!id || id === "unknown") return;

    const existing = studies.get(id) || {
      id,
      doi: claim.study_doi || "",
      openalexId: claim.openalex_id || "",
      title: claim.study_title || "Untitled study",
      year: Number(claim.study_year) || 0,
      claims: 0,
      compounds: new Set(),
      rights: new Set(),
      authors: new Set(),
    };

    existing.claims += 1;
    if (claim.compound) existing.compounds.add(claim.compound);
    if (claim[rightKey]) existing.rights.add(claim[rightKey]);
    const authors = claimAuthors(claim);
    if (authors) {
      authors
        .split(",")
        .map((part) => part.trim())
        .filter(Boolean)
        .forEach((name) => existing.authors.add(name));
    }
    if (!existing.title && claim.study_title) existing.title = claim.study_title;
    if (!existing.year && Number(claim.study_year)) existing.year = Number(claim.study_year);

    studies.set(id, existing);
  });

  const rows = Array.from(studies.values())
    .map((entry) => ({
      ...entry,
      compoundsText: Array.from(entry.compounds).sort().join(", "),
      rightsText: Array.from(entry.rights).sort().join(", "),
      authorsText: Array.from(entry.authors).sort().join(", "),
    }))
    .sort((a, b) => {
      const byYear = b.year - a.year;
      if (byYear !== 0) return byYear;
      const byClaims = b.claims - a.claims;
      if (byClaims !== 0) return byClaims;
      return a.title.localeCompare(b.title);
    });

  const bibliographyQuery = normalizeValue(bibliographySearchInput?.value);
  const filteredRows = !bibliographyQuery
    ? rows
    : rows.filter((entry) => {
        const haystack = normalizeValue(
          [
            entry.title,
            entry.authorsText,
            entry.compoundsText,
            entry.rightsText,
            entry.doi,
            entry.openalexId,
          ].join(" ")
        );
        return haystack.includes(bibliographyQuery);
      });

  if (!filteredRows.length) {
    studyListEl.innerHTML = '<div class="detail-empty">No studies in the current view.</div>';
    return;
  }

  const visibleRows = filteredRows.slice(0, MAX_BIBLIOGRAPHY_RENDER);
  studyListEl.innerHTML = visibleRows
    .map((entry) => {
      const doiLink = entry.doi
        ? `<a href="https://doi.org/${encodeURI(entry.doi)}" target="_blank" rel="noopener noreferrer">${entry.doi}</a>`
        : "";
      const openAlexLink = entry.openalexId
        ? `<a href="${openAlexUrl(entry.openalexId)}" target="_blank" rel="noopener noreferrer">${entry.openalexId}</a>`
        : "";

      return `
        <article class="study-item">
          <h3>${entry.title}${entry.year ? ` (${entry.year})` : ""}</h3>
          <div class="meta">
            <div><strong>Claims:</strong> ${entry.claims}</div>
            <div><strong>Compounds:</strong> ${entry.compoundsText || "Unknown"}</div>
            <div><strong>${rightLabel}:</strong> ${entry.rightsText || "Unknown"}</div>
            <div><strong>Authors:</strong> ${entry.authorsText || "not available"}</div>
          </div>
          <div class="study-links">
            ${doiLink ? `<span><strong>DOI:</strong> ${doiLink}</span>` : ""}
            ${openAlexLink ? `<span><strong>OpenAlex:</strong> ${openAlexLink}</span>` : ""}
          </div>
        </article>
      `;
    })
    .join("");

  if (filteredRows.length > visibleRows.length) {
    const note = document.createElement("div");
    note.className = "detail-empty";
    note.textContent = `Showing ${visibleRows.length} of ${filteredRows.length} studies. Filter to narrow further.`;
    studyListEl.appendChild(note);
  }
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
    const label = item[key];
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

function bucketStepForYears(minYear, maxYear) {
  const span = maxYear - minYear + 1;
  if (span > 28) return 5;
  if (span > 16) return 2;
  return 1;
}

function buildYearBuckets(items) {
  const entries = uniqueStudyEntries(items).filter((entry) => entry.year !== null);
  if (!entries.length) return [];

  const years = entries.map((entry) => entry.year);
  const minYear = Math.min(...years);
  const maxYear = Math.max(...years);
  const step = bucketStepForYears(minYear, maxYear);
  const startYear = Math.floor(minYear / step) * step;
  const buckets = [];

  for (let start = startYear; start <= maxYear; start += step) {
    buckets.push({
      start,
      end: Math.min(start + step - 1, maxYear),
      count: 0,
    });
  }

  entries.forEach((entry) => {
    const index = Math.floor((entry.year - startYear) / step);
    if (buckets[index]) buckets[index].count += 1;
  });

  return buckets.map((bucket) => ({
    ...bucket,
    label: bucket.start === bucket.end ? String(bucket.start) : `${bucket.start}-${bucket.end}`,
  }));
}

function summarizeConnectionEvidence(items, key) {
  const map = new Map();

  items.forEach((claim, index) => {
    const label = claim[key];
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

function countByField(items, field, options = {}) {
  const counts = new Map();
  const studySeen = new Set();

  items.forEach((claim, index) => {
    const value = normalizeValue(claim[field]) || "unknown";
    if (options.uniqueStudies) {
      const key = `${studyKey(claim, index)}|${value}`;
      if (studySeen.has(key)) return;
      studySeen.add(key);
    }
    counts.set(value, (counts.get(value) || 0) + 1);
  });

  return Array.from(counts.entries()).map(([label, count]) => ({ label, count }));
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
  return [...visible, { label: "other", count: otherCount }];
}

function colorForCategory(label, index, field = "") {
  const normalized = normalizeValue(label) || "unknown";
  if (field === "result_direction" && DIRECTION_COLORS[normalized]) return DIRECTION_COLORS[normalized];
  if (field === "system" && SYSTEM_COLORS[normalized]) return SYSTEM_COLORS[normalized];
  return CATEGORY_COLORS[index % CATEGORY_COLORS.length];
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

function trendCardHtml(title, subtitle, body) {
  return `
    <section class="trend-card">
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
    return trendCardHtml("Publications by year", "", '<div class="trend-empty">No publication years available.</div>');
  }

  const width = 280;
  const height = 132;
  const margin = { top: 12, right: 10, bottom: 24, left: 26 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const maxCount = Math.max(1, ...buckets.map((bucket) => bucket.count));
  const step = plotWidth / buckets.length;
  const barWidth = Math.max(3, Math.min(16, step * 0.68));
  const bars = buckets
    .map((bucket, index) => {
      const x = margin.left + index * step + (step - barWidth) / 2;
      const barHeight = (bucket.count / maxCount) * plotHeight;
      const y = margin.top + plotHeight - barHeight;
      return `<rect x="${x.toFixed(2)}" y="${y.toFixed(2)}" width="${barWidth.toFixed(2)}" height="${barHeight.toFixed(2)}" rx="2" fill="${chartFillSoft(
        "#49d6c8"
      )}"><title>${escapeHtml(bucket.label)}: ${bucket.count} studies</title></rect>`;
    })
    .join("");
  const firstLabel = buckets[0].label;
  const lastLabel = buckets[buckets.length - 1].label;

  return trendCardHtml(
    "Publications by year",
    "",
    `
      <svg class="trend-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Publications by publication year">
        <line x1="${margin.left}" y1="${margin.top + plotHeight}" x2="${width - margin.right}" y2="${margin.top + plotHeight}" class="trend-axis-line" />
        <line x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${margin.top + plotHeight}" class="trend-axis-line faint" />
        ${bars}
        <text x="${margin.left}" y="${height - 5}" class="trend-axis-label" text-anchor="start">${escapeHtml(firstLabel)}</text>
        <text x="${width - margin.right}" y="${height - 5}" class="trend-axis-label" text-anchor="end">${escapeHtml(lastLabel)}</text>
        <text x="${margin.left - 6}" y="${margin.top + 8}" class="trend-axis-label" text-anchor="end">${maxCount}</text>
      </svg>
    `
  );
}

function renderHorizontalBarChart(entries, title, subtitle) {
  if (!entries.length) {
    return trendCardHtml(title, subtitle, '<div class="trend-empty">No connected evidence in this selection.</div>');
  }

  const maxStudies = Math.max(1, ...entries.map((entry) => entry.studies));
  const body = `
    <div class="trend-bars">
      ${entries
        .map((entry, index) => {
          const width = Math.max(4, (entry.studies / maxStudies) * 100);
          return `
            <div class="trend-bar-row" style="--bar-width: ${width.toFixed(2)}%">
              <div class="trend-bar-topline">
                <span>${escapeHtml(entry.label)}</span>
                <strong>${formatCompactNumber(entry.studies)}</strong>
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
      return `<span style="width: ${width.toFixed(2)}%; background: ${chartFillSoft(
        colorForCategory(entry.label, index, field)
      )}" title="${escapeHtml(displayFieldLabel(entry.label))}: ${entry.count}"></span>`;
    })
    .join("");
  const legend = entries
    .map(
      (entry, index) => `
        <span class="trend-legend-item">
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

function renderDetailClaimCards(items) {
  if (!items.length) {
    return trendCardHtml("Claim cards", "", '<div class="trend-empty">No claim cards in this selection.</div>');
  }

  const sortedClaims = [...items].sort((a, b) => {
    const yearDiff = (parseYearValue(b.study_year) || 0) - (parseYearValue(a.study_year) || 0);
    if (yearDiff !== 0) return yearDiff;
    return (a.study_title || "").localeCompare(b.study_title || "");
  });

  const rightKey = mode === "mechanistic" ? "target" : "disorder";
  const body = `
    <div class="detail-claim-cards">
      ${sortedClaims
        .map((claim) => {
          const relation = `${claim.compound || "Unknown"} → ${claim[rightKey] || "Unknown"}`;
          const doiHref = doiUrl(claim.study_doi);
          const source = doiHref
            ? `<a href="${doiHref}" target="_blank" rel="noopener noreferrer">${escapeHtml(claim.study_doi)}</a>`
            : claim.openalex_id
            ? `<a href="${openAlexUrl(claim.openalex_id)}" target="_blank" rel="noopener noreferrer">${escapeHtml(claim.openalex_id)}</a>`
            : "";
          const mainLine =
            mode === "mechanistic"
              ? `${claim.affinity_type || "Affinity"} ${claim.affinity_value || ""} ${claim.affinity_unit || ""}`.trim()
              : `${claim.outcome_type || "Outcome"}${claim.outcome_measure ? ` · ${claim.outcome_measure}` : ""}`;
          const contextLine =
            mode === "mechanistic"
              ? `System: ${claim.system || "unknown"} · Species: ${claim.species || "unknown"}`
              : `Direction: ${resultDirectionLabel(claim.result_direction)} · Population: ${claim.population || "unknown"}`;

          return `
            <article class="detail-claim-card">
              <h5>${escapeHtml(relation)}</h5>
              <div class="detail-claim-meta">
                <div>${escapeHtml(mainLine)}</div>
                <div>${escapeHtml(contextLine)}</div>
                <div>${escapeHtml(claim.study_title || "Unknown study")}${claim.study_year ? ` (${escapeHtml(claim.study_year)})` : ""}</div>
                ${source ? `<div>${source}</div>` : ""}
              </div>
              <div class="badge-row">${claimBadgeHtml(claim)}</div>
            </article>
          `;
        })
        .join("")}
    </div>
  `;

  return trendCardHtml("Claim cards", "", body);
}

function renderEdgeDetail(compound, target, edgeClaims) {
  const studies = uniqueStudyCount(edgeClaims);
  setDetailHeader(`${compound} → ${target}`);

  const primaryComposition =
    mode === "disorders"
      ? renderCompositionChart(edgeClaims, "result_direction", "Result direction")
      : renderCompositionChart(edgeClaims, "system", "Experimental system");

  detailBody.innerHTML = `
    <div class="trend-dashboard">
      ${renderTrendStats(edgeClaims)}
      ${renderAnnualPublicationChart(edgeClaims)}
      ${primaryComposition}
      ${renderDetailClaimCards(edgeClaims)}
    </div>
  `;
}

function renderNodeDetail(type, name, nodeClaims) {
  const rightKey = mode === "mechanistic" ? "target" : "disorder";
  const connectionKey = type === "compound" ? rightKey : "compound";
  const connections = summarizeConnectionEvidence(nodeClaims, connectionKey);
  const connectionLabel = type === "compound" ? (mode === "mechanistic" ? "targets" : "indications") : "compounds";

  setDetailHeader(name);

  const composition =
    mode === "disorders"
      ? renderCompositionChart(nodeClaims, "result_direction", "Result direction")
      : renderCompositionChart(nodeClaims, "system", "Experimental system");

  detailBody.innerHTML = `
    <div class="trend-dashboard">
      ${renderTrendStats(nodeClaims, [{ label: "Connections", value: formatCompactNumber(connections.length) }])}
      ${renderAnnualPublicationChart(nodeClaims)}
      ${composition}
      ${renderHorizontalBarChart(connections, displayFieldLabel(connectionLabel), "Ranked by unique studies")}
      ${renderDetailClaimCards(nodeClaims)}
    </div>
  `;
}

function renderOverviewDetail(data) {
  const rightKey = mode === "mechanistic" ? "target" : "disorder";
  const rightLabel = mode === "mechanistic" ? "Targets" : "Indications";
  const compoundEntries = summarizeConnectionEvidence(data, "compound");
  const rightEntries = summarizeConnectionEvidence(data, rightKey);

  setDetailHeader(mode === "mechanistic" ? "All targets" : "All indications");

  if (!data.length) {
    detailBody.innerHTML = '<div class="detail-empty">No claims match the current filters.</div>';
    return;
  }

  const composition =
    mode === "disorders"
      ? renderCompositionChart(data, "result_direction", "Result direction")
      : renderCompositionChart(data, "system", "Experimental system");

  detailBody.innerHTML = `
    <div class="trend-dashboard">
      ${renderTrendStats(data, [
        { label: "Compounds", value: formatCompactNumber(compoundEntries.length) },
        { label: rightLabel, value: formatCompactNumber(rightEntries.length) },
      ])}
      ${renderAnnualPublicationChart(data)}
      ${composition}
      ${renderHorizontalBarChart(compoundEntries, "Compounds", "Ranked by unique studies")}
      ${renderHorizontalBarChart(rightEntries, rightLabel, "Ranked by unique studies")}
    </div>
  `;
}

function renderSelectedDetailFromData(data) {
  if (!selected) return;

  const rightKey = mode === "mechanistic" ? "target" : "disorder";
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

  const rightKey = mode === "mechanistic" ? "target" : "disorder";
  const compoundCounts = new Map();
  const rightCounts = new Map();
  const compoundConnections = new Map();
  const rightConnections = new Map();
  const incidentEdgeKeysByCompound = new Map();
  const incidentEdgeKeysByRight = new Map();

  data.forEach((claim) => {
    const compound = claim.compound;
    const right = claim[rightKey];
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

  const longestLeftLabelPx = Math.max(80, ...compounds.map(estimateLabelWidth));
  const longestRightLabelPx = Math.max(80, ...targets.map(estimateLabelWidth));
  const baseSideMargin = clampNumber(Math.floor(width * 0.18), 110, 220);
  let leftMargin = Math.max(baseSideMargin, longestLeftLabelPx + 28);
  let rightMargin = Math.max(baseSideMargin, longestRightLabelPx + 28);
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
  const leftLabelMaxWidth = Math.max(20, compoundX - labelOffset - 10);
  const rightLabelMaxWidth = Math.max(20, width - (targetX + labelOffset) - 10);

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
    const compound = claim.compound;
    const right = claim[rightKey];
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

    const key = `${claim.compound}|${claim[rightKey]}`;
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
  if (selected) {
    renderSelectedDetailFromData(filtered);
  } else {
    renderOverviewDetail(filtered);
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

function updateModeUI() {
  modeButtons.forEach((btn) => {
    const isActive = btn.dataset.mode === mode;
    btn.classList.toggle("active", isActive);
    btn.setAttribute("aria-selected", isActive ? "true" : "false");
  });
}

function switchMode(nextMode) {
  if (mode === nextMode) return;
  mode = nextMode;
  selected = null;
  isolateSelection = false;
  clearSelectedStyles();
  updateModeUI();
  syncYearFilterControls(activeClaimsForMode());
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

function mechanisticFromPayload(payload) {
  const contributions = Array.isArray(payload?.contributions) ? payload.contributions : [];
  return contributions.map((item) => ({
    compound: item?.resources?.compound || "",
    target: item?.resources?.target || "",
    assay_type: item?.properties?.assay_type || "",
    affinity_type: item?.properties?.affinity_type || "",
    affinity_value: item?.properties?.affinity_value ?? "",
    affinity_unit: item?.properties?.affinity_unit || "",
    species: item?.properties?.species || "",
    system: item?.properties?.system || "",
    study_doi: item?.paper?.doi || "",
    openalex_id: item?.paper?.openalex_id || "",
    study_title: item?.paper?.title || "",
    study_year: item?.paper?.year ?? "",
    authors:
      item?.paper?.authors ??
      item?.paper?.author_list ??
      item?.paper?.author ??
      item?.paper?.first_author ??
      "",
    evidence_level: item?.properties?.evidence_level || "low",
    source: item?.properties?.source || "",
    paper_type: item?.provenance?.paper_type || "",
    source_type: item?.provenance?.source_type || "",
    access_level: item?.provenance?.access_level || "",
    evidence_location: item?.provenance?.evidence_location || "",
    evidence_locator: item?.provenance?.evidence_locator || "",
    study_design: item?.provenance?.study_design || "",
    notes: item?.provenance?.notes || "",
  }));
}

function disorderFromPayload(payload) {
  const contributions = Array.isArray(payload?.contributions) ? payload.contributions : [];
  return contributions.map((item) => ({
    compound: item?.resources?.compound || "",
    disorder: item?.resources?.disorder || "",
    outcome_type: item?.properties?.outcome_type || "",
    result_direction: item?.properties?.result_direction || "",
    outcome_measure: item?.properties?.outcome_measure || "",
    population: item?.properties?.population || "",
    system: item?.properties?.system || "",
    study_doi: item?.paper?.doi || "",
    openalex_id: item?.paper?.openalex_id || "",
    study_title: item?.paper?.title || "",
    study_year: item?.paper?.year ?? "",
    authors:
      item?.paper?.authors ??
      item?.paper?.author_list ??
      item?.paper?.author ??
      item?.paper?.first_author ??
      "",
    evidence_level: item?.properties?.evidence_level || "low",
    source: item?.properties?.source || "",
    paper_type: item?.provenance?.paper_type || "",
    source_type: item?.provenance?.source_type || "",
    access_level: item?.provenance?.access_level || "",
    evidence_location: item?.provenance?.evidence_location || "",
    evidence_locator: item?.provenance?.evidence_locator || "",
    study_design: item?.provenance?.study_design || "",
    notes: item?.provenance?.notes || "",
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

async function init() {
  const loadErrors = [];

  try {
    const { data } = await fetchJsonFromCandidates([
      "../data/curated/claims.json",
      "/data/curated/claims.json",
      "data/curated/claims.json",
    ]);
    claims = Array.isArray(data) ? data : [];
  } catch (primaryErr) {
    loadErrors.push(`mechanistic curated: ${primaryErr.message}`);
    try {
      const { data } = await fetchJsonFromCandidates([
        "../data/processed/graph_payload_mechanistic.json",
        "/data/processed/graph_payload_mechanistic.json",
        "data/processed/graph_payload_mechanistic.json",
      ]);
      claims = mechanisticFromPayload(data);
    } catch (fallbackErr) {
      loadErrors.push(`mechanistic payload fallback: ${fallbackErr.message}`);
      claims = [];
    }
  }

  try {
    const { data } = await fetchJsonFromCandidates([
      "../data/curated/disorder_claims.json",
      "/data/curated/disorder_claims.json",
      "data/curated/disorder_claims.json",
    ]);
    disorderClaims = Array.isArray(data) ? data : [];
  } catch (primaryErr) {
    loadErrors.push(`disorder curated: ${primaryErr.message}`);
    try {
      const { data } = await fetchJsonFromCandidates([
        "../data/processed/graph_payload_disorder.json",
        "/data/processed/graph_payload_disorder.json",
        "data/processed/graph_payload_disorder.json",
      ]);
      disorderClaims = disorderFromPayload(data);
    } catch (fallbackErr) {
      loadErrors.push(`disorder payload fallback: ${fallbackErr.message}`);
      disorderClaims = [];
    }
  }

  if (!claims.length && !disorderClaims.length) {
    renderLoadError(loadErrors);
    return;
  }

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
window.addEventListener("resize", scheduleRender);

init();
