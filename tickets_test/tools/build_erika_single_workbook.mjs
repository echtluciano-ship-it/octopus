import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const sourcePath = process.argv[2];
const outputPath = process.argv[3];
const previewPath = process.argv[4];

if (!sourcePath || !outputPath || !previewPath) {
  throw new Error("Uso: node build_erika_single_workbook.mjs <control.xlsx> <salida.xlsx> <preview.png>");
}

const source = await SpreadsheetFile.importXlsx(await FileBlob.load(sourcePath));
const control = source.worksheets.getItem("Control");
const sourceRows = control.getRange("A2:R21").values;

const fieldLabels = [
  [4, "fecha del ticket"],
  [5, "monto"],
  [7, "número de comprobante, operación o ID Coelsa"],
  [8, "nombre y apellido"],
  [9, "CUIT"],
  [10, "banco"],
];

function observation(row) {
  const status = String(row[2] ?? "");
  if (status === "READY_FOR_SHEET") return "";
  if (status === "WRONG_ACCOUNT_REVIEW") {
    return "REVIEW: la cuenta de destino no corresponde a una cuenta válida.";
  }
  if (!row[3]) {
    return "REVIEW: no se pudo confirmar si corresponde a una transferencia o a un depósito.";
  }
  const missing = fieldLabels.filter(([index]) => row[index] === null || row[index] === "").map(([, label]) => label);
  if (missing.length) return `REVIEW: falta confirmar ${missing.join(", ")}.`;
  return "REVIEW: el comprobante requiere validación manual.";
}

const rows = sourceRows.map((row) => [
  row[4],
  row[5],
  row[7] === null || row[7] === "" ? null : `\u200B${String(row[7])}`,
  row[8],
  row[9],
  row[10],
  observation(row),
]);

const workbook = Workbook.create();
const sheet = workbook.worksheets.add("Tickets");
sheet.showGridLines = false;
sheet.freezePanes.freezeRows(1);

sheet.getRange("A1:G21").values = [
  ["FECHA TICKET", "MONTO", "NRO COMPROBANTE", "NOMBRE Y APELLIDO", "CUIT", "BANCO", "OBSERVACIONES"],
  ...rows,
];

sheet.getRange("A1:G21").format.font = { name: "Arial", size: 10, color: "#1F2937" };
sheet.getRange("A1:G1").format = {
  fill: "#1F4E78",
  font: { name: "Arial", size: 10, bold: true, color: "#FFFFFF" },
  horizontalAlignment: "center",
  verticalAlignment: "center",
  borders: { preset: "all", style: "thin", color: "#FFFFFF" },
};
sheet.getRange("A2:G21").format.verticalAlignment = "center";
sheet.getRange("A2:A21").format.horizontalAlignment = "center";
sheet.getRange("B2:B21").format.horizontalAlignment = "right";
sheet.getRange("C2:C21").format.horizontalAlignment = "center";
sheet.getRange("C2:C21").format.wrapText = true;
sheet.getRange("C2:C21").format.numberFormat = "@";
sheet.getRange("E2:E21").format.horizontalAlignment = "center";
sheet.getRange("F2:F21").format.horizontalAlignment = "center";
sheet.getRange("G2:G21").format.wrapText = true;

sheet.getRange("A2:A21").format.numberFormat = "dd/mm/yyyy";
sheet.getRange("B2:B21").format.numberFormat = '"$"#,##0.00';

sourceRows.forEach((sourceRow, index) => {
  const excelRow = index + 2;
  const review = String(sourceRow[2] ?? "") !== "READY_FOR_SHEET";
  const range = sheet.getRange(`A${excelRow}:G${excelRow}`);
  range.format.fill = review ? "#FCE8E6" : "#E6F4EA";
  if (review) {
    range.format.font = { name: "Arial", size: 10, color: "#A61B1B" };
  }
});

sheet.getRange("A1:A21").format.columnWidth = 14;
sheet.getRange("B1:B21").format.columnWidth = 17;
sheet.getRange("C1:C21").format.columnWidth = 40;
sheet.getRange("D1:D21").format.columnWidth = 31;
sheet.getRange("E1:E21").format.columnWidth = 19;
sheet.getRange("F1:F21").format.columnWidth = 20;
sheet.getRange("G1:G21").format.columnWidth = 58;
sheet.getRange("1:1").format.rowHeight = 25;
sheet.getRange("2:21").format.rowHeight = 34;

const table = sheet.tables.add("A1:G21", true, "TicketsErikaTable");
table.style = "TableStyleMedium2";
table.showBandedRows = false;

workbook.recalculate();

const inspection = await workbook.inspect({
  kind: "table",
  range: "Tickets!A1:G21",
  include: "values,formulas",
  tableMaxRows: 25,
  tableMaxCols: 7,
});
console.log(inspection.ndjson);

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options: { useRegex: true, maxResults: 50 },
  summary: "final formula error scan",
});
console.log(errors.ndjson);

await fs.mkdir(path.dirname(outputPath), { recursive: true });
const preview = await workbook.render({ sheetName: "Tickets", range: "A1:G21", scale: 1.5, format: "png" });
await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);

console.log(JSON.stringify({ outputPath, previewPath, rows: rows.length }));
