import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";
const workbook = Workbook.create();
const sheet = workbook.worksheets.add("Test");
sheet.getRange("A1:B3").values = [["A", "B"], [1, 2], [3, 4]];
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save("minimal_export_test.xlsx");
console.log("ok");
