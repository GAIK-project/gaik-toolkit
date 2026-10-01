"use client";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
} from "@/components/ui/card";
import { apiFetch } from "@/lib/api-client";
import { parseSSEEvents } from "@/lib/sse";
import { cn } from "@/lib/utils";
import { SectionGuide, type GuideStep } from "@/components/demo/section-guide";
import {
  ArrowRight,
  Calculator,
  CheckCircle2,
  ExternalLink,
  FileSearch,
  FileSpreadsheet,
  FileText,
  Files,
  Layers,
  ListChecks,
  Table2,
  Loader2,
  Play,
  Sparkles,
  Wand2,
} from "lucide-react";
import posthog from "posthog-js";
import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";
import {
  BOM_OF_MATERIAL,
  EXAMPLE_CASES,
  EXAMPLE_DIR,
  EXAMPLE_DOCUMENTS,
  type ExampleCase,
  type ExampleDocument,
  PROCESS_STEPS,
  SINGLE_EXAMPLE_DIR,
  SINGLE_EXAMPLE_DOCUMENTS,
  SINGLE_PROCESS_STEPS,
  stepOfStatus,
} from "./example-data";
import {
  type ExtractedData,
  ExampleResults,
  type ProcessOrderResponse,
  SingleResults,
} from "./example-results";

const PIPELINES = {
  multi: [
    { icon: Files, label: "Documents", detail: "PO, BOMs, price list" },
    { icon: Sparkles, label: "Extract", detail: "AI reads the fields" },
    { icon: ListChecks, label: "Match", detail: "Each line to its BOM" },
    { icon: Calculator, label: "Price", detail: "Material plus fees" },
    { icon: FileText, label: "Order draft", detail: "Totals and PDF" },
  ],
  single: [
    { icon: FileText, label: "Document", detail: "One purchase order PDF" },
    { icon: Sparkles, label: "Extract", detail: "AI reads the fields" },
    { icon: Table2, label: "Structured data", detail: "Header and line items" },
  ],
};

const DESCRIPTIONS: Record<ExampleCase, string> = {
  single:
    "A purchase order arrives as a single PDF. The model reads its header fields and every line item into structured data. Browse the document, see what is read from it, then process it.",
  multi:
    "A customer sends a purchase order with three bills of materials (BOMs). The supplier's price list turns it into a priced order draft. Browse the documents, see what is read from each, then process them.",
};

async function detail(response: Response, fallback: string) {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
  } catch {
    // Not JSON: keep the fallback.
  }
  return fallback;
}

const fileUrl = (dir: string, file: string) =>
  `${dir}/${encodeURIComponent(file)}`;

function DocumentIcon({ doc }: { doc: ExampleDocument }) {
  const Icon = doc.kind === "price" ? FileSpreadsheet : FileText;
  return (
    <span
      className={cn(
        "flex size-9 shrink-0 items-center justify-center rounded-lg",
        doc.kind === "po" && "bg-primary/10 text-primary",
        doc.kind === "bom" && "bg-sky-500/10 text-sky-700",
        doc.kind === "price" && "bg-amber-500/10 text-amber-700",
      )}
    >
      <Icon className="size-4" />
    </span>
  );
}

type Cell = string | number | null;

/** Money-like columns (prices and fees) read best with two decimals. */
const isMoneyColumn = (title: Cell) => /price|fee/i.test(String(title ?? ""));

/**
 * The whole master price list, in a box that scrolls both ways. The rows this order
 * uses are highlighted. The sheet comes from price-list.json, a copy of the xlsx that
 * scripts/build_example_price_list.py keeps in step.
 */
function PriceList({ highlight }: { highlight: string[] }) {
  const [rows, setRows] = useState<Cell[][] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let active = true;
    fetch(`${EXAMPLE_DIR}/price-list.json`)
      .then((response) => {
        if (!response.ok) throw new Error(String(response.status));
        return response.json() as Promise<{ rows: Cell[][] }>;
      })
      .then((data) => active && setRows(data.rows))
      .catch(() => active && setFailed(true));
    return () => {
      active = false;
    };
  }, []);

  if (failed) {
    return (
      <p className="text-muted-foreground p-4 text-sm">
        The price list could not be shown here. Use Open file to see it.
      </p>
    );
  }
  if (!rows) {
    return (
      <p className="text-muted-foreground p-4 text-sm">
        Loading the price list…
      </p>
    );
  }

  const columns = Math.max(...rows.map((row) => row.length));
  const header = rows.find((row) => /^item no/i.test(String(row[0] ?? "")));
  const used = rows.filter((row) => highlight.includes(String(row[0]))).length;
  const total = rows.filter((row) =>
    /^[A-Z]{2,3}-\d+/.test(String(row[0])),
  ).length;

  return (
    <div className="space-y-2 p-4">
      <p className="text-muted-foreground text-xs">
        The whole master price list. The {used} of {total} materials this order
        uses are highlighted.
      </p>
      <div className="max-h-[480px] overflow-auto rounded-lg border bg-white">
        <table className="w-full min-w-[820px] text-sm">
          <tbody>
            {rows.map((row, index) => {
              const filled = row.filter((cell) => cell !== null);
              if (filled.length === 0) {
                return (
                  <tr key={index}>
                    <td colSpan={columns} className="h-2" />
                  </tr>
                );
              }
              if (row === header) {
                return (
                  <tr key={index}>
                    {Array.from({ length: columns }, (_, i) => (
                      <th
                        key={i}
                        className="bg-muted sticky top-0 z-10 px-3 py-2 text-left text-xs font-medium whitespace-nowrap"
                      >
                        {row[i] ?? ""}
                      </th>
                    ))}
                  </tr>
                );
              }
              if (filled.length === 1) {
                const label = String(filled[0]);
                const section = /^[A-Z0-9 &/-]+$/.test(label);
                return (
                  <tr key={index}>
                    <td
                      colSpan={columns}
                      className={cn(
                        "px-3 py-1.5",
                        section
                          ? "bg-muted/60 text-xs font-semibold tracking-wide"
                          : "text-muted-foreground text-xs",
                      )}
                    >
                      {label}
                    </td>
                  </tr>
                );
              }
              return (
                <tr
                  key={index}
                  className={cn(
                    "border-t",
                    highlight.includes(String(row[0])) && "bg-primary/10",
                  )}
                >
                  {Array.from({ length: columns }, (_, i) => {
                    const cell = row[i] ?? null;
                    const money =
                      typeof cell === "number" &&
                      isMoneyColumn(header?.[i] ?? null);
                    return (
                      <td
                        key={i}
                        className={cn(
                          "px-3 py-1.5 whitespace-nowrap",
                          i === 0 && "font-medium",
                          typeof cell === "number" && "tabular-nums",
                        )}
                      >
                        {money ? cell.toFixed(2) : (cell ?? "")}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const MULTI_GUIDE_STEPS: GuideStep[] = [
  {
    icon: Layers,
    title: "Pick an example",
    text: "Single-file purchase order, or purchase order + BOMs + price list. The two cards below switch between them.",
  },
  {
    icon: FileSearch,
    title: "Read the documents",
    text: "Click a document to open it and see which fields are read from it.",
  },
  {
    icon: Play,
    title: "Process the example",
    text: "Press the button. The steps parsing, extracting and preparing results show the progress.",
  },
  {
    icon: ListChecks,
    title: "Explore the result",
    text: "Header fields, order lines with BOM details and fees, and the order total. Click a BOM name to see its source, and open the order draft PDF.",
  },
];
const MULTI_GUIDE_NOTES = [
  "Fees come from the price list: cutting, testing and certificates by the row rate, hydrostatic testing and packaging by a flat rate per unit. Tax applies to material, fees and shipping.",
  "The example documents are fixed. To try your own documents or fields, open Test with your own data or examples.",
];
const SINGLE_GUIDE_STEPS: GuideStep[] = [
  {
    icon: Layers,
    title: "Pick an example",
    text: "Single-file purchase order, or purchase order + BOMs + price list.",
  },
  {
    icon: FileSearch,
    title: "Read the document",
    text: "Open the purchase order and see the fields that are read from it.",
  },
  {
    icon: Play,
    title: "Process the example",
    text: "Press the button. The first run generates and saves the schema, so it takes longer than later runs.",
  },
  {
    icon: ListChecks,
    title: "Explore the result",
    text: "Header fields, order lines and the subtotal. Click the file name to jump back to the source.",
  },
];
const SINGLE_GUIDE_NOTES = [
  "This example only extracts what the order states. It does not price the fees listed under each position or calculate a new total.",
  "The example document is fixed. To try your own documents or fields, open Test with your own data or examples.",
];

/**
 * The fixed example of purchase order processing: the documents and what is read from
 * them, a button that processes them, and the result to explore. The user's own
 * documents go through "Test with your own data or examples".
 */
export function ExampleShowcase({ onCreate }: { onCreate?: () => void }) {
  const [caseKey, setCaseKey] = useState<ExampleCase>("single");
  const [activeFile, setActiveFile] = useState("PO.pdf");
  const [processing, setProcessing] = useState(false);
  const [step, setStep] = useState(-1);
  const [result, setResult] = useState<ProcessOrderResponse | null>(null);
  const [singleResult, setSingleResult] = useState<{
    data: ExtractedData;
    seconds: number;
  } | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const explorerRef = useRef<HTMLDivElement>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  const single = caseKey === "single";
  const documents = single ? SINGLE_EXAMPLE_DOCUMENTS : EXAMPLE_DOCUMENTS;
  const dir = single ? SINGLE_EXAMPLE_DIR : EXAMPLE_DIR;
  const stepLabels = single
    ? SINGLE_PROCESS_STEPS
    : PROCESS_STEPS.map((item) => item.label);
  const hasResult = single ? singleResult !== null : result !== null;
  const active =
    documents.find((doc) => doc.file === activeFile) ?? documents[0];

  const changeCase = (next: ExampleCase) => {
    abortRef.current?.abort();
    setCaseKey(next);
    setActiveFile("PO.pdf");
    setProcessing(false);
    setStep(-1);
  };

  const showSource = (file: string) => {
    setActiveFile(file);
    explorerRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const fetchExample = async (file: string) => {
    const response = await fetch(fileUrl(dir, file));
    if (!response.ok) throw new Error(`Failed to fetch ${file}`);
    return new File([await response.blob()], file);
  };

  const processOrder = async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setProcessing(true);
    setStep(0);
    setResult(null);
    try {
      const [po, pricing, ...boms] = await Promise.all([
        fetchExample("PO.pdf"),
        fetchExample("price list.xlsx"),
        ...EXAMPLE_DOCUMENTS.filter((doc) => doc.kind === "bom").map((doc) =>
          fetchExample(doc.file),
        ),
      ]);
      const formData = new FormData();
      formData.append("po_file", po);
      formData.append("pricing_file", pricing);
      boms.forEach((bom) => formData.append("bom_files", bom));

      posthog.capture("luvata_order_process_started", { example: true });
      const response = await apiFetch("/api/luvata-order/process", {
        method: "POST",
        body: formData,
        signal: controller.signal,
      });
      if (!response.ok) throw new Error("Failed to process order");
      const reader = response.body?.getReader();
      if (!reader) throw new Error("No response body");

      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const { events, remaining } = parseSSEEvents(buffer);
        buffer = remaining;
        for (const event of events) {
          if (event.type === "status") {
            const index = stepOfStatus(String(event.data.message ?? ""));
            if (index >= 0) setStep((prev) => Math.max(prev, index));
          } else if (event.type === "complete") {
            setStep(PROCESS_STEPS.length);
            setResult(event.data as unknown as ProcessOrderResponse);
            setProcessing(false);
            toast.success("Example processed");
            posthog.capture("luvata_order_process_completed", {
              example: true,
              items_count: (event.data.items as unknown[])?.length || 0,
            });
            requestAnimationFrame(() =>
              document
                .getElementById("example-results")
                ?.scrollIntoView({ behavior: "smooth", block: "start" }),
            );
          } else if (event.type === "error") {
            setProcessing(false);
            toast.error((event.data.message as string) || "Processing failed");
          }
        }
      }
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") return;
      toast.error("An error occurred");
      console.error(error);
    } finally {
      setProcessing(false);
    }
  };

  const processSingle = async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setProcessing(true);
    setStep(0);
    setSingleResult(null);
    const started = performance.now();
    try {
      const po = await fetchExample("PO.pdf");
      posthog.capture("luvata_order_process_started", {
        example: true,
        single: true,
      });

      // The schema is generated once and saved by the server; later runs reuse it.
      const schemaResponse = await apiFetch(
        "/api/luvata-order/example/single/schema",
        { method: "POST", signal: controller.signal },
      );
      if (!schemaResponse.ok) {
        throw new Error(
          await detail(schemaResponse, "Failed to prepare the extraction"),
        );
      }

      setStep(1);
      const formData = new FormData();
      formData.append("po_file", po);
      const response = await apiFetch(
        "/api/luvata-order/example/single/extract",
        {
          method: "POST",
          body: formData,
          signal: controller.signal,
        },
      );
      if (!response.ok) {
        throw new Error(await detail(response, "Extraction failed"));
      }
      const body = (await response.json()) as { data: ExtractedData };

      setStep(SINGLE_PROCESS_STEPS.length);
      setSingleResult({
        data: body.data,
        seconds: (performance.now() - started) / 1000,
      });
      toast.success("Example processed");
      posthog.capture("luvata_order_process_completed", {
        example: true,
        single: true,
      });
      requestAnimationFrame(() =>
        document
          .getElementById("example-results")
          ?.scrollIntoView({ behavior: "smooth", block: "start" }),
      );
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") return;
      toast.error(error instanceof Error ? error.message : "An error occurred");
      console.error(error);
    } finally {
      setProcessing(false);
    }
  };

  const processExample = single ? processSingle : processOrder;

  return (
    <div className="space-y-6">
      <SectionGuide
        heading="How to try the example"
        steps={single ? SINGLE_GUIDE_STEPS : MULTI_GUIDE_STEPS}
        notes={single ? SINGLE_GUIDE_NOTES : MULTI_GUIDE_NOTES}
      />
      <Card>
        <CardHeader>
          <CardDescription>{DESCRIPTIONS[caseKey]}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Which example to look at */}
          <div
            role="radiogroup"
            aria-label="Example"
            className="grid gap-3 sm:grid-cols-2"
          >
            {EXAMPLE_CASES.map(({ value, title, description }) => (
              <label
                key={value}
                className={cn(
                  "has-checked:border-primary has-checked:bg-primary/5 flex cursor-pointer items-start gap-3 rounded-xl border p-3.5 transition-colors",
                  caseKey !== value && "hover:bg-muted/50",
                  processing && "cursor-not-allowed opacity-60",
                )}
              >
                <input
                  type="radio"
                  name="example-case"
                  value={value}
                  checked={caseKey === value}
                  disabled={processing}
                  onChange={() => changeCase(value)}
                  className="sr-only"
                />
                <span className="bg-primary/10 text-primary flex size-9 shrink-0 items-center justify-center rounded-lg">
                  {value === "single" ? (
                    <FileText className="size-4" />
                  ) : (
                    <Files className="size-4" />
                  )}
                </span>
                <span>
                  <span className="block font-semibold">{title}</span>
                  <span className="text-muted-foreground block text-sm">
                    {description}
                  </span>
                </span>
              </label>
            ))}
          </div>

          {/* The path from documents to the result */}
          <ol
            className={cn(
              "grid gap-2",
              single ? "sm:grid-cols-3" : "sm:grid-cols-5",
            )}
          >
            {PIPELINES[caseKey].map(({ icon: Icon, label, detail }, index) => (
              <li
                key={label}
                className="bg-muted/40 relative flex items-center gap-3 rounded-xl border p-3"
              >
                <span className="bg-primary/10 text-primary flex size-8 shrink-0 items-center justify-center rounded-lg">
                  <Icon className="size-4" />
                </span>
                <span className="min-w-0">
                  <span className="block text-sm font-semibold">{label}</span>
                  <span className="text-muted-foreground block text-xs">
                    {detail}
                  </span>
                </span>
                {index < PIPELINES[caseKey].length - 1 && (
                  <ArrowRight className="text-muted-foreground/50 absolute top-1/2 -right-2.5 z-10 hidden size-4 -translate-y-1/2 sm:block" />
                )}
              </li>
            ))}
          </ol>

          {/* The documents, and what is read from each */}
          <div
            ref={explorerRef}
            className="grid scroll-mt-24 gap-4 lg:grid-cols-[17rem_minmax(0,1fr)]"
          >
            <div
              role="tablist"
              aria-label="Example documents"
              className="grid content-start gap-2"
            >
              {documents.map((doc) => (
                <button
                  key={doc.file}
                  type="button"
                  role="tab"
                  aria-selected={doc.file === active.file}
                  onClick={() => setActiveFile(doc.file)}
                  className={cn(
                    "flex items-start gap-3 rounded-xl border p-3 text-left transition-colors",
                    doc.file === active.file
                      ? "border-primary bg-primary/5"
                      : "hover:bg-muted/50",
                  )}
                >
                  <DocumentIcon doc={doc} />
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-2">
                      <span className="truncate text-sm font-semibold">
                        {doc.title}
                      </span>
                      {hasResult && (
                        <CheckCircle2 className="text-success size-3.5 shrink-0" />
                      )}
                    </span>
                    <span className="text-muted-foreground block truncate text-xs">
                      {doc.file}
                    </span>
                  </span>
                </button>
              ))}
            </div>

            <div className="min-w-0 space-y-3 rounded-xl border p-4">
              <div key={active.file} className="space-y-4">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <h3 className="font-semibold">{active.title}</h3>
                    <p className="text-muted-foreground text-sm">
                      {active.summary}
                    </p>
                  </div>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() =>
                      window.open(fileUrl(dir, active.file), "_blank")
                    }
                  >
                    <ExternalLink className="mr-1.5 size-3.5" />
                    Open file
                  </Button>
                </div>

                <div className="space-y-3">
                  <p className="text-sm font-semibold">
                    {active.method === "ai"
                      ? "Extracted by AI"
                      : "Read from the sheet"}
                  </p>
                  {(
                    active.groups ?? [{ title: "", fields: active.fields }]
                  ).map((group) => (
                    <div key={group.title} className="space-y-1.5">
                      {group.title && (
                        <p className="text-muted-foreground text-xs font-medium">
                          {group.title}
                        </p>
                      )}
                      <ul className="flex flex-wrap gap-2">
                        {group.fields.map((field) => (
                          <li
                            key={field.name}
                            className="bg-primary/5 border-primary/20 rounded-lg border px-2.5 py-1 text-sm"
                          >
                            <span className="font-medium">{field.name}</span>
                            {field.note && (
                              <span className="text-muted-foreground ml-2 text-xs">
                                {field.note}
                              </span>
                            )}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>

                <div className="bg-muted/15 overflow-hidden rounded-lg border">
                  {active.kind === "price" ? (
                    <PriceList highlight={Object.keys(BOM_OF_MATERIAL)} />
                  ) : (
                    <iframe
                      title={active.title}
                      src={`${fileUrl(dir, active.file)}#toolbar=0&view=FitH`}
                      className="h-[520px] w-full bg-white"
                    />
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Process */}
          <div className="space-y-3 border-t pt-5">
            <div className="flex flex-wrap items-center gap-3">
              <Button
                type="button"
                size="lg"
                disabled={processing}
                onClick={processExample}
                className="h-11 rounded-xl px-6 font-semibold shadow-sm"
              >
                {processing ? (
                  <>
                    <Loader2 className="mr-2 size-4 animate-spin" />
                    Processing...
                  </>
                ) : (
                  <>
                    <Play className="mr-2 size-4" />
                    {hasResult
                      ? "Process the example again"
                      : "Process the example"}
                  </>
                )}
              </Button>
              <button
                type="button"
                onClick={onCreate}
                className="text-primary inline-flex items-center gap-1.5 text-sm font-medium hover:underline"
              >
                <Wand2 className="size-4" />
                Want other fields or your own documents? Test with your own data
              </button>
            </div>

            {(processing || step >= 0) && !hasResult && (
              <ol className="grid gap-2 sm:grid-cols-3">
                {stepLabels.map((label, index) => {
                  const done = index < step;
                  const current = index === step && processing;
                  return (
                    <li
                      key={label}
                      className={cn(
                        "flex items-center gap-2 rounded-lg border px-3 py-2 text-sm transition-colors",
                        done && "border-emerald-500/30 bg-emerald-500/5",
                        current && "border-primary bg-primary/5",
                        !done && !current && "text-muted-foreground",
                      )}
                    >
                      {done ? (
                        <CheckCircle2 className="size-4 shrink-0 text-emerald-600" />
                      ) : current ? (
                        <Loader2 className="text-primary size-4 shrink-0 animate-spin" />
                      ) : (
                        <span className="border-muted-foreground/40 size-4 shrink-0 rounded-full border" />
                      )}
                      {label}
                    </li>
                  );
                })}
              </ol>
            )}
          </div>
        </CardContent>
      </Card>

      {!single && result && (
        <ExampleResults result={result} onShowSource={showSource} />
      )}
      {single && singleResult && (
        <SingleResults
          data={singleResult.data}
          seconds={singleResult.seconds}
          onShowSource={showSource}
        />
      )}
    </div>
  );
}
