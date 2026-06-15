import { afterEach, expect, test } from "bun:test";
import { getReportWriterLimits } from "./limits";

const KEYS = [
  "REPORT_WRITER_MAX_REPORTS",
  "REPORT_WRITER_MAX_TOKENS_PER_REPORT",
  "REPORT_WRITER_MAX_UPLOAD_MB",
  "REPORT_WRITER_MAX_SECTIONS",
  "REPORT_WRITER_MAX_EVIDENCE_CHARS",
];

afterEach(() => {
  for (const k of KEYS) delete process.env[k];
});

test("defaults when env is unset", () => {
  expect(getReportWriterLimits()).toEqual({
    maxReports: 5,
    maxTokensPerReport: 32000,
    maxUploadMb: 25,
    maxSections: 12,
    maxEvidenceChars: 200000,
  });
});

test("reads positive integer env overrides", () => {
  process.env.REPORT_WRITER_MAX_REPORTS = "3";
  process.env.REPORT_WRITER_MAX_UPLOAD_MB = "10";
  const l = getReportWriterLimits();
  expect(l.maxReports).toBe(3);
  expect(l.maxUploadMb).toBe(10);
});

test("ignores invalid / non-positive env values, falling back to default", () => {
  process.env.REPORT_WRITER_MAX_REPORTS = "abc";
  process.env.REPORT_WRITER_MAX_SECTIONS = "0";
  const l = getReportWriterLimits();
  expect(l.maxReports).toBe(5);
  expect(l.maxSections).toBe(12);
});
