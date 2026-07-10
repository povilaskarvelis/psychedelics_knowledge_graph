import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputDir = new URL(".", import.meta.url).pathname;
const allCandidates = JSON.parse(await fs.readFile(`${outputDir}/source_identity_candidates.json`, "utf8"));
const offset = Number(process.env.OFFSET || 0);
const limit = process.env.LIMIT ? Number(process.env.LIMIT) : allCandidates.length;
const candidates = allCandidates.slice(offset, offset + limit);
const outputName = process.env.OUTPUT_NAME || "source_identity_manual_review.xlsx";
const subsetLabel = process.env.SUBSET_LABEL || "All candidates";
const scanSummary = JSON.parse(await fs.readFile(`${outputDir}/source_identity_summary.json`, "utf8"));
const workbook = Workbook.create();

const guide = workbook.worksheets.add("Review Guide");
const queue = workbook.worksheets.add("Review Queue");

const navy = "#17324D";
const teal = "#0F766E";
const paleTeal = "#DFF4F1";
const paleRed = "#FDE8E7";
const paleAmber = "#FFF3D6";
const paleBlue = "#E8F1FB";
const paleGreen = "#E5F4EA";
const paleGray = "#F3F5F7";
const text = "#1F2937";
const muted = "#5B6573";

function cleanCell(value) {
  if (typeof value !== "string") return value;
  return value
    .toWellFormed()
    .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

for (const sheet of [guide, queue]) {
  sheet.showGridLines = false;
}

// Review Guide
guide.mergeCells("A1:H2");
guide.getRange("A1").values = [[`Source Identity Manual Review — ${subsetLabel}`]];
guide.getRange("A1:H2").format = {
  fill: navy,
  font: { bold: true, color: "#FFFFFF", size: 18 },
  verticalAlignment: "center",
};
guide.mergeCells("A3:H3");
guide.getRange("A3").values = [[
  "Candidate records where the extraction task identity may not match the supplied full-text artifact. Candidates are not confirmed errors."
]];
guide.getRange("A3:H3").format = { fill: "#EAF0F6", font: { color: text, italic: true }, wrapText: true };

guide.getRange("A5:H5").values = [[
  "Total candidates", "High priority", "Medium priority", "Screening only",
  "Candidates with KG findings", "KG findings on candidates", "Explicit DOI conflicts", "Mixed-source warnings"
]];
guide.getRange("A5:H5").format = { fill: teal, font: { bold: true, color: "#FFFFFF" }, wrapText: true };
const lastRow = candidates.length + 1;
guide.getRange("A6:H6").values = [[
  candidates.length,
  candidates.filter((row) => row.priority === "High").length,
  candidates.filter((row) => row.priority === "Medium").length,
  candidates.filter((row) => row.priority === "Screening").length,
  candidates.filter((row) => row.current_kg_finding_count > 0).length,
  candidates.reduce((sum, row) => sum + row.current_kg_finding_count, 0),
  candidates.filter((row) => row.problem_type.includes("Artifact header DOI differs")).length,
  candidates.filter((row) => row.problem_type.includes("Merged/multi-study source warning")).length,
]];
guide.getRange("A6:H6").format = {
  fill: paleTeal,
  font: { bold: true, color: navy, size: 14 },
  horizontalAlignment: "center",
};
guide.getRange("A6:H6").format.numberFormat = "#,##0";

guide.mergeCells("A8:H9");
guide.getRange("A8").values = [[
  "What a DOI conflict means: Requested DOI is the identity used by the extraction task. Artifact header DOI is parsed from the artifact's own JATS/TEI front matter. If they differ, the artifact may be the wrong paper—but a repository DOI, preprint, accepted manuscript, or publisher punctuation variant can be legitimate. Review the title, abstracts, warning, and artifact path before deciding."
]];
guide.getRange("A8:H9").format = { fill: paleAmber, font: { color: text, bold: true }, wrapText: true, verticalAlignment: "center" };

guide.getRange("A11:B11").values = [["Suggested workflow", "Meaning"]];
guide.getRange("A11:B11").format = { fill: navy, font: { bold: true, color: "#FFFFFF" } };
guide.getRange("A12:B18").values = [
  ["1. Start with High", "These have stronger identity evidence and/or currently contribute KG findings."],
  ["2. Compare identities", "Check requested DOI/title/abstract against artifact DOI/title/abstract."],
  ["3. Inspect the artifact", "Open the local artifact path when the title/abstract comparison is not decisive."],
  ["4. Record one decision", "Set Manual review status in the Review Queue; add a short note for ambiguous cases."],
  ["Confirmed source mismatch", "The artifact belongs to a different paper than the requested record."],
  ["Confirmed mixed container", "The artifact contains multiple papers/abstracts and was not correctly sliced."],
  ["Metadata only issue", "The artifact is usable, but DOI/title/PMID/PMCID metadata needs correction."],
];
guide.getRange("A12:B18").format = { wrapText: true, verticalAlignment: "top" };
guide.getRange("A12:A18").format = { fill: paleGray, font: { bold: true, color: navy }, wrapText: true };

guide.getRange("D11:E11").values = [["Priority", "Definition"]];
guide.getRange("D11:E11").format = { fill: navy, font: { bold: true, color: "#FFFFFF" } };
guide.getRange("D12:E14").values = [
  ["High", "Strong warning/container evidence or a non-equivalent header DOI, with current graph impact where applicable."],
  ["Medium", "Identity evidence needs checking; may have no current graph impact or may be a legitimate version linkage."],
  ["Screening", "Only low text similarity; expect more false positives, including translated titles and repository wrappers."],
];
guide.getRange("D12:E14").format = { wrapText: true, verticalAlignment: "top" };
guide.getRange("D12").format.fill = paleRed;
guide.getRange("D13").format.fill = paleAmber;
guide.getRange("D14").format.fill = paleBlue;

guide.mergeCells("D16:H18");
guide.getRange("D16").values = [[
  `Scope: ${scanSummary.scan_stats.article_text_papers.toLocaleString()} unique article-text records used by this routed run. ` +
  `${scanSummary.scan_stats.header_doi_recovered.toLocaleString()} had a recoverable front-matter DOI. ` +
  `This workbook contains ${candidates.length} of ${scanSummary.candidate_count} candidates. ` +
  "Counts overlap because one record can have a DOI conflict, a model warning, and mixed-source evidence."
]];
guide.getRange("D16:H18").format = { fill: "#EAF0F6", font: { color: muted }, wrapText: true, verticalAlignment: "center" };

guide.getRange("A20:H20").values = [["Source files", "", "", "", "", "", "", ""]];
guide.getRange("A20:H20").format = { fill: teal, font: { bold: true, color: "#FFFFFF" } };
guide.mergeCells("A21:H22");
guide.getRange("A21").values = [[
  "Extraction outputs: data/processed/extraction/routed_runs/gemini3_flash_20260628_primary_extraction/route_extraction_outputs.jsonl\n" +
  "Tasks: data/processed/extraction/route_extraction_tasks.jsonl\n" +
  "Artifacts: data/processed/fulltext/articles/\n" +
  "Current KG: data/processed/kg_routed_runs/gemini3_flash_20260628_primary_extraction/findings.parquet"
]];
guide.getRange("A21:H22").format = { fill: paleGray, font: { color: text }, wrapText: true, verticalAlignment: "top" };
guide.freezePanes.freezeRows(3);
guide.getRange("A:H").format.columnWidth = 18;
guide.getRange("A:A").format.columnWidth = 27;
guide.getRange("B:B").format.columnWidth = 52;
guide.getRange("D:D").format.columnWidth = 20;
guide.getRange("E:E").format.columnWidth = 48;
guide.getRange("A1:H22").format.rowHeight = 24;
guide.getRange("A1:H2").format.rowHeight = 32;
guide.getRange("A8:H9").format.rowHeight = 42;
guide.getRange("A21:H22").format.rowHeight = 38;

// Review Queue: the editable master table.
const queueHeaders = [
  "Candidate ID", "Priority", "Manual review status", "Manual notes", "Current KG findings",
  "Problem type", "Requested DOI", "Requested title", "Artifact header DOI", "Artifact header title",
  "Title similarity", "Abstract similarity", "Warning excerpt", "Recommended action", "Source family", "Artifact path"
];
const queueRows = candidates.map((row) => ([
  row.candidate_id, row.priority, row.manual_review_status, row.manual_notes, row.current_kg_finding_count,
  row.problem_type, row.requested_doi, row.requested_title, row.artifact_header_doi, row.artifact_header_title,
  row.title_similarity, row.abstract_similarity, row.extraction_warnings.slice(0, 320), row.recommended_action,
  row.source_family, row.artifact_path,
]).map(cleanCell));
queue.getRangeByIndexes(0, 0, queueRows.length + 1, queueHeaders.length).values = [queueHeaders, ...queueRows];
const queueTable = queue.tables.add(`A1:P${lastRow}`, true, "SourceIdentityReviewQueue");
queueTable.style = "TableStyleMedium2";
queueTable.showFilterButton = true;
queue.freezePanes.freezeRows(1);
queue.freezePanes.freezeColumns(4);
queue.getRange("A1:P1").format = { fill: navy, font: { bold: true, color: "#FFFFFF" }, wrapText: true, verticalAlignment: "center" };
queue.getRange(`A2:P${lastRow}`).format = { wrapText: true, verticalAlignment: "top", font: { color: text } };
queue.getRange(`A2:P${lastRow}`).format.rowHeight = 48;
queue.getRange("A1:P1").format.rowHeight = 32;
queue.getRange(`C2:C${lastRow}`).dataValidation = {
  rule: {
    type: "list",
    values: [
      "Not reviewed", "Confirmed source mismatch", "Confirmed mixed container", "Metadata only issue",
      "Benign DOI/version alias", "Correct artifact", "Unsure"
    ],
  },
};
queue.getRange(`E2:E${lastRow}`).format.numberFormat = "#,##0";
queue.getRange(`K2:L${lastRow}`).format.numberFormat = "0.00";
queue.getRange("A:A").format.columnWidth = 13;
queue.getRange("B:B").format.columnWidth = 12;
queue.getRange("C:C").format.columnWidth = 25;
queue.getRange("D:D").format.columnWidth = 35;
queue.getRange("E:E").format.columnWidth = 14;
queue.getRange("F:F").format.columnWidth = 38;
queue.getRange("G:G").format.columnWidth = 28;
queue.getRange("H:H").format.columnWidth = 48;
queue.getRange("I:I").format.columnWidth = 28;
queue.getRange("J:J").format.columnWidth = 48;
queue.getRange("K:L").format.columnWidth = 13;
queue.getRange("M:M").format.columnWidth = 44;
queue.getRange("N:N").format.columnWidth = 48;
queue.getRange("O:O").format.columnWidth = 20;
queue.getRange("P:P").format.columnWidth = 58;

// Compact verification before export.
const queueCheck = await workbook.inspect({
  kind: "table",
  range: "Review Queue!A1:P8",
  include: "values,formulas",
  tableMaxRows: 8,
  tableMaxCols: 16,
  maxChars: 9000,
});
console.log(queueCheck.ndjson);
const formulaErrors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "final formula error scan",
  maxChars: 3000,
});
console.log(formulaErrors.ndjson);

const exported = await SpreadsheetFile.exportXlsx(workbook);
await exported.save(`${outputDir}/${outputName}`);
console.log(`saved ${outputDir}/${outputName}`);

const previewSuffix = outputName.replace(/\.xlsx$/i, "");
for (const [sheetName, range, fileName, scale] of [
  ["Review Guide", "A1:H22", `preview_${previewSuffix}_guide.png`, 1.25],
  ["Review Queue", "A1:P10", `preview_${previewSuffix}_queue.png`, 0.8],
]) {
  const preview = await workbook.render({ sheetName, range, scale, format: "png" });
  await fs.writeFile(`${outputDir}/${fileName}`, new Uint8Array(await preview.arrayBuffer()));
}
