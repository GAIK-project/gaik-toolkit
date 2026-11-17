import { readFile } from "node:fs/promises";
import { test, expect, type Page, type Request } from "@playwright/test";
import { strFromU8, strToU8, unzipSync, zipSync } from "fflate";
import { loginAsDev } from "./helpers/auth";
import { setMockSessionStep } from "./helpers/dev-step";
import { resetMockSessions } from "./helpers/mock";

/**
 * The PoC tab's file editor and the .env form beside the deployable package.
 *
 * A file in the package's tree opens in an editor: text files of the package
 * are edited and saved, the AI marker is shown read-only, and a save over a
 * file that changed meanwhile is refused. The keys for the package's .env are
 * typed where the package is taken and written into the downloaded zip in
 * the browser: no request carries them.
 *
 * The mock store has no package on disk: the package's listing and the zip
 * are answered here, and the files themselves by the mock store
 * (lib/mock-sessions.ts), through the app's own /poc/file route.
 */

const SESSION = "ses_laskut";
const API = `**/api/sessions/${SESSION}`;
const FILE_URL = `/api/sessions/${SESSION}/poc/file`;

const FILES = [
  ".env.example",
  "README.md",
  "run_poc.py",
  "requirements.txt",
  "config.yaml",
  "schemas/output_schema.py",
];
const PACKAGE_FILES = [
  ...FILES.map((f) => `poc/${f}`),
  "poc/AI-GENERATED.json",
  "use_case.blueprint.json",
  "AI-GENERATED.json",
];

const PACKAGE_ZIP = zipSync({
  "poc/run_poc.py": strToU8("print('ok')\n"),
  "poc/.env.example": strToU8("AZURE_API_KEY=\n"),
  "poc/AI-GENERATED.json": strToU8('{"ai_generated": true}\n'),
  "use_case.blueprint.json": strToU8("{}\n"),
});

/** The shape of the scaffolder's .env.example: a section per provider, everything commented out. */
const GENERATED_ENV_EXAMPLE = [
  "# Environment variables for Invoice extraction",
  "# Copy to .env and enable only providers used by config.yaml stages.",
  "",
  "# --- Azure OpenAI (model is your deployment name) ---",
  "# AZURE_API_KEY=",
  "# AZURE_ENDPOINT=https://your-resource.openai.azure.com/",
  "# AZURE_API_VERSION=2025-03-01-preview",
  "",
  "# --- OpenAI ---",
  "# OPENAI_API_KEY=",
  "# OPENAI_MODEL=gpt-6-luna",
  "",
  "# --- Native Google Gemini Developer API ---",
  "# GOOGLE_API_KEY=",
  "# GEMINI_API_KEY is also accepted.",
  "# GOOGLE_MODEL=gemini-2.5-flash",
  "",
  "# --- External services (outside GAIK) ---",
  "# Web search for the enrichment step.",
  "TAVILY_API_KEY=",
  "",
  "# A config.yaml address not on this machine needs its host here.",
  "# GAIK_ALLOWED_ENDPOINT_HOSTS=",
  "",
].join("\n");

const sse = (events: object[]) => events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join("");

/** A checked package with no test material, so the steps stay open; `recorded` adds a passed test run. */
async function fakePackage(
  page: Page,
  {
    recorded = false,
    tested,
    digest,
  }: {
    recorded?: boolean;
    /** wizard_api's digests: of the package the recorded run tested, and of the package as it is now. */
    tested?: string;
    digest?: string;
  } = {},
) {
  await page.route(`${API}/poc/files`, (route) =>
    route.fulfill({
      json: {
        generated: true,
        ready: true,
        problems: [],
        files: FILES,
        package_files: PACKAGE_FILES,
        version: "v1",
        ...(recorded ? { recordedRun: "run-1" } : {}),
        ...(tested ? { testedPackage: tested } : {}),
        ...(digest ? { package_digest: digest } : {}),
      },
    }),
  );
  await page.route(`${API}/poc/input`, (route) => route.fulfill({ json: { files: [] } }));
  await page.route(`${API}/poc/check`, (route) => route.fulfill({ json: { run_id: "check-1" } }));
  await page.route(`${API}/runs/check-1/stream`, (route) =>
    route.fulfill({
      contentType: "text/event-stream",
      body: sse([{ log: "all stages load" }, { done: true, phase: "succeeded" }]),
    }),
  );
  await page.route(`${API}/poc/deployable`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/zip",
      headers: { "Content-Disposition": `attachment; filename="poc-${SESSION}-deployable.zip"` },
      body: Buffer.from(PACKAGE_ZIP),
    }),
  );
}

async function openPoc(page: Page) {
  await loginAsDev(page);
  await page.goto(`/sessions/${SESSION}`);
  await expect(page.getByRole("tab", { name: "PoC" })).toHaveAttribute("aria-selected", "true");
  await expect(page.locator('[data-testid="poc-check"][data-phase="ok"]')).toBeVisible();
}

/** The package's tree, behind "Paketin tiedot". */
async function openTree(page: Page) {
  const details = page.getByTestId("poc-package-details");
  if (!(await details.evaluate((el) => (el as HTMLDetailsElement).open))) {
    await details.getByText("Paketin tiedot").click();
  }
  return details.getByTestId("poc-file-tree");
}

async function openFile(page: Page, path: string) {
  const tree = await openTree(page);
  await tree.locator(`li[data-path="poc/${path}"] button`).click();
  const editor = page.getByTestId("poc-file-editor");
  await expect(editor).toBeVisible();
  return editor;
}

/** Type at the end of the document, as a user would. */
async function typeAtEnd(page: Page, text: string) {
  await page.getByTestId("poc-file-editor").locator(".cm-content").click();
  await page.keyboard.press("ControlOrMeta+End");
  await page.keyboard.type(text);
}

test.describe("PoC file editor", () => {
  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("a file of the package opens highlighted, is edited and saved, and is the saved one when opened again", async ({
    page,
  }) => {
    await fakePackage(page);
    await openPoc(page);

    const editor = await openFile(page, "run_poc.py");
    await expect(editor.getByRole("heading")).toHaveText("poc/run_poc.py");
    const content = editor.locator(".cm-content");
    await expect(content).toContainText("def main() -> None:");
    await expect(content).toHaveAttribute("aria-label", "Tiedoston run_poc.py sisältö");
    // Highlighted: the language arrives in a chunk of its own and colours the keywords.
    await expect
      .poll(() => content.locator("span").filter({ hasText: /^def$/ }).first().evaluate((el) => getComputedStyle(el).color))
      .not.toBe(await content.evaluate((el) => getComputedStyle(el).color));
    // What a save sets off is said before it: this file is one the test run is tied to.
    await expect(editor.getByTestId("poc-file-note")).toHaveText(
      "Tallennus muuttaa pakettia: se tarkistetaan uudelleen, eikä aiempi testiajo enää päde.",
    );
    const save = editor.getByTestId("poc-file-save");
    await expect(save).toBeDisabled();

    await typeAtEnd(page, "# muokattu käsin");
    await expect(editor).toHaveAttribute("data-dirty", "true");
    await expect(save).toBeEnabled();
    const listed = page.waitForRequest((r) => r.url().endsWith("/poc/files"));
    await save.click();

    await expect(editor.getByTestId("poc-file-status")).toHaveText("Tallennettu");
    await expect(save).toBeDisabled();
    // The package is read again, as after a change by the wizard.
    await listed;

    await editor.getByTestId("poc-file-close").click();
    await expect(editor).toBeHidden();
    const again = await openFile(page, "run_poc.py");
    await expect(again.locator(".cm-content")).toContainText("# muokattu käsin");
  });

  test("Ctrl+S saves, and discarding puts the saved text back", async ({ page }) => {
    await fakePackage(page);
    await openPoc(page);
    const editor = await openFile(page, "README.md");
    // Documentation is not what a test run is tied to: no line about one.
    await expect(editor.getByTestId("poc-file-note")).toHaveCount(0);

    await typeAtEnd(page, "Lisätty rivi.");
    await editor.getByTestId("poc-file-discard").click();
    await expect(editor.locator(".cm-content")).not.toContainText("Lisätty rivi.");
    await expect(editor).not.toHaveAttribute("data-dirty", "true");

    await typeAtEnd(page, "Toinen rivi.");
    await page.keyboard.press("ControlOrMeta+s");
    await expect(editor.getByTestId("poc-file-status")).toHaveText("Tallennettu");
    const saved = await (await page.request.get(`${FILE_URL}?path=README.md`)).json();
    expect(saved.content).toContain("Toinen rivi.");
  });

  test("closing with unsaved changes asks first", async ({ page }) => {
    await fakePackage(page);
    await openPoc(page);
    const editor = await openFile(page, "config.yaml");
    await typeAtEnd(page, "# kesken");

    // Esc, and the close button: both ask, and the text stays.
    await page.keyboard.press("Escape");
    const question = editor.getByTestId("poc-file-unsaved");
    await expect(question).toContainText("Tallentamattomat muutokset häviävät");
    await question.getByRole("button", { name: "Jatka muokkausta" }).click();
    await expect(question).toBeHidden();
    await expect(editor.locator(".cm-content")).toContainText("# kesken");

    await editor.getByTestId("poc-file-close").click();
    await editor.getByTestId("poc-file-discard-close").click();
    await expect(editor).toBeHidden();

    const again = await openFile(page, "config.yaml");
    await expect(again.locator(".cm-content")).not.toContainText("# kesken");
    // Nothing to lose: it closes at once.
    await page.keyboard.press("Escape");
    await expect(again).toBeHidden();
  });

  test("a save over a file that changed since it was opened is refused, and the new version can be opened", async ({
    page,
  }) => {
    await fakePackage(page);
    await openPoc(page);
    const editor = await openFile(page, "requirements.txt");
    await expect(editor.locator(".cm-content")).toContainText("python-dotenv");

    // The file changes behind the editor, as when the wizard rewrites it.
    const read = await (await page.request.get(`${FILE_URL}?path=requirements.txt`)).json();
    const other = await page.request.put(`${FILE_URL}?path=requirements.txt`, {
      data: { content: "gaik[extract]\ntavily-python\n", base_digest: read.digest },
    });
    expect(other.ok()).toBe(true);

    await typeAtEnd(page, "requests");
    await editor.getByTestId("poc-file-save").click();

    const conflict = editor.getByTestId("poc-file-conflict");
    await expect(conflict).toContainText("Tiedosto on muuttunut sen jälkeen, kun avasit sen");
    // The user's text is still in the editor, and the file is the other version.
    await expect(editor.locator(".cm-content")).toContainText("requests");
    const stored = await (await page.request.get(`${FILE_URL}?path=requirements.txt`)).json();
    expect(stored.content).toBe("gaik[extract]\ntavily-python\n");

    await conflict.getByTestId("poc-file-open-new").click();
    await expect(editor.locator(".cm-content")).toContainText("tavily-python");
    await expect(editor.locator(".cm-content")).not.toContainText("requests");
    await expect(conflict).toBeHidden();
  });

  test("the editor is a modal dialog: the page behind is dimmed and out of reach, and focus stays inside", async ({
    page,
  }) => {
    await fakePackage(page);
    await openPoc(page);
    const editor = await openFile(page, "AI-GENERATED.json");
    await expect(editor.locator(".cm-content")).toBeVisible();

    const state = await editor.evaluate((el) => ({
      modal: el.matches(":modal"),
      inBody: el.parentElement === document.body,
      backdrop: getComputedStyle(el, "::backdrop").backgroundColor,
      focusInside: el.contains(document.activeElement),
    }));
    expect(state.modal).toBe(true);
    expect(state.inBody).toBe(true);
    expect(state.focusInside).toBe(true);
    // Dimmed: a colour with some of the page showing through, not none at all.
    expect(state.backdrop).toMatch(/\/ 0\.4\)$/);

    // The page's own controls cannot be pressed through it.
    const approve = page.getByTestId("gate3-actions").getByRole("button").first();
    await expect(approve).toBeVisible();
    await expect(approve.click({ timeout: 1_000 })).rejects.toThrow();
    await expect(editor).toBeVisible();

    // Tab goes round inside the dialog, never out to the page.
    for (let i = 0; i < 8; i++) {
      await page.keyboard.press("Tab");
      const where = await page.evaluate(() => {
        const dialog = document.querySelector('[data-testid="poc-file-editor"]');
        const active = document.activeElement;
        return active === document.body || Boolean(dialog?.contains(active));
      });
      expect(where).toBe(true);
    }
    await page.keyboard.press("Escape");
    await expect(editor).toBeHidden();
    // Focus goes back to the file that was opened.
    await expect(page.locator('li[data-path="poc/AI-GENERATED.json"] button')).toBeFocused();
  });

  test("code the api keeps read-only (the runs use the shared key) is shown with the reason and no save", async ({
    page,
  }) => {
    await fakePackage(page);
    // wizard_api's answer while the test runs use the project's shared runner key.
    await page.route(
      (url) => url.pathname.endsWith("/poc/file") && url.searchParams.get("path") === "run_poc.py",
      (route) =>
        route.fulfill({
          json: {
            path: "run_poc.py",
            content: "print('ok')\n",
            digest: "d1",
            bytes: 12,
            editable: false,
            read_only_reason: "code_edit_needs_own_runner_key",
            affects_package: true,
          },
        }),
    );
    await openPoc(page);

    const editor = await openFile(page, "run_poc.py");

    await expect(editor.getByTestId("poc-file-note")).toHaveText(
      "Vain luku: koodia ja config.yaml-tiedostoa voi muokata täällä, kun testiajot käyttävät omaa avaintaan.",
    );
    await expect(editor.getByTestId("poc-file-save")).toHaveCount(0);
    await expect(editor.locator(".cm-content")).toHaveAttribute("contenteditable", "false");
  });

  test("the AI marker is shown read-only, and what lies beside poc/ is not opened", async ({ page }) => {
    await fakePackage(page);
    await openPoc(page);
    const tree = await openTree(page);
    // The blueprint and the root marker are listed, not buttons.
    await expect(tree.locator('li[data-path="use_case.blueprint.json"] button')).toHaveCount(0);
    await expect(tree.locator('li[data-path="AI-GENERATED.json"] button')).toHaveCount(0);

    const editor = await openFile(page, "AI-GENERATED.json");
    await expect(editor.getByTestId("poc-file-note")).toHaveText("Vain luku: tätä tiedostoa ei muokata käsin.");
    await expect(editor.locator(".cm-content")).toContainText('"ai_generated": true');
    await expect(editor.locator(".cm-content")).toHaveAttribute("contenteditable", "false");
    await expect(editor.getByTestId("poc-file-save")).toHaveCount(0);
  });

  test("an environment file with keys is neither read nor saved, and a path out of the package is refused", async ({
    page,
  }) => {
    await loginAsDev(page);
    for (const path of [".env", ".env.local", "config/.env"]) {
      const read = await page.request.get(`${FILE_URL}?path=${encodeURIComponent(path)}`);
      expect(read.status()).toBe(422);
      expect((await read.json()).detail.error).toBe("secrets_not_stored");
      const saved = await page.request.put(`${FILE_URL}?path=${encodeURIComponent(path)}`, {
        data: { content: "NAME=value\n", base_digest: "d" },
      });
      expect(saved.status()).toBe(422);
      expect((await saved.json()).detail.error).toBe("secrets_not_stored");
    }
    const outside = await page.request.get(`${FILE_URL}?path=${encodeURIComponent("../use_case.blueprint.json")}`);
    expect(outside.status()).toBe(422);
    expect((await outside.json()).detail.error).toBe("invalid_path");
    const marker = await page.request.put(`${FILE_URL}?path=AI-GENERATED.json`, {
      data: { content: "{}", base_digest: "d" },
    });
    expect(marker.status()).toBe(403);
  });
});

test.describe("The .env form beside the deployable package", () => {
  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  // Not a key: a value no scanner takes for one, and easy to search requests for.
  const TYPED = "typed-in-the-browser-only";

  test("the variables of .env.example are asked for, and the download carries them in poc/.env without sending them", async ({
    page,
  }) => {
    await fakePackage(page, { recorded: true });
    const sent: Request[] = [];
    page.on("request", (request) => sent.push(request));
    await openPoc(page);

    const form = page.getByTestId("poc-env-form");
    await expect(page.getByTestId("poc-env").locator("summary")).toHaveText("Ympäristömuuttujat (.env)");
    await expect(form.getByTestId("poc-env-note")).toContainText("Avaimet pysyvät omalla koneellasi");
    // From the package's .env.example, with the comment above each as its help.
    await expect(form.locator("label")).toHaveText([
      /^AZURE_API_KEY.*Azure OpenAI: the model the PoC calls\.$/,
      /^AZURE_ENDPOINT$/,
      /^TAVILY_API_KEY.*valinnainen · Web search \(optional\)\.$/,
    ]);
    const key = form.locator('[data-testid="poc-env-value"][data-name="AZURE_API_KEY"]');
    await expect(key).toHaveAttribute("type", "password");
    await expect(key).toHaveAttribute("autocomplete", "off");
    await expect(key).not.toHaveAttribute("name");

    await key.fill(TYPED);
    await form.getByTestId("poc-env-toggle").first().click();
    await expect(key).toHaveAttribute("type", "text");
    await form.getByTestId("poc-env-toggle").first().click();
    await expect(key).toHaveAttribute("type", "password");
    // A key the example does not list yet.
    await form.getByTestId("poc-env-add").click();
    await form.getByTestId("poc-env-extra-name").fill("google cse id");
    await expect(form.getByTestId("poc-env-extra-name")).toHaveValue("GOOGLE_CSE_ID");
    await form.locator('[data-testid="poc-env-value"][data-name="extra-0"]').fill("second value");

    const download = page.waitForEvent("download");
    await page.getByTestId("poc-deployable").click();
    const saved = await download;
    expect(saved.suggestedFilename()).toBe(`poc-${SESSION}-deployable.zip`);
    // Made in the page, not followed to the server.
    expect(saved.url()).toMatch(/^blob:/);
    const zip = unzipSync(new Uint8Array(await readFile(await saved.path())));

    // The package as the server gave it, and the .env made here.
    expect(Object.keys(zip).sort()).toEqual([...Object.keys(unzipSync(PACKAGE_ZIP)), "poc/.env"].sort());
    expect(strFromU8(zip["poc/run_poc.py"])).toBe("print('ok')\n");
    expect(strFromU8(zip["poc/.env"]).split("\n")).toEqual([
      "# Azure OpenAI: the model the PoC calls.",
      `AZURE_API_KEY=${TYPED}`,
      "AZURE_ENDPOINT=",
      "",
      "# Web search (optional).",
      "# TAVILY_API_KEY=",
      "GOOGLE_CSE_ID='second value'",
      "",
    ]);

    // No request carried a value: not in a body, not in an address.
    for (const request of sent) {
      expect(request.url()).not.toContain(TYPED);
      expect(request.postData() ?? "").not.toContain(TYPED);
      expect(request.postData() ?? "").not.toContain("second value");
    }
    // Nor is it kept in the browser's storage.
    const stored = await page.evaluate(() => JSON.stringify([{ ...localStorage }, { ...sessionStorage }]));
    expect(stored).not.toContain(TYPED);

    // Leaving the tab forgets what was typed.
    await page.getByRole("tab", { name: "Blueprint" }).click();
    await page.getByRole("tab", { name: "PoC" }).click();
    await expect(page.locator('[data-testid="poc-env-value"][data-name="AZURE_API_KEY"]')).toHaveValue("");
    await expect(page.getByTestId("poc-env-extra-name")).toHaveCount(0);
  });

  test("a generated .env.example shows the provider the package uses, marks what is needed and folds the rest", async ({
    page,
  }) => {
    await fakePackage(page, { recorded: true });
    await loginAsDev(page);
    // The scaffolder's .env.example in place of the mock store's short one.
    const read = await (await page.request.get(`${FILE_URL}?path=.env.example`)).json();
    const put = await page.request.put(`${FILE_URL}?path=.env.example`, {
      data: { content: GENERATED_ENV_EXAMPLE, base_digest: read.digest },
    });
    expect(put.ok()).toBe(true);
    await page.goto(`/sessions/${SESSION}`);
    await expect(page.locator('[data-testid="poc-check"][data-phase="ok"]')).toBeVisible();

    const form = page.getByTestId("poc-env-form");
    // The mock package's config.yaml names azure: its section, then the external services.
    const shown = form.locator(':scope > [data-testid="poc-env-section"]');
    await expect(shown.locator("h4")).toHaveText([
      "Azure OpenAI (model is your deployment name)",
      "External services (outside GAIK)",
    ]);
    await expect(shown.first().locator("label")).toHaveText([
      /^AZURE_API_KEY\s*tarvitaan$/,
      /^AZURE_ENDPOINT\s*tarvitaan$/,
      /^AZURE_API_VERSION$/,
    ]);
    await expect(shown.last().locator("label")).toHaveText([/^TAVILY_API_KEY\s*tarvitaan · Web search/]);
    // No heading of the file is anyone's help, and nothing here is "optional".
    await expect(form).not.toContainText("---");
    await expect(form.getByText("valinnainen")).toHaveCount(0);

    const rest = form.getByTestId("poc-env-rest");
    await expect(rest).toHaveJSProperty("open", false);
    await expect(rest.locator("summary")).toHaveText("Muut palveluntarjoajat ja asetukset (5)");
    await expect(rest.locator("label").first()).toBeHidden();
    await rest.locator("summary").click();
    await expect(rest.locator("h4")).toHaveText(["OpenAI", "Native Google Gemini Developer API"]);
    await expect(rest.locator("label")).toHaveCount(5);

    // A value typed behind the disclosure is written like any other.
    await form.locator('[data-testid="poc-env-value"][data-name="AZURE_API_KEY"]').fill(TYPED);
    await rest.locator('[data-testid="poc-env-value"][data-name="GOOGLE_API_KEY"]').fill("second-typed");
    const download = page.waitForEvent("download");
    await page.getByTestId("poc-deployable").click();
    const zip = unzipSync(new Uint8Array(await readFile(await (await download).path())));
    const env = strFromU8(zip["poc/.env"]).split("\n");
    expect(env).toContain(`AZURE_API_KEY=${TYPED}`);
    expect(env).toContain("GOOGLE_API_KEY=second-typed");
    expect(env).toContain("# AZURE_ENDPOINT=https://your-resource.openai.azure.com/");
    expect(env).toContain("# --- OpenAI ---");
  });

  test("with every field empty the download is the server's package as it is", async ({ page }) => {
    await fakePackage(page, { recorded: true });
    await openPoc(page);
    await expect(page.getByTestId("poc-env-form")).toBeVisible();

    const link = page.getByTestId("poc-deployable");
    await expect(link).toHaveAttribute("href", `/api/sessions/${SESSION}/poc/deployable`);
    const fetched: string[] = [];
    page.on("request", (r) => {
      if (r.url().endsWith("/poc/deployable")) fetched.push(r.resourceType());
    });
    const download = page.waitForEvent("download");
    await link.click();
    const saved = await download;

    // The link itself is followed: the file comes from the server's address,
    // not from a zip put together in the page, and nothing fetched it there.
    // (A followed link is the browser's own request, which the answer faked
    // above does not reach: the mock store has no package to send.)
    expect(new URL(saved.url()).pathname).toBe(`/api/sessions/${SESSION}/poc/deployable`);
    expect(fetched).not.toContain("fetch");
  });

  test("a variable added to .env.example in the editor appears in the form", async ({ page }) => {
    await fakePackage(page, { recorded: true });
    await openPoc(page);
    const form = page.getByTestId("poc-env-form");
    await expect(form.locator("label")).toHaveCount(3);

    const editor = await openFile(page, ".env.example");
    await typeAtEnd(page, "SERPER_API_KEY=");
    await editor.getByTestId("poc-file-save").click();
    await expect(editor.getByTestId("poc-file-status")).toHaveText("Tallennettu");
    await editor.getByTestId("poc-file-close").click();

    await expect(form.locator("label")).toHaveCount(4);
    await expect(form.locator("label").last()).toHaveText("SERPER_API_KEY");
  });

  test("a key's value typed into .env.example is refused before it leaves the browser", async ({ page }) => {
    await fakePackage(page, { recorded: true });
    await openPoc(page);
    const puts: string[] = [];
    page.on("request", (r) => {
      if (r.method() === "PUT" && r.url().includes("/poc/file")) puts.push(r.url());
    });

    const editor = await openFile(page, ".env.example");
    await typeAtEnd(page, "SERPER_API_KEY=typed-by-mistake");
    await editor.getByTestId("poc-file-save").click();

    await expect(editor.getByTestId("poc-file-save-error")).toHaveText(
      "Avainten arvoja ei tallenneta palvelimelle: jätä SERPER_API_KEY tyhjäksi .env.example-tiedostossa ja anna arvo, kun lataat käyttöönottopaketin. Muutoksiasi ei tallennettu.",
    );
    await expect(editor).toHaveAttribute("data-dirty", "true");
    expect(puts).toEqual([]);
    const kept = await (await page.request.get(`${FILE_URL}?path=.env.example`)).json();
    expect(kept.content).not.toContain("typed-by-mistake");
  });

  test("the finished solution's banner download carries what is typed in the form, and is the only download", async ({
    page,
    request,
    baseURL,
  }) => {
    await setMockSessionStep(request, baseURL as string, SESSION, 11, "run-1");
    await fakePackage(page, { recorded: true });
    await loginAsDev(page);
    await page.goto(`/sessions/${SESSION}`);
    await page.getByTestId("gate3-actions").getByRole("button", { name: "Hyväksy testiajo" }).click();
    await page
      .getByTestId("gate4-actions")
      .getByRole("button", { name: "Hyväksy luovutus" })
      .click({ timeout: 20_000 });
    await expect(page.getByTestId("solution-done")).toBeVisible({ timeout: 20_000 });
    await page.goto(`/sessions/${SESSION}?tab=poc`);

    // One download on the page, the banner's: the tab does not offer a second.
    const form = page.getByTestId("poc-env-form");
    await expect(form).toBeVisible();
    const banner = page.getByTestId("solution-done-download");
    await expect(page.locator(`a[href="/api/sessions/${SESSION}/poc/deployable"]`)).toHaveCount(1);
    await expect(form.getByRole("button", { name: /Lataa/ })).toHaveCount(0);

    // With a value typed, that one download is made in the page and has the .env.
    await form.locator('[data-testid="poc-env-value"][data-name="AZURE_API_KEY"]').fill(TYPED);
    const download = page.waitForEvent("download");
    await banner.click();
    const saved = await download;
    expect(saved.url()).toMatch(/^blob:/);
    const zip = unzipSync(new Uint8Array(await readFile(await saved.path())));
    expect(strFromU8(zip["poc/.env"])).toContain(`AZURE_API_KEY=${TYPED}`);
    expect(strFromU8(zip["poc/run_poc.py"])).toBe("print('ok')\n");

    // With the field emptied again, the banner's link is followed as it always was.
    await form.locator('[data-testid="poc-env-value"][data-name="AZURE_API_KEY"]').fill("");
    const plain = page.waitForEvent("download");
    await banner.click();
    expect(new URL((await plain).url()).pathname).toBe(`/api/sessions/${SESSION}/poc/deployable`);
  });

  test("a package changed after the run that passed is not offered for download: a new test run is asked for", async ({
    page,
  }) => {
    await fakePackage(page, { recorded: true, tested: "digest-before", digest: "digest-after" });
    await openPoc(page);

    const deployable = page.getByTestId("poc-deployable");
    await expect(deployable).toBeDisabled();
    await expect(deployable).toHaveAttribute("title", /Pakettia on muutettu onnistuneen testiajon jälkeen/);
    await expect(page.getByTestId("poc-use-status")).toHaveText(
      "Pakettia on muutettu onnistuneen testiajon jälkeen. Aja testi uudelleen, niin käyttöönottopaketin voi ladata.",
    );
    await expect(page.getByTestId("poc-step-use").locator("[data-mark]")).toHaveAttribute("data-mark", "number");
    await expect(page.getByTestId("poc-env")).toHaveCount(0);
    await expect(page.locator(`a[href="/api/sessions/${SESSION}/poc/deployable"]`)).toHaveCount(0);
  });

  test("a run that tested the package as it is keeps the download open", async ({ page }) => {
    await fakePackage(page, { recorded: true, tested: "digest-same", digest: "digest-same" });
    await openPoc(page);
    await expect(page.getByTestId("poc-deployable")).toHaveAttribute(
      "href",
      `/api/sessions/${SESSION}/poc/deployable`,
    );
    await expect(page.getByTestId("poc-env-form")).toBeVisible();
  });

  test("the form is not offered before a test run has succeeded", async ({ page }) => {
    await fakePackage(page);
    await openPoc(page);
    await expect(page.getByTestId("poc-deployable")).toBeDisabled();
    await expect(page.getByTestId("poc-env")).toHaveCount(0);
  });
});
