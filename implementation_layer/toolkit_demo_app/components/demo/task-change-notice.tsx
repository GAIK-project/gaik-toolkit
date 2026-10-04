import { Info } from "lucide-react";

/**
 * Shown when the extraction task was edited: the ready-made schema of an example, or the
 * schema of the last run, no longer matches the text, so a new one is made at the next run.
 */
export function TaskChangeNotice() {
  return (
    <p
      role="status"
      className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-50 px-3 py-2 text-xs text-amber-800"
    >
      <Info className="mt-0.5 size-3.5 shrink-0" />
      <span>
        You changed the extraction task, so a new schema will be generated when
        you run it. Nothing is saved: the schema stays in this session, and is
        used again while the text stays the same.
      </span>
    </p>
  );
}
