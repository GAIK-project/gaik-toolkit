import { describe, expect, it } from "vitest";
import { isCrossSiteWrite } from "./same-origin";

const req = (method: string, headers: Record<string, string>) => ({ method, headers: new Headers(headers) });

describe("cross-site write guard", () => {
  it("lets same-origin writes and every read through", () => {
    expect(isCrossSiteWrite(req("POST", { host: "wizard.example", origin: "https://wizard.example" }))).toBe(false);
    expect(isCrossSiteWrite(req("GET", { host: "wizard.example", origin: "https://other.example" }))).toBe(false);
  });

  it("uses the router's forwarded host", () => {
    const headers = { host: "10.0.0.5:3000", "x-forwarded-host": "wizard.example", origin: "https://wizard.example" };
    expect(isCrossSiteWrite(req("PATCH", headers))).toBe(false);
  });

  it("treats the scheme's default port as the same host", () => {
    expect(isCrossSiteWrite(req("POST", { host: "wizard.example:443", origin: "https://wizard.example" }))).toBe(false);
    expect(isCrossSiteWrite(req("POST", { host: "wizard.example:8443", origin: "https://wizard.example" }))).toBe(true);
  });

  it("refuses a write from another origin, a sibling subdomain or an opaque origin", () => {
    expect(isCrossSiteWrite(req("POST", { host: "wizard.example", origin: "https://other.example" }))).toBe(true);
    expect(isCrossSiteWrite(req("DELETE", { host: "a.apps.example", origin: "https://b.apps.example" }))).toBe(true);
    expect(isCrossSiteWrite(req("POST", { host: "wizard.example", origin: "null" }))).toBe(true);
  });

  it("falls back to Sec-Fetch-Site when there is no Origin", () => {
    expect(isCrossSiteWrite(req("POST", { host: "w", "sec-fetch-site": "same-site" }))).toBe(true);
    expect(isCrossSiteWrite(req("POST", { host: "w", "sec-fetch-site": "same-origin" }))).toBe(false);
  });

  it("leaves non-browser calls to the session check", () => {
    expect(isCrossSiteWrite(req("POST", { host: "w" }))).toBe(false);
  });
});
