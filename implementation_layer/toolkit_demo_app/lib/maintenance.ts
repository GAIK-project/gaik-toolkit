// Maintenance mode: an operator closes the demo for a break, and opens it
// again, with environment variables on the frontend deployment (`oc set env`,
// see openshift/README.md, "Maintenance break"):
//
//   DEMO_MAINTENANCE          "on": every page answers with the maintenance
//                             page and every API call with 503;
//                             "planned": nothing is refused, every page shows
//                             a banner about the coming break; anything else
//                             (or unset): off.
//   DEMO_MAINTENANCE_START    when a planned break begins (ISO 8601), for the
//                             banner. Optional.
//   DEMO_MAINTENANCE_UNTIL    when the break is expected to end (ISO 8601), for
//                             the page, the banner and Retry-After. Optional.
//   DEMO_MAINTENANCE_MESSAGE  a line of the operator's own, shown as plain
//                             text. Optional.
//
// The proxy (proxy.ts) applies the gate before any other check, so it covers
// the report runs that forward themselves too. An admin session (/admin) still
// gets in, to check the demo before it opens; /admin, its API and /privacy stay
// open for that. /api/health is answered here while the mode is on: the pod's
// probes call it, and it would otherwise ask the backend, which may be the very
// thing that is down for the break.

import { NextResponse } from "next/server";
import { MAINTENANCE_HEADER } from "@/lib/maintenance-watch";

export { MAINTENANCE_HEADER };

export type MaintenanceState = "off" | "planned" | "on";

export type MaintenanceSettings = {
  state: MaintenanceState;
  start: Date | null;
  until: Date | null;
  message: string | null;
};

/** Retry-After when no end time is given, or it has already passed. */
export const DEFAULT_RETRY_AFTER_S = 300;

const MAX_MESSAGE_CHARS = 500;
const TIME_ZONE = "Europe/Helsinki";

function parseTime(value: string | undefined): Date | null {
  if (!value?.trim()) return null;
  const date = new Date(value.trim());
  return Number.isNaN(date.getTime()) ? null : date;
}

export function maintenanceSettings(
  env: Record<string, string | undefined> = process.env,
): MaintenanceSettings {
  const raw = env.DEMO_MAINTENANCE?.trim().toLowerCase();
  const state: MaintenanceState =
    raw === "on" || raw === "planned" ? raw : "off";
  return {
    state,
    start: parseTime(env.DEMO_MAINTENANCE_START),
    until: parseTime(env.DEMO_MAINTENANCE_UNTIL),
    message:
      env.DEMO_MAINTENANCE_MESSAGE?.trim().slice(0, MAX_MESSAGE_CHARS) || null,
  };
}

/** Paths that stay open while the mode is on: the admin sign-in and /privacy. */
export function staysOpen(path: string): boolean {
  return (
    path === "/admin" ||
    path.startsWith("/admin/") ||
    path.startsWith("/api/admin/") ||
    path === "/privacy"
  );
}

export function retryAfterSeconds(
  settings: MaintenanceSettings,
  now: Date = new Date(),
): number {
  if (!settings.until) return DEFAULT_RETRY_AFTER_S;
  const seconds = Math.ceil((settings.until.getTime() - now.getTime()) / 1000);
  return seconds > 0 ? seconds : DEFAULT_RETRY_AFTER_S;
}

/** A time as a reader in Finland reads it, e.g. "26.11.2026 klo 18.00". */
export function formatTime(date: Date, locale: "fi" | "en"): string {
  return date.toLocaleString(locale === "fi" ? "fi-FI" : "en-GB", {
    timeZone: TIME_ZONE,
    day: "numeric",
    month: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/**
 * The maintenance page, Finnish first and English below. Self-contained: it
 * loads nothing from the app and runs no script, so it shows whatever state
 * the rest of the demo is in. It reloads itself every minute and is back in
 * the demo once the mode is off.
 */
export function maintenancePage(settings: MaintenanceSettings): string {
  const until = settings.until;
  const fiUntil = until
    ? `<p>Arvioitu päättymisaika: ${escapeHtml(formatTime(until, "fi"))} (Suomen aikaa).</p>`
    : "";
  const enUntil = until
    ? `<p>Expected to end: ${escapeHtml(formatTime(until, "en"))} (Finnish time).</p>`
    : "";
  const message = settings.message
    ? `<p class="note">${escapeHtml(settings.message)}</p>`
    : "";
  return `<!doctype html>
<html lang="fi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="60">
<meta name="robots" content="noindex">
<title>Huoltokatko – GAIK Toolkit Demo</title>
<style>
body{margin:0;font-family:system-ui,-apple-system,"Segoe UI",sans-serif;background:#f6f7f9;color:#1f2933;line-height:1.5}
main{max-width:36rem;margin:12vh auto;padding:2rem;background:#fff;border:1px solid #e2e5ea;border-radius:12px}
h1{font-size:1.35rem;margin:0 0 .75rem}
h2{font-size:1.1rem;margin:0 0 .5rem}
section+section{margin-top:1.5rem;padding-top:1.5rem;border-top:1px solid #e2e5ea}
.note{padding:.75rem 1rem;background:#f1f4f8;border-radius:8px;white-space:pre-line}
small{color:#5c6773}
</style>
</head>
<body>
<main>
<section lang="fi">
<h1>Palvelussa on huoltokatko</h1>
<p>GAIK Toolkit Demo on hetken pois käytöstä huollon vuoksi. Tallennetut tietosi säilyvät, ja voit jatkaa, kun palvelu on taas käytössä.</p>
${fiUntil}
</section>
${message}
<section lang="en">
<h2>The demo is down for maintenance</h2>
<p>GAIK Toolkit Demo is briefly unavailable for maintenance. Your saved data is kept, and you can continue once the demo is back.</p>
${enUntil}
</section>
<p><small>Sivu päivittyy itsestään minuutin välein. · This page reloads itself every minute.</small></p>
</main>
</body>
</html>
`;
}

/** The answer to a request the mode refuses: the page, or 503 for the API. */
export function maintenanceResponse(
  path: string,
  settings: MaintenanceSettings,
  now: Date = new Date(),
): NextResponse {
  const headers = {
    "Retry-After": String(retryAfterSeconds(settings, now)),
    "Cache-Control": "no-store",
    [MAINTENANCE_HEADER]: "on",
  };
  if (path.startsWith("/api/")) {
    const text = "Palvelussa on huoltokatko. The demo is down for maintenance.";
    // The pages read `error` from the proxy's answers and `detail` from the API's.
    return NextResponse.json(
      { error: text, detail: text, maintenance: true },
      { status: 503, headers },
    );
  }
  return new NextResponse(maintenancePage(settings), {
    status: 503,
    headers: { ...headers, "Content-Type": "text/html; charset=utf-8" },
  });
}

/**
 * The gate: null lets the request on (to the usual checks), a response answers
 * it. `admin` is whether the request carries a valid admin session.
 */
export function maintenanceGate(
  path: string,
  admin: boolean,
  settings: MaintenanceSettings = maintenanceSettings(),
  now: Date = new Date(),
): NextResponse | null {
  if (settings.state !== "on") return null;
  // The probes: alive, without asking the backend.
  if (path === "/api/health") {
    return NextResponse.json(
      { status: "maintenance" },
      { status: 200, headers: { "Cache-Control": "no-store" } },
    );
  }
  if (staysOpen(path) || admin) return null;
  return maintenanceResponse(path, settings, now);
}

/** The banner text for a planned break, Finnish then English, or null. */
export function plannedBannerText(
  settings: MaintenanceSettings,
): string | null {
  if (settings.state !== "planned") return null;
  const fi: string[] = [
    settings.start
      ? `Palveluun on tulossa huoltokatko ${formatTime(settings.start, "fi")} alkaen.`
      : "Palveluun on tulossa huoltokatko.",
  ];
  const en: string[] = [
    settings.start
      ? `A maintenance break begins at ${formatTime(settings.start, "en")} (Finnish time).`
      : "A maintenance break is coming.",
  ];
  if (settings.until) {
    fi.push(`Arvioitu päättymisaika ${formatTime(settings.until, "fi")}.`);
    en.push(`Expected to end at ${formatTime(settings.until, "en")}.`);
  }
  const lines = [fi.join(" "), en.join(" ")];
  if (settings.message) lines.push(settings.message);
  return lines.join("\n");
}
