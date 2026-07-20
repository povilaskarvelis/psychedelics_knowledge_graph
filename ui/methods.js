const methodsPipelineEl = document.getElementById("methodsPipeline");
const methodsBibliographySectionEl = document.getElementById("paper-bibliography");
const methodsBibliographySearchEl = document.getElementById("methodsBibliographySearch");
const methodsBibliographySummaryEl = document.getElementById("methodsBibliographySummary");
const methodsBibliographyRowsEl = document.getElementById("methodsBibliographyRows");
const methodsBibliographyLoadMoreEl = document.getElementById("methodsBibliographyLoadMore");
const PUBLIC_DATA_POINTER_URL = "https://data.psychedelicskg.com/browser/active.json";
const PUBLIC_DATA_POINTER_SCHEMAS = new Set(["psychedelics_kg_browser_r2_active_v1"]);
const REQUIRED_METHODS_DATA = new Set([
  "pipeline_status",
  "bibliography",
  "graph_inclusion_dispositions",
]);

const methodsState = {
  pipelineStatus: null,
  bibliographyRows: [],
  bibliographyFilteredRows: [],
  bibliographyRendered: 0,
  bibliographyPromise: null,
  bibliographySearchTimer: null,
  publicDataPointerPromise: null,
};
const dataFetchOptions =
  ["", "localhost", "127.0.0.1", "::1"].includes(window.location.hostname) ? { cache: "no-store" } : {};

const DATASET_LABELS = {
  overall: "Search and graph-inclusion flow",
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

function validatedPublicDataPointer(data) {
  const schemaVersion = String(data?.schema_version || "").trim();
  if (!PUBLIC_DATA_POINTER_SCHEMAS.has(schemaVersion)) {
    throw new Error("The public data pointer has an unsupported schema.");
  }
  const releaseId = String(data?.release_id || "").trim();
  const objectPrefix = String(data?.object_prefix || "").replace(/^\/+|\/+$/g, "");
  if (!releaseId || !objectPrefix.startsWith("browser/releases/")) {
    throw new Error("The public data pointer is missing its release identity.");
  }
  if (!data?.methods || typeof data.methods !== "object") {
    throw new Error("The public data pointer is missing Methods data.");
  }
  REQUIRED_METHODS_DATA.forEach((name) => {
    const key = String(data.methods[name] || "").replace(/^\/+/, "");
    if (!key || !key.startsWith(`${objectPrefix}/`)) {
      throw new Error(`The public data pointer is missing methods.${name}.`);
    }
  });
  return data;
}

async function loadPublicDataPointer() {
  if (methodsState.publicDataPointerPromise) return methodsState.publicDataPointerPromise;
  methodsState.publicDataPointerPromise = fetchJsonFromCandidates([PUBLIC_DATA_POINTER_URL])
    .then(validatedPublicDataPointer);
  return methodsState.publicDataPointerPromise;
}

async function loadMethodsData(name) {
  if (!REQUIRED_METHODS_DATA.has(name)) {
    throw new Error(`Unknown Methods dataset: ${name}`);
  }
  const pointer = await loadPublicDataPointer();
  const key = String(pointer.methods[name]).replace(/^\/+/, "");
  const url = new URL(key, `${new URL(PUBLIC_DATA_POINTER_URL).origin}/`).href;
  return fetchJsonFromCandidates([url]);
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
    <section class="prisma-panel" aria-label="PRISMA-style record and report flow">
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
      ${href ? `<a class="doi-link" href="${href}" target="_blank" rel="noopener noreferrer">${escapeHtml(doi)}</a>` : ""}
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
  const query = methodsBibliographySearchEl?.value?.trim() || "";
  const filterText = query
    ? `Filtered to ${formatNumber(filtered)} of ${formatNumber(total)} records.`
    : `${formatNumber(total)} records in the full search corpus.`;
  methodsBibliographySummaryEl.textContent = `${filterText} Showing ${formatNumber(rendered)}.`;
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
  const rows = methodsState.bibliographyRows.filter((row) => {
    if (queryTerms.length && !queryTerms.every((term) => row.search_text.includes(term))) return false;
    return true;
  });
  methodsState.bibliographyFilteredRows = rows;
  methodsState.bibliographyRendered = 0;
  methodsBibliographyRowsEl.innerHTML = "";
  if (!rows.length) {
    methodsBibliographyRowsEl.innerHTML = `
      <tr>
        <td colspan="5" class="methods-bibliography-empty">No records match your search.</td>
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
    methodsBibliographySummaryEl.textContent = `The full record audit is not available yet. ${error.message}`;
  }
  if (methodsBibliographyRowsEl) {
    methodsBibliographyRowsEl.innerHTML = `
      <tr>
        <td colspan="5" class="methods-bibliography-empty">Record data is currently unavailable. Please try again later.</td>
      </tr>
    `;
  }
}

async function loadMethodsBibliography() {
  if (!methodsBibliographyRowsEl) return;
  if (methodsState.bibliographyPromise) return methodsState.bibliographyPromise;
  methodsState.bibliographyPromise = loadMethodsData("bibliography")
    .then((payload) => {
      methodsState.bibliographyRows = bibliographyRowsFromPayload(payload);
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
    const pipelineStatus = await loadMethodsData("pipeline_status");
    methodsState.pipelineStatus = pipelineStatus;
    renderPipeline();
  } catch (error) {
    renderMethodsError(error);
  }
}

initMethods();
initMethodsBibliography();

methodsBibliographySearchEl?.addEventListener("input", scheduleBibliographyRender);
methodsBibliographyLoadMoreEl?.addEventListener("click", appendBibliographyRows);
