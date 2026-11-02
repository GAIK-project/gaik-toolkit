import readXlsxFile from "read-excel-file/browser";

type Cell = unknown;

function cellText(cell: Cell): string {
  if (cell === null || cell === undefined) return "";
  if (cell instanceof Date) return cell.toISOString().slice(0, 10);
  return String(cell);
}

/** CSV text for the rows of a sheet: quoted where a cell holds a comma, quote or line break. */
export function rowsToCsv(rows: Cell[][]): string {
  return rows
    .map((row) =>
      row
        .map((cell) => {
          const text = cellText(cell);
          return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
        })
        .join(","),
    )
    .join("\n");
}

/**
 * The sheets of an Excel workbook as CSV documents, so that the CSV reader
 * handles them like any other list. Each is named `<file> (<sheet>).csv`, or
 * `<file>.csv` when the workbook has one sheet; empty sheets are left out.
 */
export async function spreadsheetToCsv(
  file: File,
): Promise<{ name: string; text: string }[]> {
  const sheets = await readXlsxFile(file);
  const base = file.name.replace(/\.xlsx$/i, "");
  const filled = sheets.filter((sheet) =>
    sheet.data.some((row) => row.some((cell) => cellText(cell) !== "")),
  );
  return filled.map((sheet) => ({
    name: filled.length === 1 ? `${base}.csv` : `${base} (${sheet.sheet}).csv`,
    text: rowsToCsv(sheet.data),
  }));
}
