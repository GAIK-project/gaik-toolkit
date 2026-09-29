import {
  Braces,
  ClipboardList,
  FilePen,
  HardHat,
  type LucideIcon,
  ReceiptText,
  ScanText,
  Search,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";

/** One glyph per asset id; a skill and its prompt share it. */
const icons: Record<string, LucideIcon> = {
  "incident-report-writing": ShieldAlert,
  "safety-observation-reporting": ShieldCheck,
  "construction-diary-creation": HardHat,
  "purchase-order-processing": ReceiptText,
  "report-writing": FilePen,
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
