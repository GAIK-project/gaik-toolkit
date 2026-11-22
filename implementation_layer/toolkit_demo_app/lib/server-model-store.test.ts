import { expect, test } from "bun:test";
import { reportModelNames, type ServerModels } from "./server-model-store";

const catalog = (
  report_models: ServerModels["report_models"],
): ServerModels => ({
  default: "azure:gpt-6-luna",
  models: [],
  report_models,
});

test("a report model field suggests the names its route accepts, by kind", () => {
  const listed = catalog({
    chat: ["gpt-6-luna", "gpt-6-sol"],
    transcription: ["gpt-4o-transcribe", "whisper-1"],
  });
  expect(reportModelNames(listed, "chat")).toEqual(["gpt-6-luna", "gpt-6-sol"]);
  expect(reportModelNames(listed, "transcription")).toEqual([
    "gpt-4o-transcribe",
    "whisper-1",
  ]);
});

test("without the list (loading, an older API, a bad answer) a field suggests nothing", () => {
  expect(reportModelNames(null, "chat")).toEqual([]);
  expect(reportModelNames(catalog(undefined), "chat")).toEqual([]);
  expect(reportModelNames(catalog(null), "transcription")).toEqual([]);
  const odd = catalog({ chat: ["gpt-6-luna", "", 7 as unknown as string] });
  expect(reportModelNames(odd, "chat")).toEqual(["gpt-6-luna"]);
  expect(reportModelNames(odd, "transcription")).toEqual([]);
});
