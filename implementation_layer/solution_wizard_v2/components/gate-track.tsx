import type { GateMark } from "@/lib/session-list";

// The stage in progress is outlined, so it differs from the others by shape
// as well as by colour.
const OPEN = "bg-brand-soft ring-1 ring-inset ring-brand";

const SEGMENT: Record<GateMark, string> = {
  approved: "bg-brand",
  open: OPEN,
  waiting: OPEN,
  rejected: OPEN,
  ahead: "bg-border-strong",
};

/**
 * The four gates as four segments: filled once approved, outlined while the
 * session works on that stage, grey ahead. Short ones, to leave a sidebar row
 * room for its text. A drawing only: the text beside it says where the session
 * stands, so it is hidden from assistive tech.
 */
export function GateTrack({ marks, title }: { marks: GateMark[]; title?: string }) {
  return (
    <span aria-hidden title={title} className="inline-flex shrink-0 items-center gap-[3px]">
      {marks.map((mark, i) => (
        <span key={i} className={`h-1.5 w-3 rounded-full ${SEGMENT[mark]}`} />
      ))}
    </span>
  );
}
