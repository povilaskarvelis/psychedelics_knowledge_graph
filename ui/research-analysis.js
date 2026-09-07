/* Evidence coverage supplements the main Analyze charts. */
const RESEARCH_FIELDS = {
  population: "Population / model", design: "Study design", outcome: "Outcome / measure",
  comparator: "Comparator", followup: "Follow-up", system: "Experimental system",
  assay: "Assay / method", topic: "Topic", area: "Research area", compound: "Compound",
};
let researchCoverageAxes = ["population", "design"];
let researchCategoryQueries = ["", ""];
let researchCoverageCell = null;
let researchRowCache = new WeakMap();
let researchCoverageRows = [];
let researchCoverageCache = null;

function researchList(...parts) {
  return [...new Set(parts.flat().map(meaningfulText).filter(Boolean))];
}

function researchRow(claim) {
  if (researchRowCache.has(claim)) return researchRowCache.get(claim);
  const primary = !isSecondaryLiteratureClaim(claim);
  const areas = ENTITY_CATEGORY_OPTIONS.filter((area) => claimMatchesEntityViewOption(claim, area));
  const fields = {
    design: researchList(primary ? studyDesignFacetLabel(claim) : isMetaAnalysisClaim(claim) ? metaAnalysisDesignFacetLabel(claim) : reviewDesignFacetLabel(claim)),
    population: researchList(populationModelFacetLabel(claim)),
    comparator: researchList(clinicalComparatorFacetLabel(claim)),
    followup: researchList(clinicalFollowUpWindowFacetLabel(claim)),
    outcome: researchList(outcomeScaleLabelsForClaim(claim)),
    system: researchList(analysisExperimentalSystemFacetLabel(claim)),
    assay: researchList(mechanisticAssayFamilyFacetLabel(claim), brainMeasureFacetLabels(claim)),
    area: areas.map((area) => area.label),
    topic: researchList(areas.map((area) => analysisConceptLabelForClaim(claim, area.key))),
    compound: researchList(analysisCompoundSubjectsForClaim(claim).map((subject) => subject.label)),
  };
  const row = {
    claim, fields, paperKey: studyKey(claim, 0), year: parseYearValue(claim.study_year),
    title: meaningfulText(claim.study_title) || "Untitled report",
  };
  researchRowCache.set(claim, row);
  return row;
}

function researchBaseRows({ ignoreFocus = false } = {}) {
  // Always reapply scope on findings. The publication index may have matched a
  // different finding in the same paper, or a different evidence type.
  const items = (claimStores.normalized.bySource.all || []).filter((claim) => !isHiddenMainGraphItem(claim) && isMainGraphAdmitted(claim));
  const min = parseYearValue(yearMinFilter?.value);
  const max = parseYearValue(yearMaxFilter?.value);
  const scoped = analysisClaimsWithinScope(items.filter((claim) => {
    const year = parseYearValue(claim.study_year);
    if (year === null || (min !== null && year < min) || (max !== null && year > max)) return false;
    if (accessView === "open" && !isOpenAccessClaim(claim)) return false;
    if (evidenceView === "primary" && isSecondaryLiteratureClaim(claim)) return false;
    if (evidenceView === "meta_analyses" && !isMetaAnalysisClaim(claim)) return false;
    if (evidenceView === "reviews" && !isReviewLiteratureClaim(claim)) return false;
    return true;
  }));
  const entityRows = analysisClaimsWithCurrentEntity(scoped);
  return (ignoreFocus ? entityRows : analysisClaimsForFocusedEntity(entityRows)).map(researchRow);
}

function researchCaptureState() {
  return { axes: [...researchCoverageAxes], queries: [...researchCategoryQueries], cell: researchCoverageCell ? [...researchCoverageCell] : null };
}

function researchValidateState(raw) {
  const input = raw && typeof raw === "object" ? raw : {};
  const axes = Array.isArray(input.axes) && input.axes.length === 2 && input.axes.every((key) => typeof key === "string" && Object.hasOwn(RESEARCH_FIELDS, key)) && input.axes[0] !== input.axes[1]
    ? [...input.axes] : ["population", "design"];
  const pair = (value) => Array.isArray(value) && value.length === 2 && value.every((entry) => typeof entry === "string");
  return {
    axes,
    queries: pair(input.queries) ? input.queries.map((value) => value.slice(0, 200)) : ["", ""],
    cell: pair(input.cell) ? input.cell.map((value) => value.slice(0, 1000)) : null,
  };
}

function researchApplyState(raw) {
  const state = researchValidateState(raw);
  researchCoverageAxes = state.axes;
  researchCategoryQueries = state.queries;
  researchCoverageCell = state.cell;
}

function researchUrlState(url) {
  ["task", "research", "coverage"].forEach((key) => url.searchParams.delete(key));
  if (explorerMode !== "analysis") {
    ["from", "to"].forEach((key) => url.searchParams.delete(key));
    return;
  }
  ["from", "to"].forEach((key) => url.searchParams.delete(key));
  if (yearMinFilter.value) url.searchParams.set("from", yearMinFilter.value);
  if (yearMaxFilter.value) url.searchParams.set("to", yearMaxFilter.value);
  const state = researchCaptureState();
  if (state.axes.join() !== "population,design" || state.queries.some(Boolean) || state.cell) url.searchParams.set("coverage", JSON.stringify(state));
}

function researchReadUrl(params) {
  let state = {};
  try { state = JSON.parse((params.get("coverage") || params.get("research") || "{}").slice(0, 16000)); } catch (_) { /* Malformed links use defaults. */ }
  // Legacy task links open Analyze without silently applying old evidence filters.
  researchApplyState(state);
  yearFilterState[currentYearFilterKey()] = { min: params.get("from") || "", max: params.get("to") || "" };
}

function researchUpdateControls() {
  const navigation = document.getElementById("researchNavigation");
  if (navigation) navigation.hidden = false;
}

function researchScopeChanged() {
  researchCoverageCell = null;
  researchCategoryQueries = ["", ""];
}

function researchCoverageView(rows) {
  const axesKey = researchCoverageAxes.join();
  if (researchCoverageCache?.rows !== rows || researchCoverageCache.axesKey !== axesKey) {
    researchCoverageCache = { rows, axesKey, matrix: PKGResearch.coverage(rows, ...researchCoverageAxes) };
  }
  const matrix = researchCoverageCache.matrix;
  const matches = (labels, query) => labels.filter((label) => label.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
  const rowLabels = matches(matrix.rows, researchCategoryQueries[0]);
  const columnLabels = matches(matrix.columns, researchCategoryQueries[1]);
  // A shared cell remains visible even outside the leading categories.
  const visible = (labels, limit, selected) => {
    const leading = labels.slice(0, limit);
    return selected && labels.includes(selected) && !leading.includes(selected)
      ? [...leading.slice(0, limit - 1), selected] : leading;
  };
  return { matrix, rowLabels, columnLabels,
    rows: visible(rowLabels, 18, researchCoverageCell?.[0]),
    columns: visible(columnLabels, 12, researchCoverageCell?.[1]) };
}

function researchCoverageResults() {
  const view = researchCoverageView(researchCoverageRows);
  const { matrix, rows, columns } = view;
  let max = 1;
  matrix.cells.forEach((keys) => { max = Math.max(max, keys.size); });
  const selectionCount = researchCoverageCell ? matrix.cells.get(JSON.stringify(researchCoverageCell))?.size || 0 : 0;
  return `${rows.length && columns.length ? `<div class="research-table-scroll" tabindex="0" role="region" aria-label="Evidence coverage matrix"><table class="research-matrix"><thead><tr><th scope="col">${escapeHtml(RESEARCH_FIELDS[researchCoverageAxes[0]])}</th>${columns.map((label) => `<th scope="col">${escapeHtml(label)}</th>`).join("")}</tr></thead><tbody>${rows.map((a) => `<tr><th scope="row">${escapeHtml(a)}</th>${columns.map((b) => {
    const count = matrix.cells.get(JSON.stringify([a, b]))?.size || 0;
    const active = researchCoverageCell?.[0] === a && researchCoverageCell?.[1] === b;
    return `<td><button type="button" data-research-cell-a="${escapeHtml(a)}" data-research-cell-b="${escapeHtml(b)}" aria-pressed="${active}" aria-label="${escapeHtml(`${a}, ${b}: ${count} reports`)}" style="--coverage-strength:${count ? 0.12 + 0.65 * Math.sqrt(count / max) : 0}" ${count ? "" : "disabled"}>${count}</button></td>`;
  }).join("")}</tr>`).join("")}</tbody></table></div>` : '<p class="analytics-empty compact">No matching coverage.</p>'}
    ${researchCoverageCell ? `<div class="research-cell-selection"><span>${escapeHtml(researchCoverageCell.join(" × "))} · ${selectionCount} reports</span><button type="button" class="ghost small" data-research-open-cell ${selectionCount ? "" : "disabled"}>View findings</button><button type="button" class="ghost small" data-research-clear-cell>Clear selection</button></div>` : ""}`;
}

function researchAppendCoverage(content) {
  if (!content || explorerMode !== "analysis" || content.querySelector(".research-coverage")) return;
  researchCoverageRows = researchBaseRows();
  const panel = document.createElement("section");
  panel.className = "analytics-panel research-coverage";
  panel.innerHTML = `<div class="analytics-panel-heading"><h3>Evidence coverage</h3></div>
    <div class="research-coverage-body">
    <div class="research-coverage-controls">${researchCoverageAxes.map((axis, index) => {
      const position = index ? "Columns" : "Rows";
      const valueLabel = RESEARCH_FIELDS[axis].toLocaleLowerCase();
      return `<div class="research-axis-controls"><label class="analysis-publication-field research-coverage-field"><span>${position}</span><select data-research-axis="${index}" aria-label="Evidence coverage ${position.toLocaleLowerCase()}">${Object.entries(RESEARCH_FIELDS).filter(([key]) => key !== researchCoverageAxes[1 - index]).map(([key, label]) => `<option value="${key}" ${key === axis ? "selected" : ""}>${escapeHtml(label)}</option>`).join("")}</select></label><label class="analysis-publication-field research-coverage-field"><span>Search ${position.toLocaleLowerCase()}</span><input type="search" data-research-category="${index}" aria-label="Search ${valueLabel} values used as ${position.toLocaleLowerCase()}" maxlength="200" autocomplete="off" spellcheck="false" value="${escapeHtml(researchCategoryQueries[index])}" placeholder="Search ${escapeHtml(valueLabel)}" /></label></div>`;
    }).join("")}</div>
    <div data-research-coverage-results>${researchCoverageResults()}</div></div>`;
  content.appendChild(panel);
}

function researchRefreshCoverage({ updateUrl = true } = {}) {
  const results = graphEl.querySelector("[data-research-coverage-results]");
  if (results) results.innerHTML = researchCoverageResults();
  if (updateUrl) updateExplorerUrlState();
}

function researchOpenCoverageCell({ scroll = true } = {}) {
  if (!researchCoverageCell) return;
  const rows = PKGResearch.matchingCell(researchCoverageRows, ...researchCoverageAxes, ...researchCoverageCell);
  if (!rows.length) return;
  renderExplorerSelectionDetail(researchCoverageCell.join(" · "), rows.map((row) => row.claim));
  if (scroll) document.querySelector(".findings-section")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function researchClearCoverageSelection() {
  if (!researchCoverageCell) return;
  researchCoverageCell = null;
  clearDetailForTransition();
  cardsEl.replaceChildren();
  studyListEl?.replaceChildren();
  activeDetailItems = [];
  activeDetailAllAccessItems = [];
}

function researchHandleClick(event) {
  const button = event.target.closest?.("button");
  if (!button) return false;
  const data = button.dataset;
  if ("researchCopy" in data) {
    copyExplorerViewLink();
  } else if ("researchCellA" in data) {
    researchCoverageCell = [data.researchCellA, data.researchCellB];
    researchRefreshCoverage({ updateUrl: false });
    updateExplorerUrlState({ history: "push" });
    researchOpenCoverageCell();
  } else if ("researchOpenCell" in data) researchOpenCoverageCell();
  else if ("researchClearCell" in data) { researchClearCoverageSelection(); researchRefreshCoverage(); }
  else return false;
  event.preventDefault();
  return true;
}

function researchHandleChange(event) {
  const index = Number(event.target.dataset.researchAxis);
  if (event.target.dataset.researchAxis === undefined || ![0, 1].includes(index)) return false;
  if (!Object.hasOwn(RESEARCH_FIELDS, event.target.value) || event.target.value === researchCoverageAxes[1 - index]) return true;
  researchCoverageAxes[index] = event.target.value;
  researchClearCoverageSelection();
  researchScopeChanged();
  const panel = graphEl.querySelector(".research-coverage");
  const content = panel?.parentElement;
  panel?.remove();
  researchAppendCoverage(content);
  updateExplorerUrlState();
  graphEl.querySelector(`[data-research-axis="${index}"]`)?.focus({ preventScroll: true });
  return true;
}

document.addEventListener("click", (event) => {
  if (event.target.closest?.("#researchNavigation")) researchHandleClick(event);
});
document.addEventListener("input", (event) => {
  const value = event.target.dataset.researchCategory;
  if (value === undefined || !["0", "1"].includes(value)) return;
  researchCategoryQueries[Number(value)] = event.target.value.slice(0, 200);
  researchClearCoverageSelection();
  researchRefreshCoverage();
});
