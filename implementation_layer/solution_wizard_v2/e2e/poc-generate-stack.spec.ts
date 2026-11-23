import { test, expect, type APIRequestContext, type Page } from "@playwright/test";
import { DEV_USERS, loginAsDev } from "./helpers/auth";
import { getWizardApiUrl, setApiSessionStep, waitForApiHealthy } from "./helpers/api";
import { createSession } from "./helpers/session";

const STACK_E2E = process.env.PLAYWRIGHT_STACK_E2E === "true";

function sessionIdFromPath(url: string): string {
  return new URL(url).pathname.split("/").pop() as string;
}

/**
 * #93 (S5-5) — the wizard generates the runnable PoC package.
 *
 * Until now "Aja PoC" streamed a simulated log and produced nothing: the
 * listing and download endpoints (#151) only ever served what the agent had
 * already written to disk. This drives the real path — UI → wizard_api →
 * solution_wizard's V1 scaffolder — and checks a package actually lands and
 * can be downloaded, which is what Gate 3 needs.
 */
test.describe("#93 PoC package generation (stack)", () => {
  test.skip(!STACK_E2E, "set PLAYWRIGHT_STACK_E2E=true (docker-test.sh --step stack-e2e)");

  test.beforeAll(async ({ request }) => {
    await waitForApiHealthy(request);
  });

  async function openPocTab(
    page: Page,
    request: APIRequestContext,
  ): Promise<string> {
    await loginAsDev(page, DEV_USERS.primary);
    await createSession(page, `PoC gen ${Date.now()}`);
    const id = sessionIdFromPath(page.url());
    await setApiSessionStep(request, id, 10); // PoC phase
    await page.reload({ waitUntil: "load" });

    const tab = page.getByRole("tab", { name: "PoC" });
    await expect(async () => {
      await tab.click();
      await expect(tab).toHaveAttribute("aria-selected", "true", { timeout: 1_000 });
    }).toPass({ timeout: 15_000 });
    return id;
  }

  test("generating scaffolds the package, and an unfinished one is not handed out", async ({
    page,
    request,
  }) => {
    test.setTimeout(120_000);
    const id = await openPocTab(page, request);

    // Nothing exists before the run — the tab says so rather than offering a
    // download link to a package that was never generated.
    const listedBefore = await request.get(`${getWizardApiUrl()}/sessions/${id}/poc/files`);
    expect((await listedBefore.json()).generated).toBe(false);

    await page.getByRole("button", { name: "Generoi PoC-paketti" }).click();

    // The log reports the real scaffolder's output, not a simulated walk.
    // Scoped to the log line: the generated file list names run_poc.py too.
    await expect(page.getByText("✓ Kirjoitettu poc/run_poc.py")).toBeVisible({
      timeout: 30_000,
    });

    const listed = await (await request.get(`${getWizardApiUrl()}/sessions/${id}/poc/files`)).json();
    expect(listed.generated).toBe(true);
    // The file set the V1 scaffolder produces, not a subset the UI invented.
    expect(listed.files).toEqual(
      expect.arrayContaining([
        "run_poc.py",
        "requirements.txt",
        "config.yaml",
        "schemas/output_schema.py",
        "evals/run_basic_eval.py",
      ]),
    );

    // A session with no agent draft scaffolds the generic skeleton, which wires
    // no gaik component. The api refuses it as incomplete (#252), and the UI's
    // proxy passes that on with the reasons instead of reporting a failed call.
    expect(listed.ready).toBe(false);
    expect(listed.problems.length).toBeGreaterThan(0);
    const zip = await page.request.get(`/api/sessions/${id}/poc/download`);
    expect(zip.status()).toBe(409);
    expect((await zip.json()).detail.error).toBe("poc_package_incomplete");
    await expect(page.getByRole("link", { name: /Lataa työversio/ })).toHaveCount(0);
  });

  test("running it again rewrites the package instead of doing nothing", async ({
    page,
    request,
  }) => {
    test.setTimeout(120_000);
    const id = await openPocTab(page, request);

    await page.getByRole("button", { name: "Generoi PoC-paketti" }).click();
    await expect(page.getByText("✓ Kirjoitettu poc/run_poc.py")).toBeVisible({
      timeout: 30_000,
    });

    // A second run is the case the acceptance criteria call out: the scaffolder
    // leaves an existing schema alone so a reviewed one survives, which would
    // otherwise make this a silent no-op.
    await page.getByRole("button", { name: "Generoi paketti uudelleen" }).click();
    await expect(page.getByText("✓ Kirjoitettu poc/run_poc.py")).toBeVisible({
      timeout: 30_000,
    });

    const again = await (
      await request.post(`${getWizardApiUrl()}/sessions/${id}/poc/generate`)
    ).json();
    expect(again.regenerated).toBe(true);
    expect(again.files).toContain("run_poc.py");
  });
});
