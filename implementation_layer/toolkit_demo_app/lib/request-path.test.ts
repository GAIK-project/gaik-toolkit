import { expect, test } from "bun:test";
import { routedPath } from "./request-path";

test("a plain path is matched as it is", () => {
  expect(routedPath("/")).toBe("/");
  expect(routedPath("/api/extract")).toBe("/api/extract");
  expect(routedPath("/api/wizard/start/")).toBe("/api/wizard/start/");
});

test("an encoded letter is matched as the route it reaches", () => {
  expect(routedPath("/api/%65xtract")).toBe("/api/extract");
  expect(routedPath("/api/%77izard/start")).toBe("/api/wizard/start");
  expect(routedPath("/%73olution-wizard")).toBe("/solution-wizard");
});

test("an encoded space in a file name stays part of the name", () => {
  expect(routedPath("/api/report-writer/example/file/site%20visit.pdf")).toBe(
    "/api/report-writer/example/file/site visit.pdf",
  );
});

test("a path the rules cannot judge is refused", () => {
  for (const path of [
    "/api/%E0%A4%A", // does not decode
    "/api/extract%00",
    "/api/a%5Cb", // backslash
    "/api//wizard/start",
    "/api/x/%2e%2e/wizard/start",
    "/api/./extract",
  ])
    expect(routedPath(path)).toBeNull();
});
