"use client";

// Maintenance mode in an open page (lib/maintenance.ts): the banner about a
// planned break, which the reader can close for this tab, and the watch that
// reloads the page into the maintenance page once the break begins.

import { useEffect, useState, useSyncExternalStore } from "react";
import { watchForMaintenance } from "@/lib/maintenance-watch";

const DISMISS_KEY = "gaik.demo.maintenanceBannerClosed";

function readClosed(): string | null {
  try {
    return window.sessionStorage.getItem(DISMISS_KEY);
  } catch {
    // Storage refused (private mode): the banner simply shows.
    return null;
  }
}

// Nothing else writes the key in this tab; closing it is tracked in state.
const subscribe = () => () => {};

export function MaintenanceNotice({
  bannerText,
}: {
  bannerText: string | null;
}) {
  // Closed for this text only: a changed notice shows again.
  const closedText = useSyncExternalStore(subscribe, readClosed, () => null);
  const [closedNow, setClosedNow] = useState(false);

  useEffect(
    () => watchForMaintenance(window, () => window.location.reload()),
    [],
  );

  if (!bannerText || closedNow || closedText === bannerText) return null;
  return (
    <div className="pointer-events-none fixed inset-x-0 top-2 z-50 flex justify-center px-4">
      <div
        role="status"
        className="pointer-events-auto flex max-w-2xl items-start gap-3 rounded-md border border-amber-300 bg-amber-50 px-4 py-2 text-sm text-amber-900 shadow-sm dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100"
      >
        <p className="whitespace-pre-line">{bannerText}</p>
        <button
          type="button"
          className="shrink-0 rounded px-1 font-medium underline-offset-2 hover:underline"
          onClick={() => {
            try {
              window.sessionStorage.setItem(DISMISS_KEY, bannerText);
            } catch {
              // Not kept; closed until the next page load.
            }
            setClosedNow(true);
          }}
        >
          Sulje / Close
        </button>
      </div>
    </div>
  );
}
