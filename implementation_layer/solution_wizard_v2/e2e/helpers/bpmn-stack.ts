import { expect, type APIRequestContext, type Page } from "@playwright/test";
import { DEV_USERS, loginAsDev } from "./auth";
import { getWizardApiUrl, setApiSessionStep } from "./api";
import { createSession } from "./session";
import { openBpmnView, selectWorkspaceTab, setChatOpen } from "./workspace";

/**
 * The BPMN editor's stack specs (e2e/bpmn-editing-stack.spec.ts,
 * e2e/bpmn-step-panel-stack.spec.ts): a session at the BPMN step whose agent
 * draft is written and read through wizard_api's test hook
 * (`/test/sessions/{id}/draft`, mounted only with WIZARD_TEST_HOOKS=1, as the
 * stack E2E's wizard-api-e2e sets it): the Playwright container cannot reach
 * the API's session folder.
 */

export type Step = { id: string; name: string; type: string; depends_on: string[]; description?: string; component?: string };

/** A small valid blueprint: upload → extract → review → deliver. */
export function draft() {
  const generated = (by: string, final = false) => ({
    type: "structured_json",
    source: "generated",
    optional: false,
    produced_by: by,
    final_output: final,
  });
  const step = (id: string, name: string, type: string, deps: string[], inputs: string[], outputs: string[]) => ({
    id,
    name,
    type,
    inputs,
    outputs,
    depends_on: deps,
    ...(type === "automated_task" ? { component: "custom" } : {}),
  });
  return {
    use_case: { id: "invoices", name: "Invoices", description: "Invoice handling", domain: "finance" },
    business_spec: { intended_users: ["Clerk"], reviewers: ["Controller"], current_process: "by hand" },
    technical_spec: { input_types: ["pdf"], output_types: ["structured_json"] },
    artifacts: {
      invoice: { type: "pdf", source: "user_upload", optional: false },
      fields: generated("extract"),
      reviewed: generated("review"),
      report: generated("deliver", true),
    },
    workflow: {
      steps: [
        step("upload", "Upload invoice", "user_task", [], [], ["invoice"]),
        step("extract", "Extract fields", "automated_task", ["upload"], ["invoice"], ["fields"]),
        step("review", "Review fields", "human_review", ["extract"], ["fields"], ["reviewed"]),
        step("deliver", "Deliver report", "automated_task", ["review"], ["reviewed"], ["report"]),
      ],
    },
    business_process: {
      participants: [
        { id: "clerk", name: "Clerk", default_lane_for: ["user_task"] },
        { id: "system", name: "AI system", kind: "system" },
      ],
    },
  };
}

/** A session at the BPMN step, its version showing the steps of `draft()`; the agent has written no draft yet. */
export async function sessionAtBpmn(page: Page, request: APIRequestContext): Promise<string> {
  await loginAsDev(page, DEV_USERS.primary);
  await createSession(page, `BPMN ops ${Date.now()}`);
  const id = new URL(page.url()).pathname.split("/").pop() as string;
  await setApiSessionStep(request, id, 8);
  const base = getWizardApiUrl();
  const res = await request.post(`${base}/sessions/${id}/versions`, {
    data: {
      note: "e2e: the agent's draft",
      content: {
        name: "Invoices",
        description: "Invoice handling",
        goal: "",
        steps: [
          { id: "upload", name: "Upload invoice", type: "io" },
          { id: "extract", name: "Extract fields", type: "ai", component: "custom" },
          { id: "review", name: "Review fields", type: "human_review" },
          { id: "deliver", name: "Deliver report", type: "ai", component: "custom" },
        ],
        integration_targets: [],
      },
    },
  });
  expect(res.ok(), `seed version: ${res.status()}`).toBe(true);
  return id;
}

/** Writes `draft()` as the agent would, through the test hook. */
export async function writeDraft(request: APIRequestContext, id: string) {
  const res = await request.post(`${getWizardApiUrl()}/test/sessions/${id}/draft`, { data: draft() });
  expect(res.status(), `write draft: ${await res.text()}`).toBe(204);
}

/** The agent's draft as wizard_api has it now. */
export async function draftSteps(request: APIRequestContext, id: string): Promise<Step[]> {
  const res = await request.get(`${getWizardApiUrl()}/test/sessions/${id}/draft`);
  expect(res.ok(), `read draft: ${res.status()}`).toBe(true);
  return ((await res.json()) as { workflow: { steps: Step[] } }).workflow.steps;
}

export async function openEditor(page: Page) {
  await setChatOpen(page, false);
  await selectWorkspaceTab(page, "Työnkulku");
  await openBpmnView(page);
  await expect(page.getByTestId("bpmn-panel")).toHaveAttribute("data-ops", "on", { timeout: 45_000 });
  await expect(page.locator(".bpmn-editable")).toHaveAttribute("data-read-only", "false");
  await expect(page.locator(".bpmn-editable")).toHaveAttribute("aria-busy", "false");
  // The tools come once the page's steps fit the diagram's mapping.
  await expect(page.locator('.bpmn-editable .djs-palette .entry[data-action="gaik-add-step"]')).toBeVisible();
}
