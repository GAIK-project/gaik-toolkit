import { test, expect, type APIRequestContext, type Page } from "@playwright/test";
import { getWizardApiUrl, waitForApiHealthy } from "./helpers/api";
import { draftSteps, openEditor, sessionAtBpmn, writeDraft } from "./helpers/bpmn-stack";
import { centre, drag, focusStep, laneAt } from "./helpers/bpmn-canvas";

const STACK_E2E = process.env.PLAYWRIGHT_STACK_E2E === "true";

/**
 * Lanes on the BPMN canvas against the real stack (UI + wizard_api +
 * Postgres): a lane added from the palette is drawn, a step dragged into it
 * is put in it (its `performed_by`), and both are there after a reload, in
 * the canvas and in the agent's draft. A lane a step is in is not removed;
 * once the step is back in the lane of its type (the step panel's lane
 * select), it is. e2e/bpmn-lanes.spec.ts covers what is sent on the mock store.
 */

type Participant = { id: string; name: string };

async function participants(request: APIRequestContext, id: string): Promise<Participant[]> {
  const res = await request.get(`${getWizardApiUrl()}/test/sessions/${id}/draft`);
  expect(res.ok()).toBe(true);
  return ((await res.json()) as { business_process: { participants: Participant[] } }).business_process.participants;
}

/** The lane on the canvas whose name is `name`: its element id. */
async function laneNamed(page: Page, name: string): Promise<string> {
  const lane = page.locator(".bpmn-editable .djs-element[data-element-id^='Lane_']", {
    has: page.locator(`text="${name}"`),
  });
  await expect(lane).toHaveCount(1, { timeout: 30_000 });
  return (await lane.getAttribute("data-element-id"))!;
}

/** A point on screen where the lane itself is hit: not a shape, a flow or the palette over it. */
async function freeSpot(page: Page, lane: string): Promise<[number, number]> {
  const point = await page.evaluate((lane) => {
    const r = document
      .querySelector(`.bpmn-editable .djs-element[data-element-id="${lane}"] .djs-visual`)!
      .getBoundingClientRect();
    for (let x = Math.max(r.left, 0) + 120; x < r.right; x += 37) {
      for (const y of [r.top + r.height / 2, r.top + 12, r.bottom - 12]) {
        const hit = document.elementFromPoint(x, y)?.closest("[data-element-id]")?.getAttribute("data-element-id");
        if (hit === lane) return [x, y] as [number, number];
      }
    }
    return null;
  }, lane);
  expect(point, `a free spot in ${lane}`).toBeTruthy();
  return point!;
}

/** The lanes on the canvas, top to bottom, with their names and places in diagram units. */
async function lanePlaces(page: Page) {
  return page.evaluate(() =>
    [...document.querySelectorAll<SVGGElement>('.bpmn-editable .djs-element[data-element-id^="Lane_"]')]
      .map((g) => {
        const m = g.transform.baseVal.consolidate()!.matrix;
        return { name: g.querySelector("text")?.textContent ?? "", y: Math.round(m.f) };
      })
      .sort((a, b) => a.y - b.y),
  );
}

/** A point inside the lane, on screen, at `x`. */
async function inLane(page: Page, lane: string, x: number) {
  const box = (await page.locator(`.bpmn-editable [data-element-id="${lane}"]`).first().boundingBox())!;
  return { x, y: box.y + Math.min(50, box.height / 2) };
}

const operationAnswer = (page: Page) =>
  page.waitForResponse((r) => r.url().includes("/blueprint/operations") && r.request().method() === "POST");

test.describe("BPMN lanes (stack)", () => {
  test.skip(!STACK_E2E, "set PLAYWRIGHT_STACK_E2E=true (docker-test.sh --step stack-e2e)");
  test.use({ viewport: { width: 1600, height: 1100 } });

  test.beforeAll(async ({ request }) => {
    await waitForApiHealthy(request);
  });

  test("a lane added from the palette, and a step dragged into it, are kept over a reload", async ({ page, request }) => {
    test.setTimeout(240_000);
    const id = await sessionAtBpmn(page, request);
    await writeDraft(request, id);
    await page.reload();
    await openEditor(page);

    // Add lane: drawn empty, below every other lane, which stay where they were.
    const lanesBefore = await lanePlaces(page);
    const added = operationAnswer(page);
    await page.locator('.bpmn-editable .djs-palette .entry[data-action="gaik-add-lane"]').click();
    expect((await added).status()).toBe(200);
    await expect(page.locator(".bpmn-editable")).toHaveAttribute("aria-busy", "false");
    const lane = await laneNamed(page, "Uusi kaista");
    const lanesAfter = await lanePlaces(page);
    expect(lanesAfter.at(-1)!.name).toBe("Uusi kaista");
    expect(lanesAfter.slice(0, -1)).toEqual(lanesBefore);
    expect(await participants(request, id)).toContainEqual(expect.objectContaining({ id: "uusi_kaista", name: "Uusi kaista" }));

    // The upload step goes into it, by a drag.
    await expect(page.locator('.bpmn-editable .djs-palette .entry[data-action="gaik-add-step"]')).toBeVisible();
    await focusStep(page, 0);
    const from = await centre(page, "Activity_upload");
    const to = await inLane(page, lane, from.x);
    expect(await laneAt(page, to)).toBe(lane);
    const resets: string[] = [];
    page.on("request", (r) => {
      if (r.method() === "PUT" && r.url().includes("/bpmn/layout")) resets.push(r.postData() ?? "");
    });
    const moved = operationAnswer(page);
    await drag(page, from, to);
    const answer = await moved;
    expect(answer.status()).toBe(200);
    expect(answer.request().postDataJSON().operations).toEqual([
      { op: "set_step_lane", step_id: "upload", lane_id: "uusi_kaista" },
    ]);
    // The step's kept place goes once the change is made.
    await expect.poll(() => resets.length).toBe(2);
    expect(JSON.parse(resets[0]).shapes).toEqual({ Activity_upload: null });
    await expect.poll(async () => laneAt(page, await centre(page, "Activity_upload")), { timeout: 15_000 }).toBe(lane);

    // After a reload: the lane, and the step in it, on the canvas and in the draft.
    await page.reload();
    await openEditor(page);
    expect(await laneNamed(page, "Uusi kaista")).toBe(lane);
    expect(await laneAt(page, await centre(page, "Activity_upload"))).toBe(lane);
    const upload = (await draftSteps(request, id)).find((s) => s.id === "upload") as { performed_by?: string };
    expect(upload.performed_by).toBe("uusi_kaista");
  });

  test("a lane a step is in is not removed; once the step is back in the lane of its type, it is", async ({
    page,
    request,
  }) => {
    test.setTimeout(240_000);
    const id = await sessionAtBpmn(page, request);
    await writeDraft(request, id);
    await page.reload();
    await openEditor(page);
    let answer = operationAnswer(page);
    await page.locator('.bpmn-editable .djs-palette .entry[data-action="gaik-add-lane"]').click();
    expect((await answer).status()).toBe(200);
    await expect(page.locator(".bpmn-editable")).toHaveAttribute("aria-busy", "false");
    const lane = await laneNamed(page, "Uusi kaista");

    // The step panel puts the review step in the new lane.
    await page.getByTestId("flow-step-list").locator("li").nth(2).getByRole("button").first().click();
    const select = page.getByTestId("bpmn-step-lane");
    await expect(select).toBeEnabled();
    answer = operationAnswer(page);
    await select.selectOption("uusi_kaista");
    expect((await answer).status()).toBe(200);
    await expect(page.locator(".bpmn-editable")).toHaveAttribute("aria-busy", "false");
    // Drawn in it once the server's diagram is on the canvas.
    await expect.poll(async () => laneAt(page, await centre(page, "Activity_review")), { timeout: 15_000 }).toBe(lane);
    await page.getByTestId("bpmn-properties").getByRole("button", { name: "Sulje" }).click();

    // Remove is refused while the step is in it.
    // Picked anew each time: a click on the lane still selected opens no pad.
    const removeLane = async () => {
      await expect(page.locator('.bpmn-editable [data-element-id="Activity_extract"]').first()).toBeVisible();
      const step = await centre(page, "Activity_extract");
      await page.mouse.click(step.x, step.y);
      await page.getByTestId("bpmn-properties").getByRole("button", { name: "Sulje" }).click();
      await page.mouse.click(...(await freeSpot(page, lane)));
      const pending = operationAnswer(page);
      await page.locator('.djs-context-pad .entry[data-action="gaik-lane-remove"]').click();
      return pending;
    };
    expect((await removeLane()).status()).toBe(422);
    await expect(page.getByTestId("bpmn-status")).toContainText("Kaistaa ei poistettu");
    expect((await participants(request, id)).map((p) => p.id)).toContain("uusi_kaista");

    // Back in the lane of its type, then the lane goes.
    await page.getByTestId("flow-step-list").locator("li").nth(2).getByRole("button").first().click();
    answer = operationAnswer(page);
    await page.getByTestId("bpmn-step-lane").selectOption("");
    expect((await answer).status()).toBe(200);
    await expect(page.locator(".bpmn-editable")).toHaveAttribute("aria-busy", "false");
    await page.getByTestId("bpmn-properties").getByRole("button", { name: "Sulje" }).click();
    expect((await removeLane()).status()).toBe(200);
    await expect(page.locator(`.bpmn-editable [data-element-id="${lane}"]`)).toHaveCount(0);
    expect((await participants(request, id)).map((p) => p.id)).not.toContain("uusi_kaista");
  });
});
