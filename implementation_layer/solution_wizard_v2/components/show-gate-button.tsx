"use client";

import { useSyncExternalStore } from "react";
import { GATE_BAR_ATTRIBUTE, GATE_POINT_EVENT } from "@/lib/chat-events";
import { Icon } from "./icons";

const noChange = () => () => {};
const barOnPage = () => document.querySelector(`[${GATE_BAR_ATTRIBUTE}]`) !== null;

/**
 * "Show me" beside the approval the wizard's reply carries: it points at the
 * gate's decision bar on the page (GATE_POINT_EVENT). Rendered only when there
 * is a bar to point at, and only where the chat stands beside the workspace:
 * below 1280 px the open chat lies over the bar, and the approval beside this
 * button is the control there.
 */
export function ShowGateButton({ label, name }: { label: string; name: string }) {
  // Read as the reply's approval is rendered: the bar and that approval come
  // and go with the same page data. Not on the server, which has no page.
  const there = useSyncExternalStore(noChange, barOnPage, () => false);
  if (!there) return null;
  return (
    <button
      type="button"
      aria-label={name}
      onClick={() => window.dispatchEvent(new Event(GATE_POINT_EVENT))}
      className="btn-inline max-xl:hidden"
    >
      <Icon name="arrowLeft" size={13} />
      {label}
    </button>
  );
}
