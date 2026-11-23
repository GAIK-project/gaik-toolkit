import { describe, expect, it } from "vitest";
import { config } from "@/proxy";

// The matcher is a path regex; Next anchors it to the whole path.
const runs = (path: string) => config.matcher.some((m) => new RegExp(`^${m}$`).test(path));

describe("which requests the proxy sees", () => {
  it("leaves the file uploads to their routes, which check the owner themselves", () => {
    expect(runs("/api/sessions/abc/poc/input")).toBe(false);
    expect(runs("/api/sessions/abc/cases/3f1c2a4e-5b6d-4e7f-8a9b-0c1d2e3f4a5b/inputs")).toBe(false);
  });

  it("leaves public images to the server, but no API route", () => {
    expect(runs("/logo.svg")).toBe(false);
    expect(runs("/images/a.png")).toBe(false);
    expect(runs("/api/sessions/abc/runs/r1/files/chart.png")).toBe(true);
    expect(runs("/api/anything.svg")).toBe(true);
  });

  it("still guards pages and every other API route", () => {
    expect(runs("/sessions/abc/cases")).toBe(true);
    expect(runs("/api/sessions/abc/poc/input/report.pdf")).toBe(true);
    expect(runs("/api/sessions/abc/cases/3f1c2a4e-5b6d-4e7f-8a9b-0c1d2e3f4a5b/inputs/a.wav")).toBe(true);
    expect(runs("/api/sessions/abc/cases/3f1c2a4e-5b6d-4e7f-8a9b-0c1d2e3f4a5b/submit")).toBe(true);
  });
});
