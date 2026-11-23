/**
 * Server-side bpmnlint wrapper (Node only — do not import from client components).
 * Spawns scripts/lint-bpmn.mjs so bpmnlint's NodeResolver works under Next.js.
 *
 * The child runs asynchronously with a deadline. The first version used
 * spawnSync, which parks the whole Node event loop until bpmnlint is done:
 * one signed-in user posting large diagrams back to back stalled every other
 * request on the server, chat streams included (review T3). The route also
 * caps the XML size before anything is spawned.
 *
 * Each lint is a whole Node process sharing the web container's memory, so
 * only a few run at once; a few more wait their turn, and past that a lint is
 * refused as busy rather than started.
 */
import { spawn } from "node:child_process";
import path from "node:path";

export type BpmnLintIssue = {
  rule: string;
  id: string;
  message: string;
  category: "error" | "warn" | "info";
};

export type BpmnLintResult = {
  ok: boolean;
  errors: BpmnLintIssue[];
  warnings: BpmnLintIssue[];
  issues: BpmnLintIssue[];
};

/** Largest BPMN document the sync route accepts. A real diagram is tens of KB. */
export const BPMN_XML_MAX_BYTES = 2 * 1024 * 1024;

/** How long one lint may take before it is killed and reported as unavailable. */
export const BPMN_LINT_TIMEOUT_MS = 20_000;

const MAX_OUTPUT_BYTES = 20 * 1024 * 1024;

/** Lint processes one server runs at once, and lints that may wait for a turn. */
export const BPMN_LINT_MAX_RUNNING = 2;
export const BPMN_LINT_MAX_WAITING = 8;

/** Too many lints in flight: the caller should answer "try again shortly". */
export class BpmnLintBusyError extends Error {
  constructor() {
    super("bpmn lint is busy");
    this.name = "BpmnLintBusyError";
  }
}

let running = 0;
const waiting: Array<() => void> = [];

async function takeTurn(): Promise<() => void> {
  if (running >= BPMN_LINT_MAX_RUNNING) {
    if (waiting.length >= BPMN_LINT_MAX_WAITING) throw new BpmnLintBusyError();
    await new Promise<void>((go) => waiting.push(go));
  } else {
    running += 1;
  }
  // A turn handed over by release() keeps `running` as it was.
  return () => {
    const next = waiting.shift();
    if (next) next();
    else running -= 1;
  };
}

export type LintOptions = {
  /** Path of the lint script; the default is the real one. Tests point elsewhere. */
  script?: string;
  timeoutMs?: number;
};

export async function lintBpmnXml(xml: string, options: LintOptions = {}): Promise<BpmnLintResult> {
  const script = options.script ?? path.join(process.cwd(), "scripts", "lint-bpmn.mjs");
  const timeoutMs = options.timeoutMs ?? BPMN_LINT_TIMEOUT_MS;
  const release = await takeTurn();
  let stdout: string;
  try {
    stdout = await runLintProcess(script, xml, timeoutMs);
  } finally {
    release();
  }
  const parsed = JSON.parse(stdout) as BpmnLintResult;
  return {
    ok: Boolean(parsed.ok),
    errors: parsed.errors ?? [],
    warnings: parsed.warnings ?? [],
    issues: parsed.issues ?? [],
  };
}

function runLintProcess(script: string, xml: string, timeoutMs: number): Promise<string> {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [script], {
      cwd: process.cwd(),
      stdio: ["pipe", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    let settled = false;
    const finish = (fn: () => void) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      fn();
    };
    const timer = setTimeout(() => {
      child.kill("SIGKILL");
      finish(() => reject(new Error(`bpmn lint timed out after ${timeoutMs} ms`)));
    }, timeoutMs);

    const collect = (into: "stdout" | "stderr") => (chunk: Buffer) => {
      const text = chunk.toString("utf8");
      if (into === "stdout") stdout += text;
      else stderr += text;
      if (stdout.length + stderr.length > MAX_OUTPUT_BYTES) {
        child.kill("SIGKILL");
        finish(() => reject(new Error("bpmn lint produced more output than allowed")));
      }
    };
    child.stdout.on("data", collect("stdout"));
    child.stderr.on("data", collect("stderr"));
    child.on("error", (err) => finish(() => reject(err)));
    child.on("close", (code) => {
      finish(() => {
        if (code === 0) resolve(stdout);
        else reject(new Error(`bpmn lint process exited ${code}: ${stderr || stdout}`));
      });
    });
    // The child may exit before it reads stdin (a missing dependency, say);
    // an EPIPE on write is then just the exit we are already handling.
    child.stdin.on("error", () => {});
    child.stdin.end(xml);
  });
}
