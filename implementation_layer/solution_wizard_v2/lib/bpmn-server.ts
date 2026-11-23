import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import type { Blueprint } from "@/lib/mock-sessions";

const SCRIPTS_DIR = path.join(process.cwd(), "scripts");

/** Prefer project venv so `npm run dev` works without system pydantic. */
function resolvePythonBin(): string {
  if (process.env.WIZARD_BPMN_PYTHON) {
    return process.env.WIZARD_BPMN_PYTHON;
  }
  const venvPython = path.join(
    process.cwd(),
    ".venv",
    process.platform === "win32" ? "Scripts/python.exe" : "bin/python3",
  );
  if (fs.existsSync(venvPython)) {
    return venvPython;
  }
  return "python3";
}

function runPythonScript(
  scriptName: string,
  args: string[],
  stdinPayload: string,
): Promise<string> {
  return new Promise((resolve, reject) => {
    const python = resolvePythonBin();
    // turbopackIgnore: the interpreter's path is only known at run time, and
    // Turbopack would otherwise trace the whole project (sources, tests, docs)
    // into the standalone output to be safe. scripts/ is still traced.
    const child = spawn(/*turbopackIgnore: true*/ python, [path.join(SCRIPTS_DIR, scriptName), ...args], {
      stdio: ["pipe", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk: Buffer) => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString();
    });
    child.on("error", reject);
    child.on("close", (code) => {
      if (code === 0) resolve(stdout);
      else {
        const hint =
          /No module named ['"]pydantic['"]/.test(stderr)
            ? "\nHint: run `./scripts/setup.sh` in solution_wizard_v2 (installs .venv + pydantic), then restart `npm run dev`."
            : "";
        reject(new Error((stderr || `python exited ${code}`) + hint));
      }
    });
    child.stdin.write(stdinPayload);
    child.stdin.end();
  });
}

export async function generateBpmnXmlFromBlueprint(
  blueprint: Blueprint,
  sessionId: string,
): Promise<string> {
  return runPythonScript(
    "generate_bpmn_from_v2.py",
    [sessionId],
    JSON.stringify(blueprint),
  );
}

export async function syncBlueprintFromBpmnXml(
  blueprint: Blueprint,
  xml: string,
): Promise<Blueprint> {
  const out = await runPythonScript(
    "sync_blueprint_from_bpmn.py",
    [],
    JSON.stringify({ blueprint, xml }),
  );
  return JSON.parse(out) as Blueprint;
}
