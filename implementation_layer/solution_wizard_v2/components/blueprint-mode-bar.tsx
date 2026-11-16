import type { ReactNode, Ref } from "react";

/**
 * The first row of the Blueprint tab, at the plan's width: what the view says
 * about itself and, at the row's end, its control. Reading, that is "Muokkaa
 * blueprintia", with what a change costs from the PoC step on; in the form,
 * where the draft stands and "Valmis", the way out. The two controls
 * take the same place, next to what they change: at the end of the tab row
 * a wide window put the first one a long way from the plan. It stays at the
 * top of the tab as the tab scrolls, so both are always in view; for that it
 * is a direct child of the view it heads.
 */
export function BlueprintModeBar({
  mode = "edit",
  children,
  control,
  ref,
}: {
  mode?: "read" | "edit";
  /** The row itself, for whoever needs to know how much of the tab's top it covers. */
  ref?: Ref<HTMLDivElement>;
  /** What the view says about itself; the row's end is the control's. */
  children?: ReactNode;
  control: ReactNode;
}) {
  return (
    <div
      ref={ref}
      className="sticky top-0 z-10 flex flex-wrap items-center justify-end gap-x-3 gap-y-1.5 bg-surface pb-3 -mb-3"
      data-testid="blueprint-mode-bar"
      data-mode={mode}
    >
      {children}
      {control}
    </div>
  );
}
