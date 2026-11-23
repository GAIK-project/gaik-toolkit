import fs from "node:fs";
import path from "node:path";
import { test, expect, type APIRequestContext } from "@playwright/test";
import { agentE2eEnabled, createSessionViaApi, sendChatViaApi } from "./helpers/agent-api";
import { getWizardApiUrl, waitForApiHealthy } from "./helpers/api";

/**
 * Use-case acceptance run — the customer's own measure of Sprint 3/4.
 *
 * "For the use cases you provide, 5 of 5 generate a PoC that runs in the sandbox
 * and produces the correct output" (7 Sep 2026 plan). Sprint 3 owns the first
 * half: the wizard has to reach a blueprint and a runnable PoC package from the
 * case description alone, picking the component the case requires.
 *
 * The case files are the customer's unpublished material and live outside this
 * repository. Point UC_CASES_DIR at them; without it every case skips.
 *
 * Prerequisites (local only, never CI):
 *   - wizard_api on WIZARD_API_URL with Claude ambient auth
 *   - the API running on this machine, so its session output_dir is readable here
 *
 * Run:
 *   PLAYWRIGHT_AGENT_E2E=true PLAYWRIGHT_SKIP_WEBSERVER=true \
 *   WIZARD_API_URL=http://127.0.0.1:8100 \
 *   UC_CASES_DIR=/path/to/use-case-bundle/cases \
 *   UC_ONLY=UC02 npm run test:e2e:uc
 */

type UseCase = {
  id: string;
  description: string;
  requiredBehaviour: string;
  answers: string[];
  expect: {
    components?: string[];
    forbiddenComponents?: string[];
    mentionsAll?: string[];
    artifacts: string[];
  };
};

const casesDir = process.env.UC_CASES_DIR?.trim();
const only = process.env.UC_ONLY?.split(",")
  .map((s) => s.trim().toUpperCase())
  .filter(Boolean);
const runsDir = process.env.UC_RUNS_DIR?.trim();
const gatheringDoneStep = Number(process.env.UC_GATHERING_STEP ?? 4);
// Phases 4–10 of the agent's flow: schema, components, blueprint, scaffolding.
const continueTurns = Number(process.env.UC_CONTINUE_TURNS ?? 25);
// Assembling a blueprint or scaffolding a package is one long turn — well past
// the three minutes a question-and-answer turn needs.
const turnTimeoutMs = Number(process.env.UC_TURN_TIMEOUT_MS ?? 900_000);
const testTimeoutMin = Number(process.env.UC_TEST_TIMEOUT_MIN ?? 90);

function loadCases(): UseCase[] {
  if (!casesDir || !fs.existsSync(casesDir)) return [];
  return fs
    .readdirSync(casesDir)
    .filter((f) => f.endsWith(".json"))
    .map((f) => JSON.parse(fs.readFileSync(path.join(casesDir, f), "utf8")) as UseCase)
    .filter((c) => !only || only.includes(c.id.toUpperCase()))
    .sort((a, b) => a.id.localeCompare(b.id));
}

/** "AudioToStructuredData" and "audio_to_structured_data" are the same thing. */
function normalise(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]/g, "");
}

/** Every component the blueprint names, wherever it names it. */
function componentsIn(blueprint: Record<string, unknown>): Set<string> {
  const found = new Set<string>();
  const components = blueprint.components as
    | { selected_modules?: { id?: string; name?: string }[]; selected_building_blocks?: string[] }
    | undefined;
  for (const m of components?.selected_modules ?? []) {
    if (m.id) found.add(normalise(m.id));
    if (m.name) found.add(normalise(m.name));
  }
  for (const b of components?.selected_building_blocks ?? []) found.add(normalise(b));
  const workflow = blueprint.workflow as { steps?: { component?: string | null }[] } | undefined;
  for (const step of workflow?.steps ?? []) {
    if (step.component) found.add(normalise(step.component));
  }
  return found;
}

/** The agent's own draft, or null while it has not written one yet. */
function readDraft(outputDir: string): Record<string, unknown> | null {
  const file = path.join(outputDir, "use_case.blueprint.json");
  if (!fs.existsSync(file)) return null;
  try {
    return JSON.parse(fs.readFileSync(file, "utf8")) as Record<string, unknown>;
  } catch {
    // A half-written file during a save — the next poll will read it whole.
    return null;
  }
}

function hasDesign(draft: Record<string, unknown> | null): boolean {
  if (!draft) return false;
  const steps = (draft.workflow as { steps?: unknown[] } | undefined)?.steps ?? [];
  return steps.length > 0 && componentsIn(draft).size > 0;
}

/** Design assembled and the package scaffolded — the whole forward flow. */
function designComplete(outputDir: string): boolean {
  return (
    hasDesign(readDraft(outputDir)) && fs.existsSync(path.join(outputDir, "poc", "run_poc.py"))
  );
}

/**
 * Answer the agent in the terms of whatever it is still missing. The flow is
 * linear here and each phase ends by asking to proceed, so a plain yes is the
 * answer it asked for — a long instruction only risks steering it off its own
 * checklist.
 */
function nextInstruction(outputDir: string): string {
  return hasDesign(readDraft(outputDir))
    ? "Yes — please scaffold the proof of concept package now."
    : "Yes — please continue. Record a clearly labelled assumption for anything " +
        "I did not specify.";
}

/** Step ids of the blueprint the UI would render for this session. */
async function sessionBlueprintSteps(
  request: APIRequestContext,
  id: string,
): Promise<string[]> {
  const res = await request.get(`${getWizardApiUrl()}/sessions/${id}`);
  if (!res.ok()) throw new Error(`read session failed: ${res.status()}`);
  const body = (await res.json()) as { blueprint?: { steps?: { id?: string }[] } };
  return (body.blueprint?.steps ?? []).map((s) => s.id ?? "");
}

/** Every new session starts from this four-step seed. */
const PLACEHOLDER_STEPS = ["input", "process", "review", "output"];

function isPlaceholder(steps: string[]): boolean {
  return (
    steps.length === PLACEHOLDER_STEPS.length &&
    steps.every((id, i) => id === PLACEHOLDER_STEPS[i])
  );
}

async function sessionStep(request: APIRequestContext, id: string): Promise<number> {
  const res = await request.get(`${getWizardApiUrl()}/sessions/${id}`);
  if (!res.ok()) throw new Error(`read session failed: ${res.status()}`);
  return ((await res.json()) as { step: number }).step;
}

function copyInto(from: string, to: string): void {
  fs.mkdirSync(to, { recursive: true });
  fs.cpSync(from, to, { recursive: true });
}

const cases = loadCases();

test.describe("Use-case acceptance (live agent)", () => {
  test.skip(
    !agentE2eEnabled() || cases.length === 0,
    "local only: PLAYWRIGHT_AGENT_E2E=true + UC_CASES_DIR pointing at the case files",
  );

  test.beforeAll(async ({ request }) => {
    await waitForApiHealthy(request);
  });

  // Keep the file from registering zero tests: a silent empty suite looks the
  // same as a passing one in a report.
  if (cases.length === 0) {
    test("no use cases loaded", () => {
      test.skip(true, "set UC_CASES_DIR to the directory holding the case files");
    });
  }

  for (const useCase of cases) {
    test(`${useCase.id} — description to a runnable PoC package`, async ({ request }) => {
      // A full gathering conversation plus blueprint, BPMN and scaffolding.
      test.setTimeout(testTimeoutMin * 60_000);

      const session = await createSessionViaApi(
        request,
        "dev@gaik.local",
        `${useCase.id} acceptance ${new Date().toISOString().slice(0, 16)}`,
      );
      const outputDir = session.outputDir;
      test.info().annotations.push(
        { type: "session", description: session.id },
        { type: "output_dir", description: outputDir },
      );

      const opening = await sendChatViaApi(request, session.id, useCase.description, {
        locale: "en",
        timeoutMs: turnTimeoutMs,
      });
      expect(opening.length, "the agent should open the conversation").toBeGreaterThan(20);

      // Answer as the customer's own answer sheet does, one block per turn,
      // until the agent has what it needs and the session leaves gathering.
      for (const answer of useCase.answers) {
        if ((await sessionStep(request, session.id)) >= gatheringDoneStep) break;
        await sendChatViaApi(request, session.id, answer, {
          locale: "en",
          timeoutMs: turnTimeoutMs,
        });
      }

      // Still asking after the sheet is exhausted: the remaining answers are
      // the ones already given, so say so rather than inventing new facts.
      for (let nudge = 0; nudge < 3; nudge++) {
        if ((await sessionStep(request, session.id)) >= gatheringDoneStep) break;
        await sendChatViaApi(
          request,
          session.id,
          "Everything I can specify is in the answers above. For anything still " +
            "missing, record a clearly labelled assumption and continue.",
          { locale: "en", timeoutMs: turnTimeoutMs },
        );
      }

      const blueprintPath = path.join(outputDir, "use_case.blueprint.json");
      expect(
        fs.existsSync(outputDir),
        `session output_dir is not readable from here: ${outputDir}`,
      ).toBe(true);

      // Reaching Gate 1 only means the requirements are in. Component selection,
      // blueprint assembly and PoC scaffolding are later phases of the agent's
      // own flow, so keep the conversation going until it has actually produced
      // them. Stopping at Gate 1 and scaffolding from the session's placeholder
      // blueprint would "pass" with a package that has no components in it.
      for (let turn = 0; turn < continueTurns && !designComplete(outputDir); turn++) {
        await sendChatViaApi(request, session.id, nextInstruction(outputDir), {
          locale: "en",
          timeoutMs: turnTimeoutMs,
        });
      }

      const draft = readDraft(outputDir);
      expect(draft, `the agent never wrote ${path.basename(blueprintPath)}`).not.toBeNull();
      expect(
        (draft?.workflow as { steps?: unknown[] } | undefined)?.steps?.length ?? 0,
        "the blueprint has no workflow steps — nothing was designed",
      ).toBeGreaterThan(0);

      for (const artifact of useCase.expect.artifacts) {
        expect(fs.existsSync(path.join(outputDir, artifact)), `missing ${artifact}`).toBe(true);
      }

      // #141: the workspace reads the session's blueprint, not the agent's file.
      // A session still carrying the seeded placeholder means the design never
      // reached the UI, however good the file on disk looks.
      let sessionSteps = await sessionBlueprintSteps(request, session.id);
      if (isPlaceholder(sessionSteps)) {
        await sendChatViaApi(request, session.id, "Thank you — that is all for now.", {
          locale: "en",
          timeoutMs: turnTimeoutMs,
        });
        sessionSteps = await sessionBlueprintSteps(request, session.id);
      }
      expect(
        isPlaceholder(sessionSteps),
        `the session still shows the placeholder blueprint [${sessionSteps.join(", ")}]`,
      ).toBe(false);

      // The visual workflow is generated from the blueprint on request and is
      // never written to the session directory, so ask for it the way the UI does.
      const bpmnResponse = await request.get(
        `${getWizardApiUrl()}/sessions/${session.id}/bpmn`,
        { timeout: 120_000 },
      );
      expect(bpmnResponse.ok(), `BPMN generation failed: ${bpmnResponse.status()}`).toBe(true);
      const bpmnXml = await bpmnResponse.text();
      expect(bpmnXml).toContain("bpmn:definitions");
      expect(bpmnXml).toMatch(/bpmn:(task|serviceTask|userTask|manualTask)/);

      const blueprint = JSON.parse(fs.readFileSync(blueprintPath, "utf8")) as Record<
        string,
        unknown
      >;
      const selected = componentsIn(blueprint);
      for (const required of useCase.expect.components ?? []) {
        expect(
          selected.has(normalise(required)),
          `${useCase.id} requires ${required}; blueprint selected [${[...selected].join(", ")}]`,
        ).toBe(true);
      }
      for (const forbidden of useCase.expect.forbiddenComponents ?? []) {
        expect(
          selected.has(normalise(forbidden)),
          `${useCase.id} must not be solved with ${forbidden}`,
        ).toBe(false);
      }
      const blueprintText = JSON.stringify(blueprint).toLowerCase();
      for (const word of useCase.expect.mentionsAll ?? []) {
        expect(blueprintText.includes(word.toLowerCase()), `blueprint never mentions ${word}`).toBe(
          true,
        );
      }

      if (runsDir) {
        const target = path.join(runsDir, useCase.id);
        copyInto(outputDir, target);
        fs.writeFileSync(path.join(target, "workflow.bpmn"), bpmnXml);
      }
    });
  }
});
