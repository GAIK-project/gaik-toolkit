import { afterEach, expect, test } from "bun:test";
import {
  forgetServerModels,
  getServerModels,
  loadServerModels,
  reportModelNames,
  type ServerModels,
} from "./server-model-store";

const originalFetch = globalThis.fetch;
const originalWindow = globalThis.window;
afterEach(() => {
  forgetServerModels();
  globalThis.fetch = originalFetch;
  globalThis.window = originalWindow;
});

/** The list as the API gives a team member, answered when `answer` is called. */
function serveTeamList(): { answer: () => void } {
  let answer = () => {};
  globalThis.window = { setTimeout } as unknown as Window & typeof globalThis;
  globalThis.fetch = (() =>
    new Promise<Response>((resolve) => {
      answer = () =>
        resolve(
          Response.json(catalog({ chat: ["gpt-6-luna", "team-only-model"] })),
        );
    })) as unknown as typeof fetch;
  return { answer: () => answer() };
}

test("a signed-out page reads no names, and sign-out forgets the team's list", async () => {
  const server = serveTeamList();
  const loading = loadServerModels();
  server.answer();
  await loading;
  expect(reportModelNames(getServerModels(), "chat")).toContain(
    "team-only-model",
  );
  // Signed out without a reload: the fields read nothing from the list.
  expect(getServerModels(false)).toBeNull();
  forgetServerModels();
  expect(getServerModels()).toBeNull();
});

test("a list that arrives after sign-out is not taken", async () => {
  const server = serveTeamList();
  const loading = loadServerModels();
  forgetServerModels();
  server.answer();
  await loading;
  expect(getServerModels()).toBeNull();
});

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
