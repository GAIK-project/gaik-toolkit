/**
 * Parts of a CodeMirror document that cannot be edited: the full blueprint's
 * read-only sections in the advanced editor (components/code-editor's
 * `lockedRanges`). The ranges follow their text as the rest is edited; a
 * change that touches one is left out of its transaction. Text typed right at
 * a range's edge is not part of it.
 */
import { EditorState, RangeSet, RangeValue, StateField, type Extension } from "@codemirror/state";

class Locked extends RangeValue {
  // Text inserted at either edge stays outside the range.
  override startSide = 1;
  override endSide = -1;
}
const LOCKED = new Locked();

export const lockedRangesField = StateField.define<RangeSet<Locked>>({
  create: () => RangeSet.empty,
  update: (ranges, tr) => ranges.map(tr.changes),
});

/** The field with `ranges` in it, and the filter that keeps changes out of them. */
export function lockedRanges(ranges: readonly { from: number; to: number }[]): Extension {
  const spans = ranges.filter((r) => r.to > r.from);
  if (spans.length === 0) return [];
  return [
    lockedRangesField.init(() => RangeSet.of(spans.map((r) => LOCKED.range(r.from, r.to)), true)),
    EditorState.changeFilter.of((tr) => {
      const out: number[] = [];
      tr.startState.field(lockedRangesField).between(0, tr.startState.doc.length, (from, to) => {
        out.push(from, to);
      });
      return out.length > 0 ? out : true;
    }),
  ];
}
