import { afterAll, describe, expect, it } from "vitest";
import {
  BPMN_LINT_MAX_RUNNING,
  BPMN_LINT_MAX_WAITING,
  BpmnLintBusyError,
  lintBpmnXml,
} from "@/lib/bpmn-lint";
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { execFileSync } from "node:child_process";

const BAD_XML = `<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
  id="Definitions_1" targetNamespace="http://bpmn.io/schema/bpmn">
  <bpmn:process id="Process_1" isExecutable="false" />
</bpmn:definitions>`;

function pythonEnv(): NodeJS.ProcessEnv {
  const swSrc = resolve(__dirname, "../../solution_wizard/src");
  const implSrc = resolve(__dirname, "../../src");
  return {
    ...process.env,
    PYTHONPATH: [swSrc, implSrc, process.env.PYTHONPATH ?? ""].join(":"),
  };
}

/**
 * The generated-BPMN case shells out to the Python wizard. That source is not
 * in the Next.js test image (`docker-test.sh --step ui`), so the case can only
 * run in a full checkout — detect it and skip rather than fail there.
 */
function wizardPythonAvailable(): boolean {
  try {
    execFileSync("python3", ["-c", "import pydantic, solution_wizard"], {
      stdio: "ignore",
      env: pythonEnv(),
    });
    return true;
  } catch {
    return false;
  }
}

function generatedWizardXml(): string {
  const script = `
from solution_wizard.v2_adapter import v2_to_v1_dict
from solution_wizard.bpmn_generator import generate_bpmn
from solution_wizard.blueprint import Blueprint
v2 = {"name":"Demo","description":"","goal":"","steps":[
 {"id":"a","name":"Upload","type":"io"},
 {"id":"b","name":"Extract","type":"ai","component":"DataExtractor"},
]}
print(generate_bpmn(Blueprint.model_validate(v2_to_v1_dict(v2, session_id="t"))))
`;
  return execFileSync("python3", ["-c", script], {
    encoding: "utf8",
    env: pythonEnv(),
  });
}

describe("lintBpmnXml (#47)", () => {
  it("blocks incomplete process with errors", async () => {
    const result = await lintBpmnXml(BAD_XML);
    expect(result.ok).toBe(false);
    expect(result.errors.length).toBeGreaterThan(0);
    expect(result.errors.some((e) => e.rule.includes("start-event"))).toBe(true);
  });

  it.skipIf(!wizardPythonAvailable())(
    "accepts wizard-generated BPMN (recommended rules)",
    async () => {
      const xml = generatedWizardXml();
      const result = await lintBpmnXml(xml);
      expect(result.errors).toEqual([]);
      expect(result.ok).toBe(true);
    },
  );

  it("lints a customer reference BPMN without crashing", async () => {
    // Customer BPMN lives under gitignored docs/6.7_demo/ — skip in CI/clean clones.
    const ref = resolve(
      __dirname,
      "../docs/6.7_demo/extracted/Use_Case_Audio-to-Structured.bpmn",
    );
    if (!existsSync(ref)) {
      return;
    }
    const xml = readFileSync(ref, "utf8");
    const result = await lintBpmnXml(xml);
    expect(Array.isArray(result.issues)).toBe(true);
    expect(typeof result.ok).toBe("boolean");
  });
});


// --- The child process is asynchronous and bounded (review T3) ----------------
//
// Fake lint scripts stand in for scripts/lint-bpmn.mjs so these cases do not
// depend on bpmnlint's speed.

const scratch = mkdtempSync(join(tmpdir(), "bpmn-lint-test-"));
afterAll(() => rmSync(scratch, { recursive: true, force: true }));

function fakeScript(name: string, source: string): string {
  const file = join(scratch, `${name}.mjs`);
  writeFileSync(file, source);
  return file;
}

const OK_JSON = JSON.stringify({ ok: true, errors: [], warnings: [], issues: [] });

describe("lintBpmnXml runs the linter without parking the server", () => {
  it("kills a lint that does not finish and reports it as unavailable", async () => {
    const script = fakeScript("hangs", "setInterval(() => {}, 1000);");
    await expect(lintBpmnXml(BAD_XML, { script, timeoutMs: 300 })).rejects.toThrow(/timed out after 300 ms/);
  });

  it("lets other work run while the linter is busy", async () => {
    const script = fakeScript(
      "slow",
      `for await (const _ of process.stdin) {}\nsetTimeout(() => { process.stdout.write(${JSON.stringify(OK_JSON)}); }, 400);`,
    );
    const order: string[] = [];
    const lint = lintBpmnXml(BAD_XML, { script }).then((r) => {
      order.push("lint");
      return r;
    });
    const timer = new Promise<void>((done) =>
      setTimeout(() => {
        order.push("timer");
        done();
      }, 50),
    );
    const [result] = await Promise.all([lint, timer]);
    // With spawnSync the 50 ms timer could only fire after the 400 ms lint.
    expect(order).toEqual(["timer", "lint"]);
    expect(result.ok).toBe(true);
  });

  it("runs only a few lints at once, queues a few more and refuses the rest", async () => {
    const script = fakeScript(
      "counted",
      `for await (const _ of process.stdin) {}\nsetTimeout(() => { process.stdout.write(${JSON.stringify(OK_JSON)}); }, 300);`,
    );
    const capacity = BPMN_LINT_MAX_RUNNING + BPMN_LINT_MAX_WAITING;
    const results = await Promise.allSettled(
      Array.from({ length: capacity + 3 }, () => lintBpmnXml(BAD_XML, { script })),
    );
    const done = results.filter((r) => r.status === "fulfilled");
    const busy = results.filter(
      (r) => r.status === "rejected" && r.reason instanceof BpmnLintBusyError,
    );
    expect(done).toHaveLength(capacity);
    expect(busy).toHaveLength(3);
    // Every turn was given back: the next lint runs straight away.
    await expect(lintBpmnXml(BAD_XML, { script })).resolves.toMatchObject({ ok: true });
  });

  it("reports a linter that exits with an error, stderr included", async () => {
    const script = fakeScript("fails", 'console.error("boom"); process.exit(3);');
    await expect(lintBpmnXml(BAD_XML, { script })).rejects.toThrow(/exited 3: boom/);
  });
});
