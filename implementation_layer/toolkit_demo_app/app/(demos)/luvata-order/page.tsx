"use client";

import { FileUpload } from "@/components/demo/file-upload";
import { FeedbackButton } from "@/components/feedback";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { parseSSEEvents } from "@/lib/sse";
import { apiFetch } from "@/lib/api-client";
import { formatFileSize } from "@/lib/utils";
import {
  AlertCircle,
  CheckCircle,
  CheckCircle2,
  Download,
  File as FileIcon,
  FileText,
  Loader2,
  ArrowLeft,
  ChevronDown,
  Package,
  RotateCcw,
  Upload,
  X,
} from "lucide-react";
import { motion } from "motion/react";
import posthog from "posthog-js";
import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import toast from "react-hot-toast";

interface EnrichedItem {
  material: string;
  description: string;
  type_designation?: string | null;
  quantity: number;
  unit_price?: number | null;
  material_subtotal?: number | null;
  cutting_fee: number;
  testing_fee: number;
  cert_fee: number;
  total_fees: number;
  line_total?: number | null;
  delivery_date?: string | null;
  bom_match: boolean;
  price_match: boolean;
  error?: string | null;
}

interface OrderSummary {
  total_items: number;
  total_quantity: number;
  material_subtotal: number;
  total_fees: number;
  grand_total: number;
}

interface ProcessOrderResponse {
  success: boolean;
  po_number?: string | null;
  customer?: string | null;
  items: EnrichedItem[];
  summary?: OrderSummary | null;
  errors: string[];
  warnings: string[];
  pdf_job_id?: string | null;
}

export default function LuvataOrderPage() {
  const router = useRouter();
  const abortControllerRef = useRef<AbortController | null>(null);
  const [poFile, setPoFile] = useState<File | null>(null);
  const [bomFiles, setBomFiles] = useState<File[]>([]);
  const [pricingFile, setPricingFile] = useState<File | null>(null);
  const [processing, setProcessing] = useState(false);
  const [progress, setProgress] = useState(0);
  const [statusMessage, setStatusMessage] = useState("");
  const [result, setResult] = useState<ProcessOrderResponse | null>(null);
  const [howItWorksOpen, setHowItWorksOpen] = useState(false);
  const [sourceDocumentsOpen, setSourceDocumentsOpen] = useState(false);
  const [activeDocumentTab, setActiveDocumentTab] = useState("po");
  const [previewUrls, setPreviewUrls] = useState<Record<string, string>>({});
  const [pricingPreviewText, setPricingPreviewText] = useState("");

  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  const loadExampleData = async () => {
    try {
      const fetchExampleFile = async (url: string) => {
        const response = await fetch(url);
        if (!response.ok) {
          throw new Error(`Failed to fetch example asset: ${url} (${response.status})`);
        }
        return response.blob();
      };

      const [poBlob, pricingBlob, bom1Blob, bom2Blob, bom3Blob] =
        await Promise.all([
          fetchExampleFile("/data/po-bom-example/PO.pdf"),
          fetchExampleFile("/data/po-bom-example/price%20list.xlsx"),
          fetchExampleFile("/data/po-bom-example/BOM1.pdf"),
          fetchExampleFile("/data/po-bom-example/BOM2.pdf"),
          fetchExampleFile("/data/po-bom-example/BOM3.pdf"),
        ]);

      setPoFile(new File([poBlob], "PO.pdf", { type: "application/pdf" }));
      setPricingFile(
        new File([pricingBlob], "price list.xlsx", {
          type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }),
      );
      setBomFiles([
        new File([bom1Blob], "BOM1.pdf", { type: "application/pdf" }),
        new File([bom2Blob], "BOM2.pdf", { type: "application/pdf" }),
        new File([bom3Blob], "BOM3.pdf", { type: "application/pdf" }),
      ]);

      toast.success("Example data loaded");
      posthog.capture("luvata_order_example_loaded");
    } catch (error) {
      toast.error("Failed to load example data");
      console.error(error);
    }
  };

  const processOrder = async () => {
    if (!poFile) {
      toast.error("Please upload a purchase order");
      return;
    }
    if (bomFiles.length === 0) {
      toast.error("Please upload at least one BOM");
      return;
    }
    if (!pricingFile) {
      toast.error("Please upload a pricing table");
      return;
    }

    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();

    setProcessing(true);
    setProgress(0);
    setStatusMessage("Starting order processing...");
    setResult(null);

    try {
      const formData = new FormData();
      formData.append("po_file", poFile);
      formData.append("pricing_file", pricingFile);
      bomFiles.forEach((file) => {
        formData.append("bom_files", file);
      });

      posthog.capture("luvata_order_process_started", {
        bom_count: bomFiles.length,
      });

      const response = await apiFetch("/api/luvata-order/process", {
        method: "POST",
        body: formData,
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok) {
        throw new Error("Failed to process order");
      }

      // Stream SSE events
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
            setStatusMessage((event.data.message as string) || "Processing...");
            setProgress((prev) => Math.min(prev + 15, 90));
          } else if (event.type === "complete") {
            setProgress(100);
            setResult(event.data as unknown as ProcessOrderResponse);
            setProcessing(false);
            toast.success("Order processed successfully");
            posthog.capture("luvata_order_process_completed", {
              items_count: (event.data.items as unknown[])?.length || 0,
              has_errors: ((event.data.errors as unknown[])?.length || 0) > 0,
            });
          } else if (event.type === "error") {
            setProcessing(false);
            toast.error((event.data.message as string) || "Processing failed");
            posthog.capture("luvata_order_process_failed", {
              error: event.data.message,
            });
          }
        }
      }
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") return;
      setProcessing(false);
      toast.error("An error occurred");
      console.error(error);
    }
  };

  useEffect(() => {
    const nextUrls: Record<string, string> = {};
    const createdUrls: string[] = [];

    if (poFile) {
      const url = URL.createObjectURL(poFile);
      nextUrls.po = url;
      createdUrls.push(url);
    }

    bomFiles.forEach((file, index) => {
      const url = URL.createObjectURL(file);
      nextUrls[`bom-${index}`] = url;
      createdUrls.push(url);
    });

    if (pricingFile) {
      const url = URL.createObjectURL(pricingFile);
      nextUrls.pricing = url;
      createdUrls.push(url);
    }

    setPreviewUrls(nextUrls);

    return () => {
      createdUrls.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [poFile, bomFiles, pricingFile]);

  useEffect(() => {
    if (!pricingFile) {
      setPricingPreviewText("");
      return;
    }

    if (!pricingFile.name.toLowerCase().endsWith(".csv")) {
      setPricingPreviewText("");
      return;
    }

    pricingFile
      .text()
      .then((content) => {
        setPricingPreviewText(content.split("\n").slice(0, 20).join("\n"));
      })
      .catch(() => {
        setPricingPreviewText("");
      });
  }, [pricingFile]);

  const documentTabs = useMemo(() => [
    ...(poFile ? [{ key: "po", label: "PO", type: "pdf" as const, file: poFile }] : []),
    ...bomFiles.map((file, index) => ({
      key: `bom-${index}`,
      label: `BOM ${index + 1}`,
      type: "pdf" as const,
      file,
    })),
    ...(pricingFile
      ? [{ key: "pricing", label: "Pricing table", type: "sheet" as const, file: pricingFile }]
      : []),
  ], [poFile, bomFiles, pricingFile]);

  useEffect(() => {
    if (documentTabs.length === 0) {
      setActiveDocumentTab("po");
      return;
    }

    if (!documentTabs.some((tab) => tab.key === activeDocumentTab)) {
      setActiveDocumentTab(documentTabs[0].key);
    }
  }, [documentTabs, activeDocumentTab]);

  const activeDocument = documentTabs.find((tab) => tab.key === activeDocumentTab) ?? null;

  const resetDemo = () => {
    setPoFile(null);
    setBomFiles([]);
    setPricingFile(null);
    setResult(null);
    setProgress(0);
    setStatusMessage("");
  };

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      {/* Header */}
      <div className="space-y-4">
        <div>
          <Button
            type="button"
            variant="ghost"
            className="-ml-3 h-9 rounded-full px-3 text-sm"
            onClick={() => {
              router.push("/");
            }}
          >
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back
          </Button>
        </div>

        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="flex items-center gap-2 font-serif text-3xl font-semibold tracking-tight">
              <Package className="h-8 w-8" />
              Purchase Order Processing
            </h1>
            <p className="mt-2 text-muted-foreground">
              Process purchase orders with BOM matching and automated pricing
              calculations
            </p>
          </div>
          <FeedbackButton demoType="luvata-order" />
        </div>
      </div>

      {/* Upload Section */}
      <Card>
        <CardHeader>
          <CardTitle>Upload Documents</CardTitle>
          <CardDescription>
            Upload a purchase order PDF, BOM PDFs, and a pricing table
            (CSV/Excel)
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-3 md:items-start">
            <div className="flex flex-col gap-2">
              <label className="block text-sm font-medium">Purchase Order PDF</label>
              <FileUpload
                accept=".pdf"
                file={poFile}
                onFileSelect={setPoFile}
              />
            </div>
            <div className="flex flex-col gap-2 w-full">
              <label className="block text-sm font-medium">
                BOM PDFs (multiple)
              </label>

              {bomFiles.length > 0 ? (
                <div className="space-y-2">
                  {bomFiles.map((file, index) => (
                    <div
                      key={`${file.name}-${index}`}
                      className="flex items-center gap-3 rounded-lg border border-success/30 bg-success/10 p-4"
                    >
                      <CheckCircle className="h-5 w-5 text-success" />
                      <FileIcon className="h-5 w-5 text-muted-foreground" />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium">{file.name}</p>
                        <p className="text-xs text-muted-foreground">
                          {formatFileSize(file.size)}
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() => {
                          setBomFiles(bomFiles.filter((_, fileIndex) => fileIndex !== index));
                        }}
                        className="rounded-full p-1 transition-colors hover:bg-success/20"
                        aria-label={`Remove ${file.name}`}
                      >
                        <X className="h-4 w-4" />
                      </button>
                    </div>
                  ))}

                  <label className="flex cursor-pointer items-center justify-center gap-2 rounded-lg border border-dashed border-muted-foreground/25 px-4 py-3 text-sm font-medium text-muted-foreground transition-colors hover:border-primary/50 hover:bg-muted/50">
                    <Upload className="h-4 w-4" />
                    Add more BOM PDFs
                    <input
                      type="file"
                      accept=".pdf"
                      multiple
                      onChange={(e) => {
                        const files = Array.from(e.target.files || []);
                        if (files.length > 0) {
                          setBomFiles([...bomFiles, ...files]);
                        }
                      }}
                      className="sr-only"
                    />
                  </label>
                </div>
              ) : (
                <label className="flex min-h-[176px] cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed border-muted-foreground/25 p-8 transition-all hover:border-primary/50 hover:bg-muted/50">
                  <Upload className="h-10 w-10 text-muted-foreground" />
                  <div className="text-center">
                    <p className="font-medium">Drag & drop or click to upload</p>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Supports: .pdf (multiple files, max 10MB each)
                    </p>
                  </div>
                  <input
                    type="file"
                    accept=".pdf"
                    multiple
                    onChange={(e) => {
                      const files = Array.from(e.target.files || []);
                      setBomFiles(files);
                    }}
                    className="sr-only"
                  />
                </label>
              )}
            </div>
            <div className="flex flex-col gap-2">
              <label className="block text-sm font-medium">Pricing Table</label>
              <FileUpload
                accept=".csv,.xlsx"
                file={pricingFile}
                onFileSelect={setPricingFile}
              />
            </div>
          </div>

          <div className="border-t border-border/60 pt-4">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <Button
                onClick={processOrder}
                disabled={
                  processing || !poFile || bomFiles.length === 0 || !pricingFile
                }
                className="h-11 w-full rounded-xl px-6 text-sm font-semibold shadow-sm lg:flex-1"
              >
                {processing ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Processing...
                  </>
                ) : (
                  <>
                    <Package className="mr-2 h-4 w-4" />
                    Process Order
                  </>
                )}
              </Button>

              <div className="flex flex-wrap items-center gap-2 lg:justify-end">
                <Button
                  onClick={loadExampleData}
                  type="button"
                  variant="secondary"
                  className="h-11 rounded-xl px-4 text-sm font-medium shadow-sm"
                >
                  <FileText className="mr-2 h-4 w-4" />
                  Load Example
                </Button>

                {(poFile || bomFiles.length > 0 || pricingFile) && (
                  <Button
                    onClick={resetDemo}
                    type="button"
                    variant="outline"
                    className="h-11 rounded-xl px-4 text-sm font-medium"
                  >
                    <RotateCcw className="mr-2 h-4 w-4" />
                    Reset
                  </Button>
                )}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {documentTabs.length > 0 && (
        <Card>
          <button
            type="button"
            onClick={() => setSourceDocumentsOpen((open) => !open)}
            className="flex w-full items-center justify-between px-6 py-5 text-left transition-colors hover:bg-muted/30"
            aria-expanded={sourceDocumentsOpen}
          >
            <div>
              <h2 className="text-lg font-semibold text-foreground">Source Documents</h2>
              <p className="mt-1 text-sm text-muted-foreground">View the uploaded input documents.</p>
            </div>
            <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
              <span>{sourceDocumentsOpen ? "Hide" : "Show"}</span>
              <ChevronDown
                className={`h-5 w-5 shrink-0 transition-transform ${sourceDocumentsOpen ? "rotate-180" : "rotate-0"}`}
              />
            </div>
          </button>
          {sourceDocumentsOpen && (
            <CardContent className="space-y-4 border-t pt-5">
              <div className="flex flex-wrap gap-2">
                {documentTabs.map((tab) => (
                  <Button
                    key={tab.key}
                    type="button"
                    variant={activeDocumentTab === tab.key ? "default" : "outline"}
                    className="rounded-full"
                    onClick={() => setActiveDocumentTab(tab.key)}
                  >
                    {tab.label}
                  </Button>
                ))}
              </div>

              <div className="overflow-hidden rounded-xl border bg-muted/15">
                {activeDocument?.type === "pdf" && previewUrls[activeDocument.key] ? (
                  <iframe
                    title={activeDocument.label}
                    src={`${previewUrls[activeDocument.key]}#toolbar=0`}
                    className="h-[720px] w-full bg-white"
                  />
                ) : activeDocument?.type === "sheet" ? (
                  <div className="space-y-4 p-5">
                    <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                      <div>
                        <p className="text-sm font-medium text-foreground">{activeDocument.file.name}</p>
                        <p className="text-sm text-muted-foreground">
                          {formatFileSize(activeDocument.file.size)}
                        </p>
                      </div>
                      {previewUrls[activeDocument.key] && (
                        <Button
                          type="button"
                          variant="outline"
                          onClick={() => {
                            window.open(previewUrls[activeDocument.key], "_blank");
                          }}
                        >
                          <Download className="mr-2 h-4 w-4" />
                          Open file
                        </Button>
                      )}
                    </div>

                    {pricingPreviewText ? (
                      <div className="rounded-lg border bg-background p-4">
                        <p className="mb-3 text-sm font-medium text-foreground">CSV preview</p>
                        <pre className="overflow-x-auto whitespace-pre-wrap text-xs text-muted-foreground">
                          {pricingPreviewText}
                        </pre>
                      </div>
                    ) : (
                      <div className="rounded-lg border border-dashed bg-background/70 p-6 text-sm text-muted-foreground">
                        Spreadsheet preview is not rendered inline for this file type. Use <strong>Open file</strong> to inspect the uploaded pricing table.
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="p-6 text-sm text-muted-foreground">
                    No preview available for this document.
                  </div>
                )}
              </div>
            </CardContent>
          )}
        </Card>
      )}

      {/* Progress */}
      {processing && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Loader2 className="h-5 w-5 animate-spin" />
                {statusMessage}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <Progress value={progress} className="h-2" />
            </CardContent>
          </Card>
        </motion.div>
      )}

      {/* Results */}
      {result && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="space-y-4"
        >
          {/* Summary Card */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <CheckCircle2 className="h-5 w-5 text-success" />
                Order Summary
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid gap-4 md:grid-cols-5">
                <div>
                  <p className="text-sm text-muted-foreground">PO Number</p>
                  <p className="text-lg font-semibold">{result.po_number}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Customer</p>
                  <p className="text-lg font-semibold">{result.customer}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Material Subtotal</p>
                  <p className="text-lg font-semibold">
                    ${(result.summary?.material_subtotal ?? 0).toFixed(2)}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Processing Fees</p>
                  <p className="text-lg font-semibold">
                    ${(result.summary?.total_fees ?? 0).toFixed(2)}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Grand Total</p>
                  <p className="text-lg font-semibold">
                    ${(result.summary?.grand_total ?? 0).toFixed(2)}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Errors/Warnings */}
          {result.errors.length > 0 && (
            <Card className="border-destructive/30 bg-destructive/10">
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-destructive">
                  <AlertCircle className="h-5 w-5" />
                  Errors
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="list-disc space-y-1 pl-4">
                  {result.errors.map((error, i) => (
                    <li key={i} className="text-sm text-destructive">
                      {error}
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}

          {/* Items Table */}
          <Card>
            <CardHeader>
              <CardTitle>Order Items</CardTitle>
              <CardDescription>
                {result.items.length} items with calculated pricing
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Material</TableHead>
                      <TableHead>Description</TableHead>
                      <TableHead className="text-right">Qty</TableHead>
                      <TableHead className="text-right">Unit Price</TableHead>
                      <TableHead className="text-right">Subtotal</TableHead>
                      <TableHead className="text-right">Fees</TableHead>
                      <TableHead className="text-right">Total USD</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {result.items.map((item, i) => (
                      <TableRow
                        key={i}
                        className={item.error ? "bg-destructive/10" : ""}
                      >
                        <TableCell className="font-medium">
                          {item.material}
                        </TableCell>
                        <TableCell>{item.description}</TableCell>
                        <TableCell className="text-right">
                          {item.quantity}
                        </TableCell>
                        <TableCell className="text-right">
                          {item.unit_price
                            ? `$${item.unit_price.toFixed(2)}`
                            : "-"}
                        </TableCell>
                        <TableCell className="text-right">
                          {item.material_subtotal
                            ? `$${item.material_subtotal.toFixed(2)}`
                            : "-"}
                        </TableCell>
                        <TableCell className="text-right">
                          <div>${item.total_fees.toFixed(2)}</div>
                          <div className="text-xs text-muted-foreground">
                            C ${item.cutting_fee.toFixed(2)} | T ${item.testing_fee.toFixed(2)} | Cert ${item.cert_fee.toFixed(2)}
                          </div>
                        </TableCell>
                        <TableCell className="text-right">
                          {item.line_total
                            ? `$${item.line_total.toFixed(2)}`
                            : "-"}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>

          {result.pdf_job_id && (
            <Card>
              <CardHeader>
                <CardTitle>Order Draft Preview</CardTitle>
                <CardDescription>
                  View the generated order-draft PDF directly in the demo.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="overflow-hidden rounded-xl border bg-muted/15">
                  <iframe
                    title="Order Draft Preview"
                    src={`/api/luvata-order/pdf/${result.pdf_job_id}#toolbar=0`}
                    className="h-[720px] w-full bg-white"
                  />
                </div>
              </CardContent>
            </Card>
          )}

          {/* Download PDF Button */}
          {result.pdf_job_id && (
            <Button
              variant="outline"
              className="w-full"
              onClick={() => {
                window.open(`/api/luvata-order/pdf/${result.pdf_job_id}?download=1`, "_blank");
              }}
            >
              <Download className="mr-2 h-4 w-4" />
              Download Order Draft PDF
            </Button>
          )}
        </motion.div>
      )}

      {/* Info Card */}
      {!result && !processing && (
        <Card>
          <button
            type="button"
            onClick={() => setHowItWorksOpen((open) => !open)}
            className="flex w-full items-center justify-between px-6 py-5 text-left transition-colors hover:bg-muted/30"
            aria-expanded={howItWorksOpen}
          >
            <h2 className="text-lg font-semibold text-foreground">How It Works</h2>
            <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
              <span>{howItWorksOpen ? "Hide" : "Show"}</span>
              <ChevronDown
                className={`h-5 w-5 shrink-0 transition-transform ${howItWorksOpen ? "rotate-180" : "rotate-0"}`}
              />
            </div>
          </button>
          {howItWorksOpen && (
            <CardContent className="space-y-4 border-t pt-5 text-sm text-muted-foreground">
              <p>
                <strong>1. Upload the source files:</strong> Provide one purchase
                order PDF, one or more BOM PDFs, and a pricing file in CSV or
                Excel format. If you want to test quickly, use
                <strong> Load Example</strong> to load the built-in sample set.
              </p>
              <p>
                <strong>2. Parse and extract key fields:</strong> The tool parses
                each document into markdown and extracts the main PO fields such
                as PO number, customer, material numbers, descriptions,
                quantities, and delivery dates. From each BOM it extracts the
                material ID, type/part designation, dimensions, material grade,
                and fee-related requirement flags such as cutting, testing, and
                certificates.
              </p>
              <p>
                <strong>3. Match PO items to BOMs and pricing rows:</strong> Each
                PO line is matched to a BOM using the material code. The matched
                BOM is then linked to the pricing table, primarily by item or
                material ID and secondarily by type designation when needed.
              </p>
              <p>
                <strong>4. Calculate the order value:</strong> The tool computes a
                material subtotal from quantity and unit price, then adds the
                applicable processing fees from the pricing table, such as
                Cutting, testing, and certificate fees, as mentioned in the BoM.
              </p>
              <p>
                <strong>5. Generate the order draft:</strong> The result view shows
                the order lines, fee breakdowns, totals, and any errors. It also
                generates a downloadable order-draft PDF.
              </p>
            </CardContent>
          )}
        </Card>
      )}
    </div>
  );
}
