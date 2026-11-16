import { test, expect, type Page } from "@playwright/test";
import { loginAsDev } from "./helpers/auth";
import { setMockSessionStep } from "./helpers/dev-step";
import { resetMockSessions } from "./helpers/mock";
import { openBlueprintEditor, setChatOpen } from "./helpers/workspace";

/**
 * The PoC tab after Gate 2: a checked package folds to one status line with
 * its files and controls behind "Paketin tiedot", the check is remembered for
 * the browser tab, the set-up steps and the result sit side by side on a wide
 * panel, and several flat records come out as one table. The mock store has
 * no PoC package and no sandbox, so the PoC API is answered here. ses_laskut
 * stands at Gate 3 (step 11) and opens on the PoC tab.
 */

const SESSION = "ses_laskut";
const API = `**/api/sessions/${SESSION}`;

const FILES = ["README.md", "run_poc.py", "requirements.txt", "config.yaml", "schemas/output_schema.py"];

const RECORDS = [
  {
    supplier: "Lyreco Finland Oy",
    invoice_number: "INV-2024-118",
    total_amount: "412.90 EUR",
    paid: true,
    confidence: 0.93,
    needs_review: false,
  },
  {
    supplier: "Elisa Oyj",
    invoice_number: "9081-22",
    total_amount: "1 280.00 EUR",
    paid: false,
    confidence: 0.71,
    needs_review: true,
  },
  {
    supplier: "Fazer Food Services",
    invoice_number: "FF-55102",
    total_amount: "86.40 EUR",
    paid: true,
    confidence: 0.88,
    needs_review: false,
  },
];

const sse = (events: object[]) => events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join("");

type Fake = {
  checks: number;
  generations: number;
  version: string;
  runs: number;
  /** Set to leave the checks started from now on unanswered. */
  holdChecks: boolean;
};
/** How the package check ends: it passes, finds a problem, cannot run (no sandbox), or never ends. */
type Check = "ok" | "failed" | "none" | "pending";

async function fakePoc(
  page: Page,
  {
    record = RECORDS,
    check = "ok",
    inputs = true,
    solution,
  }: {
    record?: unknown;
    check?: Check;
    /** Test material is in the package. */ inputs?: boolean;
    /** What the deployable package carries beside poc/ (wizard_api's `solution_files`). */
    solution?: string[];
  } = {},
): Promise<Fake> {
  const fake: Fake = { checks: 0, generations: 0, version: "v1", runs: 0, holdChecks: false };
  await page.route(`${API}/poc/files`, (route) =>
    route.fulfill({
      json: {
        generated: true,
        ready: true,
        problems: [],
        files: FILES,
        version: fake.version,
        ...(solution ? { solution_files: solution } : {}),
      },
    }),
  );
  await page.route(`${API}/poc/input`, (route) =>
    route.fulfill({ json: { files: inputs ? [{ name: "invoice_001.pdf", bytes: 184320 }] : [] } }),
  );
  await page.route(`${API}/poc/check`, (route) => {
    fake.checks += 1;
    if (check === "none") return route.fulfill({ status: 503, json: { detail: "no sandbox" } });
    return route.fulfill({ json: { run_id: `check-${fake.checks}` } });
  });
  await page.route(`${API}/runs/check-*/stream`, (route) => {
    if (check === "pending" || fake.holdChecks) return; // left unanswered: the check is still going
    return route.fulfill({
      contentType: "text/event-stream",
      body: sse(
        check === "failed"
          ? [
              { log: "PROBLEM: run_poc.py cannot import gaik.software_modules.missing" },
              { done: true, phase: "failed" },
            ]
          : [{ log: "all stages load" }, { done: true, phase: "succeeded" }],
      ),
    });
  });
  await page.route(`${API}/poc`, (route) => {
    if (route.request().method() !== "POST") return route.continue();
    fake.generations += 1;
    return route.fulfill({
      contentType: "text/event-stream",
      body: sse([{ log: "✓ Kirjoitettu poc/run_poc.py" }, { done: true, status: "success" }]),
    });
  });
  await page.route(`${API}/runs`, (route) => {
    if (route.request().method() !== "POST") return route.continue();
    fake.runs += 1;
    return route.fulfill({ json: { run_id: "run-1" } });
  });
  await page.route(`${API}/runs/run-1/stream`, (route) =>
    route.fulfill({
      contentType: "text/event-stream",
      body: sse([
        { log: "Stage 1/2: 3 files" },
        { log: "Wrote output/result.json" },
        { done: true, phase: "succeeded" },
      ]),
    }),
  );
  await page.route(`${API}/runs/run-1/output`, (route) =>
    route.fulfill({
      json: {
        runId: "run-1",
        record,
        validation: { passed: true },
        files: [
          { name: "result.json", body: JSON.stringify(record, null, 2) },
          { name: "summary.csv", body: "supplier,total\nLyreco Finland Oy,412.90\n" },
        ],
        downloads: [
          { name: "result.json", size: 2048 },
          { name: "summary.csv", size: 512 },
          { name: "report.pdf", size: 48213 },
        ],
        skipped: [],
      },
    }),
  );
  return fake;
}

const checkPassed = (page: Page) => page.locator('[data-testid="poc-check"][data-phase="ok"]');

/** The session, which opens on its PoC tab. */
async function openPoc(page: Page) {
  await loginAsDev(page);
  await page.goto(`/sessions/${SESSION}`);
  await expect(page.getByRole("tab", { name: "PoC" })).toHaveAttribute("aria-selected", "true");
}

/**
 * The PoC tab of the session, once the package check has passed. With test
 * material the run starts by itself, and once it has succeeded the set-up
 * steps fold to one line: that line also says the check is behind us.
 */
async function openCheckedPoc(page: Page) {
  await openPoc(page);
  await expect(checkPassed(page).or(page.getByTestId("poc-setup-summary")).first()).toBeVisible();
}

/** Start the test run (once the page reacts to the click) and wait for its output. */
async function runTest(page: Page) {
  const run = page.getByTestId("poc-run-sandbox");
  await expect(async () => {
    if ((await page.getByTestId("poc-run-phase").count()) === 0) await run.click({ timeout: 1_000 });
    await expect(page.getByTestId("poc-run-output")).toBeVisible({ timeout: 2_000 });
  }).toPass({ timeout: 20_000 });
}

test.describe("PoC tab", () => {
  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("the package's tree has the blueprint, the diagrams and the documentation beside poc/, as the zip has them", async ({
    page,
  }) => {
    const solution = [
      "use_case.blueprint.json",
      "workflow.bpmn",
      "workflow.mmd",
      "docs/technical_specification.md",
      "docs/user_guide.md",
    ];
    // No test material: the run waits, so the package step stays in view.
    await fakePoc(page, { solution, inputs: false });
    await openCheckedPoc(page);
    const details = page.getByTestId("poc-package-details");
    await details.getByText("Paketin tiedot").click();

    // One tree: docs/ and poc/ at the root, then the files that stand beside them.
    await expect(details.getByText("Käyttöönottopaketin tiedostot (10)")).toBeVisible();
    const tree = details.getByTestId("poc-file-tree");
    await expect(tree.locator(":scope > li")).toHaveText([
      /^docs\//,
      /^poc\//,
      "use_case.blueprint.json",
      "workflow.bpmn",
      "workflow.mmd",
    ]);
    await expect(tree.locator('li[data-path="docs/"] li')).toHaveText([
      "technical_specification.md",
      "user_guide.md",
    ]);
  });

  test("an api that names nothing beside the package shows poc/ alone", async ({ page }) => {
    await fakePoc(page, { inputs: false });
    await openCheckedPoc(page);
    const details = page.getByTestId("poc-package-details");
    await details.getByText("Paketin tiedot").click();
    const tree = details.getByTestId("poc-file-tree");
    await expect(tree.locator(":scope > li")).toHaveCount(1);
    await expect(tree.locator(":scope > li")).toHaveAttribute("data-path", "poc/");
  });

  test("a checked package is one status line, with its files and controls behind Paketin tiedot", async ({
    page,
  }) => {
    // No test material: the run waits, so the package step stays in view.
    const fake = await fakePoc(page, { inputs: false });
    await openCheckedPoc(page);

    const details = page.getByTestId("poc-package-details");
    const download = page.getByRole("link", { name: "Lataa työversio" });
    await expect(page.getByTestId("poc-package-status")).toHaveAttribute("data-state", "ready");
    await expect(page.getByTestId("poc-package-status")).toHaveText("Valmis ajettavaksi");
    await expect(details).toHaveJSProperty("open", false);
    await expect(download).toBeHidden();
    await expect(page.getByRole("button", { name: "Generoi uudelleen" })).toBeHidden();
    // The primary generate button is for a session with no package only.
    await expect(page.getByRole("button", { name: "Generoi PoC-paketti" })).toHaveCount(0);

    await details.getByText("Paketin tiedot").click();
    await expect(download).toBeVisible();
    await expect(download).toHaveAttribute("href", `/api/sessions/${SESSION}/poc/download`);
    // The files as a tree under poc/, folders first: an answer that does not
    // list the deployment package (the mock store) shows its files there.
    const tree = details.getByTestId("poc-file-tree");
    await expect(tree.locator('li[data-path$="/"] > span')).toHaveText(["poc/", "schemas/"]);
    await expect(tree.locator('li[data-path]:not([data-path$="/"])')).toHaveText([
      "output_schema.py",
      "config.yaml",
      "README.md",
      "requirements.txt",
      "run_poc.py",
    ]);
    await expect(details.getByTestId("poc-work-only")).toHaveCount(0);

    // Generating again replaces the package, so it asks first.
    await page.getByRole("button", { name: "Generoi uudelleen" }).click();
    const confirm = page.getByTestId("poc-regen-confirm");
    await expect(confirm).toContainText("Uusi paketti korvaa nykyisen.");
    await expect(page.getByRole("button", { name: "Korvaa paketti" })).toBeFocused();
    await page.getByRole("button", { name: "Peruuta" }).click();
    await expect(confirm).toHaveCount(0);
    expect(fake.generations).toBe(0);

    await page.getByRole("button", { name: "Generoi uudelleen" }).click();
    await page.getByRole("button", { name: "Korvaa paketti" }).click();
    await expect(confirm).toHaveCount(0);
    await expect.poll(() => fake.generations).toBe(1);
  });

  test("the package's files are the deployment zip's, as it opens, and what only the working version carries is said", async ({
    page,
  }) => {
    await fakePoc(page, { inputs: false });
    // Registered last, so it answers first: the api's list of the deployment zip.
    await page.route(`${API}/poc/files`, (route) =>
      route.fulfill({
        json: {
          generated: true,
          ready: true,
          problems: [],
          files: [...FILES, "sample_input/invoice_001.pdf"],
          package_files: [...FILES.map((f) => `poc/${f}`), "poc/AI-GENERATED.json"],
          version: "v1",
        },
      }),
    );
    await openCheckedPoc(page);

    const details = page.getByTestId("poc-package-details");
    await details.getByText("Paketin tiedot").click();
    await expect(details.getByText("Käyttöönottopaketin tiedostot (6)")).toBeVisible();
    const tree = details.getByTestId("poc-file-tree");
    await expect(tree.locator('li[data-path]:not([data-path$="/"])')).toHaveText([
      "output_schema.py",
      "AI-GENERATED.json",
      "config.yaml",
      "README.md",
      "requirements.txt",
      "run_poc.py",
    ]);
    await expect(tree).not.toContainText("sample_input");
    await expect(details.getByTestId("poc-work-only")).toHaveText("Vain työversiossa: sample_input/");
  });

  test("a failed check keeps the step open: its findings, the working copy and Generoi uudelleen", async ({
    page,
  }) => {
    const fake = await fakePoc(page, { check: "failed" });
    await openPoc(page);

    await expect(page.getByTestId("poc-package-status")).toHaveAttribute("data-state", "failed");
    await expect(page.getByTestId("poc-check-problems").getByRole("listitem")).toHaveText([
      "run_poc.py cannot import gaik.software_modules.missing",
    ]);
    // Nothing is folded away while something is wrong with the package.
    await expect(page.getByTestId("poc-package-details")).toHaveCount(0);
    await expect(page.getByRole("link", { name: "Lataa työversio" })).toBeVisible();
    // Replacing a package that cannot run needs no second question.
    await page.getByRole("button", { name: "Generoi uudelleen" }).click();
    await expect(page.getByTestId("poc-regen-confirm")).toHaveCount(0);
    await expect.poll(() => fake.generations).toBe(1);
  });

  test("a package nobody could check is folded the same way, and is not called ready", async ({ page }) => {
    await fakePoc(page, { check: "none" });
    await openPoc(page);

    const status = page.getByTestId("poc-package-status");
    await expect(status).toHaveAttribute("data-state", "unchecked");
    await expect(status).toHaveText("Generoitu PoC-paketti");
    await expect(page.getByTestId("poc-package-details")).toHaveJSProperty("open", false);
    await expect(page.getByRole("link", { name: "Lataa työversio" })).toBeHidden();
    await expect(page.getByRole("button", { name: "Generoi PoC-paketti" })).toHaveCount(0);
  });

  test("a reload shows the stored check; only a new package version is checked again", async ({ page }) => {
    const fake = await fakePoc(page, { inputs: false });
    await openCheckedPoc(page);
    expect(fake.checks).toBe(1);

    // Once the page has gone quiet: a second check started after the stored
    // one is shown would be counted too.
    await page.reload();
    await expect(checkPassed(page)).toBeVisible();
    await page.waitForLoadState("networkidle");
    expect(fake.checks).toBe(1);

    fake.version = "v2";
    await page.reload();
    await expect(checkPassed(page)).toBeVisible();
    await expect.poll(() => fake.checks).toBe(2);
    // The new version's result is the stored one: a reload starts no third check.
    await page.reload();
    await expect(checkPassed(page)).toBeVisible();
    await page.waitForLoadState("networkidle");
    expect(fake.checks).toBe(2);
  });

  test("the test run starts by itself once the package is checked, and once only", async ({ page }) => {
    const fake = await fakePoc(page);
    await openCheckedPoc(page);

    // Nobody pressed Run: the result is there, with the material it is of.
    await expect(page.getByTestId("poc-run-output")).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId("poc-result-from")).toHaveText("Aineisto: invoice_001.pdf");
    expect(fake.runs).toBe(1);
    await expect(page.getByTestId("poc-run-sandbox")).toHaveText("Aja uudelleen");

    // The package has not changed: looking at another tab and back starts nothing.
    await page.getByRole("tab", { name: "Blueprint" }).click();
    await page.getByRole("tab", { name: "PoC" }).click();
    await expect(page.getByTestId("poc-run-output")).toBeVisible();
    expect(fake.runs).toBe(1);

    // The wizard changes the package: the new one is checked and run.
    fake.version = "v2";
    await expect.poll(() => fake.runs, { timeout: 30_000 }).toBe(2);
  });

  test("without test material the run waits for the user", async ({ page }) => {
    const fake = await fakePoc(page, { inputs: false });
    await openCheckedPoc(page);

    await expect(page.getByTestId("poc-run-sandbox")).toHaveText("Aja testi");
    await page.waitForTimeout(1_000);
    expect(fake.runs).toBe(0);
  });

  test("without test material the step says what the run waits for", async ({ page }) => {
    await fakePoc(page, { inputs: false });
    await openCheckedPoc(page);

    await expect(page.getByTestId("poc-auto-run")).toHaveText(
      "Lisää testiaineisto, niin testiajo käynnistyy itsestään.",
    );
  });

  test("a full sandbox is waited for and asked again, not shown as an error", async ({ page }) => {
    const fake = await fakePoc(page);
    // The sandbox has no room for the first request, and room for the next.
    let refused = 0;
    await page.route(`${API}/runs`, (route) => {
      if (route.request().method() !== "POST") return route.continue();
      if (refused === 0) {
        refused += 1;
        return route.fulfill({
          status: 429,
          headers: { "Retry-After": "1" },
          json: { detail: { error: "sandbox_busy", message: "3 runs are going" } },
        });
      }
      return route.fallback();
    });
    await openCheckedPoc(page);

    await expect(page.getByTestId("poc-auto-run")).toHaveText(
      "Sandbox on varattu. Testiajo käynnistyy itsestään, kun tilaa vapautuu.",
    );
    await expect(page.getByTestId("poc-run-message")).toHaveCount(0);
    await expect(page.getByTestId("poc-run-output")).toBeVisible({ timeout: 20_000 });
    expect(refused).toBe(1);
    expect(fake.runs).toBe(1);
  });

  test("a traced result shows under each value where it comes from", async ({ page }) => {
    const record = {
      delivery_note_number: "LH-2026-11873",
      lines: [
        { product_code: "NF-M8X40-A4", quantity: 2000 },
        { product_code: "NF-AL-8-A4", quantity: 4000 },
      ],
    };
    await fakePoc(page, { record });
    await page.route(`${API}/runs/run-1/output`, (route) =>
      route.fulfill({
        json: {
          runId: "run-1",
          record,
          validation: { passed: true },
          files: [
            { name: "result.json", body: JSON.stringify(record) },
            {
              name: "invoice_001_source_trace.json",
              body: JSON.stringify({
                summary: {},
                documents: [],
                sources: [
                  {
                    field: "delivery_note_number",
                    quote: "Lähetenumero: LH-2026-11873",
                    verdict: "verified",
                    record: null,
                  },
                  // gaik numbers a list's citations by row, not by result.
                  { field: "lines[0].quantity", quote: "2000 kpl", verdict: "verified", record: 0 },
                  { field: "lines[1].quantity", quote: "4 000 kpl", verdict: "check", record: 1 },
                ],
              }),
            },
          ],
          downloads: [],
          skipped: [],
        },
      }),
    );
    await openCheckedPoc(page);

    await expect(page.getByTestId("poc-run-output")).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId("poc-sources-summary")).toHaveText("Lähteet: 2/3 vahvistettu");
    const sources = page.getByTestId("poc-field-sources");
    await expect(sources).toHaveCount(2);
    await expect(sources.first()).toContainText("Lähetenumero: LH-2026-11873");
    // Both rows of the list, each with its place and the check's verdict.
    await expect(sources.nth(1).getByRole("listitem")).toHaveCount(2);
    await expect(sources.nth(1)).toContainText("[1].quantity");
    await expect(sources.nth(1).locator('[data-verdict="check"]')).toContainText(
      "Tarkista: arvoa ei löydy lainauksesta",
    );

    await page.getByTestId("poc-sources-toggle").click();
    await expect(sources).toHaveCount(0);
    await expect(page.getByTestId("poc-sources-toggle")).toHaveText("Näytä lähteet");
  });

  test("a table of several records has no sources to show or hide", async ({ page }) => {
    await fakePoc(page);
    await page.route(`${API}/runs/run-1/output`, (route) =>
      route.fulfill({
        json: {
          runId: "run-1",
          record: RECORDS,
          validation: { passed: true },
          files: [
            {
              name: "invoices_source_trace.json",
              body: JSON.stringify({
                sources: [{ field: "supplier", quote: "Lyreco Finland Oy", verdict: "verified", record: 0 }],
              }),
            },
          ],
          downloads: [],
          skipped: [],
        },
      }),
    );
    await openCheckedPoc(page);

    await expect(page.getByTestId("poc-run-table")).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId("poc-sources-toggle")).toHaveCount(0);
  });

  test("on a wide panel the set-up steps sit left of the result; with the chat open it is one column", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    // Without test material the run waits for the user, so the tab can be
    // looked at before its first run.
    await fakePoc(page, { inputs: false });
    await openCheckedPoc(page);
    // The session waits on Gate 3, so the chat is open: measure without it first.
    await setChatOpen(page, false);

    // Before the first run the result keeps its place with one line.
    const result = page.getByTestId("poc-result");
    await expect(page.getByTestId("poc-result-empty")).toHaveText("Tulos näkyy tässä testiajon jälkeen.");
    // The panel widens as the chat closes; the result takes its column then.
    await expect(result).toBeVisible();
    const inputs = (await page.getByTestId("poc-inputs").boundingBox())!;
    const wide = (await result.boundingBox())!;
    expect(wide.x).toBeGreaterThanOrEqual(inputs.x + inputs.width);
    expect(wide.width).toBeGreaterThan(inputs.width * 1.5);

    // The chat takes the width: the steps stack and the empty result goes.
    await setChatOpen(page, true);
    await expect(result).toBeHidden();

    await runTest(page);
    const stacked = (await result.boundingBox())!;
    const inputsNow = (await page.getByTestId("poc-inputs").boundingBox())!;
    expect(stacked.y).toBeGreaterThan(inputsNow.y + inputsNow.height);
  });

  test("several flat records are one table: yes/no, a percentage and a review mark", async ({ page }) => {
    await fakePoc(page);
    await openCheckedPoc(page);
    await runTest(page);

    const table = page.getByTestId("poc-run-table");
    // The review flag marks its row instead of being a column.
    await expect(table.getByRole("columnheader")).toHaveText([
      "Supplier",
      "Invoice number",
      "Total amount",
      "Paid",
      "Confidence",
    ]);
    const rows = page.getByTestId("poc-run-record");
    await expect(rows).toHaveCount(3);
    await expect(rows.nth(0).getByRole("cell")).toHaveText(["INV-2024-118", "412.90 EUR", "Kyllä", "93 %"]);
    await expect(rows.nth(1).getByRole("cell")).toHaveText(["9081-22", "1 280.00 EUR", "Ei", "71 %"]);
    await expect(rows.nth(1)).toHaveAttribute("data-flagged", "true");
    await expect(rows.nth(1).getByRole("rowheader")).toContainText("Tarkistettava");
    await expect(rows.nth(0).getByRole("rowheader")).toHaveText("Lyreco Finland Oy");
    // A grounding check that passed is one line, as in the cases view.
    await expect(page.getByTestId("poc-run-grounding")).toHaveText("Lähdetarkistus läpi");
    await expect(page.getByTestId("poc-run-grounding-flags")).toHaveCount(0);
  });

  // A meeting's minutes: a list of records with a sentence and its sources in
  // each, as a generated solution writes them.
  const MINUTES = {
    meeting_title: "Project Nimbus weekly",
    recorded: true,
    attendees: ["Aino Virtanen", "Mikael Lahti", "Sara Niemi"],
    discussion_summaries: [
      {
        agenda_item: "Pilot scope",
        summary:
          "The team agreed to run the pilot in Helsinki first, with synthetic data only, and to review the results before any other site is added.",
        evidence: ["project_nimbus_meeting.wav|00:00:00|00:01:12", "project_nimbus_agenda.pdf|2"],
      },
      {
        agenda_item: "Schedule",
        summary: "The pilot starts in week 48 and runs for four weeks; the steering group meets after the second week.",
        evidence: ["project_nimbus_meeting.wav|00:01:12|00:03:40"],
      },
    ],
    owners: [
      { name: "Aino Virtanen", role: "Lead" },
      { name: "Sara Niemi", role: "Data" },
    ],
    notes: [1, { odd: true }],
    follow_up: null,
  };

  async function openMinutes(page: Page, validation: object | null = null) {
    await fakePoc(page, { record: MINUTES });
    await page.route(`${API}/runs/run-1/output`, (route) =>
      route.fulfill({
        json: {
          runId: "run-1",
          record: MINUTES,
          validation,
          files: [{ name: "minutes.json", body: JSON.stringify(MINUTES) }],
          downloads: [],
          skipped: [],
        },
      }),
    );
    await openCheckedPoc(page);
    await runTest(page);
  }

  test("a record's list of long records is label and value pairs under the field's name, with sources as files", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await openMinutes(page);
    const record = page.getByTestId("poc-run-record");

    // The field's name is a heading above its records, not a column beside them.
    const field = record.locator('[data-field="discussion_summaries"]');
    const heading = field.locator("dt").first();
    await expect(heading).toHaveText("Discussion summaries");
    const list = field.getByTestId("poc-run-records");
    const headingBox = (await heading.boundingBox())!;
    const listBox = (await list.boundingBox())!;
    expect(headingBox.y + headingBox.height).toBeLessThanOrEqual(listBox.y);
    expect(Math.abs(headingBox.x - listBox.x)).toBeLessThan(2);

    // Each record is numbered pairs: the sentence has the width, not a third of a table.
    const first = list.getByRole("listitem").first();
    await expect(list.locator(":scope > li")).toHaveCount(2);
    await expect(first.locator("dt")).toHaveText(["Agenda item", "Summary", "Evidence"]);
    const summary = first.locator("dd").nth(1);
    await expect(summary).toContainText("The team agreed to run the pilot in Helsinki first");
    expect((await summary.boundingBox())!.height).toBeLessThan(100);
    await expect(record.locator("table")).toHaveCount(1);

    // A source reads as its file, with the file type's mark, and where in it.
    const refs = first.getByTestId("source-ref");
    await expect(refs).toHaveText(["project_nimbus_meeting.wav0:00–1:12", "project_nimbus_agenda.pdfs. 2"]);
    await expect(refs.nth(0).locator('svg[data-file-kind="audio"]')).toBeVisible();
    await expect(refs.nth(1).locator('svg[data-file-kind="pdf"]')).toBeVisible();
    await expect(record).not.toContainText("|");
    await expect(record).not.toContainText("00:00:00");

    // A list is lines, a boolean a word, nothing a dash; few short fields stay a table.
    await expect(record.locator('[data-field="attendees"]').getByRole("listitem")).toHaveText([
      "Aino Virtanen",
      "Mikael Lahti",
      "Sara Niemi",
    ]);
    await expect(record.locator('[data-field="recorded"] dd')).toHaveText("Kyllä");
    await expect(record.locator('[data-field="follow_up"] dd')).toHaveText("—");
    const owners = record.locator('[data-field="owners"]').getByTestId("poc-run-records-table");
    await expect(owners.getByRole("columnheader")).toHaveText(["Name", "Role"]);
    await expect(owners.locator("tbody tr")).toHaveCount(2);
    // A shape with no plain reading is behind its disclosure, not JSON on the page.
    const raw = record.locator('[data-field="notes"]');
    await expect(raw.getByText("Näytä raakadata")).toBeVisible();
    await expect(raw.locator("pre")).toBeHidden();

    // Nothing scrolls inside the page's own scroll.
    const boxes = await record.evaluate(
      (el) =>
        [...el.querySelectorAll("*")].filter((n) =>
          /auto|scroll/.test(getComputedStyle(n).overflowX + getComputedStyle(n).overflowY),
        ).length,
    );
    expect(boxes).toBe(0);

    // On a phone the label is above its value and nothing is cut off sideways.
    await page.setViewportSize({ width: 390, height: 844 });
    const label = (await first.locator("dt").nth(1).boundingBox())!;
    const value = (await summary.boundingBox())!;
    expect(label.y + label.height).toBeLessThanOrEqual(value.y + 1);
    expect(value.width).toBeGreaterThan(220);
    for (const ref of await refs.all()) {
      const box = (await ref.boundingBox())!;
      expect(box.x + box.width).toBeLessThanOrEqual(390);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });

  test("a failed grounding check lists the values it names, as the cases view does", async ({ page }) => {
    await openMinutes(page, {
      passed: false,
      hallucination_flags: [
        { field: "discussion_summaries.0.agenda_item", value: "Pilot scope", reason: "Not in the source." },
        { field: "attendees", value: "['Aino Virtanen', 'Mikael Lahti']", reason: "" },
        { field: "follow_up", value: "None", reason: "" },
        { field: "recorded", value: "True", reason: "" },
      ],
    });
    const grounding = page.getByTestId("poc-run-grounding");
    await expect(grounding).toContainText("Lähdetarkistus: mahdollisia keksittyjä arvoja");
    const flags = grounding.getByTestId("poc-run-grounding-flags").locator(":scope > li");
    await expect(flags).toHaveText([
      "Discussion summaries › 1 › Agenda item: Pilot scopeNot in the source.",
      "Attendees: Aino VirtanenMikael Lahti",
      "Follow up: —",
      "Recorded: Kyllä",
    ]);
    await expect(grounding).toContainText("Tarkista nämä arvot lähteestä ennen kuin käytät tulosta.");
  });

  test("a failed grounding check that names no values is one line that says what to do", async ({ page }) => {
    await openMinutes(page, { passed: false });
    const grounding = page.getByTestId("poc-run-grounding");
    await expect(grounding).toHaveText(
      "Lähdetarkistus: mahdollisia keksittyjä arvoja. Tarkista tulos lähteestä ennen kuin käytät sitä.",
    );
    await expect(grounding.locator("p")).toHaveCount(1);
    await expect(page.getByTestId("poc-run-grounding-flags")).toHaveCount(0);
  });

  test("the output files are listed once, each with its download and its text", async ({ page }) => {
    await fakePoc(page);
    await openCheckedPoc(page);
    await runTest(page);

    const files = page.getByTestId("poc-run-downloads").getByRole("listitem");
    await expect(files).toHaveCount(3);
    await expect(page.getByText("Tulostiedostot")).toHaveCount(1);

    const report = page.getByRole("link", { name: "Lataa report.pdf" });
    await expect(report).toHaveAttribute("href", `/api/sessions/${SESSION}/runs/run-1/files/report.pdf`);
    // A file the run printed as text can be read here; a PDF cannot.
    await expect(page.getByRole("button", { name: "Näytä report.pdf" })).toHaveCount(0);
    const show = page.getByRole("button", { name: "Näytä summary.csv" });
    await expect(show).toHaveAttribute("aria-expanded", "false");
    await show.click();
    await expect(files.nth(1)).toContainText("Lyreco Finland Oy,412.90");
    const hide = page.getByRole("button", { name: "Piilota summary.csv" });
    await expect(hide).toHaveAttribute("aria-expanded", "true");
    await hide.click();
    await expect(files.nth(1)).not.toContainText("Lyreco Finland Oy,412.90");
  });

  test("a run that succeeded reads as finished while the package check is still going", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await fakePoc(page, { record: RECORDS[1], check: "pending" });
    await openPoc(page);
    await expect(page.locator('[data-testid="poc-check"][data-phase="running"]')).toBeVisible();
    await runTest(page);

    // One card: what was run and that it passed, then what to do with it.
    // The set-up steps, "Checking the package…" among them, are behind it.
    const done = page.getByTestId("poc-setup-summary");
    await expect(done).toContainText("Ajo onnistui");
    await expect(done.getByTestId("poc-result-from")).toHaveText("Aineisto: invoice_001.pdf");
    await expect(page.getByTestId("poc-result-from")).toHaveCount(1);
    await expect(done.getByRole("listitem")).toHaveText([
      "Kokeile omilla tapauksilla",
      "Lataa käyttöönottopaketti",
      "Aja uudelleen",
    ]);
    await expect(page.getByTestId("poc-package-status")).toHaveCount(0);
    await expect(page.getByTestId("poc-inputs")).toHaveCount(0);
    await expect(page.getByTestId("poc-refine-hint")).toHaveCount(0);
    await expect(page.getByText("Kokeile ja ota käyttöön")).toHaveCount(0);

    await page.getByTestId("poc-setup-toggle").click();
    await expect(page.getByTestId("poc-package-status")).toContainText("Tarkistetaan pakettia…");
  });

  test("a package the wizard changed after the run is not shown as run: its check comes first", async ({ page }) => {
    const fake = await fakePoc(page, { record: RECORDS[1] });
    await openCheckedPoc(page);
    await expect(page.getByTestId("poc-setup-summary")).toContainText("Ajo onnistui", { timeout: 20_000 });

    // The wizard rewrites the package, and the new one's check has not ended.
    fake.holdChecks = true;
    fake.version = "v2";
    await expect(page.getByTestId("poc-package-status")).toContainText("Tarkistetaan pakettia…", { timeout: 30_000 });
    await expect(page.getByTestId("poc-setup-summary")).toHaveCount(0);
    await expect(page.getByTestId("poc-inputs")).toBeVisible();
    expect(fake.runs).toBe(1);
  });

  test("a single record keeps its field list", async ({ page }) => {
    await fakePoc(page, { record: RECORDS[1] });
    await openCheckedPoc(page);
    await runTest(page);

    await expect(page.getByTestId("poc-run-table")).toHaveCount(0);
    const record = page.getByTestId("poc-run-record");
    await expect(record).toHaveCount(1);
    await expect(record.locator("[data-field] dt")).toHaveText([
      "Supplier",
      "Invoice number",
      "Total amount",
      "Paid",
      "Confidence",
      "Needs review",
    ]);
    await expect(record.locator('[data-field="paid"] dd')).toHaveText("Ei");
    await expect(record.locator('[data-field="confidence"] dd')).toHaveText("71 %");
  });

  test("a list of decisions with their sources is a table, and trying the solution sits with the steps", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await fakePoc(page, {
      record: {
        title: "Pilot readiness review",
        decisions: [
          { decision_id: "D1", statement: "The pilot covers the Helsinki team.", citations: ["meeting.wav", "agenda.pdf|2"] },
          { decision_id: "D2", statement: "Synthetic data only.", citations: ["meeting.wav"] },
        ],
      },
    });
    await openCheckedPoc(page);
    await runTest(page);

    // One list inside each row used to turn the whole field back into JSON.
    const decisions = page.getByTestId("poc-run-record").locator('[data-field="decisions"]');
    await expect(decisions.locator("dt").first()).toHaveText("Decisions");
    const table = decisions.getByTestId("poc-run-records-table");
    await expect(table.getByRole("columnheader")).toHaveText(["Decision id", "Statement", "Citations"]);
    // A row's sources are lines in its cell; one that names a page reads as the file and the page.
    const sources = table.locator("tbody tr").first().getByRole("cell").last();
    await expect(sources.getByRole("listitem")).toHaveText(["meeting.wav", "agenda.pdfs. 2"]);
    await expect(decisions).not.toContainText("{");
    await expect(decisions).not.toContainText("|");
    // The fourth step is with the other three, not under the result.
    await expect(page.getByTestId("poc-open-cases")).toBeInViewport();
    // The three finished set-up steps are one line; they open on request.
    await expect(page.getByTestId("poc-setup-summary")).toContainText("Ajo onnistui");
    await expect(page.getByTestId("poc-inputs")).toHaveCount(0);
    await page.getByTestId("poc-setup-toggle").click();
    await expect(page.getByTestId("poc-inputs")).toBeVisible();
    await expect(page.getByTestId("poc-run-sandbox")).toHaveCount(1);
  });
});

/**
 * A blueprint saved after the PoC package was made: the package does not have
 * the change. The note under the saved blueprint says so only where the user
 * can act on it, and brings the control with it.
 */
test.describe("a blueprint saved after the PoC package was made", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  const saved = (page: Page) =>
    page.waitForResponse(
      (r) => /\/api\/sessions\/[^/]+\/blueprint$/.test(r.url()) && r.request().method() === "PATCH" && r.ok(),
    );
  /** Change the goal in the Blueprint form and wait for the save. */
  async function saveBlueprint(page: Page) {
    await openBlueprintEditor(page);
    const done = saved(page);
    const goal = page.getByTestId("blueprint-field-goal");
    await goal.fill("Shorter handling time");
    await goal.blur();
    await done;
    await expect(page.getByTestId("blueprint-save-status")).toHaveAttribute("data-state", "saved");
  }

  test("after Gate 2 the note has Generoi uudelleen, which opens the PoC tab at that question", async ({ page }) => {
    // No test material: no run starts, and the package step stays as it is.
    const fake = await fakePoc(page, { inputs: false });
    await openCheckedPoc(page);
    await saveBlueprint(page);

    const note = page.getByTestId("blueprint-saved-poc-note");
    await expect(note).toContainText("Blueprint päivitettiin, mutta PoC-paketti ei päivity itsestään.");
    // The note does not send the user to look for the control: it has it.
    await expect(note).not.toContainText("PoC-välilehdellä");
    await note.getByRole("button", { name: "Generoi uudelleen" }).click();

    await expect(page.getByRole("tab", { name: "PoC" })).toHaveAttribute("aria-selected", "true");
    // The same question the tab's own control asks: a new package replaces this one.
    await expect(page.getByTestId("poc-package-details")).toHaveJSProperty("open", true);
    await expect(page.getByTestId("poc-regen-confirm")).toContainText("Uusi paketti korvaa nykyisen.");
    await expect(page.getByRole("button", { name: "Korvaa paketti" })).toBeFocused();
    expect(fake.generations).toBe(0);
    await page.getByRole("button", { name: "Korvaa paketti" }).click();
    await expect.poll(() => fake.generations).toBe(1);
    await expect(page.getByTestId("poc-regen-confirm")).toHaveCount(0);
  });

  test("before Gate 2 is approved there is no note: the PoC tab is locked and nothing can be generated", async ({
    page,
  }) => {
    // A session waiting at Gate 2 that has a package (the gate was reopened
    // after one was made).
    const session = "ses_gate2_pending";
    let asked = 0;
    await page.route(`**/api/sessions/${session}/poc/files`, (route) => {
      asked += 1;
      return route.fulfill({ json: { generated: true, ready: true, problems: [], files: FILES, version: "v1" } });
    });
    await loginAsDev(page);
    await page.goto(`/sessions/${session}`);
    await expect(page.getByTestId("poc-locked")).toBeVisible();
    await saveBlueprint(page);

    // The panel has asked whether a package exists, and it does.
    await expect.poll(() => asked).toBeGreaterThan(0);
    await page.waitForLoadState("networkidle");
    await expect(page.getByTestId("blueprint-saved-poc-note")).toHaveCount(0);
    await expect(page.getByText("PoC-paketti ei päivity itsestään")).toHaveCount(0);
  });
});

test.describe("PoC tab, a run that finished with warnings", () => {
  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  // The run-output answer as wizard_api sends it: the run's phase stays
  // "succeeded", and `warnings` says what looks wrong in the record.
  const withWarnings = (page: Page) =>
    page.route(`${API}/runs/run-1/output`, (route) =>
      route.fulfill({
        json: {
          run_id: "run-1",
          warnings: [
            { code: "empty_record", message: "Record 2 has no values: every field is empty.", records: [2] },
            {
              code: "required_field_empty",
              message: "The required field total_amount is empty in record 3 and filled in others.",
              records: [3],
              field: "total_amount",
            },
          ],
          record: RECORDS,
          validation: null,
          transcript: "",
          document: "",
          files: [{ name: "result.json", body: JSON.stringify(RECORDS, null, 2) }],
        },
      }),
    );
  /** wizard_api has the run on record, so the package can be taken. */
  const runOnRecord = (page: Page) =>
    page.route(`${API}/poc/files`, (route) =>
      route.fulfill({
        json: { generated: true, ready: true, problems: [], files: FILES, version: "v1", recordedRun: "run-1" },
      }),
    );
  const SUCCEEDED = "Testiajo onnistui: kokeile ratkaisua omilla tapauksilla tai lataa paketti käyttöönottoon.";
  const TO_CHECK =
    "Testiajossa jäi tarkistettavaa: katso tulos ja kokeile sitten omilla tapauksilla tai aja uudelleen.";

  test("the warnings wizard_api found in the output are on the result, and the run is not called a success", async ({
    page,
  }) => {
    await fakePoc(page);
    await runOnRecord(page);
    await withWarnings(page);
    await openCheckedPoc(page);
    await runTest(page);

    await expect(page.getByTestId("poc-run-warnings").getByRole("listitem")).toHaveText([
      "Record 2 has no values: every field is empty.",
      "The required field total_amount is empty in record 3 and filled in others.",
    ]);
    await expect(page.getByTestId("poc-run-warnings")).toHaveAccessibleName("Ajo päättyi, tarkista tulos");
    // The records are still there to look at.
    await expect(page.getByTestId("poc-run-record")).toHaveCount(RECORDS.length);

    // The card that stands for the finished steps says the same, once, and
    // nowhere that the run succeeded. The package can be taken, after the
    // two things the result asks for first.
    const summary = page.getByTestId("poc-setup-summary");
    await expect(summary.getByRole("heading")).toHaveText("Ajo päättyi, tarkista tulos");
    await expect(page.getByText("onnistui")).toHaveCount(0);
    await expect(summary.getByRole("listitem")).toHaveText([
      "Kokeile omilla tapauksilla",
      "Aja uudelleen",
      "Lataa käyttöönottopaketti",
    ]);
    await expect(page.getByTestId("poc-deployable")).toHaveAttribute("href", `/api/sessions/${SESSION}/poc/deployable`);
  });

  test("without warnings the finished steps' card is as it was: the package before running again", async ({ page }) => {
    await fakePoc(page);
    await runOnRecord(page);
    await openCheckedPoc(page);
    await runTest(page);

    const summary = page.getByTestId("poc-setup-summary");
    await expect(summary.getByRole("heading")).toHaveText("Ajo onnistui");
    await expect(page.getByTestId("poc-run-warnings")).toHaveCount(0);
    await expect(summary.getByRole("listitem")).toHaveText([
      "Kokeile omilla tapauksilla",
      "Lataa käyttöönottopaketti",
      "Aja uudelleen",
    ]);
  });

  test("the last step does not say the run succeeded, and trying the solution is its first action", async ({
    page,
  }) => {
    // No test material: the steps stay open after the run, the last one with them.
    await fakePoc(page, { inputs: false });
    await runOnRecord(page);
    await withWarnings(page);
    await openCheckedPoc(page);
    await runTest(page);

    await expect(page.getByTestId("poc-run-phase")).toHaveText("Ajo päättyi, tarkista tulos");
    await expect(page.getByTestId("poc-use-status")).toHaveText(TO_CHECK);
    await expect(page.getByText("onnistui")).toHaveCount(0);
    await expect(page.getByTestId("poc-open-cases")).toHaveClass(/\bbtn-brand\b/);
    // Nor is the step ticked: its mark says there is something to look at.
    const mark = page.getByTestId("poc-step-use").locator("[data-mark]");
    await expect(mark).toHaveAttribute("data-mark", "attention");
    await expect(mark).toHaveClass(/\bbg-warning-bg\b/);
    await expect(mark).not.toHaveClass(/\bbg-brand\b/);
    // Warnings inform, they do not block: the package is there, as a second action.
    const deployable = page.getByTestId("poc-deployable");
    await expect(deployable).toHaveAttribute("href", `/api/sessions/${SESSION}/poc/deployable`);
    await expect(deployable).toHaveClass(/\bbtn-secondary\b/);
  });

  test("trying the solution opens in place, and the cases page leads back to the session", async ({
    page,
    context,
  }) => {
    // Both of the PoC tab's links: the last step's, and the finished run's card's.
    await fakePoc(page, { inputs: false });
    await runOnRecord(page);
    await openCheckedPoc(page);
    await runTest(page);
    const step = page.getByTestId("poc-open-cases");
    await expect(step).not.toHaveAttribute("target");
    await expect(step.locator("svg")).toHaveCount(1);
    await step.click();
    await expect(page).toHaveURL(new RegExp(`/sessions/${SESSION}/cases$`));
    expect(context.pages()).toHaveLength(1);
    await page.getByTestId("case-back").click();
    await expect(page).toHaveURL(new RegExp(`/sessions/${SESSION}\\?tab=poc$`));

    await page.unrouteAll({ behavior: "ignoreErrors" });
    await fakePoc(page);
    await runOnRecord(page);
    await openCheckedPoc(page);
    await runTest(page);
    const row = page.getByTestId("poc-setup-summary").getByTestId("poc-open-cases");
    await expect(row).not.toHaveAttribute("target");
    await expect(row.locator("svg")).toHaveCount(1);
    await row.click();
    await expect(page).toHaveURL(new RegExp(`/sessions/${SESSION}/cases$`));
    expect(context.pages()).toHaveLength(1);
    await expect(page.getByTestId("case-back")).toBeVisible();
  });

  // The finished solution's banner is above the workspace: it must not call a
  // success what the workspace under it says to check.
  const AFTER_ACTION = { timeout: 20_000 };
  async function finishSolution(page: Page) {
    await loginAsDev(page);
    await page.goto(`/sessions/${SESSION}`);
    await page.getByTestId("gate3-actions").getByRole("button", { name: "Hyväksy testiajo" }).click();
    await page.getByTestId("gate4-actions").getByRole("button", { name: "Hyväksy luovutus" }).click(AFTER_ACTION);
    await expect(page.getByTestId("solution-done")).toBeVisible(AFTER_ACTION);
    await page.goto(`/sessions/${SESSION}?tab=poc`);
  }

  test("the finished solution's banner takes the warning tone, says what to check first and puts trying ahead of the package", async ({
    page,
    request,
    baseURL,
  }) => {
    await setMockSessionStep(request, baseURL as string, SESSION, 11, "run-1");
    await fakePoc(page, { inputs: false });
    await runOnRecord(page);
    await withWarnings(page);
    await finishSolution(page);

    const done = page.getByTestId("solution-done");
    const actions = done.getByRole("link");
    // Until the workspace shows a run, the banner is as for any finished solution.
    await expect(done).toHaveAttribute("data-tone", "success");
    await expect(actions).toHaveText(["Lataa paketti", "Kokeile omilla tapauksilla"]);

    await runTest(page);
    await expect(done).toHaveAttribute("data-tone", "warning");
    await expect(done).toHaveClass(/\bbg-warning-bg\b/);
    await expect(done).not.toHaveClass(/\bbg-success-bg\b/);
    // The line about the run is the first thing under the heading, ahead of the actions.
    const line = page.getByTestId("solution-done-warnings");
    await expect(line).toHaveText("Viimeisessä testiajossa jäi tarkistettavaa.");
    const lineBox = (await line.boundingBox())!;
    const firstAction = (await actions.first().boundingBox())!;
    expect(lineBox.y + lineBox.height).toBeLessThanOrEqual(firstAction.y);
    await expect(actions).toHaveText(["Kokeile omilla tapauksilla", "Lataa paketti"]);
    await expect(page.getByTestId("solution-done-try")).toHaveClass(/\bbtn-brand\b/);
    await expect(page.getByTestId("solution-done-download")).toHaveClass(/\bbtn-secondary\b/);
    await expect(page.getByTestId("solution-done-download")).toHaveAttribute(
      "href",
      `/api/sessions/${SESSION}/poc/deployable`,
    );
    // The banner's two actions are on the page once: the PoC tab under it repeats neither.
    await expect(page.getByTestId("poc-step-use")).toBeVisible();
    await expect(page.getByTestId("poc-open-cases")).toHaveCount(0);
    await expect(page.getByTestId("poc-deployable")).toHaveCount(0);
    await expect(page.locator(`a[href="/sessions/${SESSION}/cases"]`)).toHaveCount(1);
    await expect(page.locator(`a[href="/api/sessions/${SESSION}/poc/deployable"]`)).toHaveCount(1);
  });

  test("without warnings the finished solution's banner stays as it was after a run", async ({
    page,
    request,
    baseURL,
  }) => {
    await setMockSessionStep(request, baseURL as string, SESSION, 11, "run-1");
    await fakePoc(page, { inputs: false });
    await runOnRecord(page);
    await finishSolution(page);
    await runTest(page);

    const done = page.getByTestId("solution-done");
    await expect(done).toHaveAttribute("data-tone", "success");
    await expect(done).toHaveClass(/\bbg-success-bg\b/);
    await expect(page.getByTestId("solution-done-warnings")).toHaveCount(0);
    await expect(done.getByRole("link")).toHaveText(["Lataa paketti", "Kokeile omilla tapauksilla"]);
    await expect(page.getByTestId("solution-done-download")).toHaveClass(/\bbtn-brand\b/);
    await expect(page.getByTestId("solution-done-try")).toHaveClass(/\bbtn-secondary\b/);
    // Each of the two is on the page once, in the banner; the last step still says where the run stands.
    await expect(page.getByTestId("poc-use-status")).toHaveText(SUCCEEDED);
    await expect(page.getByTestId("poc-open-cases")).toHaveCount(0);
    await expect(page.getByTestId("poc-deployable")).toHaveCount(0);
    await expect(page.locator(`a[href="/sessions/${SESSION}/cases"]`)).toHaveCount(1);
    await expect(page.locator(`a[href="/api/sessions/${SESSION}/poc/deployable"]`)).toHaveCount(1);
  });

  test("without warnings the last step says the run succeeded, with no action set above the other", async ({
    page,
  }) => {
    await fakePoc(page, { inputs: false });
    await runOnRecord(page);
    await openCheckedPoc(page);
    await runTest(page);

    await expect(page.getByTestId("poc-run-phase")).toHaveText("Ajo onnistui");
    await expect(page.getByTestId("poc-use-status")).toHaveText(SUCCEEDED);
    await expect(page.getByTestId("poc-open-cases")).toHaveClass(/\bbtn-secondary\b/);
    await expect(page.getByTestId("poc-deployable")).toHaveClass(/\bbtn-secondary\b/);
    await expect(page.getByTestId("poc-step-use").locator("[data-mark]")).toHaveAttribute("data-mark", "done");
  });
});

test.describe("PoC tab on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("the result table scrolls inside its card, with the first column kept in place", async ({ page }) => {
    await fakePoc(page);
    await openCheckedPoc(page);
    await runTest(page);

    const table = page.getByTestId("poc-run-table");
    await table.scrollIntoViewIfNeeded();
    const size = await table.evaluate((el) => ({ sw: el.scrollWidth, cw: el.clientWidth }));
    expect(size.sw).toBeGreaterThan(size.cw);

    const first = page.getByTestId("poc-run-record").first().getByRole("rowheader");
    const before = (await first.boundingBox())!;
    await table.evaluate((el) => {
      el.scrollLeft = el.scrollWidth;
    });
    const after = (await first.boundingBox())!;
    expect(Math.abs(after.x - before.x)).toBeLessThan(1);
    await expect(page.getByTestId("poc-run-record").first().getByRole("cell").last()).toBeInViewport();

    // Nothing pushes the page itself sideways.
    const doc = await page.evaluate(() => ({
      sw: document.documentElement.scrollWidth,
      cw: document.documentElement.clientWidth,
    }));
    expect(doc.sw).toBeLessThanOrEqual(doc.cw);
  });
});
