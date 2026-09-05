/* Task-oriented analysis. The existing graph supplies canonical findings and
 * domain labelers; research-model.js owns publication-level calculations. */
const RESEARCH_TASKS = new Set(["landscape", "compare", "evidence"]);
const RESEARCH_FIELDS = {
  design: "Study design", population: "Population / model", comparator: "Comparator",
  followup: "Follow-up", outcome: "Outcome / measure", system: "Experimental system",
  assay: "Assay / method", area: "Research area", topic: "Topic", compound: "Compound",
  paperType: "Paper type", transparency: "Reporting signals", relationship: "Relationship type",
  graphSubject: "Graph subject",
};
const RESEARCH_SAVE_KEY = "psychedelics-kg-research-questions-v1";
let analysisTask = "landscape";
let researchFilters = {};
let researchCompare = [];
let researchCompareKind = "compound";
let researchCompareMetric = "count";
let researchCompareField = "area";
let researchTableMode = "studies";
let researchCoverageAxes = ["population", "design"];
let researchCoverageCell = null;
let researchPage = 0;
let researchChangeReview = null;
let researchChangeSubset = "";
let researchPendingSaved = null;
let researchRelease = "";
let researchRenderedRows = [];
let researchCompareCandidates = [];
let researchRowCache = new WeakMap();
let researchCurrentSavedId = "";
let researchCoverageExpanded = false;

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
    graphSubject: researchList(graphOverviewSubjectsForClaim(claim).map((subject) => subject.label)),
    paperType: [primary ? "Primary studies" : isMetaAnalysisClaim(claim) ? "Meta-analyses" : "Reviews"],
    transparency: researchList(openScienceFacetValues(claim)),
    relationship: researchList(claim.mechanistic_relationship_type, claim.brain_relationship_type, claim.relation_type),
  };
  // Never treat a meta-analysis participant total as the size of a primary study.
  const sample = primary ? parseSampleSize(claim.sample_size_total) : null;
  const row = {
    claim, fields, sample: Number.isFinite(sample) && sample > 0 ? sample : null,
    paperKey: studyKey(claim, 0), year: parseYearValue(claim.study_year),
    title: meaningfulText(claim.study_title) || "Untitled report",
  };
  row.search = researchList(row.title, claimMainFindingText(claim), Object.values(fields).flat(),
    claim.support, claim.population, claim.population_or_subgroup, claim.comparator, claim.effect_size, claim.study_doi).join(" ").toLocaleLowerCase();
  row.signature = JSON.stringify([row.title, row.year, fields, row.sample,
    ...["population", "population_or_subgroup", "sample_size_by_arm", "dose", "administration_route", "session_context",
      "comparator", "timepoint", "follow_up_duration", "effect_size", "p_value", "risk_of_bias_summary",
      "evidence_strength", "heterogeneity_i_squared", "meta_analysis_subgroup_or_moderator", "evidence_location",
      "source_access_level", "notes", "extraction_warnings", "supporting_quote", "heterogeneity_interpretation"].map((key) => meaningfulText(claim[key])), meaningfulText(claim.support) || claimMainFindingText(claim)]);
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
  return (ignoreFocus ? scoped : analysisClaimsForFocusedEntity(scoped)).map(researchRow);
}

function researchSelectedRows() {
  let rows = PKGResearch.filter(researchChangeReview?.comparisonRows || researchBaseRows(), researchFilters);
  if (researchCoverageCell) rows = PKGResearch.matchingCell(rows, ...researchCoverageAxes, ...researchCoverageCell);
  if (researchChangeSubset && researchChangeReview) {
    const keys = new Set(researchChangeReview[researchChangeSubset] || []);
    rows = rows.filter((row) => keys.has(row.paperKey));
  }
  return rows;
}

function researchFilterClaims(items) {
  return Object.values(researchFilters).some(Boolean)
    ? PKGResearch.filter(items.map(researchRow), researchFilters).map((row) => row.claim)
    : items;
}

function researchOption(value, label, selectedValue) {
  return `<option value="${escapeHtml(value)}"${value === selectedValue ? " selected" : ""}>${escapeHtml(label)}</option>`;
}

function researchSelect(field, label, options, value, attribute = "data-research-filter") {
  return `<label class="research-field"><span>${escapeHtml(label)}</span><select ${attribute}="${escapeHtml(field)}" aria-label="${escapeHtml(label)}">${options.map(([key, text]) => researchOption(key, text, value)).join("")}</select></label>`;
}

function researchStatus(message) {
  const status = document.getElementById("researchStatus");
  if (status) status.textContent = message;
}

function researchUpdateControls() {
  const navigation = document.getElementById("researchNavigation");
  if (!navigation) return;
  navigation.hidden = explorerMode !== "analysis";
  navigation.querySelectorAll("[data-research-task]").forEach((button) => {
    const active = button.dataset.researchTask === analysisTask;
    button.setAttribute("aria-selected", String(active));
    button.classList.toggle("active", active);
  });
  const helper = document.getElementById("researchTaskDescription");
  if (helper) helper.textContent = {
    landscape: "Map research activity, coverage, and the people behind it.",
    compare: "Compare research profiles under the same scope and filters.",
    evidence: "Examine methods, populations, results, and limitations across source reports.",
  }[analysisTask];
  document.querySelectorAll(".analysis-query-entity, #explorerNavigationRow").forEach((element) => {
    element.hidden = analysisTask === "compare";
  });
  const filtersActive = Object.values(researchFilters).some(Boolean);
  const badge = document.getElementById("researchFiltersNotice");
  if (badge) {
    badge.hidden = !filtersActive || analysisTask !== "landscape";
    badge.textContent = `Evidence filters: ${Object.entries(researchFilters).filter(([, value]) => value).map(([field, value]) => `${RESEARCH_FIELDS[field] || field}: ${value}`).join(" · ")}. Adjust these in Evidence.`;
  }
  researchRenderSavedList();
}

function researchResetView() {
  researchPage = 0;
  researchCoverageCell = null;
  researchChangeSubset = "";
}

function switchResearchTask(task) {
  if (!RESEARCH_TASKS.has(task)) return;
  if (task !== analysisTask) researchScopeChanged();
  if (task === "compare" && explorerFocus && EXPLORER_ENTITY_LENSES.has(explorerLens)) {
    const candidate = { kind: explorerLens, key: explorerFocus.key, label: explorerFocus.label, filters: {} };
    if (!researchCompare.some((entry) => entry.kind === candidate.kind && entry.key === candidate.key) && researchCompare.length < 4) researchCompare.push(candidate);
  }
  analysisTask = task;
  researchResetView();
  if (task === "compare") {
    explorerFocus = null;
    explorerLens = "all";
    explorerLastAnalysisLens = "all";
  }
  updateExplorerControls();
  updateExplorerUrlState();
  loadAnalysisAndRender({ resetYears: false });
}

function researchRenderFilters(rows) {
  const mechanistic = ["target_system", "pathway_readout", "brain_system"].includes(explorerScopeAreaKey);
  const preferred = mechanistic
    ? ["population", "system", "assay", "design", "outcome", "relationship"]
    : ["design", "population", "comparator", "followup", "outcome", "system"];
  const fields = [...new Set([...preferred, ...Object.keys(researchFilters).filter((key) => Object.hasOwn(RESEARCH_FIELDS, key))])];
  const controls = fields.map((field) => {
    const others = { ...researchFilters, [field]: "" };
    const distribution = PKGResearch.distribution(PKGResearch.filter(rows, others), field);
    const entries = distribution.map((entry) => [entry.label, `${entry.label} (${entry.count})`]);
    if (researchFilters[field] && !entries.some(([value]) => value === researchFilters[field])) entries.unshift([researchFilters[field], `${researchFilters[field]} (0)`]);
    return researchSelect(field, RESEARCH_FIELDS[field], [["", "Any"], ...entries], researchFilters[field] || "");
  }).join("");
  return `<form class="research-filter-grid" data-research-filter-form>
    ${controls}
    <label class="research-field"><span>Minimum sample (primary only)</span><input type="number" min="1" step="1" data-research-filter="minSample" aria-label="Minimum sample size" value="${escapeHtml(researchFilters.minSample || "")}" placeholder="Any" /></label>
    <label class="research-field research-query"><span>Search reports and findings</span><input type="search" data-research-query aria-label="Search evidence" value="${escapeHtml(researchFilters.query || "")}" placeholder="Outcome, population, method, or DOI" /></label>
    <button class="ghost small" type="submit">Apply search</button>
    <button class="ghost small" type="button" data-research-clear>Clear evidence filters</button>
  </form>`;
}

function researchScopeSummary(rows) {
  const papers = PKGResearch.papers(rows);
  const primary = papers.filter((paper) => paper.rows.some((row) => row.fields.paperType.includes("Primary studies"))).length;
  const meta = papers.filter((paper) => paper.rows.some((row) => row.fields.paperType.includes("Meta-analyses"))).length;
  const reviews = papers.filter((paper) => paper.rows.some((row) => row.fields.paperType.includes("Reviews"))).length;
  return `<div class="research-summary" aria-live="polite">
    <span><strong>${formatCompactNumber(papers.length)}</strong> source reports</span>
    <span><strong>${formatCompactNumber(rows.length)}</strong> matching findings</span>
    <span>${formatCompactNumber(primary)} primary · ${formatCompactNumber(meta)} meta-analyses · ${formatCompactNumber(reviews)} reviews</span>
  </div>`;
}

function researchValue(value) {
  return meaningfulText(value) ? escapeHtml(meaningfulText(value)) : '<span class="research-missing">Not recorded</span>';
}

function researchFieldValues(paper, field) {
  const values = PKGResearch.paperValues(paper, field);
  return values.length === 1 && values[0] === PKGResearch.MISSING ? researchValue("") : values.map(escapeHtml).join("<br/>");
}

function researchClaimValues(paper, ...fields) {
  return researchValue(researchList(paper.rows.flatMap((row) => fields.map((field) => row.claim[field]))).join(" · "));
}

function researchPaperReference(row) {
  return `${studyReferenceHtml(row.claim, "research-citation")}<span class="research-source-type">${escapeHtml(row.fields.paperType[0])} · ${isOpenAccessClaim(row.claim) ? "Full-text extraction" : "Abstract / other text"}</span>`;
}

function researchAppraisal(claim) {
  const recorded = [
    ["Risk of bias reported by source", claim.risk_of_bias_summary],
    ["Certainty reported by source", claim.evidence_strength],
    ["Heterogeneity", researchList(claim.heterogeneity_i_squared, claim.heterogeneity_interpretation).join(" · ")],
    ["Subgroup / sensitivity analysis", claim.meta_analysis_subgroup_or_moderator],
  ].filter(([, value]) => meaningfulText(value));
  return `${recorded.length ? `<dl>${recorded.map(([label, value]) => `<dt>${escapeHtml(label)}</dt><dd>${researchValue(value)}</dd>`).join("")}</dl>` : '<p class="research-missing">No source appraisal recorded for this finding.</p>'}
    ${meaningfulText(claim.notes) ? `<dl><dt>Extracted notes and uncertainty</dt><dd>${researchValue(claim.notes)}</dd></dl>` : ""}
    ${meaningfulText(claim.extraction_warnings) ? `<details><summary>Extraction notes</summary>${researchValue(claim.extraction_warnings)}</details>` : ""}`;
}

function researchTable(rows) {
  const papers = PKGResearch.papers(rows);
  const results = researchTableMode === "results";
  const records = results ? papers.flatMap((paper) => paper.rows) : papers;
  const size = results ? 40 : 25;
  researchPage = Math.min(researchPage, Math.max(0, Math.ceil(records.length / size) - 1));
  const shown = records.slice(researchPage * size, (researchPage + 1) * size);
  const headings = results
    ? ["Source report", "Outcome and context", "Reported result", "Limitations and appraisal"]
    : ["Source report", "Design and population", "Sample and intervention", "Comparator and follow-up", "Outcomes / methods"];
  const body = shown.map((record) => {
    if (results) {
      const row = record;
      const claim = row.claim;
      return `<tr><td>${researchPaperReference(row)}<button class="ghost small" data-research-paper="${escapeHtml(row.paperKey)}">Open findings</button></td>
        <td><strong>${researchValue(row.fields.topic.join(" · "))}</strong><p>${researchValue(row.fields.outcome.join(" · "))}</p>
          <dl><dt>Population / system</dt><dd>${researchValue(claim.population || claim.population_or_subgroup || claim.system)}</dd>
          <dt>Comparator</dt><dd>${researchValue(claim.comparator_normalized || claim.comparator)}</dd>
          <dt>Timepoint</dt><dd>${researchValue(claim.timepoint || claim.follow_up_duration)}</dd></dl></td>
        <td>${researchValue(meaningfulText(claim.support) || claimMainFindingText(claim))}<dl><dt>Estimate as reported</dt><dd>${researchValue(claim.effect_size)}</dd>
          ${meaningfulText(claim.p_value) ? `<dt>P value</dt><dd>${researchValue(claim.p_value)}</dd>` : ""}<dt>Source location</dt><dd>${researchValue(claim.evidence_location || claim.evidence_locator)}</dd></dl></td>
        <td>${researchAppraisal(claim)}</td></tr>`;
    }
    const paper = record;
    const row = paper.rows[0];
    return `<tr><td>${researchPaperReference(row)}<button class="ghost small" data-research-paper="${escapeHtml(paper.key)}">Open ${paper.rows.length} matching ${paper.rows.length === 1 ? "finding" : "findings"}</button></td>
      <td>${researchFieldValues(paper, "design")}<p>${researchFieldValues(paper, "population")}</p><details><summary>Population / system details</summary>${researchClaimValues(paper, "population", "population_or_subgroup", "system")}</details></td>
      <td><dl><dt>Reported sample size(s)</dt><dd>${researchClaimValues(paper, "sample_size_total")}</dd><dt>Dose</dt><dd>${researchClaimValues(paper, "dose")}</dd>
        <dt>Route / session</dt><dd>${researchClaimValues(paper, "administration_route", "route", "session_context")}</dd></dl></td>
      <td>${researchFieldValues(paper, "comparator")}<p>${researchFieldValues(paper, "followup")}</p><details><summary>Exact comparators and timepoints</summary>${researchClaimValues(paper, "comparator", "follow_up_duration", "timepoint")}</details></td>
      <td>${researchFieldValues(paper, "outcome")}<p>${researchFieldValues(paper, "assay")}</p><details><summary>Research topics</summary>${researchFieldValues(paper, "topic")}</details></td></tr>`;
  }).join("");
  return `<section class="analytics-panel research-evidence-table"><div class="research-panel-heading"><h3>${results ? "Results and limitations" : "Study characteristics"}</h3>
    <div class="research-switch" role="group" aria-label="Evidence table view">
      <button data-research-table="studies" aria-pressed="${!results}">Study characteristics</button>
      <button data-research-table="results" aria-pressed="${results}">Results & limitations</button></div></div>
    <p class="research-note">${results ? "One row per finding. Estimates remain as reported; no effects are pooled or ranked. Appraisals belong to the source and its stated scope." : "One row per publication. Multiple reports may use the same participants; sample sizes are not added. Expand details to inspect differing measurements within a report."}</p>
    ${records.length ? `<div class="research-table-scroll" tabindex="0" role="region" aria-label="${results ? "Results and limitations" : "Study characteristics"} table"><table class="research-table"><thead><tr>${headings.map((heading) => `<th scope="col">${heading}</th>`).join("")}</tr></thead><tbody>${body}</tbody></table></div>` : '<div class="analytics-empty">No matching evidence. Clear a filter or broaden the research scope.</div>'}
    <div class="research-pagination"><span>${records.length ? `${researchPage * size + 1}–${Math.min(records.length, (researchPage + 1) * size)} of ${formatCompactNumber(records.length)}` : "0 records"}</span>
      <button class="ghost small" data-research-page="-1" ${researchPage ? "" : "disabled"}>Previous</button><button class="ghost small" data-research-page="1" ${(researchPage + 1) * size < records.length ? "" : "disabled"}>Next</button></div></section>`;
}

function researchCoverage(rows) {
  const dimensions = ["population", "design", "outcome", "followup", "system", "assay", "topic", "area", "compound"];
  const options = dimensions.map((key) => [key, RESEARCH_FIELDS[key]]);
  const matrix = PKGResearch.coverage(rows, ...researchCoverageAxes);
  const visibleRows = matrix.rows.slice(0, 18);
  const columns = matrix.columns.slice(0, 12);
  const max = Math.max(1, ...[...matrix.cells.values()].map((keys) => keys.size));
  return `<section class="analytics-panel research-coverage"><div class="research-panel-heading"><h3>Evidence coverage</h3>
    <div class="research-inline-fields">${researchSelect("0", "Rows", options, researchCoverageAxes[0], "data-research-axis")}${researchSelect("1", "Columns", options, researchCoverageAxes[1], "data-research-axis")}</div></div>
    <p class="research-note">Unique reports with both characteristics recorded in this scope. A shared report does not establish an association between them. Zero means no matching indexed reports; “Not recorded” means missing metadata.</p>
    ${matrix.rows.length ? `<div class="research-table-scroll" tabindex="0" role="region" aria-label="Evidence coverage matrix"><table class="research-matrix"><thead><tr><th scope="col">${escapeHtml(RESEARCH_FIELDS[researchCoverageAxes[0]])}</th>${columns.map((label) => `<th scope="col">${escapeHtml(label)}</th>`).join("")}</tr></thead><tbody>${visibleRows.map((a) => `<tr><th scope="row">${escapeHtml(a)}</th>${columns.map((b) => {
      const count = matrix.cells.get(JSON.stringify([a, b]))?.size || 0;
      const active = researchCoverageCell?.[0] === a && researchCoverageCell?.[1] === b;
      return `<td><button data-research-cell-a="${escapeHtml(a)}" data-research-cell-b="${escapeHtml(b)}" aria-pressed="${active}" aria-label="${escapeHtml(`${a}, ${b}: ${count} reports`)}" style="--coverage-strength:${count ? 0.12 + 0.65 * Math.sqrt(count / max) : 0}" ${count ? "" : "disabled"}>${count}</button></td>`;
    }).join("")}</tr>`).join("")}</tbody></table></div>` : '<div class="analytics-empty compact">No coverage in this scope.</div>'}
    <p class="research-note">${visibleRows.length} of ${matrix.rows.length} rows · ${columns.length} of ${matrix.columns.length} columns, ordered by report count. Narrow the scope or use evidence filters to inspect smaller categories.</p>
    ${researchCoverageCell ? `<div class="research-cell-selection">Table filtered to ${escapeHtml(researchCoverageCell.join(" × "))}<button class="ghost small" data-research-clear-cell>Clear cell selection</button></div>` : ""}</section>`;
}

function researchChangesMarkup() {
  if (!researchChangeReview) return "";
  const changes = researchChangeReview;
  return `<div class="research-change-banner" role="status"><strong>Since ${escapeHtml(changes.date || "the saved baseline")}</strong>
    <span>${changes.added.length} new to this question · ${changes.changed.length} changed reports · ${changes.removed.length} no longer matching</span>
    <p>Changes can reflect newly indexed research, corrections, or extraction updates. This compares the same saved question with its baseline.</p>
    <button class="ghost small" data-research-changes="added" ${changes.added.length ? "" : "disabled"}>Inspect new reports</button>
    <button class="ghost small" data-research-changes="changed" ${changes.changed.length ? "" : "disabled"}>Inspect changed reports</button>
    <button class="ghost small" data-research-changes="">Show all matches</button>
    <button class="ghost small" data-research-baseline>Use current evidence as baseline</button></div>`;
}

function renderResearchEvidence() {
  const base = researchChangeReview?.comparisonRows || researchBaseRows();
  const filtered = PKGResearch.filter(base, researchFilters);
  const rows = researchSelectedRows();
  researchRenderedRows = rows;
  if (isAnalysisEntitySection() && !explorerFocus) explorerSearchMatrix = buildExplorerMatrix(explorerFilteredClaims());
  graphEl.innerHTML = `<div class="analytics-workspace research-workspace">
    ${researchChangesMarkup()}${researchRenderFilters(base)}${researchScopeSummary(rows)}
    <div class="research-actions"><button class="ghost small" data-research-pin>Add this evidence set to comparison</button><span>Filters apply together to each finding; report summaries retain the matching findings.</span></div>
    <details class="research-coverage-disclosure" ${researchCoverageExpanded || researchCoverageCell ? "open" : ""}><summary>Explore evidence coverage across populations, outcomes, and methods</summary>${researchCoverage(filtered)}</details>
    ${researchTable(rows)}
    <details class="analytics-panel research-transparency"><summary>Reporting and reproducibility</summary>${renderAnalysisTransparencyPanel(rows.map((row) => row.claim))}</details>
  </div>`;
  researchClearRecords(rows);
  autosizeExplorerWorkspace(graphEl.firstElementChild);
}

function researchClearRecords(rows) {
  activeDetailItems = rows.map((row) => row.claim);
  activeDetailAllAccessItems = activeDetailItems;
  disconnectCardsLoadObserver();
  disconnectBibliographyLoadObserver();
  cardsEl.replaceChildren();
  studyListEl?.replaceChildren();
}

function researchCandidateRows(rows, candidate) {
  let selectedRows = rows;
  if (candidate.kind === "area") selectedRows = rows.filter((row) => row.fields.area.includes(candidate.key));
  else if (candidate.kind === "topic") selectedRows = rows.filter((row) => row.fields.topic.includes(candidate.key));
  else if (EXPLORER_ENTITY_LENSES.has(candidate.kind)) {
    const aliases = candidate.kind === "author" ? buildAuthorRoleAliasMap(rows.map((row) => row.claim)) : null;
    selectedRows = rows.filter((row) => explorerEntityValuesForClaim(row.claim, aliases, candidate.kind).some((entry) => normalizeValue(entry.value || entry.label) === normalizeValue(candidate.key)));
  }
  if (candidate.scope) {
    const scope = candidate.scope;
    const area = ENTITY_CATEGORY_OPTIONS.find((entry) => entry.key === scope.area);
    selectedRows = selectedRows.filter((row) => {
      if (area && !claimMatchesEntityViewOption(row.claim, area)) return false;
      if (area && scope.concept && normalizeValue(analysisConceptLabelForClaim(row.claim, area.key)) !== scope.concept) return false;
      if (scope.min && row.year < Number(scope.min)) return false;
      if (scope.max && row.year > Number(scope.max)) return false;
      if (scope.access === "open" && !isOpenAccessClaim(row.claim)) return false;
      const paperType = { primary: "Primary studies", meta_analyses: "Meta-analyses", reviews: "Reviews" }[scope.evidence];
      return !paperType || row.fields.paperType.includes(paperType);
    });
  }
  selectedRows = PKGResearch.filter(selectedRows, candidate.filters || {});
  return candidate.coverage ? PKGResearch.matchingCell(selectedRows, ...candidate.coverage.axes, ...candidate.coverage.cell) : selectedRows;
}

function researchCandidates(rows, kind) {
  if (kind === "area" || kind === "topic") return PKGResearch.distribution(rows, kind).filter((entry) => entry.label !== PKGResearch.MISSING).map((entry) => ({ kind, key: entry.label, label: entry.label, count: entry.count }));
  const entries = new Map();
  const aliases = kind === "author" ? buildAuthorRoleAliasMap(rows.map((row) => row.claim)) : null;
  rows.forEach((row) => explorerEntityValuesForClaim(row.claim, aliases, kind).forEach((entry) => {
    const key = normalizeValue(entry.value || entry.label);
    const current = entries.get(key) || { kind, key, label: entry.label, papers: new Set() };
    current.papers.add(row.paperKey);
    entries.set(key, current);
  }));
  return [...entries.values()].map(({ papers, ...entry }) => ({ ...entry, count: papers.size })).sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
}

function researchComparisonGroups() {
  const base = PKGResearch.filter(researchBaseRows({ ignoreFocus: true }), researchFilters);
  return researchCompare.map((candidate) => ({ ...candidate, rows: researchCandidateRows(base, candidate) }));
}

function researchPinnedScopeLabel(group) {
  if (!group.scope) return "";
  const type = { all: "All papers", primary: "Primary studies", meta_analyses: "Meta-analyses", reviews: "Reviews" }[group.scope.evidence] || "All papers";
  return ` · ${type} · ${group.scope.access === "open" ? "Full-text extraction" : "All source text"}`;
}

function researchCompareTimeline(groups) {
  const min = Number(yearMinFilter.value);
  const max = Number(yearMaxFilter.value);
  if (!min || !max) return "";
  const series = groups.map((group) => {
    const counts = new Map();
    PKGResearch.papers(group.rows).forEach((paper) => counts.set(paper.year, (counts.get(paper.year) || 0) + 1));
    return Array.from({ length: max - min + 1 }, (_, index) => counts.get(min + index) || 0);
  });
  const maximum = Math.max(1, ...series.flat());
  const lines = series.map((values, index) => `<polyline fill="none" stroke="${ANALYSIS_COMPARISON_COLORS[index]}" stroke-width="3" points="${values.map((value, i) => `${48 + (i / Math.max(1, max - min)) * 850},${205 - value / maximum * 170}`).join(" ")}"/>`).join("");
  return `<section class="analytics-panel"><div class="research-panel-heading"><h3>Publication history</h3></div><svg viewBox="0 0 940 250" class="research-timeline" role="img" aria-label="Annual publication counts on the same scale"><line x1="48" y1="205" x2="898" y2="205" stroke="currentColor" opacity="0.3"/><text x="48" y="230">${min}</text><text x="864" y="230">${max}</text><text x="8" y="40">${maximum}</text><text x="22" y="208">0</text>${lines}</svg>
    <p class="research-note">Counts use the same vertical scale. The latest year may be incomplete; a lower count does not establish declining activity.</p>
    <details class="research-history-data"><summary>Annual counts as a table</summary><div class="research-table-scroll"><table class="research-matrix"><thead><tr><th>Year</th>${groups.map((group) => `<th>${escapeHtml(group.label)}</th>`).join("")}</tr></thead><tbody>${Array.from({ length: max - min + 1 }, (_, i) => `<tr><th>${min + i}</th>${series.map((values) => `<td>${values[i]}</td>`).join("")}</tr>`).join("")}</tbody></table></div></details></section>`;
}

function researchComparisonTable(groups) {
  const distributions = groups.map((group) => new Map(PKGResearch.distribution(group.rows, researchCompareField).map((entry) => [entry.label, entry.count])));
  const denominators = groups.map((group) => PKGResearch.papers(group.rows).length);
  const labels = [...new Set(distributions.flatMap((counts) => [...counts.keys()]))].sort((a, b) =>
    (a === PKGResearch.MISSING) - (b === PKGResearch.MISSING) || distributions.reduce((sum, counts) => sum + (counts.get(b) || 0) - (counts.get(a) || 0), 0) || a.localeCompare(b));
  const maximum = researchCompareMetric === "share" ? 100 : Math.max(1, ...distributions.flatMap((counts) => [...counts.values()]));
  return `<section class="analytics-panel"><div class="research-panel-heading"><h3>Research profiles</h3><div class="research-inline-fields">
    ${researchSelect("field", "Break down by", Object.entries(RESEARCH_FIELDS).filter(([key]) => !["transparency", "graphSubject"].includes(key)), researchCompareField, "data-research-comparison")}
    ${researchSelect("metric", "Display", [["count", "Report counts"], ["share", "Share of each evidence set"]], researchCompareMetric, "data-research-comparison")}</div></div>
    <div class="research-table-scroll" tabindex="0" role="region" aria-label="Comparison profiles"><table class="research-comparison-table"><thead><tr><th scope="col">${escapeHtml(RESEARCH_FIELDS[researchCompareField])}</th>${groups.map((group, index) => `<th scope="col" style="--comparison-color:${ANALYSIS_COMPARISON_COLORS[index]}"><i></i>${escapeHtml(group.label)}<small>${formatCompactNumber(denominators[index])} reports</small></th>`).join("")}</tr></thead><tbody>${labels.slice(0, 30).map((label) => `<tr><th scope="row">${escapeHtml(label)}</th>${groups.map((group, index) => {
      const count = distributions[index].get(label) || 0;
      const percent = denominators[index] ? count / denominators[index] * 100 : 0;
      const value = researchCompareMetric === "share" ? percent : count;
      return `<td><button data-research-inspect-group="${index}" data-research-inspect-value="${escapeHtml(label)}" style="--comparison-color:${ANALYSIS_COMPARISON_COLORS[index]};--comparison-width:${value / maximum * 100}%" ${count ? "" : "disabled"}><i></i><span>${researchCompareMetric === "share" ? `${percent.toFixed(1)}%` : formatCompactNumber(count)}</span><small>${count} / ${denominators[index]} reports</small></button></td>`;
    }).join("")}</tr>`).join("")}</tbody></table></div><p class="research-note">Each report counts once per category. Categories can overlap, so percentages need not sum to 100%. ${labels.length > 30 ? `Showing the 30 most represented of ${labels.length} categories.` : ""}</p></section>`;
}

function renderResearchCompare() {
  const base = researchBaseRows({ ignoreFocus: true });
  researchCompareCandidates = researchCandidates(PKGResearch.filter(base, researchFilters), researchCompareKind);
  const groups = researchComparisonGroups();
  const union = [...new Set(groups.flatMap((group) => group.rows))];
  researchRenderedRows = union;
  graphEl.innerHTML = `<div class="analytics-workspace research-workspace">
    ${researchChangesMarkup()}
    <section class="analytics-panel research-compare-builder"><div class="research-panel-heading"><h3>Choose what to compare</h3><span>Up to four selections</span></div>
      <p class="research-note">Compare separate research literatures. Shared publications and similar profiles do not establish a direct treatment comparison or equivalent effects.${researchCompareKind === "author" || groups.some((group) => group.kind === "author") ? " Author coverage uses identified first and last authors." : ""}${groups.some((group) => group.scope) ? " Pinned evidence sets retain their own filters and dates within the shared scope above." : ""}</p>
      <div class="research-inline-fields">${researchSelect("kind", "Compare", [["compound", "Compounds"], ["author", "Authors"], ["journal", "Journals"], ["area", "Research areas"], ["topic", "Topics"]], researchCompareKind, "data-research-comparison")}
      <label class="research-field research-query"><span>Find a selection</span><input type="search" data-research-candidate-query aria-label="Find a comparison selection" placeholder="Type a name or choose below" /></label></div>
      <div id="researchCandidateList" class="research-candidates"></div>
      <div class="research-selected-groups">${groups.map((group, index) => `<div class="research-group-chip" style="--comparison-color:${ANALYSIS_COMPARISON_COLORS[index]}"><strong>${escapeHtml(group.label)}</strong><span>${PKGResearch.papers(group.rows).length} reports${escapeHtml(researchPinnedScopeLabel(group))}${Object.keys(group.filters || {}).length ? " · saved evidence filters" : ""}</span><button data-research-remove-group="${index}" aria-label="Remove ${escapeHtml(group.label)}">×</button></div>`).join("")}</div>
    </section>
    <details class="analytics-panel research-shared-filters" ${Object.values(researchFilters).some(Boolean) ? "open" : ""}><summary>Shared evidence filters</summary>${researchRenderFilters(base)}</details>
    ${groups.length >= 2 ? `${researchComparisonTable(groups)}${researchCompareTimeline(groups)}<div class="research-actions"><button class="ghost small" data-research-shared-papers>Inspect publications shared by all selections</button><span>Profiles above include each selection’s entire matching literature.</span></div>` : '<div class="analytics-empty">Choose at least two selections to compare. You can also add a filtered evidence set from the Evidence tab.</div>'}
  </div>`;
  researchRenderCandidates("");
  researchClearRecords(union);
  autosizeExplorerWorkspace(graphEl.firstElementChild);
}

function researchRenderCandidates(query) {
  const container = document.getElementById("researchCandidateList");
  if (!container) return;
  const matches = researchCompareCandidates.map((entry, index) => ({ entry, index })).filter(({ entry }) => entry.label.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
  container.innerHTML = matches.slice(0, 12).map(({ entry, index }) => {
    const selected = researchCompare.some((group) => group.kind === entry.kind && group.key === entry.key && !Object.keys(group.filters || {}).length);
    return `<button data-research-add-group="${index}" ${selected || researchCompare.length >= 4 ? "disabled" : ""}><span>${escapeHtml(entry.label)}</span><small>${selected ? "Added" : `${entry.count} reports`}</small></button>`;
  }).join("") || '<p class="research-note">No matching selections in this scope.</p>';
  if (matches.length > 12) container.insertAdjacentHTML("beforeend", `<p class="research-note">Showing 12 of ${matches.length}. Type to narrow the list.</p>`);
}

function researchOpenPapers(rows) {
  renderExplorerSelectionDetail("Selected research evidence", rows.map((row) => row.claim));
  document.querySelector(".findings-section")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function researchCaptureState() {
  return {
    task: analysisTask, lens: explorerLens, focus: explorerFocus, area: explorerScopeAreaKey,
    concept: explorerScopeConceptKey, evidence: evidenceView, access: accessView,
    min: yearMinFilter.value, max: yearMaxFilter.value, filters: researchFilters,
    compare: researchCompare, compareKind: researchCompareKind, metric: researchCompareMetric,
    field: researchCompareField, table: researchTableMode, axes: researchCoverageAxes, cell: researchCoverageCell,
  };
}

function researchValidateState(raw) {
  const short = (value) => typeof value === "string" ? value.slice(0, 1000) : "";
  const filters = (input) => Object.fromEntries(Object.entries(input && typeof input === "object" ? input : {}).filter(([key, value]) =>
    (Object.hasOwn(RESEARCH_FIELDS, key) || ["query", "minSample"].includes(key)) && typeof value === "string" && (key !== "minSample" || !value || (Number.isFinite(Number(value)) && Number(value) >= 1))).map(([key, value]) => [key, short(value)]));
  const input = raw && typeof raw === "object" ? raw : {};
  const axes = (value) => Array.isArray(value) && value.length === 2 && value.every((axis) => typeof axis === "string" && Object.hasOwn(RESEARCH_FIELDS, axis)) ? value : ["population", "design"];
  const cell = (value) => Array.isArray(value) && value.length === 2 && value.every((entry) => typeof entry === "string") ? value.map(short) : null;
  const scope = (value) => value && typeof value === "object" ? {
    area: ENTITY_CATEGORY_OPTIONS.some((entry) => entry.key === value.area) ? value.area : "", concept: short(value.concept),
    min: short(value.min), max: short(value.max), access: value.access === "open" ? "open" : "all",
    evidence: ["all", "primary", "meta_analyses", "reviews"].includes(value.evidence) ? value.evidence : "all",
  } : undefined;
  return {
    task: RESEARCH_TASKS.has(input.task) ? input.task : "landscape",
    lens: ANALYSIS_SECTIONS.has(input.lens) ? input.lens : "all",
    focus: input.focus && typeof input.focus.key === "string" ? { key: short(input.focus.key), label: short(input.focus.label || input.focus.key) } : null,
    area: ENTITY_CATEGORY_OPTIONS.some((area) => area.key === input.area) ? input.area : "",
    concept: short(input.concept), evidence: ["primary", "meta_analyses", "reviews", "all"].includes(input.evidence) ? input.evidence : "all",
    access: input.access === "open" ? "open" : "all", min: short(input.min), max: short(input.max), filters: filters(input.filters),
    compare: (Array.isArray(input.compare) ? input.compare : []).slice(0, 4).filter((item) => item && ["compound", "author", "journal", "area", "topic", "set"].includes(item.kind) && typeof item.key === "string").map((item) => ({ kind: item.kind, key: short(item.key), label: short(item.label || item.key), filters: filters(item.filters), scope: scope(item.scope), coverage: item.coverage && cell(item.coverage.cell) ? { axes: axes(item.coverage.axes), cell: cell(item.coverage.cell) } : undefined })),
    compareKind: ["compound", "author", "journal", "area", "topic"].includes(input.compareKind) ? input.compareKind : "compound",
    metric: input.metric === "share" ? "share" : "count", field: Object.hasOwn(RESEARCH_FIELDS, input.field) ? input.field : "area",
    table: input.table === "results" ? "results" : "studies",
    axes: axes(input.axes), cell: cell(input.cell),
  };
}

function researchApplyState(raw) {
  const state = researchValidateState(raw);
  analysisTask = state.task;
  explorerLens = state.task === "compare" ? "all" : state.lens;
  explorerLastAnalysisLens = explorerLens;
  explorerFocus = state.task === "compare" ? null : state.focus;
  explorerScopeAreaKey = state.area;
  explorerScopeConceptKey = state.concept;
  evidenceView = state.evidence;
  accessView = state.access;
  researchFilters = state.filters;
  researchCompare = state.compare;
  researchCompareKind = state.compareKind;
  researchCompareMetric = state.metric;
  researchCompareField = state.field;
  researchTableMode = state.table;
  researchCoverageAxes = state.axes;
  yearFilterState[currentYearFilterKey()] = { min: state.min, max: state.max };
  researchResetView();
  researchCoverageCell = state.cell;
}

function researchUrlState(url) {
  const state = researchCaptureState();
  ["task", "from", "to", "research"].forEach((key) => url.searchParams.delete(key));
  if (explorerMode !== "analysis") return;
  url.searchParams.set("task", analysisTask);
  if (state.min) url.searchParams.set("from", state.min);
  if (state.max) url.searchParams.set("to", state.max);
  const extra = { filters: state.filters, compare: state.compare, compareKind: state.compareKind, metric: state.metric, field: state.field, table: state.table, axes: state.axes, cell: state.cell };
  if (analysisTask !== "landscape" || Object.values(researchFilters).some(Boolean)) url.searchParams.set("research", JSON.stringify(extra));
}

function researchReadUrl(params) {
  let extra = {};
  try { extra = JSON.parse((params.get("research") || "{}").slice(0, 16000)); } catch (_) { /* Malformed shared links use defaults. */ }
  researchApplyState({ ...extra, task: params.get("task") || (params.get("mode") === "compare" ? "compare" : "landscape"),
    lens: explorerLens, focus: explorerFocus, area: explorerScopeAreaKey, concept: explorerScopeConceptKey,
    evidence: evidenceView, access: accessView, min: params.get("from") || "", max: params.get("to") || "" });
}

function researchSavedQuestions() {
  try {
    const value = JSON.parse(localStorage.getItem(RESEARCH_SAVE_KEY) || "[]");
    return Array.isArray(value) ? value.filter((item) => item && typeof item.id === "string" && item.state && item.snapshot).slice(0, 10) : [];
  } catch (_) { return []; }
}

function researchWriteSaved(questions) {
  try { localStorage.setItem(RESEARCH_SAVE_KEY, JSON.stringify(questions)); return true; }
  catch (_) { researchStatus("This browser could not save the question. Storage may be full or disabled. You can still copy a link."); return false; }
}

function researchRenderSavedList() {
  const container = document.getElementById("researchSavedList");
  if (!container) return;
  const questions = researchSavedQuestions();
  container.innerHTML = questions.length ? questions.map((item) => `<div class="research-saved-row"><div><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.date)} · ${Object.keys(item.snapshot).length} reports at baseline</small></div><button class="ghost small" data-research-load="${escapeHtml(item.id)}">Open & check changes</button><button class="ghost small" data-research-delete="${escapeHtml(item.id)}" aria-label="Remove saved question ${escapeHtml(item.name)}">Remove</button></div>`).join("") : '<p class="research-note">No saved questions yet. Questions and baselines stay in this browser; changes are checked when you reopen them.</p>';
}

function researchSnapshotRows() {
  if (analysisTask === "compare") return [...new Set(researchComparisonGroups().flatMap((group) => group.rows))];
  const rows = PKGResearch.filter(researchBaseRows(), researchFilters);
  return researchCoverageCell ? PKGResearch.matchingCell(rows, ...researchCoverageAxes, ...researchCoverageCell) : rows;
}

function researchSaveQuestion() {
  const questions = researchSavedQuestions();
  if (questions.length >= 10) { researchStatus("You have 10 saved questions. Remove one before saving another."); return; }
  const name = document.getElementById("researchQuestionName").value.trim() || [explorerFocus?.label, analysisScopeLabel(), analysisTask].filter(Boolean).join(" · ");
  const id = `question-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const record = { id, name: name.slice(0, 200), date: new Date().toLocaleDateString(), release: researchRelease, state: researchCaptureState(), snapshot: PKGResearch.snapshot(researchSnapshotRows()) };
  if (researchWriteSaved([...questions, record])) { researchCurrentSavedId = id; researchRenderSavedList(); researchStatus(`Saved “${record.name}” in this browser.`); }
}

function researchCheckPendingSaved() {
  if (!researchPendingSaved) return;
  const saved = researchPendingSaved;
  researchPendingSaved = null;
  const rows = researchSnapshotRows();
  const after = PKGResearch.snapshot(rows);
  researchChangeReview = { ...PKGResearch.changes(saved.snapshot, after), date: saved.date, snapshot: after, comparisonRows: analysisTask === "compare" ? rows : null };
  researchCurrentSavedId = saved.id;
}

function researchScopeChanged() {
  researchResetView();
  researchChangeReview = null;
  researchCurrentSavedId = "";
}

function researchHandleClick(event) {
  const button = event.target.closest?.("button");
  if (!button) return false;
  const data = button.dataset;
  let handled = true;
  if (data.researchTask) { switchResearchTask(data.researchTask); return true; }
  if (data.researchTable) { researchTableMode = data.researchTable; researchPage = 0; }
  else if (data.researchPage) researchPage = Math.max(0, researchPage + Number(data.researchPage));
  else if (data.researchPaper) { researchOpenPapers(researchRenderedRows.filter((row) => row.paperKey === data.researchPaper)); return true; }
  else if ("researchClear" in data) { researchFilters = {}; researchScopeChanged(); }
  else if ("researchClearCell" in data) { researchCoverageCell = null; researchPage = 0; }
  else if ("researchCellA" in data) { researchCoverageCell = [data.researchCellA, data.researchCellB]; researchPage = 0; }
  else if ("researchAddGroup" in data) {
    const entry = researchCompareCandidates[Number(data.researchAddGroup)];
    if (entry && researchCompare.length < 4) researchCompare.push({ kind: entry.kind, key: entry.key, label: entry.label, filters: {} });
    researchScopeChanged();
  } else if ("researchRemoveGroup" in data) { researchCompare.splice(Number(data.researchRemoveGroup), 1); researchScopeChanged(); }
  else if ("researchPin" in data) {
    if (researchCompare.length >= 4) { researchStatus("Remove a comparison selection before adding another evidence set."); return true; }
    const scope = { area: explorerScopeAreaKey, concept: explorerScopeConceptKey, evidence: evidenceView, access: accessView, min: yearMinFilter.value, max: yearMaxFilter.value };
    researchCompare.push({ kind: explorerFocus ? explorerLens : "set", key: explorerFocus?.key || "all", label: [explorerFocus?.label || "Evidence set", analysisScopeLabel(), `${scope.min}–${scope.max}`, ...Object.entries(researchFilters).filter(([, value]) => value).map(([field, value]) => `${RESEARCH_FIELDS[field] || field}: ${value}`), researchCoverageCell?.join(" × ")].filter(Boolean).join(" · "), filters: { ...researchFilters }, scope, coverage: researchCoverageCell ? { axes: [...researchCoverageAxes], cell: [...researchCoverageCell] } : undefined });
    const ranges = researchCompare.map((candidate) => candidate.scope).filter(Boolean);
    yearFilterState[currentYearFilterKey()] = {
      min: String(Math.min(Number(scope.min), ...ranges.map((range) => Number(range.min) || Number(scope.min)))),
      max: String(Math.max(Number(scope.max), ...ranges.map((range) => Number(range.max) || Number(scope.max)))),
    };
    researchFilters = {};
    explorerFocus = null;
    explorerScopeAreaKey = "";
    explorerScopeConceptKey = "";
    evidenceView = "all";
    accessView = "all";
    researchScopeChanged();
    switchResearchTask("compare");
    return true;
  } else if ("researchInspectGroup" in data) {
    const group = researchComparisonGroups()[Number(data.researchInspectGroup)];
    if (group) {
      const keys = new Set(PKGResearch.papers(group.rows).filter((paper) => PKGResearch.paperValues(paper, researchCompareField).includes(data.researchInspectValue)).map((paper) => paper.key));
      researchOpenPapers(group.rows.filter((row) => keys.has(row.paperKey)));
    }
    return true;
  } else if ("researchSharedPapers" in data) {
    const groups = researchComparisonGroups();
    const sets = groups.map((group) => new Set(group.rows.map((row) => row.paperKey)));
    const rows = [...new Set(groups.flatMap((group) => group.rows))].filter((row) => sets.every((keys) => keys.has(row.paperKey)));
    if (rows.length) researchOpenPapers(rows); else researchStatus("No indexed publications are shared by all selected evidence sets.");
    return true;
  } else if ("researchChanges" in data) { analysisTask = "evidence"; researchChangeSubset = data.researchChanges; researchPage = 0; }
  else if ("researchSave" in data) { researchSaveQuestion(); return true; }
  else if ("researchCopy" in data) {
    updateExplorerUrlState();
    if (navigator.clipboard) navigator.clipboard.writeText(window.location.href).then(() => researchStatus("Link copied with the current scope and selections."), () => researchStatus("Copy the page address to share this question."));
    else researchStatus("Copy the page address to share this question.");
    return true;
  } else if (data.researchLoad) {
    const saved = researchSavedQuestions().find((item) => item.id === data.researchLoad);
    if (saved) {
      researchPendingSaved = saved;
      researchChangeReview = null;
      researchApplyState(saved.state);
      if (analysisTask === "landscape") analysisTask = "evidence";
      updateExplorerControls();
      loadAnalysisAndRender({ resetYears: false });
    }
    return true;
  } else if (data.researchDelete) {
    if (researchWriteSaved(researchSavedQuestions().filter((item) => item.id !== data.researchDelete))) researchRenderSavedList();
    return true;
  } else if ("researchBaseline" in data) {
    const questions = researchSavedQuestions();
    const item = questions.find((question) => question.id === researchCurrentSavedId);
    if (item) {
      item.snapshot = researchChangeReview?.snapshot || PKGResearch.snapshot(researchSnapshotRows());
      item.date = new Date().toLocaleDateString();
      item.release = researchRelease;
      if (researchWriteSaved(questions)) { researchChangeReview = null; researchChangeSubset = ""; researchStatus("Baseline updated to the current evidence."); }
    }
  } else handled = false;
  if (handled) { event.preventDefault(); updateExplorerControls(); renderAnalysisSurface(); }
  return handled;
}

function researchHandleChange(event) {
  const element = event.target;
  const data = element.dataset;
  if (data.researchFilter) {
    if (data.researchFilter === "minSample" && element.value && (!element.checkValidity() || Number(element.value) < 1)) return true;
    researchFilters[data.researchFilter] = element.value;
    researchScopeChanged();
  } else if (data.researchAxis !== undefined) {
    researchCoverageAxes[Number(data.researchAxis)] = element.value;
    researchCoverageCell = null;
  } else if (data.researchComparison) {
    if (data.researchComparison === "kind") researchCompareKind = element.value;
    if (data.researchComparison === "field") researchCompareField = element.value;
    if (data.researchComparison === "metric") researchCompareMetric = element.value;
  } else return false;
  renderAnalysisSurface();
  return true;
}

document.addEventListener("click", (event) => {
  if (event.target.closest?.("#researchNavigation")) researchHandleClick(event);
});
document.addEventListener("submit", (event) => {
  if (event.target.matches?.("[data-research-filter-form]")) {
    event.preventDefault();
    researchFilters.query = event.target.querySelector("[data-research-query]").value.trim();
    researchScopeChanged();
    renderAnalysisSurface();
  }
});
document.addEventListener("toggle", (event) => {
  if (event.target.matches?.(".research-coverage-disclosure")) researchCoverageExpanded = event.target.open;
}, true);

document.getElementById("analyzeGraphEvidence")?.addEventListener("click", () => {
  const graphSelection = cloneGraphSelection(selected);
  const area = entityViewKey;
  const paperView = evidenceView;
  const textView = accessView;
  const years = { min: yearMinFilter.value, max: yearMaxFilter.value };
  const target = graphSelection?.type === "edge" ? graphSelection.target : graphSelection?.type === "target" ? graphSelection.name : "";
  const compound = graphSelection?.type === "edge" ? graphSelection.compound : graphSelection?.type === "compound" ? graphSelection.name : "";
  const example = activeDetailItems.find((claim) => !target || claimMatchesGraphRight(claim, target));
  const concept = target && example ? normalizeValue(analysisConceptLabelForClaim(example, area)) : normalizeValue(target);
  const hadDetailFilter = Boolean(detailGraphFilter);
  const specificCompound = compound && activeDetailItems.some((claim) => claimMatchesAnalysisCompound(claim, compound));
  overviewWorkspaceFilterState = { evidenceView, accessView };
  stashActiveOverviewDetail();
  analysisWorkspaceSnapshot = null;
  resetExplorerTransitionState();
  explorerMode = "analysis";
  analysisTask = "evidence";
  explorerLens = specificCompound ? "compound" : "all";
  explorerLastAnalysisLens = explorerLens;
  explorerFocus = specificCompound ? { key: normalizeValue(compound), label: compound } : null;
  explorerScopeAreaKey = area;
  explorerScopeConceptKey = concept;
  evidenceView = paperView;
  accessView = textView;
  researchFilters = compound && !specificCompound ? { graphSubject: compound } : {};
  researchScopeChanged();
  yearFilterState[currentYearFilterKey()] = years;
  updateModeUI();
  researchStatus(hadDetailFilter ? "Opened the graph’s subject, topic, dates, paper type, and source-text scope. Use the Evidence filters to refine the detail-chart selection." : "");
  loadAnalysisAndRender({ resetYears: false });
});
