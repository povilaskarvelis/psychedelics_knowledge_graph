const compoundPage = document.body;
const compoundDataUrl = compoundPage?.dataset.compoundData || "";
const areaButtons = Array.from(document.querySelectorAll("[data-area-toggle]"));
const conceptButtons = Array.from(document.querySelectorAll("[data-concept-index]"));
const showMoreButtons = Array.from(document.querySelectorAll("[data-show-more]"));
const sourceButtons = Array.from(document.querySelectorAll("[data-compound-source]"));
const graphSourceButtons = Array.from(document.querySelectorAll("[data-compound-graph-source]"));
const viewButtons = Array.from(document.querySelectorAll("[data-compound-view]"));
const sourceToggle = document.querySelector(".compound-source-toggle");
const literatureHeading = document.getElementById("compoundLiteratureHeading");
const literatureContext = document.getElementById("compoundLiteratureContext");
const paperList = document.getElementById("compoundPaperList");
const paperMore = document.getElementById("compoundPaperMore");
const compoundGraph = document.getElementById("compoundGraph");
const compoundGraphTooltip = document.getElementById("compoundGraphTooltip");

const SOURCE_ORDER = ["primary", "meta_analyses", "reviews"];
const INITIAL_PAPER_LIMIT = 12;
const GRAPH_MAX_CONCEPTS = 12;
const GRAPH_WIDTH = 920;
const GRAPH_HEIGHT = 640;
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
  if (!paperList || !paperMore || !selectedConcept || !compoundData) return;
  const paperIds = selectedConcept.sources?.[activeSource]?.paper_ids || [];
  const visibleIds = paperIds.slice(0, visiblePaperCount);
  paperList.replaceChildren();

  if (!visibleIds.length) {
    const empty = document.createElement("li");
    empty.className = "compound-paper-empty";
    empty.textContent = `No ${sourceLabel(activeSource).toLowerCase()} are connected to this concept in the current release.`;
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
  sourceButtons.forEach((button) => {
    const buttonSource = button.dataset.compoundSource;
    const sourceCount = selectedConcept?.sources?.[buttonSource]?.studies || 0;
    const isActive = buttonSource === activeSource;
    button.disabled = sourceCount === 0;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-selected", isActive ? "true" : "false");
  });
  renderPapers();
}

function resetLiterature() {
  selectedCategory = null;
  selectedConcept = null;
  conceptButtons.forEach((button) => button.classList.remove("is-selected"));
  if (literatureHeading) literatureHeading.textContent = "Literature";
  if (literatureContext) {
    literatureContext.textContent = "Select a concept to see the publications connected to it.";
  }
  if (sourceToggle) sourceToggle.hidden = true;
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
  selectedGraphCategoryKey = category.key;
  conceptButtons.forEach((button) => {
    const isSelected =
      button.dataset.categoryKey === categoryKey &&
      Number(button.dataset.conceptIndex || 0) === conceptIndex;
    button.classList.toggle("is-selected", isSelected);
  });
  if (literatureHeading) literatureHeading.textContent = concept.label;
  if (literatureContext) {
    const connectedPapers = SOURCE_ORDER.reduce(
      (total, source) => total + Number(concept.sources?.[source]?.studies || 0),
      0
    );
    literatureContext.textContent = `${category.label} · ${connectedPapers} connected source papers`;
  }
  if (sourceToggle) sourceToggle.hidden = false;

  const availableSource =
    SOURCE_ORDER.find((source) => Number(concept.sources?.[source]?.studies || 0) > 0) || "primary";
  const requestedSource =
    preferredSource && Number(concept.sources?.[preferredSource]?.studies || 0) > 0
      ? preferredSource
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
  graphSourceButtons.forEach((button) => {
    const isActive = button.dataset.compoundGraphSource === source;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-selected", isActive ? "true" : "false");
  });
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
  compoundView = view === "table" ? "table" : "map";
  compoundPage.dataset.compoundView = compoundView;
  viewButtons.forEach((button) => {
    const isActive = button.dataset.compoundView === compoundView;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-selected", isActive ? "true" : "false");
  });
  if (compoundView === "map") renderCompoundGraph();
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

sourceButtons.forEach((button) => {
  button.addEventListener("click", () => {
    if (!button.disabled) setActiveSource(button.dataset.compoundSource || "primary");
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
