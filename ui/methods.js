const methodsPipelineEl = document.getElementById("methodsPipeline");
const methodsLandscapeEl = document.getElementById("methodsLandscape");
const methodsGapsEl = document.getElementById("methodsGaps");
const landscapeButtons = document.querySelectorAll("[data-landscape-mode]");
const gapButtons = document.querySelectorAll("[data-gap-mode]");

const methodsState = {
  semanticGraph: null,
  gapMatrix: null,
  pipelineStatus: null,
  nodeById: new Map(),
  selectedLandscapeEdgeId: "",
  landscapeMode: "compound_disorder",
  gapMode: "compound_disorder",
};

const RELATION_LABELS = {
  compound_disorder: "Indication",
  compound_target: "Target",
};

const DATASET_LABELS = {
  disorder: "Clinical indications",
  mechanistic: "Mechanistic targets",
};

const SEGMENT_COLORS = ["#49d6c8", "#f1b74b", "#ef6c9a", "#90baff", "#77d98d", "#cda7ff", "#9aa4bf"];
const GRAPH_COLOR_STOPS = [
  { r: 73, g: 214, b: 200 },
  { r: 119, g: 217, b: 141 },
  { r: 216, g: 210, b: 111 },
  { r: 241, g: 166, b: 106 },
  { r: 232, g: 117, b: 141 },
];

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatNumber(value) {
  const number = Number(value || 0);
  return new Intl.NumberFormat("en", { maximumFractionDigits: 0 }).format(number);
}

function clampNumber(value, min, max) {
  return Math.max(min, Math.min(max, Number(value) || 0));
}

function normalizeText(value) {
  return String(value || "").trim();
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
      return await response.json();
    } catch (error) {
      errors.push(`${url} -> ${error.message}`);
    }
  }
  throw new Error(errors.join("; "));
}

function prismaStep(flow, key) {
  return flow?.steps?.[key] || { label: key, count: 0 };
}

function prismaSideBox(flow, key) {
  return flow?.side_boxes?.[key] || { label: key, count: 0, reasons: [] };
}

function renderPrismaReasons(box) {
  const reasons = Array.isArray(box.reasons) ? box.reasons.filter((reason) => Number(reason.count || 0) > 0) : [];
  if (!reasons.length) {
    return `<p>${escapeHtml(box.note || "No records at this step.")}</p>`;
  }
  return `
    <ul>
      ${reasons.map((reason) => `
        <li>
          <span>${escapeHtml(reason.label)}</span>
          <strong>${formatNumber(reason.count)}</strong>
        </li>
      `).join("")}
    </ul>
  `;
}

function renderPrismaNode(step) {
  const count = Number(step.count || 0);
  return `
    <div class="prisma-node">
      <strong>${escapeHtml(step.label)}</strong>
      <span>n = ${formatNumber(count)}</span>
    </div>
  `;
}

function renderPrismaSide(box, variant = "", rowIndex = null) {
  const count = Number(box.count || 0);
  const classes = ["prisma-side"];
  if (variant) classes.push(variant);
  if (!count) classes.push("empty");
  const style = rowIndex ? ` style="grid-row: ${rowIndex}"` : "";
  return `
    <aside class="${classes.join(" ")}"${style}>
      <div>
        <strong>${escapeHtml(box.label)}</strong>
        <span>n = ${formatNumber(count)}</span>
      </div>
      ${renderPrismaReasons(box)}
    </aside>
  `;
}

function renderPrismaRetrievalBranch(box, rowIndex) {
  const count = Number(box?.count || 0);
  if (!count) {
    return `<span class="prisma-side-placeholder" style="grid-row: ${rowIndex}" aria-hidden="true"></span>`;
  }
  return `
    <span class="prisma-side-arrow" style="grid-row: ${rowIndex}" aria-hidden="true"></span>
    <div class="prisma-side-stack" style="grid-row: ${rowIndex}">
      <aside class="prisma-side retrieval-split">
        <div>
          <strong>${escapeHtml(box.label)}</strong>
          <span>n = ${formatNumber(count)}</span>
        </div>
        ${renderPrismaReasons(box)}
      </aside>
      <span class="prisma-branch-down" aria-hidden="true"></span>
      <div class="prisma-abstract-path">
        <strong>Abstract-only evidence path</strong>
        <span>n = ${formatNumber(count)}</span>
        <p>Not available for full-text extraction; retained for metadata and abstract-based evidence where applicable.</p>
      </div>
    </div>
  `;
}

function renderPrismaFlowRow(rowIndex, step, sideBox, options = {}) {
  const mainClasses = ["prisma-main-track"];
  const showSideBox = sideBox && Number(sideBox.count || 0) > 0;
  if (options.last) mainClasses.push("last");
  const sideContent = options.retrievalBranch
    ? renderPrismaRetrievalBranch(sideBox, rowIndex)
    : showSideBox
      ? `<span class="prisma-side-arrow" style="grid-row: ${rowIndex}" aria-hidden="true"></span>${renderPrismaSide(sideBox, options.sideVariant || "", rowIndex)}`
      : `<span class="prisma-side-placeholder" style="grid-row: ${rowIndex}" aria-hidden="true"></span>`;
  return `
    <div class="${mainClasses.join(" ")}" style="grid-row: ${rowIndex}">
      ${renderPrismaNode(step)}
      ${options.last ? "" : `<span class="prisma-down-arrow" aria-hidden="true"></span>`}
    </div>
    ${sideContent}
  `;
}

function renderPrismaDiagram(dataset, flow) {
  const rows = [
    renderPrismaFlowRow(1, prismaStep(flow, "records_identified"), prismaSideBox(flow, "removed_before_screening")),
    renderPrismaFlowRow(2, prismaStep(flow, "records_screened"), prismaSideBox(flow, "records_excluded")),
    renderPrismaFlowRow(3, prismaStep(flow, "reports_sought"), prismaSideBox(flow, "reports_not_retrieved"), { retrievalBranch: true }),
    renderPrismaFlowRow(4, prismaStep(flow, "reports_retrieved"), prismaSideBox(flow, "reports_not_converted")),
    renderPrismaFlowRow(5, prismaStep(flow, "reports_assessed"), prismaSideBox(flow, "reports_not_extracted"), { sideVariant: "pending" }),
    renderPrismaFlowRow(6, prismaStep(flow, "included"), null, { last: true }),
  ];
  return `
    <article class="prisma-diagram" aria-label="${DATASET_LABELS[dataset]} PRISMA-style flow">
      <h3>${DATASET_LABELS[dataset]}</h3>
      <div class="prisma-flow">
        ${rows.join("")}
      </div>
    </article>
  `;
}

function renderPrismaPanel(datasets, status) {
  const flows = status?.prisma_flow || {};
  if (!Object.keys(flows).length) return "";
  return `
    <section class="prisma-panel" aria-label="PRISMA-style paper flow">
      <div class="prisma-grid">
        ${datasets.map((dataset) => renderPrismaDiagram(dataset, flows[dataset])).join("")}
      </div>
    </section>
  `;
}

function renderPipeline() {
  if (!methodsPipelineEl || !methodsState.pipelineStatus) return;
  const status = methodsState.pipelineStatus;
  const datasets = ["disorder", "mechanistic"];
  const prismaPanel = renderPrismaPanel(datasets, status);

  methodsPipelineEl.className = "flow-dashboard";
  methodsPipelineEl.innerHTML = `<div class="flow-panel">${prismaPanel}</div>`;
}

function topValue(items, fallback = "not classified") {
  if (!Array.isArray(items) || !items.length) return fallback;
  return items[0]?.value || fallback;
}

function countValue(items, value) {
  if (!Array.isArray(items)) return 0;
  const match = items.find((item) => normalizeText(item.value).toLowerCase() === value.toLowerCase());
  return Number(match?.count || 0);
}

function segmentBar(items, maxSegments = 5) {
  const rows = Array.isArray(items) ? items.slice(0, maxSegments) : [];
  const total = rows.reduce((sum, item) => sum + Number(item.count || 0), 0);
  if (!rows.length || !total) return `<div class="segment-empty"></div>`;
  return `
    <div class="segment-bar">
      ${rows.map((item, index) => {
        const width = Math.max(3, (Number(item.count || 0) / total) * 100);
        return `<span title="${escapeHtml(item.value)}: ${formatNumber(item.count)}" style="--segment-width: ${width}%; --segment-color: ${SEGMENT_COLORS[index % SEGMENT_COLORS.length]}"></span>`;
      }).join("")}
    </div>
    <div class="segment-legend">
      ${rows.slice(0, 4).map((item, index) => `
        <span><i style="--segment-color: ${SEGMENT_COLORS[index % SEGMENT_COLORS.length]}"></i>${escapeHtml(item.value)} <strong>${formatNumber(item.count)}</strong></span>
      `).join("")}
    </div>
  `;
}

function yearLabel(profile) {
  const range = profile?.year_range || {};
  if (!range.min || !range.max) return "year range unavailable";
  if (range.min === range.max) return `${range.min}`;
  return `${range.min}-${range.max}`;
}

function edgeHeadline(edge) {
  const sourceLabel = edge.source_label || methodsState.nodeById.get(edge.source)?.label || edge.source;
  const targetLabel = edge.target_label || methodsState.nodeById.get(edge.target)?.label || edge.target;
  return `${sourceLabel} -> ${targetLabel}`;
}

function edgeSubstats(edge) {
  const profile = edge.content_profile || {};
  const status = edge.data_status || {};
  const primary = countValue(profile.source_types, "primary_study");
  const review = countValue(profile.source_types, "review") + countValue(profile.source_types, "meta_analysis");
  return [
    `${formatNumber(status.candidate_paper_count || edge.candidate_paper_count)} papers`,
    `${formatNumber(primary)} primary`,
    `${formatNumber(review)} review/meta`,
    yearLabel(profile),
  ].filter(Boolean);
}

function representativePaperList(profile) {
  const papers = Array.isArray(profile?.representative_papers) ? profile.representative_papers.slice(0, 2) : [];
  if (!papers.length) return "";
  return `
    <div class="landscape-papers">
      ${papers.map((paper) => `
        <div>
          <strong>${escapeHtml(paper.year || "")}</strong>
          <span>${escapeHtml(paper.title || paper.doi || paper.paper_id || "")}</span>
        </div>
      `).join("")}
    </div>
  `;
}

function edgeContentChips(edge) {
  const profile = edge.content_profile || {};
  const chips = [
    topValue(profile.study_designs, ""),
    topValue(profile.outcome_types, ""),
    topValue(profile.assay_types, ""),
    topValue(profile.result_directions, ""),
    topValue(profile.systems, ""),
  ].filter(Boolean);
  return chips.slice(0, 4).map((chip) => `<span>${escapeHtml(chip)}</span>`).join("");
}

function landscapeEdgesForMode(mode, limit = 36) {
  return (methodsState.semanticGraph?.edges || [])
    .filter((edge) => edge.type === mode)
    .sort((a, b) => {
      const byPapers = Number(b.data_status?.candidate_paper_count || b.candidate_paper_count || 0) - Number(a.data_status?.candidate_paper_count || a.candidate_paper_count || 0);
      if (byPapers !== 0) return byPapers;
      return Number(b.data_status?.curated_claim_count || b.curated_claim_count || 0) - Number(a.data_status?.curated_claim_count || a.curated_claim_count || 0);
    })
    .slice(0, limit);
}

function nodeLabel(nodeId) {
  return methodsState.nodeById.get(nodeId)?.label || nodeId;
}

function shortLabel(value, max = 30) {
  const text = normalizeText(value);
  if (text.length <= max) return text;
  return `${text.slice(0, Math.max(1, max - 3))}...`;
}

function edgePaperCount(edge) {
  return Number(edge.data_status?.candidate_paper_count || edge.candidate_paper_count || 0);
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

function rankedNodeIds(edges, key) {
  const weights = new Map();
  edges.forEach((edge) => {
    const id = edge[key];
    weights.set(id, (weights.get(id) || 0) + edgePaperCount(edge));
  });
  return Array.from(weights.entries())
    .sort((a, b) => b[1] - a[1] || nodeLabel(a[0]).localeCompare(nodeLabel(b[0])))
    .map(([id]) => id);
}

function yScale(index, count, height) {
  if (count <= 1) return height / 2;
  const top = 54;
  const bottom = height - 54;
  return top + (index / (count - 1)) * (bottom - top);
}

function createSvgEl(name, attrs = {}) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", name);
  Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, String(value)));
  return node;
}

function renderLandscapeGraph(edges) {
  const leftIds = rankedNodeIds(edges, "source");
  const rightIds = rankedNodeIds(edges, "target");
  const width = 980;
  const height = Math.max(520, Math.max(leftIds.length, rightIds.length) * 58 + 96);
  const leftX = 220;
  const rightX = 650;
  const labelOffset = 22;
  const leftPositions = new Map(leftIds.map((id, index) => [id, { x: leftX, y: yScale(index, leftIds.length, height) }]));
  const rightPositions = new Map(rightIds.map((id, index) => [id, { x: rightX, y: yScale(index, rightIds.length, height) }]));
  const leftColors = new Map(leftIds.map((id, index) => [id, graphColorForIndex(index, leftIds.length)]));
  const rightColors = new Map(rightIds.map((id, index) => [id, graphColorForIndex(index, rightIds.length)]));
  const maxCount = Math.max(...edges.map(edgePaperCount), 1);
  const svg = createSvgEl("svg", {
    viewBox: `0 0 ${width} ${height}`,
    role: "img",
    "aria-label": "Exploratory literature knowledge graph",
  });
  const defs = createSvgEl("defs");
  const edgeLayer = createSvgEl("g", { class: "edge-layer" });
  const nodeLayer = createSvgEl("g", { class: "node-layer" });
  svg.append(defs, edgeLayer, nodeLayer);

  edges.forEach((edge, index) => {
    const source = leftPositions.get(edge.source);
    const target = rightPositions.get(edge.target);
    if (!source || !target) return;
    const sourceColor = leftColors.get(edge.source) || graphColorForIndex(0, 1);
    const targetColor = rightColors.get(edge.target) || graphColorForIndex(0, 1);
    const gradientId = `edge-gradient-${index}`;
    const gradient = createSvgEl("linearGradient", {
      id: gradientId,
      gradientUnits: "userSpaceOnUse",
      x1: source.x,
      y1: source.y,
      x2: target.x,
      y2: target.y,
    });
    const start = createSvgEl("stop", {
      offset: "0%",
      "stop-color": rgbString(sourceColor),
      "stop-opacity": "0.78",
    });
    const end = createSvgEl("stop", {
      offset: "100%",
      "stop-color": rgbString(targetColor),
      "stop-opacity": "0.72",
    });
    gradient.append(start, end);
    defs.appendChild(gradient);

    const selected = methodsState.selectedLandscapeEdgeId === edge.id;
    const midX = (source.x + target.x) / 2;
    const curve = 80;
    const path = createSvgEl("path", {
      class: `edge${selected ? " selected" : ""}`,
      d: `M ${source.x} ${source.y} C ${midX - curve} ${source.y}, ${midX + curve} ${target.y}, ${target.x} ${target.y}`,
      "data-edge-id": edge.id,
    });
    path.style.stroke = `url(#${gradientId})`;
    path.style.setProperty("--edge-width", `${edgeWidthForCount(edgePaperCount(edge), maxCount).toFixed(2)}px`);
    path.style.setProperty("--edge-glow", rgbaString(sourceColor, 0.36));
    const title = createSvgEl("title");
    title.textContent = `${edgeHeadline(edge)}: ${formatNumber(edgePaperCount(edge))} papers`;
    path.appendChild(title);
    path.addEventListener("click", () => {
      methodsState.selectedLandscapeEdgeId = edge.id;
      renderLandscape();
    });
    path.addEventListener("mouseenter", () => {
      path.classList.add("hovered");
    });
    path.addEventListener("mouseleave", () => {
      path.classList.remove("hovered");
    });
    edgeLayer.appendChild(path);
  });

  function appendNodes(ids, positions, side) {
    ids.forEach((id) => {
      const point = positions.get(id);
      if (!point) return;
      const node = createSvgEl("circle", {
        class: `node ${side === "left" ? "compound" : "target"}`,
        cx: point.x,
        cy: point.y,
        r: 12,
      });
      applyGraphNodeColor(
        node,
        side === "left"
          ? leftColors.get(id) || graphColorForIndex(0, 1)
          : rightColors.get(id) || graphColorForIndex(0, 1),
      );
      const label = createSvgEl("text", {
        class: "node-label",
        x: side === "left" ? point.x - labelOffset : point.x + labelOffset,
        y: point.y + 5,
        "text-anchor": side === "left" ? "end" : "start",
      });
      label.textContent = shortLabel(nodeLabel(id), side === "left" ? 26 : 24);
      nodeLayer.append(node, label);
    });
  }

  appendNodes(leftIds, leftPositions, "left");
  appendNodes(rightIds, rightPositions, "right");
  return svg;
}

function renderLandscapeDetail(edge) {
  if (!edge) {
    return `
      <aside class="graph-detail kg-detail-panel">
        <h3>Select an edge</h3>
        <p>Click a line in the exploratory graph to inspect the literature composition behind that compound pair.</p>
        <div class="kg-legend">
          <span><i class="curated"></i> Has curated claims</span>
          <span><i class="ready"></i> Full text available</span>
          <span><i class="candidate"></i> Literature-only signal</span>
        </div>
      </aside>
    `;
  }
  const profile = edge.content_profile || {};
  return `
    <aside class="graph-detail kg-detail-panel">
      <div class="kg-detail-heading">
        <span>${RELATION_LABELS[edge.type]}</span>
        <h3>${escapeHtml(edgeHeadline(edge))}</h3>
      </div>
      <div class="landscape-metrics">
        ${edgeSubstats(edge).map((item) => `<span>${escapeHtml(item)}</span>`).join("")}
      </div>
      <div class="kg-detail-block">
        <strong>Paper Types</strong>
        ${segmentBar(profile.paper_types)}
      </div>
      <div class="kg-detail-block">
        <strong>Content Signals</strong>
        <div class="landscape-chips">${edgeContentChips(edge)}</div>
      </div>
      <div class="kg-detail-block">
        <strong>Representative Papers</strong>
        ${representativePaperList(profile) || `<p>No representative papers available.</p>`}
      </div>
    </aside>
  `;
}

function renderLandscape() {
  if (!methodsLandscapeEl || !methodsState.semanticGraph) return;
  const mode = methodsState.landscapeMode;
  const edges = landscapeEdgesForMode(mode);
  if (!edges.some((edge) => edge.id === methodsState.selectedLandscapeEdgeId)) {
    methodsState.selectedLandscapeEdgeId = edges[0]?.id || "";
  }
  const selectedEdge = edges.find((edge) => edge.id === methodsState.selectedLandscapeEdgeId);
  methodsLandscapeEl.className = "panel graph-panel kg-landscape";
  methodsLandscapeEl.innerHTML = `
    <div class="kg-graph-shell">
      <div class="kg-graph-canvas"></div>
    </div>
    ${renderLandscapeDetail(selectedEdge)}
  `;
  methodsLandscapeEl.querySelector(".kg-graph-canvas")?.appendChild(renderLandscapeGraph(edges));
}

function renderGaps() {
  if (!methodsGapsEl || !methodsState.gapMatrix) return;
  const mode = methodsState.gapMode;
  const records = (methodsState.gapMatrix.records || [])
    .filter((record) => record.relation_type === mode)
    .filter((record) => Number(record.curated_claim_count || 0) <= 1)
    .sort((a, b) => Number(b.candidate_paper_count || 0) - Number(a.candidate_paper_count || 0))
    .slice(0, 10);
  const maxPapers = Math.max(...records.map((record) => Number(record.candidate_paper_count || 0)), 1);

  methodsGapsEl.className = "gap-list";
  methodsGapsEl.innerHTML = records.map((record) => {
    const profile = record.content_profile || {};
    const width = Math.max(4, (Number(record.candidate_paper_count || 0) / maxPapers) * 100);
    const primary = countValue(profile.source_types, "primary_study");
    return `
      <article class="gap-row">
        <div class="gap-main">
          <h3>${escapeHtml(record.compound)} -> ${escapeHtml(record.object)}</h3>
          <div class="gap-meta">
            <span>${formatNumber(record.candidate_paper_count)} papers</span>
            <span>${formatNumber(primary)} primary studies</span>
            <span>${yearLabel(profile)}</span>
            <span>${formatNumber(record.curated_claim_count)} curated claims</span>
          </div>
          <div class="gap-track"><span style="--gap-width: ${width}%"></span></div>
        </div>
        <div class="gap-profile">
          ${segmentBar(profile.paper_types, 4)}
        </div>
      </article>
    `;
  }).join("");
}

function setButtonState(buttons, activeAttr, activeValue) {
  buttons.forEach((button) => {
    const isActive = button.dataset[activeAttr] === activeValue;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-selected", isActive ? "true" : "false");
  });
}

function renderMethodsError(error) {
  const message = `
    <div class="methods-error">
      Methods data is not available yet. Run <code>python pipeline/kg/build_kg.py</code> from the project root, then refresh this page.
      <span>${escapeHtml(error.message)}</span>
    </div>
  `;
  if (methodsPipelineEl) methodsPipelineEl.innerHTML = message;
  if (methodsLandscapeEl) methodsLandscapeEl.innerHTML = message;
  if (methodsGapsEl) methodsGapsEl.innerHTML = message;
}

async function initMethods() {
  if (!methodsPipelineEl && !methodsLandscapeEl && !methodsGapsEl) return;
  try {
    const [semanticGraph, gapMatrix, pipelineStatus] = await Promise.all([
      fetchJsonFromCandidates([
        "../data/kg/views/semantic_graph.json",
        "/data/kg/views/semantic_graph.json",
        "data/kg/views/semantic_graph.json",
      ]),
      fetchJsonFromCandidates([
        "../data/kg/aggregates/literature_gap_matrix.json",
        "/data/kg/aggregates/literature_gap_matrix.json",
        "data/kg/aggregates/literature_gap_matrix.json",
      ]),
      fetchJsonFromCandidates([
        "../data/kg/views/pipeline_status_graph.json",
        "/data/kg/views/pipeline_status_graph.json",
        "data/kg/views/pipeline_status_graph.json",
      ]),
    ]);
    methodsState.semanticGraph = semanticGraph;
    methodsState.gapMatrix = gapMatrix;
    methodsState.pipelineStatus = pipelineStatus;
    methodsState.nodeById = new Map((semanticGraph.nodes || []).map((node) => [node.id, node]));
    renderPipeline();
    renderLandscape();
    renderGaps();
  } catch (error) {
    renderMethodsError(error);
  }
}

landscapeButtons.forEach((button) => {
  button.addEventListener("click", () => {
    methodsState.landscapeMode = button.dataset.landscapeMode || "compound_disorder";
    setButtonState(landscapeButtons, "landscapeMode", methodsState.landscapeMode);
    renderLandscape();
  });
});

gapButtons.forEach((button) => {
  button.addEventListener("click", () => {
    methodsState.gapMode = button.dataset.gapMode || "compound_disorder";
    setButtonState(gapButtons, "gapMode", methodsState.gapMode);
    renderGaps();
  });
});

initMethods();
