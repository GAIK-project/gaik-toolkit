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
    // In the page's flow, above the site's sticky header: it pushes the page
    // down instead of covering a control, and scrolls away with it.
    <div className="border-b border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100">
      <div
        role="status"
        className="mx-auto flex max-w-6xl items-start gap-3 px-6 py-2 text-sm sm:px-8"
      >
        <p className="flex-1 whitespace-pre-line">{bannerText}</p>
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
