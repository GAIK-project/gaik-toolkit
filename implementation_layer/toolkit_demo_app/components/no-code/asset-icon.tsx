import { EuFlag } from "@/components/eu-flag";
import {
  Braces,
  ClipboardList,
  FileCheck,
  FilePen,
  HardHat,
  type LucideIcon,
  Presentation,
  ReceiptText,
  ScanText,
  Search,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import type { ComponentType } from "react";

/** One glyph per asset id; a skill and its prompt share it. */
const icons: Record<
  string,
  LucideIcon | ComponentType<{ className?: string }>
> = {
  "incident-report-writing": ShieldAlert,
  "safety-observation-reporting": ShieldCheck,
  "construction-diary-creation": HardHat,
  "purchase-order-processing": ReceiptText,
  "report-writing": FilePen,
  "brief-to-slides": Presentation,
  "ai-act-use-case-screening": EuFlag,
  "generate-structured-reports": FileCheck,
  "parsing-documents": ScanText,
  "extracting-structured-data": Braces,
  "searching-documents": Search,
};

export function AssetIcon({ id }: { id: string }) {
  const Icon = icons[id] ?? ClipboardList;
  return (
    <span className="bg-primary/10 text-primary flex size-10 shrink-0 items-center justify-center rounded-lg">
      <Icon className="size-5" aria-hidden="true" />
    </span>
  );
}
