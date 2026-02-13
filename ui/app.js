const graphEl = document.getElementById("graph");
const cardsEl = document.getElementById("cards");
const yearMinFilter = document.getElementById("yearMinFilter");
const yearMaxFilter = document.getElementById("yearMaxFilter");
const yearStepButtons = document.querySelectorAll(".year-step");
const searchInput = document.getElementById("searchInput");
const bibliographySearchInput = document.getElementById("bibliographySearchInput");
const tooltip = document.getElementById("tooltip");
const detailTitle = document.querySelector("#graphDetail h3");
const detailSubtitle = document.querySelector("#graphDetail p");
const detailBody = document.getElementById("detailBody");
const clearSelectionBtn = document.getElementById("clearSelection");
const modeButtons = document.querySelectorAll("[data-mode]");
const rightStatLabel = document.getElementById("rightStatLabel");
const graphTitle = document.querySelector(".graph-panel h2");
const graphSubtitle = document.querySelector(".graph-panel p");
const evidenceLegend = document.getElementById("evidenceLegend");
const evidenceInfoPopover = document.getElementById("evidenceInfoPopover");
const evidenceInfoTitle = document.getElementById("evidenceInfoTitle");
const evidenceInfoBody = document.getElementById("evidenceInfoBody");
const evidenceInfoClose = document.getElementById("evidenceInfoClose");
const studiesStatCard = document.getElementById("studiesStatCard");
const bibliographyPanel = document.getElementById("bibliographyPanel");
const studyListEl = document.getElementById("studyList");

const stats = {
  compounds: document.querySelector('[data-stat="compounds"]'),
  targets: document.querySelector('[data-stat="targets"]'),
  claims: document.querySelector('[data-stat="claims"]'),
  studies: document.querySelector('[data-stat="studies"]'),
};

const evidenceRank = { low: 1, medium: 2, high: 3 };
const MAX_GRAPH_EDGES = 500;
const MAX_CARDS_RENDER = 250;
const MAX_BIBLIOGRAPHY_RENDER = 300;

let claims = [];
let disorderClaims = [];
let selected = null;
let isolateSelection = false;
let mode = "disorders";
let renderScheduled = false;
let evidencePopoverLevel = "";
const yearFilterState = {
  mechanistic: { min: "", max: "" },
  disorders: { min: "", max: "" },
};

const defaultDetail = {
  title: "Graph Detail",
  subtitle: "Hover or click a node or edge to inspect evidence.",
};

const evidenceExplainers = {
  high: {
    title: "High evidence",
    bullets: [
      "Assigned when study design is randomized controlled trial or phase 3 trial.",
    ],
  },
  medium: {
    title: "Medium evidence",
    bullets: [
      "Assigned for review/meta-analysis source types.",
      "Also assigned for phase 2, open-label, or pilot trial designs.",
    ],
  },
  low: {
    title: "Low evidence",
    bullets: [
      "Used for case report/retrospective signals or when stronger criteria are missing.",
      "Rows start low by default before stronger design/source signals are found.",
    ],
  },
};

function normalizeValue(value) {
  return (value || "").toString().trim().toLowerCase();
}

function unique(values) {
  return Array.from(new Set(values)).sort();
}

function activeClaimsForMode() {
  return mode === "mechanistic" ? claims : disorderClaims;
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

function maxEvidenceLevel(items) {
  if (!items.length) return "low";
  let max = "low";
  let maxRank = 0;
  items.forEach((item) => {
    const rank = evidenceRank[item.evidence_level] || 1;
    if (rank > maxRank) {
      maxRank = rank;
      max = item.evidence_level;
    }
  });
  return max || "low";
}

function badgeHtml(level) {
  const safe = evidenceClass(level);
  return `<span class="badge ${safe}">${level || "low"} evidence</span>`;
}

function setDetailHeader(title, subtitle) {
  detailTitle.textContent = title;
  detailSubtitle.textContent = subtitle;
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
  setDetailHeader(defaultDetail.title, defaultDetail.subtitle);
  renderDetailEmpty();
  hideTooltip();
  scheduleRender();
}

function showTooltip(content, event) {
  tooltip.innerHTML = content;
  tooltip.style.left = `${event.clientX + 12}px`;
  tooltip.style.top = `${event.clientY + 12}px`;
  tooltip.style.opacity = "1";
  tooltip.style.transform = "translateY(0)";
}

function moveTooltip(event) {
  tooltip.style.left = `${event.clientX + 12}px`;
  tooltip.style.top = `${event.clientY + 12}px`;
}

function hideTooltip() {
  tooltip.style.opacity = "0";
  tooltip.style.transform = "translateY(6px)";
}

function closeEvidencePopover() {
  if (!evidenceInfoPopover) return;
  evidenceInfoPopover.classList.remove("open");
  evidenceInfoPopover.setAttribute("aria-hidden", "true");
  evidencePopoverLevel = "";
}

function openEvidencePopover(level, anchorEl) {
  if (!evidenceInfoPopover || !evidenceInfoTitle || !evidenceInfoBody || !anchorEl) return;

  const key = normalizeValue(level);
  const explainer = evidenceExplainers[key] || evidenceExplainers.low;
  evidenceInfoTitle.textContent = explainer.title;
  evidenceInfoBody.innerHTML = explainer.bullets.map((item) => `<div>• ${item}</div>`).join("");

  const panel = graphEl.closest(".graph-panel");
  if (!panel) return;

  evidenceInfoPopover.classList.add("open");
  evidenceInfoPopover.setAttribute("aria-hidden", "false");

  const panelRect = panel.getBoundingClientRect();
  const anchorRect = anchorEl.getBoundingClientRect();
  const popoverRect = evidenceInfoPopover.getBoundingClientRect();
  const pad = 12;

  let left = anchorRect.left - panelRect.left + anchorRect.width / 2 - popoverRect.width / 2;
  left = clampNumber(left, pad, Math.max(pad, panel.clientWidth - popoverRect.width - pad));

  let top = anchorRect.bottom - panelRect.top + 10;
  if (top + popoverRect.height > panel.clientHeight - pad) {
    top = anchorRect.top - panelRect.top - popoverRect.height - 10;
  }
  top = clampNumber(top, pad, Math.max(pad, panel.clientHeight - popoverRect.height - pad));

  evidenceInfoPopover.style.left = `${left}px`;
  evidenceInfoPopover.style.top = `${top}px`;
  evidencePopoverLevel = key;
}

function openAlexUrl(openalexId) {
  const id = (openalexId || "").toString().trim();
  if (!id) return "";
  if (id.startsWith("http://") || id.startsWith("https://")) return id;
  return `https://openalex.org/${id}`;
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

function updateStats(data) {
  stats.compounds.textContent = unique(data.map((c) => c.compound)).length;
  const rightKey = mode === "mechanistic" ? "target" : "disorder";
  stats.targets.textContent = unique(data.map((c) => c[rightKey])).length;
  stats.claims.textContent = data.length;
  stats.studies.textContent = unique(data.map((c) => c.study_doi || c.openalex_id)).length;
}

function applyFilters() {
  const rightKey = mode === "mechanistic" ? "target" : "disorder";
  const activeClaims = activeClaimsForMode();
  const yearRange = activeYearRange(activeClaims);

  const baseFiltered = activeClaims.filter((claim) => {
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

function evidenceClass(level) {
  return level ? level.toLowerCase() : "low";
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

    const badge = `<span class="badge ${evidenceClass(claim.evidence_level)}">${
      claim.evidence_level || "low"
    } evidence</span>`;

    const source = claim.study_doi
      ? `DOI: ${claim.study_doi}`
      : claim.openalex_id
      ? `OpenAlex: ${claim.openalex_id}`
      : "";

    const relation = mode === "mechanistic" ? `${claim.compound} → ${claim.target}` : `${claim.compound} → ${claim.disorder}`;
    const authors = claimAuthors(claim);

    const outcomeLine =
      mode === "disorders"
        ? `<div>Outcome: ${claim.outcome_type || "reported"}${claim.outcome_measure ? ` • ${claim.outcome_measure}` : ""}</div>`
        : "";

    card.innerHTML = `
      <div>
        <h3>${relation}</h3>
        ${badge}
      </div>
      <div class="meta">
        ${
          mode === "mechanistic"
            ? `<div><strong>${claim.affinity_type}</strong>: ${claim.affinity_value} ${claim.affinity_unit}</div>
        <div>Assay: ${claim.assay_type}</div>`
            : outcomeLine
        }
        <div>System: ${claim.system || "unknown"}</div>
        <div>${mode === "mechanistic" ? `Species: ${claim.species || "unknown"}` : `Population: ${claim.population || "unknown"}`}</div>
        <div>Study: ${claim.study_title || ""} (${claim.study_year || ""})</div>
        <div>Authors: ${authors || "not available"}</div>
        <div>${source}</div>
      </div>
      <div class="meta">${claim.notes || ""}</div>
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
      maxEvidence: "low",
      maxRank: 1,
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

    const rank = evidenceRank[claim.evidence_level] || 1;
    if (rank > existing.maxRank) {
      existing.maxRank = rank;
      existing.maxEvidence = claim.evidence_level || "low";
    }
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
            ${badgeHtml(entry.maxEvidence)}
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
    const entry = map.get(label) || { count: 0, maxEvidence: "low", rank: 0 };
    entry.count += 1;
    const rank = evidenceRank[item.evidence_level] || 1;
    if (rank > entry.rank) {
      entry.rank = rank;
      entry.maxEvidence = item.evidence_level;
    }
    map.set(label, entry);
  });
  return Array.from(map.entries())
    .map(([label, entry]) => ({ label, ...entry }))
    .sort((a, b) => b.count - a.count);
}

function renderEdgeDetail(compound, target, edgeClaims) {
  const studies = countStudies(edgeClaims);
  const maxEvidence = maxEvidenceLevel(edgeClaims);
  setDetailHeader(`${compound} → ${target}`, `${edgeClaims.length} claims across ${studies} studies`);

  const sortedClaims = [...edgeClaims].sort((a, b) => {
    const evidenceDiff = (evidenceRank[b.evidence_level] || 1) - (evidenceRank[a.evidence_level] || 1);
    if (evidenceDiff !== 0) return evidenceDiff;
    return (b.study_year || 0) - (a.study_year || 0);
  });

  const list = sortedClaims
    .map(
      (claim) => `
      <div class="detail-item">
        <h4>${
          mode === "mechanistic"
            ? `${claim.affinity_type} ${claim.affinity_value} ${claim.affinity_unit}`
            : `${claim.outcome_type || "Outcome"}`
        }</h4>
        <div class="meta">${
          mode === "mechanistic"
            ? `Assay: ${claim.assay_type}`
            : `Measure: ${claim.outcome_measure || "reported"}`
        }</div>
        <div class="meta">${
          mode === "mechanistic"
            ? `System: ${claim.system || "unknown"} • Species: ${claim.species || "unknown"}`
            : `Population: ${claim.population || "unknown"} • System: ${claim.system || "unknown"}`
        }</div>
        <div class="meta">Study: ${claim.study_title || "Unknown"} (${claim.study_year || ""})</div>
        <div class="meta">${claim.study_doi ? `DOI: ${claim.study_doi}` : claim.openalex_id ? `OpenAlex: ${claim.openalex_id}` : ""}</div>
        ${badgeHtml(claim.evidence_level)}
      </div>
    `
    )
    .join("");

  detailBody.innerHTML = `
    <div class="detail-stat"><span>Highest evidence</span><strong>${maxEvidence}</strong></div>
    <div class="detail-stat"><span>Claims</span><strong>${edgeClaims.length}</strong></div>
    <div class="detail-stat"><span>Studies</span><strong>${studies}</strong></div>
    <div class="detail-list">${list}</div>
  `;
}

function renderNodeDetail(type, name, nodeClaims) {
  const studies = countStudies(nodeClaims);
  const maxEvidence = maxEvidenceLevel(nodeClaims);
  const rightKey = mode === "mechanistic" ? "target" : "disorder";
  const connectionKey = type === "compound" ? rightKey : "compound";
  const rightTypeLabel = mode === "mechanistic" ? "Target" : "Indication";
  const connections = summarizeConnections(nodeClaims, connectionKey);

  setDetailHeader(
    `${name} (${type === "compound" ? "Compound" : rightTypeLabel})`,
    `${nodeClaims.length} claims across ${connections.length} ${connectionKey}s`
  );

  const list = connections
    .slice(0, 8)
    .map(
      (entry) => `
      <div class="detail-item">
        <h4>${entry.label}</h4>
        <div class="meta">Claims: ${entry.count}</div>
        <div class="meta">Max evidence: ${entry.maxEvidence}</div>
      </div>
    `
    )
    .join("");

  detailBody.innerHTML = `
    <div class="detail-stat"><span>Highest evidence</span><strong>${maxEvidence}</strong></div>
    <div class="detail-stat"><span>Claims</span><strong>${nodeClaims.length}</strong></div>
    <div class="detail-stat"><span>Studies</span><strong>${studies}</strong></div>
    <div class="detail-list">${list || "<div class=\"detail-empty\">No connected claims.</div>"}</div>
  `;
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
    const byDegree = (compoundConnections.get(b)?.size || 0) - (compoundConnections.get(a)?.size || 0);
    if (byDegree !== 0) return byDegree;
    const byClaims = (compoundCounts.get(b) || 0) - (compoundCounts.get(a) || 0);
    if (byClaims !== 0) return byClaims;
    return a.localeCompare(b);
  });

  const targets = Array.from(rightCounts.keys()).sort((a, b) => {
    const byDegree = (rightConnections.get(b)?.size || 0) - (rightConnections.get(a)?.size || 0);
    if (byDegree !== 0) return byDegree;
    const byClaims = (rightCounts.get(b) || 0) - (rightCounts.get(a) || 0);
    if (byClaims !== 0) return byClaims;
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
  const leftLabelMaxWidth = Math.max(20, compoundX - 20);
  const rightLabelMaxWidth = Math.max(20, width - targetX - 20);

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
      maxEvidence: "low",
      rank: 0,
      claims: [],
    };
    const rank = evidenceRank[claim.evidence_level] || 1;
    existing.count += 1;
    existing.claims.push(claim);
    if (rank > existing.rank) {
      existing.rank = rank;
      existing.maxEvidence = claim.evidence_level;
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

  edgeEntries.forEach(([key, edge]) => {
    const [compound, target] = key.split("|");
    const cPos = compoundPositions.get(compound);
    const tPos = targetPositions.get(target);
    if (!cPos || !tPos) return;

    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    const midX = (cPos.x + tPos.x) / 2;
    const curve = 80;
    const d = `M ${cPos.x} ${cPos.y} C ${midX - curve} ${cPos.y}, ${midX + curve} ${tPos.y}, ${tPos.x} ${tPos.y}`;
    path.setAttribute("d", d);
    path.setAttribute("class", `edge ${edge.maxEvidence || "low"}`);
    const edgeWidth = edgeWidthForCount(edge.count, maxEdgeCount);
    path.style.setProperty("--edge-width", `${edgeWidth.toFixed(2)}px`);
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
        `<strong>${compound} → ${target}</strong><br/>Claims: ${edge.count}<br/>Max evidence: ${edge.maxEvidence}`,
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
    setDetailHeader(defaultDetail.title, defaultDetail.subtitle);
    renderDetailEmpty();
  }
  updateStats(filtered);
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
  if (mode === "mechanistic") {
    rightStatLabel.textContent = "Targets";
    graphTitle.textContent = "Targets Graph";
    graphSubtitle.textContent = "Compound-target links.";
  } else {
    rightStatLabel.textContent = "Indications";
    graphTitle.textContent = "Indications Graph";
    graphSubtitle.textContent = "Compound-indication links.";
  }

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
  setDetailHeader(defaultDetail.title, defaultDetail.subtitle);
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
    source_type: item?.provenance?.source_type || "",
    access_level: item?.provenance?.access_level || "",
    evidence_location: item?.provenance?.evidence_location || "",
    evidence_locator: item?.provenance?.evidence_locator || "",
    study_design: item?.provenance?.study_design || "",
    notes: item?.provenance?.notes || "",
  }));
}

function renderLoadError(messages) {
  setDetailHeader("Data Load Error", "Unable to read local dataset files.");
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
        "../data/processed/orkg_payload_mechanistic.json",
        "/data/processed/orkg_payload_mechanistic.json",
        "data/processed/orkg_payload_mechanistic.json",
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
        "../data/processed/orkg_payload_disorder.json",
        "/data/processed/orkg_payload_disorder.json",
        "data/processed/orkg_payload_disorder.json",
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
  setDetailHeader(defaultDetail.title, defaultDetail.subtitle);
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
clearSelectionBtn.addEventListener("click", clearSelection);
if (evidenceLegend) {
  evidenceLegend.querySelectorAll(".evidence-chip").forEach((chip) => {
    const level = chip.dataset.evidence || "low";
    const details = evidenceExplainers[normalizeValue(level)] || evidenceExplainers.low;
    chip.setAttribute("title", details.title);
    chip.setAttribute("aria-label", `${details.title}: click for details`);
    chip.addEventListener("click", (event) => {
      event.stopPropagation();
      const chipLevel = normalizeValue(chip.dataset.evidence || "");
      if (evidenceInfoPopover?.classList.contains("open") && evidencePopoverLevel === chipLevel) {
        closeEvidencePopover();
      } else {
        openEvidencePopover(chipLevel, chip);
      }
    });
    chip.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        chip.click();
      }
    });
  });
}
if (evidenceInfoClose) {
  evidenceInfoClose.addEventListener("click", closeEvidencePopover);
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
window.addEventListener("resize", closeEvidencePopover);
document.addEventListener("click", (event) => {
  if (!evidenceInfoPopover?.classList.contains("open")) return;
  const target = event.target;
  if (target instanceof Element) {
    if (evidenceInfoPopover.contains(target) || target.closest(".evidence-chip")) return;
  }
  closeEvidencePopover();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeEvidencePopover();
  }
});

init();
