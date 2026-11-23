import { expect, type Page } from "@playwright/test";

/**
 * Pick a workspace tab, retrying until it sticks. The tablist renders
 * server-side, so a click can land before React has hydrated the panel: the
 * click succeeds, no handler runs, and the selection does not move.
 */
export async function selectWorkspaceTab(page: Page, name: string | RegExp): Promise<void> {
  const tab = page.getByRole("tab", { name });
  await expect(async () => {
    await tab.click();
    await expect(tab).toHaveAttribute("aria-selected", "true", { timeout: 1_000 });
  }).toPass({ timeout: 15_000 });
}

/**
 * Open the Blueprint tab's form editor. The tab opens in its read view; the
 * form is behind "Muokkaa" and stays open across tab switches until "Valmis".
 */
export async function openBlueprintEditor(page: Page): Promise<void> {
  await selectWorkspaceTab(page, /Blueprint/);
  const edit = page.getByTestId("blueprint-edit");
  const done = page.getByTestId("blueprint-done");
  await expect(async () => {
    if (!(await done.isVisible())) await edit.click({ timeout: 1_000 });
    await expect(done).toBeVisible({ timeout: 1_000 });
  }).toPass({ timeout: 15_000 });
}

/**
 * Open or collapse the chat dock. It opens by itself while the session waits
 * on a gate, which narrows the workspace: a test about the workspace's layout
 * says which state it measures.
 */
export async function setChatOpen(page: Page, open: boolean): Promise<void> {
  const dock = page.getByTestId("chat-dock");
  const want = String(open);
  await expect(async () => {
    if ((await dock.getAttribute("data-chat-open")) !== want) {
      await page.getByTestId("chat-dock-toggle").first().click({ timeout: 1_000 });
    }
    await expect(dock).toHaveAttribute("data-chat-open", want, { timeout: 1_000 });
  }).toPass({ timeout: 15_000 });
}

/**
 * Show the BPMN editor on the Workflow tab. The tab opens on the simple flow
 * drawn from the blueprint; the BPMN canvas is behind "Avaa BPMN-kaaviona",
 * and stays chosen while the page is open.
 *
 * After Gate 2 the canvas opens read-only, as the simple flow does. A spec
 * about editing wants the tools, so the lock is opened here unless the spec
 * says `edit: false`.
 */
export async function openBpmnView(page: Page, { edit = true }: { edit?: boolean } = {}): Promise<void> {
  const button = page.getByTestId("flow-view-bpmn");
  await expect(async () => {
    if ((await button.getAttribute("aria-pressed", { timeout: 1_000 })) !== "true") {
      await button.click({ timeout: 1_000 });
    }
    await expect(button).toHaveAttribute("aria-pressed", "true", { timeout: 1_000 });
  }).toPass({ timeout: 15_000 });
  if (edit) await unlockBpmnEditor(page);
}

/**
 * Press "Muokkaa" on a BPMN canvas that is read-only (after Gate 2); nothing
 * where it is open for edits, or where no diagram could be loaded. The lock
 * comes back each time the Workflow tab is opened again.
 */
export async function unlockBpmnEditor(page: Page): Promise<void> {
  const panel = page.getByTestId("bpmn-panel");
  await expect(panel.or(page.getByTestId("flow-diagram-error"))).toBeVisible({ timeout: 45_000 });
  if ((await panel.count()) === 0 || (await panel.getAttribute("data-locked")) !== "true") return;
  await page.getByTestId("bpmn-unlock").click();
  await expect(panel).toHaveAttribute("data-locked", "false");
}
