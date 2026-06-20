const methodsPipelineEl = document.getElementById("methodsPipeline");

const methodsState = {
  pipelineStatus: null,
};
const dataFetchOptions =
  ["", "localhost", "127.0.0.1", "::1"].includes(window.location.hostname) ? { cache: "no-store" } : {};

const DATASET_LABELS = {
  disorder: "Clinical evidence",
  mechanistic: "Molecular, brain, and behavior evidence",
  overall: "Candidate paper pipeline",
};

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
          <span>${escapeHtml(reason.label)}</span>
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
    label: "Abstract-only records",
    count: 0,
  };
  const assessed = flow.assessed;
  const pending = flow.not_extracted;
  const excluded = flow.excluded;
  const included = flow.included_total || {
    label: "Included in KG from abstracts",
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
  return ["disorder", "mechanistic"].filter((key) => flows[key]).concat(
    Object.keys(flows).filter((key) => !["disorder", "mechanistic"].includes(key)),
  );
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

function renderMethodsError(error) {
  const message = `
    <div class="methods-error">
      Methods data is not available yet. Run <code>python pipeline/kg/build_methods_flow.py --refresh-kg-tables</code> from the project root, then refresh this page.
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
