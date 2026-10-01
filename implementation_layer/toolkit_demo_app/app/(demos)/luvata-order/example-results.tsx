"use client";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import { AlertCircle, CheckCircle2, Download } from "lucide-react";
import { BOM_OF_MATERIAL } from "./example-data";

export interface FeeLine {
  name: string;
  kind: string;
  basis?: string | null;
  quantity: number;
  rate: number;
  amount: number;
}

export interface EnrichedItem {
  material: string;
  description: string;
  type_designation?: string | null;
  quantity: number;
  unit_price?: number | null;
  material_subtotal?: number | null;
  cutting_fee: number;
  testing_fee: number;
  cert_fee: number;
  other_fees: number;
  fee_lines?: FeeLine[];
  notes?: string[];
  total_fees: number;
  line_total?: number | null;
  delivery_date?: string | null;
  bom_dimensions?: string | null;
  bom_material_grade?: string | null;
  bom_match: boolean;
  price_match: boolean;
  error?: string | null;
}

export interface OrderSummary {
  total_items: number;
  total_quantity: number;
  material_subtotal: number;
  total_fees: number;
  shipping?: number;
  tax_rate?: number | null;
  tax?: number;
  grand_total: number;
}

export interface ProcessOrderResponse {
  success: boolean;
  po_number?: string | null;
  customer?: string | null;
  header?: Record<string, unknown>;
  items: EnrichedItem[];
  summary?: OrderSummary | null;
  errors: string[];
  warnings?: string[];
  pdf_job_id?: string | null;
}

const money = (value: number | null | undefined) =>
  value === null || value === undefined
    ? "-"
    : `$${value.toLocaleString("en-US", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })}`;

const count = (value: number) =>
  Number.isInteger(value) ? String(value) : value.toFixed(2);

const Dash = () => <span className="text-muted-foreground">—</span>;

/** The fees of one order line: each with its quantity, basis and rate. */
function FeeList({ item }: { item: EnrichedItem }) {
  const feeLines = item.fee_lines ?? [];
  const notes = item.notes ?? [];
  if (feeLines.length === 0 && notes.length === 0) return <Dash />;
  return (
    <div className="min-w-52 space-y-1">
      <ul className="space-y-0.5 text-xs">
        {feeLines.map((fee) => (
          <li key={fee.name} className="flex justify-between gap-4">
            <span>
              <span className="font-medium">{fee.name}</span>
              <span className="text-muted-foreground">
                {" "}
                {count(fee.quantity)}
                {fee.basis ? ` ${fee.basis.toLowerCase()}` : ""} ×{" "}
                {money(fee.rate)}
              </span>
            </span>
            <span className="tabular-nums">{money(fee.amount)}</span>
          </li>
        ))}
      </ul>
      {feeLines.length > 1 && (
        <p className="flex justify-between gap-4 border-t pt-1 text-xs font-semibold">
          <span>Fees</span>
          <span className="tabular-nums">{money(item.total_fees)}</span>
        </p>
      )}
      {notes.map((note) => (
        <p key={note} className="text-xs text-amber-700">
          {note}
        </p>
      ))}
    </div>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <h3 className="text-sm font-semibold">{children}</h3>;
}

/**
 * The processed example: the PO's header fields, a table of its lines with the fields
 * read from each BOM and the fees, and the order total.
 */
export function ExampleResults({
  result,
  onShowSource,
}: {
  result: ProcessOrderResponse;
  onShowSource: (file: string) => void;
}) {
  const summary = result.summary;
  const header = Object.entries(result.header ?? {});
  const pdfUrl = result.pdf_job_id
    ? `/api/luvata-order/pdf/${result.pdf_job_id}`
    : null;
  const totals: { label: string; value: string; strong?: boolean }[] = [
    { label: "Material subtotal", value: money(summary?.material_subtotal) },
    { label: "Additional fees", value: money(summary?.total_fees) },
    { label: "Shipping", value: money(summary?.shipping) },
    {
      label: summary?.tax_rate ? `Tax (${summary.tax_rate}%)` : "Tax",
      value: money(summary?.tax),
    },
    { label: "Grand total", value: money(summary?.grand_total), strong: true },
  ];

  return (
    <Card id="example-results" className="scroll-mt-24">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <CheckCircle2 className="text-success size-5" />
          The processed order
        </CardTitle>
        <CardDescription>
          <span className="text-foreground font-medium">
            {result.po_number} · {result.customer}
          </span>
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {(result.warnings ?? []).length > 0 && (
          <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-800">
            <p className="flex items-center gap-2 font-medium">
              <AlertCircle className="size-4" />
              Check these fees
            </p>
            <ul className="mt-1 list-disc pl-6">
              {(result.warnings ?? []).map((warning, i) => (
                <li key={i}>{warning}</li>
              ))}
            </ul>
          </div>
        )}

        {result.errors.length > 0 && (
          <div className="border-destructive/30 bg-destructive/10 text-destructive rounded-lg border p-3 text-sm">
            <p className="flex items-center gap-2 font-medium">
              <AlertCircle className="size-4" />
              Problems found
            </p>
            <ul className="mt-1 list-disc pl-6">
              {result.errors.map((error, i) => (
                <li key={i}>{error}</li>
              ))}
            </ul>
          </div>
        )}

        <Tabs defaultValue="result">
          <TabsList>
            <TabsTrigger value="result">Result</TabsTrigger>
            {pdfUrl && (
              <TabsTrigger value="draft">Order draft (PDF)</TabsTrigger>
            )}
          </TabsList>

          <TabsContent value="result" className="space-y-6 pt-4">
            {header.length > 0 && (
              <div className="space-y-2">
                <SectionTitle>Purchase order</SectionTitle>
                <HeaderFields entries={header} />
              </div>
            )}

            <div className="space-y-2">
              <SectionTitle>Order lines, BOM details and fees</SectionTitle>
              <div className="overflow-x-auto rounded-xl border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Material</TableHead>
                      <TableHead>Type designation</TableHead>
                      <TableHead>Dimensions</TableHead>
                      <TableHead>Material grade</TableHead>
                      <TableHead className="text-right">
                        Material cost
                      </TableHead>
                      <TableHead>Fees</TableHead>
                      <TableHead className="text-right">Line total</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {result.items.map((item, index) => {
                      const bom = BOM_OF_MATERIAL[item.material];
                      return (
                        <TableRow
                          key={`${item.material}-${index}`}
                          className={cn(
                            "align-top",
                            item.error && "bg-destructive/10",
                          )}
                        >
                          <TableCell className="whitespace-normal">
                            <span className="font-medium whitespace-nowrap">
                              {item.material}
                            </span>
                            <span className="text-muted-foreground block text-xs">
                              {item.description}
                            </span>
                            {bom && (
                              <button
                                type="button"
                                onClick={() => onShowSource(bom)}
                                className="text-primary block text-xs hover:underline"
                              >
                                View {bom.replace(".pdf", "")}
                              </button>
                            )}
                          </TableCell>
                          <TableCell className="whitespace-normal">
                            {text(item.type_designation)}
                          </TableCell>
                          <TableCell className="break-words whitespace-normal">
                            {text(item.bom_dimensions)}
                          </TableCell>
                          <TableCell className="whitespace-normal">
                            {text(item.bom_material_grade)}
                          </TableCell>
                          <TableCell className="text-right whitespace-nowrap">
                            {money(item.material_subtotal)}
                            <span className="text-muted-foreground block text-xs">
                              {item.quantity} × {money(item.unit_price)}
                            </span>
                          </TableCell>
                          <TableCell className="whitespace-normal">
                            <FeeList item={item} />
                          </TableCell>
                          <TableCell className="text-right font-semibold whitespace-nowrap">
                            {money(item.line_total)}
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </div>
            </div>

            <div className="space-y-2">
              <SectionTitle>Order total</SectionTitle>
              <div className="overflow-hidden rounded-xl border sm:max-w-md">
                <Table>
                  <TableBody>
                    {totals.map(({ label, value, strong }) => (
                      <TableRow
                        key={label}
                        className={cn(strong && "bg-primary/5")}
                      >
                        <TableCell
                          className={cn(strong && "text-primary font-semibold")}
                        >
                          {label}
                        </TableCell>
                        <TableCell
                          className={cn(
                            "text-right tabular-nums",
                            strong && "text-primary text-base font-semibold",
                          )}
                        >
                          {value}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
              <p className="text-muted-foreground text-xs">
                Tax applies to the material, the additional fees and the
                shipping.
              </p>
            </div>
          </TabsContent>

          {pdfUrl && (
            <TabsContent value="draft" className="space-y-3 pt-3">
              <div className="bg-muted/15 overflow-hidden rounded-xl border">
                <iframe
                  title="Order draft"
                  src={`${pdfUrl}#toolbar=0`}
                  className="h-[720px] w-full bg-white"
                />
              </div>
              <Button
                type="button"
                variant="outline"
                className="w-full"
                onClick={() => window.open(`${pdfUrl}?download=1`, "_blank")}
              >
                <Download className="mr-2 size-4" />
                Download the order draft PDF
              </Button>
            </TabsContent>
          )}
        </Tabs>
      </CardContent>
    </Card>
  );
}

export type ExtractedData = Record<string, unknown>;

const ACRONYMS = new Set(["po", "bom", "id"]);

/** "purchase_order_number" -> "Purchase order number". */
const fieldLabel = (key: string) =>
  key
    .split("_")
    .map((word, i) =>
      ACRONYMS.has(word.toLowerCase())
        ? word.toUpperCase()
        : i === 0
          ? word.charAt(0).toUpperCase() + word.slice(1)
          : word,
    )
    .join(" ");

const text = (value: unknown) =>
  value === null || value === undefined || value === ""
    ? "-"
    : typeof value === "object"
      ? JSON.stringify(value)
      : String(value);

/** A header value as it reads best: amounts as money, rates as percent. */
function headerValue(key: string, value: unknown): string {
  if (typeof value === "number") {
    if (/cost|charge|amount|fee/i.test(key)) return money(value);
    if (/rate|percent/i.test(key)) return `${value}%`;
  }
  return text(value);
}

/** The header fields of a purchase order as cards. Both examples show them this way. */
function HeaderFields({ entries }: { entries: [string, unknown][] }) {
  return (
    <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {entries.map(([key, value]) => (
        <div
          key={key}
          className={cn(
            "rounded-xl border p-3",
            String(value ?? "").length > 40 && "sm:col-span-2",
          )}
        >
          <dt className="text-muted-foreground text-xs">{fieldLabel(key)}</dt>
          <dd className="mt-0.5 text-sm font-semibold break-words">
            {headerValue(key, value)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

type Row = Record<string, unknown>;

/** The number in "200 pcs" or "28.50"; null when there is none. */
function toNumber(value: unknown): number | null {
  const parsed = parseFloat(
    String(value ?? "")
      .replace(/[^\d.,-]/g, "")
      .replace(/,/g, ""),
  );
  return Number.isFinite(parsed) ? parsed : null;
}

/** The value of the first column whose name matches, for each row. */
const columnOf = (rows: Row[], pattern: RegExp) => {
  const key = Object.keys(rows[0] ?? {}).find((name) => pattern.test(name));
  return key ? rows.map((row) => row[key]) : null;
};

/**
 * The extracted purchase order, laid out like the processed order of the other
 * example: header fields, a table of the order lines, and the order total.
 */
export function SingleResults({
  data,
  seconds,
  onShowSource,
}: {
  data: ExtractedData;
  seconds: number | null;
  onShowSource: (file: string) => void;
}) {
  const entries = Object.entries(data);
  const header = entries.filter(([, value]) => !Array.isArray(value));
  const lists = entries.filter(([, value]) => Array.isArray(value)) as [
    string,
    unknown[],
  ][];
  const number = header.find(([key]) => /number|order_no/i.test(key))?.[1];

  return (
    <Card id="example-results" className="scroll-mt-24">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <CheckCircle2 className="text-success size-5" />
          The processed order
        </CardTitle>
        <CardDescription>
          <span className="text-foreground font-medium">
            {number ? `${text(number)} · ` : ""}
            {seconds !== null ? `Read in ${seconds.toFixed(1)} s` : ""}
          </span>
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {header.length > 0 && (
          <div className="space-y-2">
            <SectionTitle>Purchase order</SectionTitle>
            <HeaderFields entries={header} />
          </div>
        )}

        {lists.map(([key, items]) => {
          const rows = items.filter(
            (item): item is Row => typeof item === "object" && item !== null,
          );
          const columns = [...new Set(rows.flatMap((row) => Object.keys(row)))];
          const quantities = columnOf(rows, /quantity/i)?.map(toNumber);
          const prices = columnOf(rows, /price/i)?.map(toNumber);
          const subtotal =
            quantities &&
            prices &&
            quantities.every((q) => q !== null) &&
            prices.every((p) => p !== null)
              ? quantities.reduce(
                  (sum, q, i) => sum + (q ?? 0) * (prices[i] ?? 0),
                  0,
                )
              : null;

          return (
            <div key={key} className="space-y-6">
              <div className="space-y-2">
                <SectionTitle>
                  {fieldLabel(key)} ({rows.length})
                </SectionTitle>
                <div className="overflow-x-auto rounded-xl border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        {columns.map((column) => (
                          <TableHead key={column}>
                            {fieldLabel(column)}
                          </TableHead>
                        ))}
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {rows.map((row, index) => (
                        <TableRow key={index} className="align-top">
                          {columns.map((column) => (
                            <TableCell
                              key={column}
                              className="whitespace-normal"
                            >
                              {text(row[column])}
                            </TableCell>
                          ))}
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
                <button
                  type="button"
                  onClick={() => onShowSource("PO.pdf")}
                  className="text-primary text-xs hover:underline"
                >
                  View the purchase order
                </button>
              </div>

              {subtotal !== null && (
                <div className="space-y-2">
                  <SectionTitle>Order total</SectionTitle>
                  <div className="overflow-hidden rounded-xl border sm:max-w-md">
                    <Table>
                      <TableBody>
                        <TableRow className="bg-primary/5">
                          <TableCell className="text-primary font-semibold">
                            Material subtotal
                          </TableCell>
                          <TableCell className="text-primary text-right text-base font-semibold tabular-nums">
                            {money(subtotal)}
                          </TableCell>
                        </TableRow>
                      </TableBody>
                    </Table>
                  </div>
                  <p className="text-muted-foreground text-xs">
                    Calculated from the extracted quantities and prices. Fees,
                    shipping and tax are not among this example&apos;s fields.
                  </p>
                </div>
              )}
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
