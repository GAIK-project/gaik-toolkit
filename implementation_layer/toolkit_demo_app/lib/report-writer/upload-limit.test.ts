import { expect, test } from "bun:test";
import {
  isMediaFile,
  REPORT_REQUEST_MAX_BYTES,
  REPORT_UPLOAD_MAX_BYTES,
  totalFileBytes,
} from "./upload-limit";

test("recognises audio and video by extension", () => {
  expect(isMediaFile("meeting.MP3")).toBe(true);
  expect(isMediaFile("recording.mp4")).toBe(true);
  expect(isMediaFile("notes.pdf")).toBe(false);
});

test("counts file content only", () => {
  expect(totalFileBytes([{ size: 1000 }, { size: 500 }])).toBe(1500);
});

test("files at exactly the budget are allowed and fit the request cap", () => {
  const bytes = totalFileBytes([{ size: REPORT_UPLOAD_MAX_BYTES }]);
  expect(bytes > REPORT_UPLOAD_MAX_BYTES).toBe(false);
  expect(REPORT_REQUEST_MAX_BYTES).toBeGreaterThan(REPORT_UPLOAD_MAX_BYTES);
});
