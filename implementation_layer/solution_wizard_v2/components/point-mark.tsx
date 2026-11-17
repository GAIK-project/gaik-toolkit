import { Icon } from "./icons";

/**
 * Where a requirement point stands, at the start of its row: its number while
 * it is open, a tick once it is answered. A status, not a control, so it is
 * drawn as text and never as a ring that reads as a radio button; what it
 * says is also there in words for a screen reader. The lists it sits in are
 * `ul`, so the number is read out too, also once the tick replaces it.
 */
export function PointMark({
  number,
  done,
  labels,
  className = "",
}: {
  /** The point's place in the list, from 1. */
  number: number;
  done: boolean;
  labels: { answered: string; open: string };
  /** Lines the mark up with the first line of the row's text. */
  className?: string;
}) {
  return (
    <span
      data-testid="point-mark"
      data-done={done || undefined}
      // w-6 holds "10." and up as well as "1.", so the rows' text stays in line.
      className={`flex h-5 w-6 shrink-0 items-center justify-end text-[0.8125rem] tabular-nums text-text-muted ${className}`}
    >
      {done ? (
        <Icon name="check" size={15} strokeWidth={2.5} className="text-success-text" />
      ) : (
        <span>{number}.</span>
      )}
      <span className="sr-only">{done ? `${number}. ${labels.answered}` : labels.open}</span>
    </span>
  );
}
