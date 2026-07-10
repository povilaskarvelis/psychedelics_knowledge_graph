import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const workDir = path.resolve("tmp/spreadsheets/source_identity_triage");
const outputDir = path.resolve("outputs/source_identity_repair_20260710");
const data = JSON.parse(await fs.readFile(path.join(workDir, "triage_data.json"), "utf8"));
const workbook = Workbook.create();

const headerFill = "#155E75";
const headerFont = { bold: true, color: "#FFFFFF" };
const lightBorder = { preset: "inside", style: "thin", color: "#D6E2E7" };

function excelColumn(index) {
  let value = index + 1;
  let out = "";
  while (value > 0) {
    value -= 1;
    out = String.fromCharCode(65 + (value % 26)) + out;
    value = Math.floor(value / 26);
  }
  return out;
}

function addDataSheet(name, headers, records, widths, tableName) {
  const sheet = workbook.worksheets.add(name);
  sheet.showGridLines = false;
  sheet.freezePanes.freezeRows(1);
  const matrix = [headers.map((h) => h.label)];
  for (const record of records) {
    matrix.push(headers.map((h) => record[h.key] ?? ""));
  }
  const lastCol = excelColumn(headers.length - 1);
  const lastRow = Math.max(1, matrix.length);
  const range = sheet.getRange(`A1:${lastCol}${lastRow}`);
  range.values = matrix;
  sheet.getRange(`A1:${lastCol}1`).format = {
    fill: headerFill,
    font: headerFont,
    verticalAlignment: "center",
    wrapText: true,
    borders: { preset: "outside", style: "thin", color: "#0E4F63" },
  };
  sheet.getRange(`A1:${lastCol}1`).format.rowHeight = 30;
  if (records.length) {
    const body = sheet.getRange(`A2:${lastCol}${lastRow}`);
    body.format = { verticalAlignment: "top", wrapText: true, borders: lightBorder };
    body.format.autofitRows();
    const table = sheet.tables.add(`A1:${lastCol}${lastRow}`, true, tableName);
    table.style = "TableStyleMedium2";
    table.showFilterButton = true;
  }
  widths.forEach((width, index) => {
    sheet.getRange(`${excelColumn(index)}:${excelColumn(index)}`).format.columnWidth = width;
  });
  return sheet;
}

const summary = workbook.worksheets.add("Summary");
summary.showGridLines = false;
summary.getRange("A1:D1").merge();
summary.getRange("A1").values = [["Source artifact cleanup - remaining review"]];
summary.getRange("A1:D1").format = {
  fill: "#0F3D4A",
  font: { bold: true, color: "#FFFFFF", size: 16 },
  verticalAlignment: "center",
};
summary.getRange("A1:D1").format.rowHeight = 34;
summary.getRange("A3:D3").values = [["Metric", "Count", "Interpretation", "Source"]];
summary.getRange("A3:D3").format = { fill: headerFill, font: headerFont, wrapText: true };
const summaryRows = [
  ["Original source-artifact universe", data.summary.original_artifact_count, "All artifacts in the fixed source-identity audit universe.", "final source-identity manifest"],
  ["Active verified artifacts", data.summary.active_verified_artifacts, "Every currently active full-text artifact passes source-identity verification.", "live source-identity audit"],
  ["Unresolved artifacts", "=B4-B5", "Original artifacts without a currently active verified replacement.", "formula"],
  ["Excluded or not retained - no repair", `=COUNTA('Excluded no download'!$A$2:$A$${data.excluded.length + 1})`, "These records are outside extraction and must not be sent to PDF retrieval.", "Excluded no download"],
  ["Retained as abstract-only - no full-text repair", `=COUNTA('Public abstract only'!$A$2:$A$${data.known_no_public_fulltext.length + 1})+COUNTA('Other abstract only'!$A$2:$A$${data.other_abstract_only.length + 1})`, "Keep the papers and abstract-derived KG evidence; no full-text artifact is required.", "two abstract-only sheets"],
  ["Confirmed no public full text", `=COUNTA('Public abstract only'!$A$2:$A$${data.known_no_public_fulltext.length + 1})`, "Abstract remains publicly usable; do not seek licensed or private copies.", "Public abstract only"],
  ["Other active abstract-only routes", `=COUNTA('Other abstract only'!$A$2:$A$${data.other_abstract_only.length + 1})`, "The current extraction route uses the public abstract and does not request full text.", "Other abstract only"],
  ["Pipeline full-text repair backlog", `=COUNTA('Pipeline fulltext repairs'!$A$2:$A$${data.fulltext_repairs.length + 1})`, "These routes genuinely require a publicly available full-text artifact; this is pipeline work, not a user assignment.", "Pipeline fulltext repairs"],
  ["Manual inbox PDFs imported and verified", `=COUNTA('Imported verified'!$A$2:$A$${data.imported.length + 1})`, "Correct PDFs promoted to canonical source artifacts in this pass.", "Imported verified"],
  ["Newly excluded by this publication-format pass", data.summary.newly_excluded_this_pass, "Additional chapters, dissertations, conference abstracts, containers, and a visual essay removed at prescreen.", "prescreen comparison"],
  ["Publication-format exclusions still leaking into active KG", data.summary.format_excluded_kg_leaks, "Must remain zero after routed KG rebuild.", "KG verification"],
];
summary.getRange(`A4:D${summaryRows.length + 3}`).values = summaryRows.map((row) => row.map((v) => typeof v === "string" && v.startsWith("=") ? null : v));
summaryRows.forEach((row, idx) => {
  if (typeof row[1] === "string" && row[1].startsWith("=")) {
    summary.getRange(`B${idx + 4}`).formulas = [[row[1]]];
  }
});
summary.getRange(`A4:D${summaryRows.length + 3}`).format = { wrapText: true, verticalAlignment: "top", borders: lightBorder };
summary.getRange(`B4:B${summaryRows.length + 3}`).format.numberFormat = "#,##0";
summary.getRange("A:A").format.columnWidth = 38;
summary.getRange("B:B").format.columnWidth = 14;
summary.getRange("C:C").format.columnWidth = 70;
summary.getRange("D:D").format.columnWidth = 30;
summary.getRange(`A4:D${summaryRows.length + 3}`).format.autofitRows();
summary.freezePanes.freezeRows(3);

addDataSheet("Public abstract only", [
  { key: "doi", label: "DOI" }, { key: "title", label: "Title" }, { key: "paper_type", label: "Paper type" },
  { key: "kg_finding_count", label: "KG findings" }, { key: "priority_tier", label: "Priority" },
  { key: "curated_access_status", label: "Access status" }, { key: "curated_access_checked_at", label: "Checked" },
  { key: "recommended_acquisition_route", label: "Full-text action" }, { key: "repair_eligibility_reason", label: "Why no repair" },
  { key: "doi_landing_url", label: "DOI URL" },
], data.known_no_public_fulltext, [28, 56, 20, 12, 27, 34, 14, 40, 62, 48], "PublicAbstractOnlyTable");

addDataSheet("Other abstract only", [
  { key: "doi", label: "DOI" }, { key: "title", label: "Title" }, { key: "paper_type", label: "Paper type" },
  { key: "kg_finding_count", label: "KG findings" }, { key: "priority_tier", label: "Priority" },
  { key: "final_action_category", label: "Artifact action" }, { key: "repair_eligibility_reason", label: "Why no repair" },
  { key: "doi_landing_url", label: "DOI URL" },
], data.other_abstract_only, [28, 56, 20, 12, 27, 40, 66, 48], "OtherAbstractOnlyTable");

addDataSheet("Pipeline fulltext repairs", [
  { key: "doi", label: "DOI" }, { key: "title", label: "Title" }, { key: "paper_type", label: "Paper type" },
  { key: "kg_finding_count", label: "KG findings" }, { key: "priority_tier", label: "Priority" },
  { key: "recommended_acquisition_route", label: "Pipeline route" }, { key: "candidate_urls_requiring_validation", label: "Candidate URL" },
  { key: "final_action_category", label: "Artifact problem" }, { key: "manual_queue_reason", label: "Required identity fix" },
  { key: "doi_landing_url", label: "DOI URL" },
], data.fulltext_repairs, [28, 56, 20, 12, 27, 30, 54, 40, 62, 48], "PipelineFulltextRepairsTable");

addDataSheet("Excluded no download", [
  { key: "doi", label: "DOI" }, { key: "title", label: "Title" }, { key: "paper_type", label: "Paper type" },
  { key: "kg_finding_count", label: "Former KG findings" }, { key: "final_action_category", label: "Final action" },
  { key: "repair_eligibility_reason", label: "Why no repair" }, { key: "quarantine_reasons", label: "Old artifact problem" },
  { key: "doi_landing_url", label: "DOI URL" },
], data.excluded, [28, 56, 20, 16, 38, 48, 45, 48], "ExcludedNoDownloadTable");

addDataSheet("Imported verified", [
  { key: "doi", label: "DOI" }, { key: "title", label: "Title" }, { key: "pdf_file", label: "PDF file" },
  { key: "match_basis", label: "Import match" }, { key: "identity_status", label: "Identity status" },
  { key: "identity_basis", label: "Identity basis" }, { key: "backend", label: "Conversion backend" },
  { key: "artifact_path", label: "Artifact path" },
], data.imported, [30, 58, 42, 24, 24, 55, 22, 65], "ImportedVerifiedTable");

await fs.mkdir(outputDir, { recursive: true });
const previews = [];
for (const sheetName of ["Summary", "Public abstract only", "Other abstract only", "Pipeline fulltext repairs", "Excluded no download", "Imported verified"]) {
  const preview = await workbook.render({ sheetName, range: sheetName === "Summary" ? "A1:D16" : "A1:J20", scale: 1.2, format: "png" });
  const previewPath = path.join(workDir, `preview_${sheetName.replaceAll(" ", "_")}.png`);
  await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));
  previews.push(previewPath);
}

const inspectSummary = await workbook.inspect({ kind: "table", range: "Summary!A1:D16", include: "values,formulas", tableMaxRows: 20, tableMaxCols: 6, maxChars: 8000 });
const inspectErrors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 100 }, summary: "final formula error scan" });
await fs.writeFile(path.join(workDir, "inspection.txt"), `${inspectSummary.ndjson}\n${inspectErrors.ndjson}\n`);

const output = await SpreadsheetFile.exportXlsx(workbook);
const outputPath = path.join(outputDir, "source_artifact_remaining_review_20260710.xlsx");
await output.save(outputPath);
console.log(JSON.stringify({ outputPath, previews, summaryInspect: inspectSummary.ndjson, errorInspect: inspectErrors.ndjson }));
