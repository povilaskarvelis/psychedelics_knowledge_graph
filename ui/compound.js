const compoundPage = document.body;
const compoundDataUrl = compoundPage?.dataset.compoundData || "";
const areaButtons = Array.from(document.querySelectorAll("[data-area-toggle]"));
const conceptButtons = Array.from(document.querySelectorAll("[data-concept-index]"));
const showMoreButtons = Array.from(document.querySelectorAll("[data-show-more]"));
const graphSourceButtons = Array.from(document.querySelectorAll("[data-compound-graph-source]"));
const viewButtons = Array.from(document.querySelectorAll("[data-compound-view]"));
const literatureHeading = document.getElementById("compoundLiteratureHeading");
const literatureContext = document.getElementById("compoundLiteratureContext");
const paperList = document.getElementById("compoundPaperList");
const paperMore = document.getElementById("compoundPaperMore");
const compoundGraph = document.getElementById("compoundGraph");
const compoundGraphTooltip = document.getElementById("compoundGraphTooltip");
const compoundAreasHeading = document.getElementById("compoundAreasHeading");
const compoundAreasDescription = document.getElementById("compoundAreasDescription");
const compoundCoverageChart = document.getElementById("compoundCoverageChart");
const compoundTimelineChart = document.getElementById("compoundTimelineChart");
const compoundTimelineContext = document.getElementById("compoundTimelineContext");
const compoundEntityChart = document.getElementById("compoundEntityChart");
const compoundEntityContext = document.getElementById("compoundEntityContext");
const compoundOverlapChart = document.getElementById("compoundOverlapChart");
const compoundChartTooltip = document.getElementById("compoundChartTooltip");

const SOURCE_ORDER = ["primary", "meta_analyses", "reviews"];
const INITIAL_PAPER_LIMIT = 12;
const GRAPH_MAX_CONCEPTS = 12;
const GRAPH_WIDTH = 920;
const GRAPH_HEIGHT = 640;
const TIMELINE_WIDTH = 760;
const TIMELINE_HEIGHT = 252;
const OVERLAP_WIDTH = 760;
const OVERLAP_HEIGHT = 640;
const ENTITY_INITIAL_LIMIT = 10;
const ENTITY_EXPANSION_STEP = 10;
const SVG_NAMESPACE = "http://www.w3.org/2000/svg";
const CATEGORY_COLORS = {
  conditions: "#708aa7",
  safety: "#b89a5b",
  cognition_behavior: "#a96f7e",
  subjective_effects: "#69a196",
  treatment_context: "#b98278",
  real_world: "#7e72a1",
  brain: "#9f9872",
  molecular_effects: "#719d96",
  targets: "#9c8670",
  pharmacokinetics: "#70819a",
};

let compoundData = null;
let selectedCategory = null;
let selectedConcept = null;
let selectedGraphCategoryKey = "conditions";
let activeSource = "primary";
let graphSource = "primary";
let compoundView = "map";
let visiblePaperCount = INITIAL_PAPER_LIMIT;
let selectedPaperIds = null;
let chartSelection = { type: "area", categoryKey: "conditions" };
let selectedChartConcept = null;
let visibleEntityCount = ENTITY_INITIAL_LIMIT;

function sourceLabel(source) {
  return compoundData?.source_labels?.[source] || source;
}

function openArea(areaKey, updateHash = true) {
  areaButtons.forEach((button) => {
    const isOpen = button.dataset.areaToggle === areaKey;
    const area = button.closest(".compound-area");
    const detail = area?.querySelector(".compound-area-detail");
    button.setAttribute("aria-expanded", isOpen ? "true" : "false");
    area?.classList.toggle("is-open", isOpen);
    if (detail) detail.hidden = !isOpen;
  });
  if (updateHash) {
    const url = new URL(window.location.href);
    url.hash = areaKey;
    window.history.replaceState(null, "", url);
  }
}

function paperMetaText(paper) {
  return [paper.authors, paper.journal, paper.year].filter(Boolean).join(" · ");
}

function paperListItem(paper) {
  const item = document.createElement("li");
  item.className = "compound-paper";

  const title = paper.url ? document.createElement("a") : document.createElement("span");
  title.className = "compound-paper-title";
  title.textContent = paper.title;
  if (paper.url) {
    title.href = paper.url;
    title.target = "_blank";
    title.rel = "noopener noreferrer";
  }
  item.appendChild(title);

  const metaText = paperMetaText(paper);
  if (metaText) {
    const meta = document.createElement("span");
    meta.className = "compound-paper-meta";
    meta.textContent = metaText;
    item.appendChild(meta);
  }
  return item;
}

function renderPapers() {
  if (!paperList || !paperMore || !compoundData) return;
  const paperIds =
    selectedPaperIds ??
    selectedConcept?.sources?.[activeSource]?.paper_ids ??
    [];
  if (selectedPaperIds === null && !selectedConcept) return;
  const visibleIds = paperIds.slice(0, visiblePaperCount);
  paperList.replaceChildren();

  if (!visibleIds.length) {
    const empty = document.createElement("li");
    empty.className = "compound-paper-empty";
    empty.textContent = `No ${sourceLabel(activeSource).toLowerCase()} are connected to this selection in the current release.`;
    paperList.appendChild(empty);
  } else {
    visibleIds.forEach((paperId) => {
      const paper = compoundData.papers?.[paperId];
      if (paper) paperList.appendChild(paperListItem(paper));
    });
  }

  const remaining = Math.max(0, paperIds.length - visibleIds.length);
  paperMore.hidden = remaining === 0;
  paperMore.textContent = remaining ? `Show ${Math.min(remaining, INITIAL_PAPER_LIMIT)} more` : "";
}

function setActiveSource(source) {
  activeSource = source;
  visiblePaperCount = INITIAL_PAPER_LIMIT;
  if (selectedCategory && selectedConcept && selectedPaperIds === null && literatureContext) {
    const sourceCount = Number(selectedConcept.sources?.[source]?.studies || 0);
    literatureContext.textContent = `${selectedCategory.label} · ${sourceLabel(source)} · ${sourceCount} unique source papers`;
  }
  renderPapers();
}

function resetLiterature() {
  selectedCategory = null;
  selectedConcept = null;
  selectedPaperIds = null;
  conceptButtons.forEach((button) => button.classList.remove("is-selected"));
  if (literatureHeading) literatureHeading.textContent = "Literature";
  if (literatureContext) {
    literatureContext.textContent = "Select a concept to see the publications connected to it.";
  }
  paperList?.replaceChildren();
  if (paperMore) paperMore.hidden = true;
}

function selectConcept(categoryKey, conceptIndex, preferredSource = "") {
  if (!compoundData) return;
  const category = compoundData.categories.find((item) => item.key === categoryKey);
  const concept = category?.concepts?.[conceptIndex];
  if (!category || !concept) return;

  selectedCategory = category;
  selectedConcept = concept;
  selectedPaperIds = null;
  selectedGraphCategoryKey = category.key;
  chartSelection = { type: "area", categoryKey: category.key };
  conceptButtons.forEach((button) => {
    const isSelected =
      button.dataset.categoryKey === categoryKey &&
      Number(button.dataset.conceptIndex || 0) === conceptIndex;
    button.classList.toggle("is-selected", isSelected);
  });
  if (literatureHeading) literatureHeading.textContent = concept.label;
  const availableSource =
    SOURCE_ORDER.find((source) => Number(concept.sources?.[source]?.studies || 0) > 0) || "primary";
  const preferredOrGlobalSource = preferredSource || graphSource;
  const requestedSource =
    preferredOrGlobalSource &&
    Number(concept.sources?.[preferredOrGlobalSource]?.studies || 0) > 0
      ? preferredOrGlobalSource
      : "";
  const nextSource =
    requestedSource ||
    (Number(concept.sources?.[activeSource]?.studies || 0) > 0 ? activeSource : availableSource);
  setActiveSource(nextSource);
  renderCompoundGraph();
}

function svgElement(tag, attributes = {}) {
  const element = document.createElementNS(SVG_NAMESPACE, tag);
  Object.entries(attributes).forEach(([name, value]) => {
    element.setAttribute(name, String(value));
  });
  return element;
}

function labelLines(label, maxCharacters = 28) {
  if (label.length <= maxCharacters) return [label];
  const words = label.split(/\s+/);
  let first = "";
  let second = "";
  words.forEach((word) => {
    if (!second && `${first} ${word}`.trim().length <= maxCharacters) {
      first = `${first} ${word}`.trim();
    } else {
      second = `${second} ${word}`.trim();
    }
  });
  if (!second) return [first];
  if (second.length > maxCharacters + 6) {
    second = `${second.slice(0, maxCharacters + 3).trimEnd()}…`;
  }
  return [first, second];
}

function appendSvgLabel(parent, label, x, y, className, maxCharacters = 28) {
  const text = svgElement("text", {
    x,
    y,
    class: className,
  });
  const lines = labelLines(label, maxCharacters);
  lines.forEach((line, index) => {
    const tspan = svgElement("tspan", {
      x,
      dy: index === 0 ? (lines.length === 1 ? "0.34em" : "-0.08em") : "1.12em",
    });
    tspan.textContent = line;
    text.appendChild(tspan);
  });
  parent.appendChild(text);
}

function curvedPath(startX, startY, endX, endY) {
  const span = Math.max(0, endX - startX);
  const offset = span * 0.42;
  return `M ${startX} ${startY} C ${startX + offset} ${startY}, ${endX - offset} ${endY}, ${endX} ${endY}`;
}

function graphCount(item, source = graphSource) {
  return Number(item?.sources?.[source]?.studies || 0);
}

function graphFindingCount(item, source = graphSource) {
  return Number(item?.sources?.[source]?.findings || 0);
}

function showGraphTooltip(event, text) {
  if (!compoundGraphTooltip || !compoundGraph) return;
  compoundGraphTooltip.textContent = text;
  compoundGraphTooltip.hidden = false;
  const graphBounds = compoundGraph.getBoundingClientRect();
  const x = Math.max(10, Math.min(graphBounds.width - 250, event.clientX - graphBounds.left + 14));
  const y = Math.max(10, Math.min(graphBounds.height - 90, event.clientY - graphBounds.top + 14));
  compoundGraphTooltip.style.left = `${x}px`;
  compoundGraphTooltip.style.top = `${y}px`;
}

function showFocusedGraphTooltip(element, text) {
  if (!compoundGraphTooltip || !compoundGraph) return;
  const graphBounds = compoundGraph.getBoundingClientRect();
  const elementBounds = element.getBoundingClientRect();
  showGraphTooltip(
    {
      clientX: elementBounds.right,
      clientY: elementBounds.top + elementBounds.height / 2,
    },
    text
  );
  compoundGraphTooltip.style.left = `${Math.min(
    graphBounds.width - 250,
    elementBounds.right - graphBounds.left + 12
  )}px`;
}

function hideGraphTooltip() {
  if (compoundGraphTooltip) compoundGraphTooltip.hidden = true;
}

function bindGraphNode(element, tooltipText, activate) {
  element.setAttribute("role", "button");
  element.setAttribute("tabindex", "0");
  element.setAttribute("aria-label", tooltipText.replace(/\n/g, ". "));
  element.addEventListener("mouseenter", (event) => showGraphTooltip(event, tooltipText));
  element.addEventListener("mousemove", (event) => showGraphTooltip(event, tooltipText));
  element.addEventListener("mouseleave", hideGraphTooltip);
  element.addEventListener("focus", () => showFocusedGraphTooltip(element, tooltipText));
  element.addEventListener("blur", hideGraphTooltip);
  element.addEventListener("click", activate);
  element.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    activate();
  });
}

function categoryForKey(categoryKey) {
  return compoundData?.categories?.find((category) => category.key === categoryKey) || null;
}

function uniquePaperIds(paperIds) {
  return Array.from(new Set(paperIds.filter(Boolean)));
}

function sortPaperIds(paperIds) {
  return uniquePaperIds(paperIds).sort((a, b) => {
    const paperA = compoundData?.papers?.[a] || {};
    const paperB = compoundData?.papers?.[b] || {};
    const byYear = Number(paperB.year || 0) - Number(paperA.year || 0);
    if (byYear) return byYear;
    return String(paperA.title || "").localeCompare(String(paperB.title || ""));
  });
}

function categoryPaperIds(category, source = graphSource) {
  return uniquePaperIds(
    (category?.concepts || []).flatMap(
      (concept) => concept.sources?.[source]?.paper_ids || []
    )
  );
}

function compoundPaperIds(source = graphSource) {
  return Object.values(compoundData?.papers || {})
    .filter((paper) => paper.source === source)
    .map((paper) => paper.id);
}

function intersectPaperIds(firstIds, secondIds) {
  const secondSet = new Set(secondIds);
  return firstIds.filter((paperId) => secondSet.has(paperId));
}

function baseChartSelection(selection = chartSelection) {
  return {
    type: selection.otherCategoryKey ? "overlap" : "area",
    categoryKey: selection.categoryKey || selectedGraphCategoryKey,
    ...(selection.otherCategoryKey
      ? { otherCategoryKey: selection.otherCategoryKey }
      : {}),
  };
}

function chartSelectionPaperIds(selection = chartSelection, includeYear = true) {
  const category = categoryForKey(selection.categoryKey);
  let paperIds = categoryPaperIds(category);
  if (selection.otherCategoryKey) {
    const otherCategory = categoryForKey(selection.otherCategoryKey);
    paperIds = intersectPaperIds(paperIds, categoryPaperIds(otherCategory));
  }
  if (includeYear && selection.type === "year") {
    paperIds = paperIds.filter((paperId) => {
      const year = Number(compoundData?.papers?.[paperId]?.year || 0);
      return year >= selection.start && year <= selection.end;
    });
  }
  return sortPaperIds(paperIds);
}

function chartSelectionLabel(selection = chartSelection, includeYear = true) {
  const category = categoryForKey(selection.categoryKey);
  const otherCategory = categoryForKey(selection.otherCategoryKey);
  const baseLabel = otherCategory
    ? `${category?.label || "Research area"} × ${otherCategory.label}`
    : category?.label || "Research area";
  if (includeYear && selection.type === "year") {
    return `${baseLabel} · ${selection.label}`;
  }
  return baseLabel;
}

function showPaperSelection(label, paperIds, source = graphSource, selectionContext = "") {
  selectedCategory = null;
  selectedConcept = null;
  selectedPaperIds = sortPaperIds(paperIds);
  conceptButtons.forEach((button) => button.classList.remove("is-selected"));
  if (literatureHeading) literatureHeading.textContent = label;
  if (literatureContext) {
    literatureContext.textContent = [
      selectionContext,
      sourceLabel(source),
      `${selectedPaperIds.length} unique source papers`,
    ]
      .filter(Boolean)
      .join(" · ");
  }
  if (sourceToggle) sourceToggle.hidden = true;
  setActiveSource(source);
}

function renderChartLiteratureSelection() {
  showPaperSelection(chartSelectionLabel(), chartSelectionPaperIds(), graphSource);
}

function chartTooltipContainer() {
  return compoundChartTooltip?.closest(".compound-chart-view") || null;
}

function showChartTooltip(event, text) {
  const container = chartTooltipContainer();
  if (!compoundChartTooltip || !container) return;
  compoundChartTooltip.textContent = text;
  compoundChartTooltip.hidden = false;
  const bounds = container.getBoundingClientRect();
  const x = Math.max(10, Math.min(bounds.width - 250, event.clientX - bounds.left + 14));
  const y = Math.max(10, Math.min(bounds.height - 92, event.clientY - bounds.top + 14));
  compoundChartTooltip.style.left = `${x}px`;
  compoundChartTooltip.style.top = `${y}px`;
}

function showFocusedChartTooltip(element, text) {
  const bounds = element.getBoundingClientRect();
  showChartTooltip(
    {
      clientX: bounds.right,
      clientY: bounds.top + bounds.height / 2,
    },
    text
  );
}

function hideChartTooltip() {
  if (compoundChartTooltip) compoundChartTooltip.hidden = true;
}

function bindChartTarget(element, tooltipText, activate) {
  element.setAttribute("aria-label", tooltipText.replace(/\n/g, ". "));
  element.addEventListener("mouseenter", (event) => showChartTooltip(event, tooltipText));
  element.addEventListener("mousemove", (event) => showChartTooltip(event, tooltipText));
  element.addEventListener("mouseleave", hideChartTooltip);
  element.addEventListener("focus", () => showFocusedChartTooltip(element, tooltipText));
  element.addEventListener("blur", hideChartTooltip);
  element.addEventListener("click", activate);
  if (element.namespaceURI === SVG_NAMESPACE) {
    element.setAttribute("role", "button");
    element.setAttribute("tabindex", "0");
    element.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      activate();
    });
  }
}

function setChartSelection(nextSelection) {
  chartSelection = nextSelection;
  selectedChartConcept = null;
  visibleEntityCount = ENTITY_INITIAL_LIMIT;
  selectedGraphCategoryKey = nextSelection.categoryKey || selectedGraphCategoryKey;
  openArea(selectedGraphCategoryKey);
  renderCompoundCharts();
  renderChartLiteratureSelection();
}

function renderCoverageChart() {
  if (!compoundCoverageChart || !compoundData) return;
  compoundCoverageChart.replaceChildren();
  const entries = compoundData.categories
    .map((category) => ({
      category,
      count: categoryPaperIds(category).length,
      findings: graphFindingCount(category),
    }))
    .sort((a, b) => b.count - a.count || a.category.label.localeCompare(b.category.label));
  const maxCount = Math.max(...entries.map((entry) => entry.count), 1);
  const selectedKeys = new Set(
    [chartSelection.categoryKey, chartSelection.otherCategoryKey].filter(Boolean)
  );

  entries.forEach(({ category, count, findings }) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "compound-coverage-row";
    button.classList.toggle("is-selected", selectedKeys.has(category.key));
    button.disabled = count === 0;
    button.setAttribute("aria-pressed", selectedKeys.has(category.key) ? "true" : "false");
    button.style.setProperty("--coverage-width", `${(count / maxCount) * 100}%`);
    button.style.setProperty("--coverage-color", CATEGORY_COLORS[category.key] || "#719d96");

    const topline = document.createElement("span");
    topline.className = "compound-coverage-topline";
    const label = document.createElement("span");
    label.textContent = category.label;
    const value = document.createElement("strong");
    value.textContent = String(count);
    topline.append(label, value);

    const track = document.createElement("span");
    track.className = "compound-coverage-track";
    track.appendChild(document.createElement("i"));
    button.append(topline, track);

    const tooltipText = `${category.label}\n${count} ${sourceLabel(graphSource).toLowerCase()}\n${findings} findings`;
    bindChartTarget(button, tooltipText, () => {
      if (!button.disabled) {
        setChartSelection({ type: "area", categoryKey: category.key });
      }
    });
    compoundCoverageChart.appendChild(button);
  });
}

function renderEntityChart() {
  if (!compoundEntityChart || !compoundData) return;
  compoundEntityChart.replaceChildren();
  const category = categoryForKey(chartSelection.categoryKey);
  const selectionIds = new Set(chartSelectionPaperIds());
  const selectionLabel = chartSelectionLabel();
  const entries = (category?.concepts || [])
    .map((concept, conceptIndex) => {
      const paperIds = uniquePaperIds(
        concept.sources?.[graphSource]?.paper_ids || []
      ).filter((paperId) => selectionIds.has(paperId));
      return {
        concept,
        conceptIndex,
        paperIds: sortPaperIds(paperIds),
        count: paperIds.length,
      };
    })
    .filter((entry) => entry.count > 0)
    .sort((a, b) => b.count - a.count || a.concept.label.localeCompare(b.concept.label));

  if (compoundEntityContext) {
    compoundEntityContext.textContent = `Entities within ${selectionLabel}, ranked by unique ${sourceLabel(graphSource).toLowerCase()}.`;
  }
  if (!entries.length) {
    const empty = document.createElement("p");
    empty.className = "compound-chart-empty";
    empty.textContent = `No entities have connected ${sourceLabel(graphSource).toLowerCase()} in this selection.`;
    compoundEntityChart.appendChild(empty);
    return;
  }

  const maxCount = Math.max(...entries.map((entry) => entry.count), 1);
  entries.slice(0, visibleEntityCount).forEach((entry) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "compound-entity-row";
    const isSelected =
      selectedChartConcept?.categoryKey === category.key &&
      selectedChartConcept?.conceptIndex === entry.conceptIndex;
    button.classList.toggle("is-selected", isSelected);
    button.setAttribute("aria-pressed", isSelected ? "true" : "false");
    button.style.setProperty("--entity-width", `${(entry.count / maxCount) * 100}%`);
    button.style.setProperty(
      "--entity-color",
      CATEGORY_COLORS[category.key] || "#719d96"
    );

    const topline = document.createElement("span");
    topline.className = "compound-entity-topline";
    const label = document.createElement("span");
    label.textContent = entry.concept.label;
    const value = document.createElement("strong");
    value.textContent = String(entry.count);
    topline.append(label, value);

    const track = document.createElement("span");
    track.className = "compound-entity-track";
    track.appendChild(document.createElement("i"));
    button.append(topline, track);

    const tooltipText = `${entry.concept.label}\n${entry.count} ${sourceLabel(graphSource).toLowerCase()}\nWithin ${selectionLabel}`;
    bindChartTarget(button, tooltipText, () => {
      selectedChartConcept = {
        categoryKey: category.key,
        conceptIndex: entry.conceptIndex,
      };
      renderEntityChart();
      showPaperSelection(
        entry.concept.label,
        entry.paperIds,
        graphSource,
        selectionLabel
      );
    });
    compoundEntityChart.appendChild(button);
  });

  const remaining = Math.max(0, entries.length - visibleEntityCount);
  if (remaining) {
    const more = document.createElement("button");
    more.type = "button";
    more.className = "compound-entity-more";
    more.textContent = `Show ${Math.min(remaining, ENTITY_EXPANSION_STEP)} more`;
    more.addEventListener("click", () => {
      visibleEntityCount += ENTITY_EXPANSION_STEP;
      renderEntityChart();
    });
    compoundEntityChart.appendChild(more);
  }
}

function publicationYear(paperId) {
  const year = Number(compoundData?.papers?.[paperId]?.year || 0);
  return year >= 1800 && year <= 2200 ? year : null;
}

function buildTimelineBuckets(paperIds) {
  const years = paperIds.map(publicationYear).filter(Boolean);
  if (!years.length) return [];
  const minYear = Math.min(...years);
  const maxYear = Math.max(...years);
  const range = maxYear - minYear;
  const step = range > 40 ? 5 : range > 18 ? 2 : 1;
  const firstYear = Math.floor(minYear / step) * step;
  const buckets = [];
  for (let start = firstYear; start <= maxYear; start += step) {
    const end = Math.min(start + step - 1, maxYear);
    buckets.push({
      start,
      end,
      label: start === end ? String(start) : `${start}–${end}`,
    });
  }
  return buckets;
}

function countPapersInBucket(paperIds, bucket) {
  return paperIds.reduce((count, paperId) => {
    const year = publicationYear(paperId);
    return count + (year !== null && year >= bucket.start && year <= bucket.end ? 1 : 0);
  }, 0);
}

function renderTimelineChart() {
  if (!compoundTimelineChart || !compoundData) return;
  compoundTimelineChart.replaceChildren();
  const allIds = sortPaperIds(compoundPaperIds());
  const seriesSelection = baseChartSelection();
  const seriesIds = chartSelectionPaperIds(seriesSelection, false);
  const buckets = buildTimelineBuckets(allIds);
  const seriesLabel = chartSelectionLabel(seriesSelection, false);
  const releaseDate = new Date(compoundData.release?.generated_at || "");
  const releaseYear = Number.isNaN(releaseDate.getTime()) ? 0 : releaseDate.getUTCFullYear();
  const releaseIsPartial = releaseYear && releaseDate.getUTCMonth() < 11;
  const releaseDateLabel = releaseIsPartial
    ? new Intl.DateTimeFormat("en-GB", {
        day: "numeric",
        month: "short",
        year: "numeric",
        timeZone: "UTC",
      }).format(releaseDate)
    : "";

  if (compoundTimelineContext) {
    const partialNote = releaseIsPartial
      ? ` ${releaseYear} is partial through ${releaseDateLabel}.`
      : "";
    compoundTimelineContext.textContent = `Colored bars show ${seriesLabel}; gray bars show all ${compoundData.compound?.label || "compound"} ${sourceLabel(graphSource).toLowerCase()}.${partialNote}`;
  }
  if (!buckets.length) {
    const empty = document.createElement("p");
    empty.className = "compound-chart-empty";
    empty.textContent = `No publication years are available for ${sourceLabel(graphSource).toLowerCase()}.`;
    compoundTimelineChart.appendChild(empty);
    return;
  }

  const margin = { top: 18, right: 18, bottom: 44, left: 42 };
  const plotWidth = TIMELINE_WIDTH - margin.left - margin.right;
  const plotHeight = TIMELINE_HEIGHT - margin.top - margin.bottom;
  const gap = buckets.length > 25 ? 2 : 4;
  const slotWidth = plotWidth / buckets.length;
  const barWidth = Math.max(3, slotWidth - gap);
  const allCounts = buckets.map((bucket) => countPapersInBucket(allIds, bucket));
  const seriesCounts = buckets.map((bucket) => countPapersInBucket(seriesIds, bucket));
  const maxCount = Math.max(...allCounts, 1);
  const color = CATEGORY_COLORS[seriesSelection.categoryKey] || "#719d96";
  const svg = svgElement("svg", {
    viewBox: `0 0 ${TIMELINE_WIDTH} ${TIMELINE_HEIGHT}`,
    role: "group",
    "aria-label": `${seriesLabel} publications over time`,
    focusable: "false",
  });

  [0, 0.5, 1].forEach((ratio) => {
    const y = margin.top + plotHeight - plotHeight * ratio;
    svg.appendChild(
      svgElement("line", {
        x1: margin.left,
        x2: TIMELINE_WIDTH - margin.right,
        y1: y,
        y2: y,
        class: "compound-timeline-gridline",
      })
    );
    const label = svgElement("text", {
      x: margin.left - 8,
      y: y + 3,
      class: "compound-chart-axis-label",
      "text-anchor": "end",
    });
    label.textContent = String(Math.round(maxCount * ratio));
    svg.appendChild(label);
  });

  const tickIndices = new Set(
    [0, Math.round((buckets.length - 1) / 3), Math.round(((buckets.length - 1) * 2) / 3), buckets.length - 1]
  );
  buckets.forEach((bucket, index) => {
    const x = margin.left + index * slotWidth + (slotWidth - barWidth) / 2;
    const allHeight = (allCounts[index] / maxCount) * plotHeight;
    const seriesHeight = (seriesCounts[index] / maxCount) * plotHeight;
    const isSelected =
      chartSelection.type === "year" &&
      chartSelection.start === bucket.start &&
      chartSelection.end === bucket.end;
    const isPartial = releaseIsPartial && releaseYear >= bucket.start && releaseYear <= bucket.end;
    const group = svgElement("g", {
      class: [
        "compound-timeline-target",
        isSelected ? "is-selected" : "",
      ]
        .filter(Boolean)
        .join(" "),
    });
    group.appendChild(
      svgElement("rect", {
        x,
        y: margin.top + plotHeight - allHeight,
        width: barWidth,
        height: Math.max(allHeight, 0),
        class: "compound-timeline-total-bar",
      })
    );
    group.appendChild(
      svgElement("rect", {
        x,
        y: margin.top + plotHeight - seriesHeight,
        width: barWidth,
        height: Math.max(seriesHeight, 0),
        class: "compound-timeline-series-bar",
        fill: color,
      })
    );
    group.appendChild(
      svgElement("rect", {
        x: margin.left + index * slotWidth,
        y: margin.top,
        width: slotWidth,
        height: plotHeight,
        class: "compound-timeline-hit",
      })
    );
    const partialText = isPartial
      ? `\n${releaseYear} is partial through ${releaseDateLabel}`
      : "";
    const tooltipText = `${bucket.label}\n${seriesLabel}: ${seriesCounts[index]} source papers\nAll ${compoundData.compound?.label || "compound"}: ${allCounts[index]}${partialText}`;
    bindChartTarget(group, tooltipText, () => {
      setChartSelection({
        ...seriesSelection,
        type: "year",
        start: bucket.start,
        end: bucket.end,
        label: bucket.label,
      });
    });
    svg.appendChild(group);

    if (tickIndices.has(index)) {
      const tick = svgElement("text", {
        x: x + barWidth / 2,
        y: TIMELINE_HEIGHT - 16,
        class: "compound-chart-axis-label",
        "text-anchor": "middle",
      });
      tick.textContent = bucket.label;
      svg.appendChild(tick);
    }
  });

  compoundTimelineChart.appendChild(svg);
}

function overlapPairIsSelected(firstKey, secondKey) {
  const selectedKeys = new Set(
    [chartSelection.categoryKey, chartSelection.otherCategoryKey].filter(Boolean)
  );
  return selectedKeys.size === 2 && selectedKeys.has(firstKey) && selectedKeys.has(secondKey);
}

function renderOverlapChart() {
  if (!compoundOverlapChart || !compoundData) return;
  compoundOverlapChart.replaceChildren();
  const categories = compoundData.categories;
  const paperSets = new Map(
    categories.map((category) => [category.key, new Set(categoryPaperIds(category))])
  );
  const overlaps = [];
  categories.forEach((first, rowIndex) => {
    categories.forEach((second, columnIndex) => {
      if (rowIndex <= columnIndex) return;
      overlaps.push(
        intersectPaperIds(
          Array.from(paperSets.get(first.key) || []),
          Array.from(paperSets.get(second.key) || [])
        ).length
      );
    });
  });
  const maxOverlap = Math.max(...overlaps, 1);
  const margin = { top: 174, right: 42, bottom: 66, left: 210 };
  const cellSize = Math.min(
    43,
    (OVERLAP_WIDTH - margin.left - margin.right) / categories.length
  );
  const svg = svgElement("svg", {
    viewBox: `0 0 ${OVERLAP_WIDTH} ${OVERLAP_HEIGHT}`,
    role: "group",
    "aria-label": `Cross-domain overlap for ${sourceLabel(graphSource).toLowerCase()}`,
    focusable: "false",
  });

  categories.forEach((category, index) => {
    const rowLabel = svgElement("text", {
      x: margin.left - 12,
      y: margin.top + index * cellSize + cellSize / 2 + 4,
      class: "compound-overlap-axis-label",
      "text-anchor": "end",
    });
    rowLabel.textContent = category.label;
    svg.appendChild(rowLabel);

    const columnX = margin.left + index * cellSize + cellSize / 2;
    const columnLabel = svgElement("text", {
      x: columnX,
      y: margin.top - 13,
      class: "compound-overlap-axis-label",
      "text-anchor": "start",
      transform: `rotate(-52 ${columnX} ${margin.top - 13})`,
    });
    columnLabel.textContent = category.label;
    svg.appendChild(columnLabel);
  });

  categories.forEach((rowCategory, rowIndex) => {
    categories.forEach((columnCategory, columnIndex) => {
      if (columnIndex > rowIndex) return;
      const x = margin.left + columnIndex * cellSize;
      const y = margin.top + rowIndex * cellSize;
      const isDiagonal = rowIndex === columnIndex;
      const rowIds = Array.from(paperSets.get(rowCategory.key) || []);
      const columnIds = Array.from(paperSets.get(columnCategory.key) || []);
      const sharedIds = isDiagonal ? rowIds : intersectPaperIds(rowIds, columnIds);
      const count = sharedIds.length;
      const isSelected = isDiagonal
        ? chartSelection.type === "area" && chartSelection.categoryKey === rowCategory.key
        : overlapPairIsSelected(rowCategory.key, columnCategory.key);
      const alpha = isDiagonal ? 0.25 : count ? 0.12 + 0.76 * Math.sqrt(count / maxOverlap) : 0.035;
      const group = svgElement("g", {
        class: [
          "compound-overlap-target",
          isDiagonal ? "is-diagonal" : "",
          count === 0 ? "is-empty" : "",
          isSelected ? "is-selected" : "",
        ]
          .filter(Boolean)
          .join(" "),
      });
      group.appendChild(
        svgElement("rect", {
          x: x + 1,
          y: y + 1,
          width: cellSize - 2,
          height: cellSize - 2,
          rx: 2,
          fill: isDiagonal
            ? CATEGORY_COLORS[rowCategory.key] || "#719d96"
            : `rgba(105, 161, 150, ${alpha.toFixed(3)})`,
          "fill-opacity": isDiagonal ? alpha : 1,
        })
      );
      if (count) {
        const value = svgElement("text", {
          x: x + cellSize / 2,
          y: y + cellSize / 2 + 4,
          class: "compound-overlap-value",
          "text-anchor": "middle",
        });
        value.textContent = String(count);
        group.appendChild(value);
      }

      if (count) {
        const smallerArea = Math.min(rowIds.length, columnIds.length) || 1;
        const share = Math.round((count / smallerArea) * 100);
        const tooltipText = isDiagonal
          ? `${rowCategory.label}\n${count} ${sourceLabel(graphSource).toLowerCase()}`
          : `${rowCategory.label} × ${columnCategory.label}\n${count} shared ${sourceLabel(graphSource).toLowerCase()}\n${share}% of the smaller area`;
        bindChartTarget(group, tooltipText, () => {
          if (isDiagonal) {
            setChartSelection({ type: "area", categoryKey: rowCategory.key });
          } else {
            setChartSelection({
              type: "overlap",
              categoryKey: rowCategory.key,
              otherCategoryKey: columnCategory.key,
            });
          }
        });
      }
      svg.appendChild(group);
    });
  });

  const legendY = margin.top + categories.length * cellSize + 34;
  const legendLabel = svgElement("text", {
    x: margin.left,
    y: legendY,
    class: "compound-chart-axis-label",
  });
  legendLabel.textContent = "Shared papers";
  svg.appendChild(legendLabel);
  const legendSteps = 6;
  for (let index = 0; index < legendSteps; index += 1) {
    const ratio = index / (legendSteps - 1);
    svg.appendChild(
      svgElement("rect", {
        x: margin.left + 92 + index * 25,
        y: legendY - 11,
        width: 24,
        height: 11,
        rx: 1,
        fill: `rgba(105, 161, 150, ${(0.035 + ratio * 0.845).toFixed(3)})`,
      })
    );
  }
  const zeroLabel = svgElement("text", {
    x: margin.left + 92,
    y: legendY + 16,
    class: "compound-chart-axis-label",
    "text-anchor": "start",
  });
  zeroLabel.textContent = "0";
  const maxLabel = svgElement("text", {
    x: margin.left + 92 + legendSteps * 25 - 1,
    y: legendY + 16,
    class: "compound-chart-axis-label",
    "text-anchor": "end",
  });
  maxLabel.textContent = String(maxOverlap);
  svg.append(zeroLabel, maxLabel);

  compoundOverlapChart.appendChild(svg);
}

function renderCompoundCharts() {
  if (!compoundData || compoundView !== "charts") return;
  hideChartTooltip();
  renderCoverageChart();
  renderTimelineChart();
  renderEntityChart();
  renderOverlapChart();
}

function renderCompoundGraph() {
  if (!compoundGraph || !compoundData || compoundView !== "map") return;
  compoundGraph.replaceChildren();
  hideGraphTooltip();

  const svg = svgElement("svg", {
    viewBox: `0 0 ${GRAPH_WIDTH} ${GRAPH_HEIGHT}`,
    role: "group",
    "aria-label": `${compoundData.compound?.label || "Compound"} research map`,
    focusable: "false",
  });
  const categories = compoundData.categories;
  const selectedCategory =
    categories.find((category) => category.key === selectedGraphCategoryKey) || categories[0];
  selectedGraphCategoryKey = selectedCategory?.key || "";
  const selectedConcepts = (selectedCategory?.concepts || [])
    .filter((concept) => graphCount(concept) > 0)
    .sort((a, b) => {
      const byStudies = graphCount(b) - graphCount(a);
      if (byStudies) return byStudies;
      const byFindings = graphFindingCount(b) - graphFindingCount(a);
      if (byFindings) return byFindings;
      return a.label.localeCompare(b.label);
    })
    .slice(0, GRAPH_MAX_CONCEPTS);

  const compoundX = 92;
  const compoundY = GRAPH_HEIGHT / 2;
  const areaX = 355;
  const conceptX = 712;
  const areaTop = 45;
  const areaBottom = GRAPH_HEIGHT - 45;
  const areaStep = categories.length > 1 ? (areaBottom - areaTop) / (categories.length - 1) : 0;
  const conceptTop = 48;
  const conceptBottom = GRAPH_HEIGHT - 48;
  const conceptStep =
    selectedConcepts.length > 1 ? (conceptBottom - conceptTop) / (selectedConcepts.length - 1) : 0;
  const maxAreaCount = Math.max(...categories.map((category) => graphCount(category)), 1);
  const maxConceptCount = Math.max(...selectedConcepts.map((concept) => graphCount(concept)), 1);
  const areaPositions = new Map();

  const edgeLayer = svgElement("g", { class: "compound-graph-edges" });
  const conceptEdgeLayer = svgElement("g", { class: "compound-graph-concept-edges" });
  const nodeLayer = svgElement("g", { class: "compound-graph-nodes" });
  svg.append(edgeLayer, conceptEdgeLayer, nodeLayer);

  categories.forEach((category, index) => {
    const y = areaTop + areaStep * index;
    const count = graphCount(category);
    const isSelected = category.key === selectedGraphCategoryKey;
    const color = CATEGORY_COLORS[category.key] || "#719d96";
    areaPositions.set(category.key, { x: areaX, y });
    const edge = svgElement("path", {
      d: curvedPath(compoundX + 10, compoundY, areaX - 10, y),
      class: [
        "compound-graph-edge",
        isSelected ? "is-selected" : "",
        count === 0 ? "is-empty" : "",
      ]
        .filter(Boolean)
        .join(" "),
      stroke: color,
      "stroke-width": count ? 1.2 + 7 * Math.sqrt(count / maxAreaCount) : 1,
    });
    edgeLayer.appendChild(edge);
  });

  const selectedPosition = areaPositions.get(selectedGraphCategoryKey);
  selectedConcepts.forEach((concept, index) => {
    const y = selectedConcepts.length === 1 ? GRAPH_HEIGHT / 2 : conceptTop + conceptStep * index;
    const count = graphCount(concept);
    const color = CATEGORY_COLORS[selectedGraphCategoryKey] || "#719d96";
    const edge = svgElement("path", {
      d: curvedPath((selectedPosition?.x || areaX) + 10, selectedPosition?.y || compoundY, conceptX - 9, y),
      class: "compound-graph-concept-edge",
      stroke: color,
      "stroke-width": 1 + 5 * Math.sqrt(count / maxConceptCount),
    });
    conceptEdgeLayer.appendChild(edge);
  });

  const compoundNode = svgElement("g", { class: "compound-graph-node compound-root-node" });
  compoundNode.appendChild(
    svgElement("circle", {
      cx: compoundX,
      cy: compoundY,
      r: 9,
    })
  );
  appendSvgLabel(
    compoundNode,
    compoundData.compound?.label || "Compound",
    compoundX,
    compoundY - 23,
    "compound-root-label",
    24
  );
  nodeLayer.appendChild(compoundNode);

  categories.forEach((category) => {
    const position = areaPositions.get(category.key);
    const count = graphCount(category);
    const findings = graphFindingCount(category);
    const isSelected = category.key === selectedGraphCategoryKey;
    const color = CATEGORY_COLORS[category.key] || "#719d96";
    const group = svgElement("g", {
      class: [
        "compound-graph-node",
        "compound-area-node",
        isSelected ? "is-selected" : "",
        count === 0 ? "is-empty" : "",
      ]
        .filter(Boolean)
        .join(" "),
    });
    group.appendChild(
      svgElement("circle", {
        cx: position.x,
        cy: position.y,
        r: count ? 5 + 6 * Math.sqrt(count / maxAreaCount) : 4,
        fill: color,
      })
    );
    appendSvgLabel(
      group,
      category.label,
      position.x + 18,
      position.y,
      "compound-area-label",
      27
    );
    const tooltipText = `${category.label}\n${count} ${sourceLabel(graphSource).toLowerCase()}\n${findings} findings`;
    bindGraphNode(group, tooltipText, () => {
      if (selectedGraphCategoryKey !== category.key) resetLiterature();
      selectedGraphCategoryKey = category.key;
      chartSelection = { type: "area", categoryKey: category.key };
      openArea(category.key);
      renderCompoundGraph();
    });
    nodeLayer.appendChild(group);
  });

  if (!selectedConcepts.length) {
    const empty = svgElement("text", {
      x: conceptX,
      y: GRAPH_HEIGHT / 2,
      class: "compound-graph-empty",
    });
    empty.textContent = `No ${sourceLabel(graphSource).toLowerCase()} in this area`;
    nodeLayer.appendChild(empty);
  }

  selectedConcepts.forEach((concept, index) => {
    const y = selectedConcepts.length === 1 ? GRAPH_HEIGHT / 2 : conceptTop + conceptStep * index;
    const count = graphCount(concept);
    const findings = graphFindingCount(concept);
    const color = CATEGORY_COLORS[selectedGraphCategoryKey] || "#719d96";
    const conceptIndex = selectedCategory.concepts.indexOf(concept);
    const isSelected = selectedConcept === concept;
    const group = svgElement("g", {
      class: [
        "compound-graph-node",
        "compound-concept-node",
        isSelected ? "is-selected" : "",
      ]
        .filter(Boolean)
        .join(" "),
    });
    group.appendChild(
      svgElement("circle", {
        cx: conceptX,
        cy: y,
        r: 4 + 5 * Math.sqrt(count / maxConceptCount),
        fill: color,
      })
    );
    appendSvgLabel(
      group,
      concept.label,
      conceptX + 17,
      y,
      "compound-concept-label",
      27
    );
    const tooltipText = `${concept.label}\n${count} ${sourceLabel(graphSource).toLowerCase()}\n${findings} findings`;
    bindGraphNode(group, tooltipText, () => {
      selectConcept(selectedCategory.key, conceptIndex, graphSource);
    });
    nodeLayer.appendChild(group);
  });

  compoundGraph.appendChild(svg);
}

function setGraphSource(source) {
  graphSource = source;
  activeSource = source;
  graphSourceButtons.forEach((button) => {
    const isActive = button.dataset.compoundGraphSource === source;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-selected", isActive ? "true" : "false");
  });
  if (compoundView === "charts") {
    selectedChartConcept = null;
    visibleEntityCount = ENTITY_INITIAL_LIMIT;
    renderCompoundCharts();
    renderChartLiteratureSelection();
    return;
  }
  if (selectedConcept) {
    if (Number(selectedConcept.sources?.[source]?.studies || 0) > 0) {
      setActiveSource(source);
    } else {
      resetLiterature();
    }
  }
  renderCompoundGraph();
}

function setCompoundView(view) {
  const previousView = compoundView;
  compoundView = ["map", "charts", "table"].includes(view) ? view : "map";
  compoundPage.dataset.compoundView = compoundView;
  viewButtons.forEach((button) => {
    const isActive = button.dataset.compoundView === compoundView;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-selected", isActive ? "true" : "false");
  });
  const headingByView = {
    map: ["Research map", "Select an area or concept to trace its connected literature."],
    charts: ["Research patterns", "Compare coverage, publication history, and connections between research areas."],
    table: ["Research table", "Expand an area to inspect its concepts and connected literature."],
  };
  if (compoundAreasHeading) compoundAreasHeading.textContent = headingByView[compoundView][0];
  if (compoundAreasDescription) compoundAreasDescription.textContent = headingByView[compoundView][1];
  if (compoundView === "map") renderCompoundGraph();
  if (compoundView === "charts") {
    if (previousView === "map" || !categoryForKey(chartSelection.categoryKey)) {
      chartSelection = { type: "area", categoryKey: selectedGraphCategoryKey };
    }
    if (previousView !== "charts") {
      selectedChartConcept = null;
      visibleEntityCount = ENTITY_INITIAL_LIMIT;
    }
    renderCompoundCharts();
    renderChartLiteratureSelection();
  }
}

async function loadCompoundData() {
  if (!compoundDataUrl) return;
  try {
    const response = await fetch(compoundDataUrl, { cache: "no-store" });
    if (!response.ok) throw new Error(`Compound data request failed: ${response.status}`);
    compoundData = await response.json();
    const initialArea = window.location.hash.slice(1);
    if (compoundData.categories.some((category) => category.key === initialArea)) {
      selectedGraphCategoryKey = initialArea;
    }
    compoundPage.classList.add("compound-enhanced");
    setCompoundView("map");
  } catch (error) {
    if (literatureContext) {
      literatureContext.textContent =
        "The research-area summary is available, but its publication index could not be loaded.";
    }
    console.error(error);
  }
}

areaButtons.forEach((button) => {
  button.addEventListener("click", () => {
    const areaKey = button.dataset.areaToggle || "";
    selectedGraphCategoryKey = areaKey;
    chartSelection = { type: "area", categoryKey: areaKey };
    openArea(areaKey);
  });
});

showMoreButtons.forEach((button) => {
  button.addEventListener("click", () => {
    const area = button.closest(".compound-area-detail");
    area?.querySelectorAll("[data-extra-concept]").forEach((concept) => {
      concept.hidden = false;
    });
    button.hidden = true;
  });
});

conceptButtons.forEach((button) => {
  button.addEventListener("click", () => {
    selectConcept(
      button.dataset.categoryKey || "",
      Number(button.dataset.conceptIndex || 0)
    );
  });
});

graphSourceButtons.forEach((button) => {
  button.addEventListener("click", () => {
    setGraphSource(button.dataset.compoundGraphSource || "primary");
  });
});

viewButtons.forEach((button) => {
  button.addEventListener("click", () => {
    setCompoundView(button.dataset.compoundView || "map");
  });
});

paperMore?.addEventListener("click", () => {
  visiblePaperCount += INITIAL_PAPER_LIMIT;
  renderPapers();
});

const initialArea = window.location.hash.slice(1);
if (areaButtons.some((button) => button.dataset.areaToggle === initialArea)) {
  selectedGraphCategoryKey = initialArea;
  openArea(initialArea, false);
}

loadCompoundData();
