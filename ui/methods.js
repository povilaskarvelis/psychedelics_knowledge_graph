const methodsPipelineEl = document.getElementById("methodsPipeline");
const methodsBibliographySectionEl = document.getElementById("paper-bibliography");
const methodsBibliographySearchEl = document.getElementById("methodsBibliographySearch");
const methodsBibliographyStageEl = document.getElementById("methodsBibliographyStage");
const methodsBibliographyKgStatusEl = document.getElementById("methodsBibliographyKgStatus");
const methodsBibliographySortEl = document.getElementById("methodsBibliographySort");
const methodsBibliographySummaryEl = document.getElementById("methodsBibliographySummary");
const methodsBibliographyRowsEl = document.getElementById("methodsBibliographyRows");
const methodsBibliographyLoadMoreEl = document.getElementById("methodsBibliographyLoadMore");

const methodsState = {
  pipelineStatus: null,
  bibliographyPayload: null,
  bibliographyRows: [],
  bibliographyFilteredRows: [],
  bibliographyRendered: 0,
  bibliographyPromise: null,
  bibliographySearchTimer: null,
};
const dataFetchOptions =
  ["", "localhost", "127.0.0.1", "::1"].includes(window.location.hostname) ? { cache: "no-store" } : {};

const DATASET_LABELS = {
  overall: "Paper search and screening flow",
};
const BIBLIOGRAPHY_GRAPH_STATUS_LABELS = {
  "In graph": "Represented in graph",
  "Not graphable": "No suitable graph relationship",
  "Not normalized": "Names not matched",
  "No graph finding": "No publishable finding",
  "Not reached": "Not reached",
};
const BIBLIOGRAPHY_PAGE_SIZE = 120;

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

function normalizeText(value) {
  return String(value ?? "").toLowerCase().replace(/\s+/g, " ").trim();
}

function doiHref(doi) {
  const clean = String(doi ?? "").trim();
  return clean ? `https://doi.org/${encodeURIComponent(clean).replace(/%2F/g, "/")}` : "";
}

async function fetchJsonFromCandidates(candidates) {
  const errors = [];
  for (const url of candidates) {
    try {
      const response = await fetch(url, dataFetchOptions);
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
  const note = box.note ? `<p>${escapeHtml(box.note)}</p>` : "";
  if (!reasons.length) {
    return note;
  }
  return `
    <ul>
      ${reasons.map((reason) => `
        <li>
          <span>${escapeHtml(BIBLIOGRAPHY_GRAPH_STATUS_LABELS[reason.label] || reason.label)}</span>
          <strong>${formatNumber(reason.count)}</strong>
        </li>
      `).join("")}
    </ul>
    ${note}
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

function renderPrismaSideSummary(box, variant = "") {
  return renderPrismaSide({ ...box, note: "", reasons: [] }, variant);
}

function renderNonFullTextFlow(flow = {}) {
  const candidates = flow.candidates || {
    label: "Records without article text",
    count: 0,
  };
  const assessed = flow.assessed;
  const pending = flow.not_extracted;
  const excluded = flow.excluded;
  const included = flow.included_total || {
    label: "Included in the knowledge graph",
    count: 0,
  };
  const hasPending = Number(pending?.count || 0) > 0;
  const hasExcluded = Number(excluded?.count || 0) > 0;
  if (!assessed || Number(assessed.count || 0) <= 0) {
    return Number(pending?.count || 0) > 0 ? renderPrismaSide(pending, "pending") : "";
  }
  return `
    <div class="prisma-mini-flow">
      <div class="prisma-mini-main">
        <span class="prisma-branch-down prisma-mini-top-arrow" aria-hidden="true"></span>
        ${renderPrismaSideSummary(candidates, "evidence-path")}
        <span class="prisma-branch-down" aria-hidden="true"></span>
        ${renderPrismaSide(assessed, "evidence-path")}
        <span class="prisma-branch-down" aria-hidden="true"></span>
        ${renderPrismaSide(included, "included")}
      </div>
      <div class="prisma-mini-asides">
        ${hasPending ? `
          <div class="prisma-mini-side-item pending">
            <span class="prisma-mini-side-arrow" aria-hidden="true"></span>
            ${renderPrismaSideSummary(pending, "pending")}
          </div>
        ` : ""}
        ${hasExcluded ? `
          <div class="prisma-mini-side-item excluded">
            <span class="prisma-mini-side-arrow" aria-hidden="true"></span>
            ${renderPrismaSide(excluded, "pending")}
          </div>
        ` : ""}
      </div>
    </div>
  `;
}

function renderPrismaRetrievalBranch(box, rowIndex) {
  const count = Number(box?.count || 0);
  const nonFullTextFlow = box?.non_fulltext_flow || {};
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
      ${Number(nonFullTextFlow?.candidates?.count || 0) ? `
        ${renderNonFullTextFlow(nonFullTextFlow)}
      ` : ""}
    </div>
  `;
}

function renderPrismaFlowRow(rowIndex, step, sideBox, options = {}) {
  const mainClasses = ["prisma-main-track"];
  const showSideBox = sideBox && Number(sideBox.count || 0) > 0;
  if (options.last) mainClasses.push("last");
  const sideVariant = options.sideVariant || options.side_variant || "";
  const sideContent = options.retrievalBranch
    ? renderPrismaRetrievalBranch(sideBox, rowIndex)
    : showSideBox
      ? `<span class="prisma-side-arrow" style="grid-row: ${rowIndex}" aria-hidden="true"></span>${renderPrismaSide(sideBox, sideVariant, rowIndex)}`
      : `<span class="prisma-side-placeholder" style="grid-row: ${rowIndex}" aria-hidden="true"></span>`;
  return `
    <div class="${mainClasses.join(" ")}" style="grid-row: ${rowIndex}">
      ${renderPrismaNode(step)}
      ${options.last ? "" : `<span class="prisma-down-arrow" aria-hidden="true"></span>`}
    </div>
    ${sideContent}
  `;
}

function legacyPrismaRows(flow) {
  return [
    renderPrismaFlowRow(1, prismaStep(flow, "records_identified"), prismaSideBox(flow, "removed_before_screening")),
    renderPrismaFlowRow(2, prismaStep(flow, "records_screened"), prismaSideBox(flow, "records_excluded")),
    renderPrismaFlowRow(3, prismaStep(flow, "reports_sought"), prismaSideBox(flow, "reports_not_retrieved"), { retrievalBranch: true }),
    renderPrismaFlowRow(4, prismaStep(flow, "reports_retrieved"), prismaSideBox(flow, "reports_not_converted")),
    renderPrismaFlowRow(5, prismaStep(flow, "reports_assessed"), prismaSideBox(flow, "reports_not_extracted"), { sideVariant: "pending" }),
    renderPrismaFlowRow(6, prismaStep(flow, "fulltext_gemini_assessed"), prismaSideBox(flow, "fulltext_excluded_after_extraction"), { sideVariant: "pending" }),
    renderPrismaFlowRow(7, prismaStep(flow, "fulltext_included"), null, { last: true }),
  ];
}

function dynamicPrismaRows(flow) {
  const rowDefs = Array.isArray(flow?.rows) ? flow.rows : [];
  if (!rowDefs.length) return legacyPrismaRows(flow);
  return rowDefs.map((row, index) => {
    const rowIndex = index + 1;
    const sideKey = row.side_box || row.sideBox || "";
    return renderPrismaFlowRow(
      rowIndex,
      prismaStep(flow, row.step),
      sideKey ? prismaSideBox(flow, sideKey) : null,
      {
        last: row.last === true || rowIndex === rowDefs.length,
        retrievalBranch: row.retrieval_branch === true || row.retrievalBranch === true,
        sideVariant: row.side_variant || row.sideVariant || "",
      },
    );
  });
}

function renderPrismaDiagram(dataset, flow) {
  const title = flow?.label || DATASET_LABELS[dataset] || dataset;
  const rows = dynamicPrismaRows(flow);
  return `
    <article class="prisma-diagram" aria-label="${escapeHtml(title)} PRISMA-style flow">
      <h3>${escapeHtml(title)}</h3>
      <div class="prisma-flow">
        ${rows.join("")}
      </div>
    </article>
  `;
}

function prismaFlowOrder(status, flows) {
  const explicitOrder = Array.isArray(status?.prisma_flow_order) ? status.prisma_flow_order : [];
  const ordered = explicitOrder.filter((key) => flows[key]);
  if (ordered.length) return ordered;
  if (flows.overall) return ["overall"];
  return Object.keys(flows).sort();
}

function renderPrismaPanel(status) {
  const flows = status?.prisma_flow || {};
  if (!Object.keys(flows).length) return "";
  const flowOrder = prismaFlowOrder(status, flows);
  const gridClasses = ["prisma-grid"];
  if (flowOrder.length === 1) gridClasses.push("single");
  return `
    <section class="prisma-panel" aria-label="PRISMA-style paper flow">
      <div class="${gridClasses.join(" ")}">
        ${flowOrder.map((dataset) => renderPrismaDiagram(dataset, flows[dataset])).join("")}
      </div>
    </section>
  `;
}

function renderPipeline() {
  if (!methodsPipelineEl || !methodsState.pipelineStatus) return;
  const status = methodsState.pipelineStatus;
  const prismaPanel = renderPrismaPanel(status);

  methodsPipelineEl.className = "flow-dashboard";
  methodsPipelineEl.innerHTML = `<div class="flow-panel">${prismaPanel}</div>`;
}

function bibliographyColumns(payload) {
  return Array.isArray(payload?.columns) ? payload.columns : [];
}

function bibliographyRowsFromPayload(payload) {
  const columns = bibliographyColumns(payload);
  const rows = Array.isArray(payload?.rows) ? payload.rows : [];
  const stringTable = Array.isArray(payload?.string_table) ? payload.string_table : [];
  const internedColumns = new Set(Array.isArray(payload?.interned_columns) ? payload.interned_columns : []);
  return rows.map((row) => {
    if (!Array.isArray(row)) return row && typeof row === "object" ? row : {};
    const item = {};
    columns.forEach((column, index) => {
      const value = row[index];
      item[column] = internedColumns.has(column) && Number.isInteger(value) ? stringTable[value] || "" : value;
    });
    item.search_text = normalizeText([
      item.authors,
      item.title,
      item.doi,
      item.year,
      item.journal,
      item.kg_label,
      item.kg_note,
    ].join(" "));
    return item;
  });
}

function bibliographyStageRankMap(payload) {
  const entries = Array.isArray(payload?.stage_options) ? payload.stage_options : [];
  const rank = {};
  entries.forEach((entry, index) => {
    rank[entry.key] = index;
  });
  return rank;
}

function populateBibliographyStageFilter(payload) {
  if (!methodsBibliographyStageEl) return;
  const currentValue = methodsBibliographyStageEl.value;
  const options = Array.isArray(payload?.stage_options) ? payload.stage_options : [];
  methodsBibliographyStageEl.innerHTML = `
    <option value="">All stages</option>
    ${options.map((option) => `
      <option value="${escapeHtml(option.key)}">
        ${escapeHtml(option.label)} (${formatNumber(option.count)})
      </option>
    `).join("")}
  `;
  methodsBibliographyStageEl.value = options.some((option) => option.key === currentValue) ? currentValue : "";
}

function populateBibliographyKgStatusFilter(payload) {
  if (!methodsBibliographyKgStatusEl) return;
  const currentValue = methodsBibliographyKgStatusEl.value;
  const options = Array.isArray(payload?.kg_options) ? payload.kg_options : [];
  methodsBibliographyKgStatusEl.innerHTML = `
    <option value="">All graph statuses</option>
    ${options.map((option) => `
      <option value="${escapeHtml(option.label)}">
        ${escapeHtml(BIBLIOGRAPHY_GRAPH_STATUS_LABELS[option.label] || option.label)} (${formatNumber(option.count)})
      </option>
    `).join("")}
  `;
  methodsBibliographyKgStatusEl.value = options.some((option) => option.label === currentValue) ? currentValue : "";
}

function bibliographySortValue(row, field) {
  const value = normalizeText(row[field] || "");
  return value || "\uffff";
}

function sortBibliographyRows(rows) {
  const sortKey = methodsBibliographySortEl?.value || "author";
  const stageRank = bibliographyStageRankMap(methodsState.bibliographyPayload);
  const sorted = [...rows];
  sorted.sort((left, right) => {
    if (sortKey === "year-desc") {
      const leftYear = Number(left.year || 0);
      const rightYear = Number(right.year || 0);
      if (leftYear !== rightYear) return rightYear - leftYear;
    } else if (sortKey === "title") {
      const value = bibliographySortValue(left, "title").localeCompare(bibliographySortValue(right, "title"));
      if (value !== 0) return value;
    } else if (sortKey === "stage") {
      const value = (stageRank[left.stage_key] ?? 999) - (stageRank[right.stage_key] ?? 999);
      if (value !== 0) return value;
    } else {
      const value = bibliographySortValue(left, "authors").localeCompare(bibliographySortValue(right, "authors"));
      if (value !== 0) return value;
    }
    return bibliographySortValue(left, "title").localeCompare(bibliographySortValue(right, "title"))
      || bibliographySortValue(left, "doi").localeCompare(bibliographySortValue(right, "doi"));
  });
  return sorted;
}

function bibliographyStageCellHtml(status, label, note) {
  const statusKey = status || "not_reached";
  const symbols = {
    pass: "✓",
    fail: "×",
    not_reached: "–",
  };
  const cleanLabel = label || "Not reached";
  const cleanNote = note || "";
  return `
    <div class="bibliography-stage-cell ${escapeHtml(statusKey)}">
      <strong><span aria-hidden="true">${symbols[statusKey] || "–"}</span>${escapeHtml(cleanLabel)}</strong>
      ${cleanNote ? `<span>${escapeHtml(cleanNote)}</span>` : ""}
    </div>
  `;
}

function bibliographyPaperHtml(row) {
  const doi = row.doi || "";
  const href = doiHref(doi);
  const title = row.title || "Title unavailable";
  const authors = row.authors || "Authors unavailable";
  const meta = [row.year, row.journal].filter(Boolean).join(" · ");
  return `
    <div class="bibliography-paper-cell">
      <strong>${escapeHtml(title)}</strong>
      <span class="bibliography-authors">${escapeHtml(authors)}</span>
      ${meta ? `<span>${escapeHtml(meta)}</span>` : ""}
      ${href ? `<a href="${href}" target="_blank" rel="noopener noreferrer">${escapeHtml(doi)}</a>` : ""}
    </div>
  `;
}

function bibliographyRowHtml(row) {
  const selectedClass = row.selected_for_extraction ? " selected" : "";
  return `
    <tr class="methods-bibliography-row${selectedClass}">
      <td>${bibliographyPaperHtml(row)}</td>
      <td>${bibliographyStageCellHtml(row.initial_screening_status, row.initial_screening_label, row.initial_screening_note)}</td>
      <td>${bibliographyStageCellHtml(row.llm_screening_status, row.llm_screening_label, row.llm_screening_note)}</td>
      <td>${bibliographyStageCellHtml(row.extraction_status, row.extraction_label, row.extraction_note)}</td>
      <td>${bibliographyStageCellHtml(row.kg_status, BIBLIOGRAPHY_GRAPH_STATUS_LABELS[row.kg_label] || row.kg_label, row.kg_note)}</td>
    </tr>
  `;
}

function updateBibliographySummary() {
  if (!methodsBibliographySummaryEl) return;
  const total = methodsState.bibliographyRows.length;
  const filtered = methodsState.bibliographyFilteredRows.length;
  const rendered = Math.min(methodsState.bibliographyRendered, filtered);
  const stage = (methodsBibliographyStageEl?.selectedOptions?.[0]?.textContent || "All stages").replace(/\s+/g, " ").trim();
  const kgStatus = (methodsBibliographyKgStatusEl?.selectedOptions?.[0]?.textContent || "All graph statuses").replace(/\s+/g, " ").trim();
  const query = methodsBibliographySearchEl?.value?.trim() || "";
  const filterText = query || methodsBibliographyStageEl?.value || methodsBibliographyKgStatusEl?.value
    ? `Filtered to ${formatNumber(filtered)} of ${formatNumber(total)} papers.`
    : `${formatNumber(total)} papers in the full search corpus.`;
  methodsBibliographySummaryEl.textContent = `${filterText} Showing ${formatNumber(rendered)}. Stage: ${stage}. Graph status: ${kgStatus}.`;
}

function appendBibliographyRows() {
  if (!methodsBibliographyRowsEl) return;
  const start = methodsState.bibliographyRendered;
  const end = Math.min(start + BIBLIOGRAPHY_PAGE_SIZE, methodsState.bibliographyFilteredRows.length);
  const slice = methodsState.bibliographyFilteredRows.slice(start, end);
  methodsBibliographyRowsEl.insertAdjacentHTML("beforeend", slice.map(bibliographyRowHtml).join(""));
  methodsState.bibliographyRendered = end;
  if (methodsBibliographyLoadMoreEl) {
    methodsBibliographyLoadMoreEl.hidden = end >= methodsState.bibliographyFilteredRows.length;
    methodsBibliographyLoadMoreEl.textContent = `Load more (${formatNumber(methodsState.bibliographyFilteredRows.length - end)} remaining)`;
  }
  updateBibliographySummary();
}

function renderBibliography() {
  if (!methodsBibliographyRowsEl) return;
  const query = normalizeText(methodsBibliographySearchEl?.value || "");
  const queryTerms = query.split(" ").filter(Boolean);
  const stage = methodsBibliographyStageEl?.value || "";
  const kgStatus = methodsBibliographyKgStatusEl?.value || "";
  let rows = methodsState.bibliographyRows.filter((row) => {
    if (stage && row.stage_key !== stage) return false;
    if (kgStatus && row.kg_label !== kgStatus) return false;
    if (queryTerms.length && !queryTerms.every((term) => row.search_text.includes(term))) return false;
    return true;
  });
  rows = sortBibliographyRows(rows);
  methodsState.bibliographyFilteredRows = rows;
  methodsState.bibliographyRendered = 0;
  methodsBibliographyRowsEl.innerHTML = "";
  if (!rows.length) {
    methodsBibliographyRowsEl.innerHTML = `
      <tr>
        <td colspan="5" class="methods-bibliography-empty">No bibliography rows match the current filters.</td>
      </tr>
    `;
    if (methodsBibliographyLoadMoreEl) methodsBibliographyLoadMoreEl.hidden = true;
    updateBibliographySummary();
    return;
  }
  appendBibliographyRows();
}

function renderBibliographyError(error) {
  if (methodsBibliographySummaryEl) {
    methodsBibliographySummaryEl.textContent = `Bibliography is not available yet. ${error.message}`;
  }
  if (methodsBibliographyRowsEl) {
    methodsBibliographyRowsEl.innerHTML = `
      <tr>
        <td colspan="5" class="methods-bibliography-empty">Bibliography data is currently unavailable. Please try again later.</td>
      </tr>
    `;
  }
}

async function loadMethodsBibliography() {
  if (!methodsBibliographyRowsEl) return;
  if (methodsState.bibliographyPromise) return methodsState.bibliographyPromise;
  methodsState.bibliographyPromise = fetchJsonFromCandidates([
    "../data/kg/views/methods_bibliography.json",
    "/data/kg/views/methods_bibliography.json",
    "data/kg/views/methods_bibliography.json",
  ])
    .then((payload) => {
      methodsState.bibliographyPayload = payload;
      methodsState.bibliographyRows = bibliographyRowsFromPayload(payload);
      populateBibliographyStageFilter(payload);
      populateBibliographyKgStatusFilter(payload);
      renderBibliography();
    })
    .catch((error) => {
      renderBibliographyError(error);
    });
  return methodsState.bibliographyPromise;
}

function initMethodsBibliography() {
  if (!methodsBibliographySectionEl || !methodsBibliographyRowsEl) return;
  const load = () => {
    loadMethodsBibliography();
  };
  if ("IntersectionObserver" in window) {
    const observer = new IntersectionObserver((entries) => {
      if (!entries.some((entry) => entry.isIntersecting)) return;
      observer.disconnect();
      load();
    }, { rootMargin: "800px 0px" });
    observer.observe(methodsBibliographySectionEl);
  } else {
    load();
  }
}

function scheduleBibliographyRender() {
  if (!methodsState.bibliographyRows.length) {
    loadMethodsBibliography();
    return;
  }
  window.clearTimeout(methodsState.bibliographySearchTimer);
  methodsState.bibliographySearchTimer = window.setTimeout(renderBibliography, 80);
}

function renderMethodsError(error) {
  const message = `
    <div class="methods-error">
      Methods data is currently unavailable. Please try again later.
      <span>${escapeHtml(error.message)}</span>
    </div>
  `;
  if (methodsPipelineEl) methodsPipelineEl.innerHTML = message;
}

async function initMethods() {
  if (!methodsPipelineEl) return;
  try {
    const pipelineStatus = await fetchJsonFromCandidates([
      "../data/kg/views/pipeline_status_graph.json",
      "/data/kg/views/pipeline_status_graph.json",
      "data/kg/views/pipeline_status_graph.json",
    ]);
    methodsState.pipelineStatus = pipelineStatus;
    renderPipeline();
  } catch (error) {
    renderMethodsError(error);
  }
}

initMethods();
initMethodsBibliography();

methodsBibliographySearchEl?.addEventListener("input", scheduleBibliographyRender);
methodsBibliographyStageEl?.addEventListener("change", scheduleBibliographyRender);
methodsBibliographyKgStatusEl?.addEventListener("change", scheduleBibliographyRender);
methodsBibliographySortEl?.addEventListener("change", scheduleBibliographyRender);
methodsBibliographyLoadMoreEl?.addEventListener("click", appendBibliographyRows);
