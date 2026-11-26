import { describe, expect, mock, test } from "bun:test";
import {
  DEFAULT_RETRY_AFTER_S,
  MAINTENANCE_HEADER,
  maintenanceGate,
  maintenancePage,
  maintenanceSettings,
  plannedBannerText,
  retryAfterSeconds,
} from "./maintenance";
import {
  isMaintenanceResponse,
  watchForMaintenance,
} from "./maintenance-watch";

const NOW = new Date("2026-11-26T14:00:00Z");
const on = (extra: Record<string, string> = {}) =>
  maintenanceSettings({ DEMO_MAINTENANCE: "on", ...extra });

describe("maintenance settings", () => {
  test("is off unless the flag says on or planned", () => {
    expect(maintenanceSettings({}).state).toBe("off");
    expect(maintenanceSettings({ DEMO_MAINTENANCE: "true" }).state).toBe("off");
    expect(maintenanceSettings({ DEMO_MAINTENANCE: " ON " }).state).toBe("on");
    expect(maintenanceSettings({ DEMO_MAINTENANCE: "planned" }).state).toBe(
      "planned",
    );
  });

  test("drops a time it cannot read and keeps the message short", () => {
    expect(on({ DEMO_MAINTENANCE_UNTIL: "soon" }).until).toBeNull();
    // No offset: the pod would read it as UTC, so it is dropped.
    expect(on({ DEMO_MAINTENANCE_UNTIL: "2026-12-04T18:00" }).until).toBeNull();
    expect(
      on({
        DEMO_MAINTENANCE_UNTIL: "2026-12-04T18:00+02:00",
      }).until?.toISOString(),
    ).toBe("2026-12-04T16:00:00.000Z");
    expect(
      on({ DEMO_MAINTENANCE_MESSAGE: "x".repeat(2000) }).message,
    ).toHaveLength(500);
    expect(on({ DEMO_MAINTENANCE_MESSAGE: "  " }).message).toBeNull();
  });
});

describe("maintenance gate", () => {
  test("lets everything on while the mode is off or only planned", () => {
    expect(
      maintenanceGate("/", false, maintenanceSettings({}), NOW),
    ).toBeNull();
    expect(
      maintenanceGate(
        "/api/extract",
        false,
        maintenanceSettings({ DEMO_MAINTENANCE: "planned" }),
        NOW,
      ),
    ).toBeNull();
  });

  test("answers a page with the maintenance page and 503", async () => {
    const res = maintenanceGate("/extract", false, on(), NOW);
    expect(res?.status).toBe(503);
    expect(res?.headers.get("content-type")).toContain("text/html");
    expect(res?.headers.get(MAINTENANCE_HEADER)).toBe("on");
    expect(res?.headers.get("cache-control")).toBe("no-store");
    const html = await res!.text();
    expect(html).toContain("Palvelussa on huoltokatko");
    expect(html).toContain("The demo is down for maintenance");
  });

  test("answers an API call with 503 JSON and Retry-After", async () => {
    const res = maintenanceGate(
      "/api/report-writer/run",
      false,
      on({ DEMO_MAINTENANCE_UNTIL: "2026-11-26T15:00:00Z" }),
      NOW,
    );
    expect(res?.status).toBe(503);
    expect(res?.headers.get("retry-after")).toBe("3600");
    const body = await res!.json();
    expect(body.maintenance).toBe(true);
    expect(body.error).toContain("maintenance");
    expect(isMaintenanceResponse(res!)).toBe(true);
  });

  test("answers the health check itself, so the probes need no backend", async () => {
    const res = maintenanceGate("/api/health", false, on(), NOW);
    expect(res?.status).toBe(200);
    expect(await res!.json()).toEqual({ status: "maintenance" });
  });

  test("keeps the admin sign-in and /privacy open, and lets an admin in", () => {
    for (const path of ["/admin", "/api/admin/auth", "/privacy"]) {
      expect(maintenanceGate(path, false, on(), NOW)).toBeNull();
    }
    expect(maintenanceGate("/administrator", false, on(), NOW)?.status).toBe(
      503,
    );
    expect(maintenanceGate("/api/extract", true, on(), NOW)).toBeNull();
  });
});

describe("Retry-After", () => {
  test("counts down to the end time, and falls back once it has passed or is missing", () => {
    expect(
      retryAfterSeconds(
        on({ DEMO_MAINTENANCE_UNTIL: "2026-11-26T14:00:30.200Z" }),
        NOW,
      ),
    ).toBe(31);
    expect(
      retryAfterSeconds(
        on({ DEMO_MAINTENANCE_UNTIL: "2026-11-26T13:00:00Z" }),
        NOW,
      ),
    ).toBe(DEFAULT_RETRY_AFTER_S);
    expect(retryAfterSeconds(on(), NOW)).toBe(DEFAULT_RETRY_AFTER_S);
  });
});

describe("maintenance page", () => {
  test("shows the end time in Finnish time and the message as plain text", () => {
    const html = maintenancePage(
      on({
        DEMO_MAINTENANCE_UNTIL: "2026-11-26T16:00:00Z",
        DEMO_MAINTENANCE_MESSAGE: "<script>alert(1)</script> & päivitys",
      }),
    );
    // 16:00 UTC is 18:00 in Helsinki in November.
    expect(html).toMatch(/Arvioitu päättymisaika: 26\.11\.2026[^<]*18[.:]00/);
    expect(html).toMatch(/Expected to end: 26\/11\/2026[^<]*18:00/);
    expect(html).not.toContain("<script>");
    expect(html).toContain(
      "&lt;script&gt;alert(1)&lt;/script&gt; &amp; päivitys",
    );
  });

  test("loads nothing and runs no script", () => {
    const html = maintenancePage(on());
    expect(html).not.toMatch(/<script|<link|src=/);
    expect(html).toContain('http-equiv="refresh"');
  });
});

describe("planned-break banner", () => {
  test("shows only while a break is planned, Finnish first", () => {
    expect(plannedBannerText(on())).toBeNull();
    expect(plannedBannerText(maintenanceSettings({}))).toBeNull();
    const text = plannedBannerText(
      maintenanceSettings({
        DEMO_MAINTENANCE: "planned",
        DEMO_MAINTENANCE_START: "2026-11-27T16:00:00Z",
        DEMO_MAINTENANCE_MESSAGE: "Päivitämme kirjautumisen.",
      }),
    );
    const [fi, en, message] = text!.split("\n");
    expect(fi).toMatch(
      /^Palveluun on tulossa huoltokatko 27\.11\.2026.*alkaen\.$/,
    );
    expect(en).toMatch(/^A maintenance break begins at 27\/11\/2026/);
    expect(message).toBe("Päivitämme kirjautumisen.");
  });
});

describe("watching for the break in an open page", () => {
  const refusal = () =>
    new Response("{}", {
      status: 503,
      headers: { [MAINTENANCE_HEADER]: "on" },
    });

  test("calls back once on a maintenance refusal and hands every response back", async () => {
    const responses = [new Response("ok"), refusal(), refusal()];
    const host = {
      fetch: mock(async () => responses.shift()!) as unknown as typeof fetch,
    };
    const onMaintenance = mock(() => {});
    watchForMaintenance(host, onMaintenance);
    expect((await host.fetch("/api/a")).status).toBe(200);
    expect(onMaintenance).not.toHaveBeenCalled();
    expect((await host.fetch("/api/b")).status).toBe(503);
    await host.fetch("/api/c");
    expect(onMaintenance).toHaveBeenCalledTimes(1);
  });

  test("leaves an ordinary 503 alone", async () => {
    const host = {
      fetch: mock(
        async () => new Response("busy", { status: 503 }),
      ) as unknown as typeof fetch,
    };
    const onMaintenance = mock(() => {});
    watchForMaintenance(host, onMaintenance);
    await host.fetch("/api/a");
    expect(onMaintenance).not.toHaveBeenCalled();
  });

  test("wraps only once and puts the original back", () => {
    const original = mock(
      async () => new Response("ok"),
    ) as unknown as typeof fetch;
    const host = { fetch: original };
    const undo = watchForMaintenance(host, () => {});
    const wrapped = host.fetch;
    watchForMaintenance(host, () => {});
    expect(host.fetch).toBe(wrapped);
    undo();
    expect(host.fetch).toBe(original);
  });
});
