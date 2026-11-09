import { expect, test } from "bun:test";

import { backendTarget, isApiPath } from "./backend-target";

const BACKEND = "http://gaik-demo-api:8000";

test("only /api and the paths below it are API paths", () => {
  expect(isApiPath("/api")).toBe(true);
  expect(isApiPath("/api/extract")).toBe(true);
  for (const path of ["/apix/y", "/api.txt", "/api@other.example/x", "/"]) {
    expect(isApiPath(path)).toBe(false);
  }
});

test("an API path maps to the same path on the backend", () => {
  expect(backendTarget(BACKEND, "/api/extract")).toBe(`${BACKEND}/extract`);
  expect(backendTarget(BACKEND, "/api/video-search/clear", "?all=1")).toBe(
    `${BACKEND}/video-search/clear?all=1`,
  );
  expect(backendTarget(`${BACKEND}/`, "/api/health")).toBe(`${BACKEND}/health`);
  expect(backendTarget(`${BACKEND}/v1`, "/api/health")).toBe(
    `${BACKEND}/v1/health`,
  );
});

test("a path that is not below /api has no backend target", () => {
  for (const path of [
    "/api@other.example/x",
    "/api.other.example/x",
    "/api:9/x",
    "/apix/y",
  ]) {
    expect(backendTarget(BACKEND, path)).toBeNull();
    // Also for a backend URL without a port, where a suffix could extend the host.
    expect(backendTarget("http://gaik-demo-api", path)).toBeNull();
  }
});

test("the target always stays on the backend's origin", () => {
  for (const path of [
    "/api//other.example/x",
    "/api/@other.example/x",
    "/api/\other.example/x",
    "/api/../x",
    "/api/%2e%2e/x",
  ]) {
    const target = backendTarget(BACKEND, path);
    expect(target).not.toBeNull();
    const url = new URL(target!);
    expect(url.origin).toBe(BACKEND);
    expect(url.username).toBe("");
  }
});
