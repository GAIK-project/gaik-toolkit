import { describe, expect, it } from "vitest";
import {
  DEFAULT_RETRY_AFTER_S,
  MAX_RETRY_AFTER_S,
  isSandboxBusy,
  preflightRetryDelayMs,
  relayHeaders,
  retryAfterMs,
} from "@/lib/sandbox-busy";

describe("retryAfterMs", () => {
  it("reads seconds", () => {
    expect(retryAfterMs("30")).toBe(30_000);
  });

  it("reads an HTTP date", () => {
    const now = Date.parse("2026-11-04T10:00:00Z");
    expect(retryAfterMs("Wed, 04 Nov 2026 10:00:45 GMT", now)).toBe(45_000);
  });

  it("falls back to the default for a missing or unreadable value", () => {
    expect(retryAfterMs(null)).toBe(DEFAULT_RETRY_AFTER_S * 1000);
    expect(retryAfterMs("soon")).toBe(DEFAULT_RETRY_AFTER_S * 1000);
  });

  it("stays within its bounds", () => {
    expect(retryAfterMs("0")).toBe(1000);
    expect(retryAfterMs("86400")).toBe(MAX_RETRY_AFTER_S * 1000);
  });
});

describe("preflightRetryDelayMs", () => {
  it("asks again after Retry-After only for a busy sandbox", () => {
    expect(preflightRetryDelayMs(429, "12")).toBe(12_000);
    expect(preflightRetryDelayMs(429, null)).toBe(DEFAULT_RETRY_AFTER_S * 1000);
    expect(preflightRetryDelayMs(409, "12")).toBeNull();
    expect(preflightRetryDelayMs(503, null)).toBeNull();
  });
});

describe("isSandboxBusy", () => {
  it("recognises the api's busy answer", () => {
    expect(isSandboxBusy(429, { detail: { error: "sandbox_busy", message: "x" } })).toBe(true);
    expect(isSandboxBusy(429, {})).toBe(true);
  });

  it("leaves other answers alone", () => {
    expect(isSandboxBusy(409, { detail: { error: "poc_package_incomplete" } })).toBe(false);
    expect(isSandboxBusy(429, { detail: { error: "agent_busy" } })).toBe(false);
    expect(isSandboxBusy(500, { detail: "boom" })).toBe(false);
  });
});

describe("relayHeaders", () => {
  it("passes Retry-After on when the api sent one", () => {
    const upstream = new Response("{}", { status: 429, headers: { "Retry-After": "30" } });
    expect(relayHeaders(upstream, { "Content-Type": "application/json" })).toEqual({
      "Content-Type": "application/json",
      "Retry-After": "30",
    });
  });

  it("adds nothing when it did not", () => {
    const upstream = new Response("{}", { status: 201 });
    expect(relayHeaders(upstream, { "Content-Type": "application/json" })).toEqual({
      "Content-Type": "application/json",
    });
  });
});
