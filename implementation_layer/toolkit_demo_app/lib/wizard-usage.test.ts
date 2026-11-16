import { expect, test } from "bun:test";
import {
  type WizardUseStore,
  readWizardUse,
  recordWizardUse,
  wizardUseKind,
} from "./wizard-usage";

function memoryStore(): WizardUseStore & {
  data: Map<string, Record<string, string>>;
} {
  const data = new Map<string, Record<string, string>>();
  const row = (key: string) => {
    if (!data.has(key)) data.set(key, {});
    return data.get(key)!;
  };
  return {
    data,
    async hincrby(key, field, increment) {
      row(key)[field] = String(Number(row(key)[field] ?? 0) + increment);
    },
    async hset(key, fields) {
      Object.assign(row(key), fields);
    },
    async hgetall(key) {
      return data.get(key) ?? null;
    },
  };
}

test("a started session and a sent message are counted, nothing else", () => {
  expect(wizardUseKind("POST", "/api/wizard/start")).toBe("session");
  expect(wizardUseKind("POST", "/api/wizard/message/abc")).toBe("message");
  expect(wizardUseKind("GET", "/api/wizard/files/abc")).toBeNull();
  expect(wizardUseKind("GET", "/api/wizard/download/abc")).toBeNull();
  expect(wizardUseKind("DELETE", "/api/wizard/end/abc")).toBeNull();
  expect(wizardUseKind("POST", "/api/extract")).toBeNull();
});

test("uses add up per user and keep the time of the last one", async () => {
  const store = memoryStore();
  await recordWizardUse(
    "u1",
    "session",
    store,
    new Date("2026-11-16T10:00:00Z"),
  );
  await recordWizardUse(
    "u1",
    "message",
    store,
    new Date("2026-11-16T10:01:00Z"),
  );
  await recordWizardUse(
    "u1",
    "message",
    store,
    new Date("2026-11-16T10:05:00Z"),
  );
  await recordWizardUse(
    "u2",
    "session",
    store,
    new Date("2026-11-16T11:00:00Z"),
  );

  expect(await readWizardUse(["u1", "u2", "u3"], store)).toEqual({
    u1: { sessions: 1, messages: 2, lastAt: "2026-11-16T10:05:00.000Z" },
    u2: { sessions: 1, messages: 0, lastAt: "2026-11-16T11:00:00.000Z" },
    u3: { sessions: 0, messages: 0, lastAt: null },
  });
});

test("without a store nothing is counted and the read says so", async () => {
  await recordWizardUse("u1", "session", null);
  expect(await readWizardUse(["u1"], null)).toBeNull();
});

test("a store that fails does not fail the request, and the read says nothing is known", async () => {
  const broken: WizardUseStore = {
    async hincrby() {
      throw new Error("unreachable");
    },
    async hset() {
      throw new Error("unreachable");
    },
    async hgetall() {
      throw new Error("unreachable");
    },
  };
  await recordWizardUse("u1", "message", broken);
  expect(await readWizardUse(["u1"], broken)).toBeNull();
});
