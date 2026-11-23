import { EventEmitter } from "node:events";
import { beforeEach, describe, expect, it, vi } from "vitest";

const spawnMock = vi.hoisted(() => vi.fn());
vi.mock("node:child_process", () => ({ spawn: spawnMock }));

const fsMock = vi.hoisted(() => ({ existsSync: vi.fn(() => false) }));
vi.mock("node:fs", () => ({ default: fsMock, ...fsMock }));

import { generateBpmnXmlFromBlueprint, syncBlueprintFromBpmnXml } from "@/lib/bpmn-server";

const blueprint = { name: "Demo", description: "", goal: "", steps: [] };

class FakeChild extends EventEmitter {
  stdout = new EventEmitter();
  stderr = new EventEmitter();
  stdin = { write: vi.fn(), end: vi.fn() };
}

function mockSpawnSucceeds(stdout: string) {
  const child = new FakeChild();
  spawnMock.mockReturnValue(child);
  queueMicrotask(() => {
    child.stdout.emit("data", Buffer.from(stdout));
    child.emit("close", 0);
  });
  return child;
}

function mockSpawnFails(stderr: string, code = 1) {
  const child = new FakeChild();
  spawnMock.mockReturnValue(child);
  queueMicrotask(() => {
    child.stderr.emit("data", Buffer.from(stderr));
    child.emit("close", code);
  });
  return child;
}

beforeEach(() => {
  vi.clearAllMocks();
  fsMock.existsSync.mockReturnValue(false);
  delete process.env.WIZARD_BPMN_PYTHON;
});

describe("generateBpmnXmlFromBlueprint", () => {
  it("spawns the generator script with the session id and pipes the blueprint over stdin", async () => {
    const child = mockSpawnSucceeds("<bpmn/>");
    const xml = await generateBpmnXmlFromBlueprint(blueprint, "s1");
    expect(xml).toBe("<bpmn/>");
    const [bin, args] = spawnMock.mock.calls[0];
    expect(bin).toBe("python3");
    expect(args[0]).toMatch(/generate_bpmn_from_v2\.py$/);
    expect(args[1]).toBe("s1");
    expect(child.stdin.write).toHaveBeenCalledWith(JSON.stringify(blueprint));
  });

  it("uses WIZARD_BPMN_PYTHON when set, without checking for a venv", async () => {
    process.env.WIZARD_BPMN_PYTHON = "/custom/python";
    mockSpawnSucceeds("<bpmn/>");
    await generateBpmnXmlFromBlueprint(blueprint, "s1");
    expect(spawnMock.mock.calls[0][0]).toBe("/custom/python");
    expect(fsMock.existsSync).not.toHaveBeenCalled();
  });

  it("prefers the project venv python when it exists", async () => {
    fsMock.existsSync.mockReturnValue(true);
    mockSpawnSucceeds("<bpmn/>");
    await generateBpmnXmlFromBlueprint(blueprint, "s1");
    expect(spawnMock.mock.calls[0][0]).toMatch(/\.venv.*python3?$/);
  });

  it("rejects with stderr, plus a setup hint, when pydantic is missing", async () => {
    mockSpawnFails("ModuleNotFoundError: No module named 'pydantic'");
    await expect(generateBpmnXmlFromBlueprint(blueprint, "s1")).rejects.toThrow(
      /scripts\/setup\.sh/,
    );
  });

  it("rejects with plain stderr for other failures", async () => {
    mockSpawnFails("boom");
    await expect(generateBpmnXmlFromBlueprint(blueprint, "s1")).rejects.toThrow("boom");
  });
});

describe("syncBlueprintFromBpmnXml", () => {
  it("spawns the sync script with blueprint+xml on stdin and parses the JSON result", async () => {
    const synced = { ...blueprint, name: "Synced" };
    const child = mockSpawnSucceeds(JSON.stringify(synced));
    const result = await syncBlueprintFromBpmnXml(blueprint, "<bpmn/>");
    expect(result).toEqual(synced);
    const [, args] = spawnMock.mock.calls[0];
    expect(args[0]).toMatch(/sync_blueprint_from_bpmn\.py$/);
    expect(child.stdin.write).toHaveBeenCalledWith(
      JSON.stringify({ blueprint, xml: "<bpmn/>" }),
    );
  });
});
