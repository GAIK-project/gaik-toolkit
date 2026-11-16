import { test, expect, type Page } from "@playwright/test";
import { loginAsDev } from "./helpers/auth";
import { resetMockSessions } from "./helpers/mock";

/**
 * The cases view: the generated solution tried on own material, with a second
 * role deciding on the result. Three things a customer review found missing
 * (12 Nov 2026): a case still waiting for its input could not be removed, the
 * decision buttons did not say what each leads to, and a returned case offered
 * no way to hand the correction to the wizard.
 *
 * The mock store has no cases (they live in wizard_api), so the cases API is
 * answered here, with the state a test needs. ses_laskut is a session the mock
 * store holds; only its page shell comes from there.
 */

const SESSION = "ses_laskut";
const CASES = `/api/sessions/${SESSION}/cases`;

const MODEL = {
  title: "Vikailmoitukset",
  spec: {
    schema_name: "Ticket",
    fields: ["reporter", "location", "urgency"],
    required_fields: ["location", "urgency"],
    allowed_values: { urgency: ["low", "medium", "high"] },
  },
  process: {
    lanes: [
      { id: "L_tech", name: "Asentaja", human: true },
      { id: "L_ai", name: "GAIK AI", human: false },
      { id: "L_sup", name: "Työnjohtaja", human: true },
    ],
    nodes: [
      { id: "S", kind: "startEvent", name: "", lane: "L_tech", inputs: [], outputs: [] },
      { id: "T_report", kind: "userTask", name: "Kirjaa vikailmoitus", lane: "L_tech", inputs: [], outputs: ["Voice Message Audio"] },
      { id: "T_extract", kind: "serviceTask", name: "Poimi tiedot", lane: "L_ai", inputs: [], outputs: [] },
      { id: "T_review", kind: "userTask", name: "Tarkista tiketti", lane: "L_sup", inputs: [], outputs: [] },
      { id: "G", kind: "exclusiveGateway", name: "", lane: "L_sup", inputs: [], outputs: [] },
      { id: "E_ok", kind: "endEvent", name: "", lane: "L_sup", inputs: [], outputs: [] },
      { id: "E_no", kind: "endEvent", name: "", lane: "L_sup", inputs: [], outputs: [] },
    ],
    flows: [
      { from: "S", to: "T_report", name: "" },
      { from: "T_report", to: "T_extract", name: "" },
      { from: "T_extract", to: "T_review", name: "" },
      { from: "T_review", to: "G", name: "" },
      { from: "G", to: "E_ok", name: "Kyllä" },
      { from: "G", to: "E_no", name: "Ei" },
    ],
  },
  reviewer: "T_review",
  accepted_inputs: [{ kind: "audio", label: "WAV", extensions: [".wav"] }],
  package_ready: true,
  package_problems: [],
};

const RECORD = { reporter: "A. Testaaja", location: "Halli 3", urgency: "high" };

type FakeCase = {
  id: string;
  number: number;
  created_at: string;
  status: string;
  round: number;
  comment: string;
  return_to: string | null;
  steps_done: string[];
  events: { at: string; role: string; action: string; detail: string }[];
  [key: string]: unknown;
};

const caseId = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`;

function fakeCase(number: number, status: string): FakeCase {
  const at = `2026-11-12T08:${String(number).padStart(2, "0")}:00+00:00`;
  const sent = status !== "draft";
  return {
    id: caseId(number),
    number,
    created_at: at,
    status,
    round: 1,
    note: "",
    comment: "",
    run_id: sent ? "run-1" : null,
    run_message: null,
    inputs: sent ? [{ name: "report.wav", bytes: 12, task: "T_report" }] : [],
    steps_done: sent ? ["T_report"] : [],
    input_tasks: sent ? { "report.wav": "T_report" } : {},
    notes: {},
    return_to: null,
    result: sent ? { record: RECORD, validation: null, transcript: "Hallissa kolme on vuoto.", files: ["ticket.json"] } : null,
    record: sent ? RECORD : null,
    events: sent
      ? [
          { at, role: "Asentaja", action: "submit", detail: "" },
          { at, role: "ai", action: "result", detail: "" },
        ]
      : [],
  };
}

type Fake = { cases: FakeCase[]; removed: string[] };

/** Answers the cases API from `cases` (oldest first), as wizard_api would. */
async function fakeCases(page: Page, cases: FakeCase[], model: object = MODEL): Promise<Fake> {
  const fake: Fake = { cases, removed: [] };
  await page.route(`**${CASES}**`, async (route) => {
    const request = route.request();
    const method = request.method();
    const path = new URL(request.url()).pathname.split(CASES)[1].replace(/^\//, "");
    if (method === "GET" && path === "model") return route.fulfill({ json: model });
    if (method === "GET" && path === "") {
      const listed = [...fake.cases]
        .reverse()
        .map(({ id, number, created_at, status, round }) => ({ id, number, created_at, status, round }));
      return route.fulfill({ json: { cases: listed } });
    }
    const [id, action] = path.split("/");
    const found = fake.cases.find((c) => c.id === id);
    const refuse = (status: number, error: string, message: string) =>
      route.fulfill({ status, json: { detail: { error, message, trace_id: "trace-e2e" } } });
    if (!found) return refuse(404, "not_found", "case not found");
    if (method === "GET" && !action) return route.fulfill({ json: found });
    if (method === "DELETE" && !action) {
      if (found.status !== "draft") {
        return refuse(409, "case_state", `the case is ${found.status}; only a case still waiting for its input can be removed`);
      }
      fake.cases = fake.cases.filter((c) => c !== found);
      fake.removed.push(found.id);
      return route.fulfill({ status: 204 });
    }
    if (method === "POST" && action === "review") {
      const body = request.postDataJSON() as { action: string; role: string; comment: string; return_to: string | null };
      const at = "2026-11-12T09:00:00+00:00";
      if (body.action === "return" || body.action === "rerun") {
        Object.assign(found, { status: "returned", comment: body.comment, rerun: body.action === "rerun", round: found.round + 1, return_to: body.return_to, steps_done: [] });
      } else {
        Object.assign(found, { status: body.action === "approve" ? "approved" : "rejected", comment: body.comment });
      }
      found.events.push({ at, role: body.role, action: body.action, detail: body.comment });
      return route.fulfill({ json: found });
    }
    // A recording asked for by the source panel's player, and anything else.
    return refuse(404, "not_found", "not found");
  });
  return fake;
}

async function openCases(page: Page) {
  await loginAsDev(page);
  await page.goto(`/sessions/${SESSION}/cases`);
  await expect(page.getByTestId("case-new")).toBeVisible();
}

/** The page's own error line; Next's route announcer is an alert too. */
const problem = (page: Page) => page.locator("main").getByRole("alert");

const rowNumbers = (page: Page) =>
  page.getByTestId("case-row").evaluateAll((rows) => rows.map((r) => /Tapaus (\d+)/.exec(r.textContent ?? "")?.[1]));

test.describe("cases view: removing a case that waits for its input", () => {
  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("a waiting case is removed after asking, and the others keep their numbers", async ({ page }) => {
    // #4 was removed earlier: the numbers are the api's, not places in the list.
    const fake = await fakeCases(page, [fakeCase(1, "approved"), fakeCase(2, "review"), fakeCase(3, "draft"), fakeCase(5, "draft")]);
    await openCases(page);

    await expect(page.getByRole("heading", { name: "Tapaus 5" })).toBeVisible();
    expect(await rowNumbers(page)).toEqual(["5", "3", "2", "1"]);
    // Only the cases that were never sent can be removed.
    await expect(page.getByTestId("case-remove")).toHaveCount(2);

    // Asked first, in the row; "Peruuta" leaves the case and gives the focus back.
    await page.getByRole("button", { name: "Poista tapaus 3" }).click();
    const ask = page.getByTestId("case-remove-ask");
    await expect(ask).toContainText("Poistetaanko tapaus 3?");
    await expect(page.getByTestId("case-remove-cancel")).toBeFocused();
    await page.getByTestId("case-remove-cancel").click();
    await expect(ask).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Poista tapaus 3" })).toBeFocused();
    expect(fake.removed).toEqual([]);

    await page.getByRole("button", { name: "Poista tapaus 3" }).click();
    await page.getByTestId("case-remove-confirm").click();

    await expect(page.getByTestId("case-row")).toHaveCount(3);
    expect(fake.removed).toEqual([caseId(3)]);
    expect(await rowNumbers(page)).toEqual(["5", "2", "1"]);
    await expect(page.getByTestId("case-removed")).toHaveText("Tapaus 3 poistettu.");
    // The open case stays open.
    await expect(page.getByRole("heading", { name: "Tapaus 5" })).toBeVisible();
    await expect(problem(page)).toHaveCount(0);
  });

  test("removing the open case opens the newest one left", async ({ page }) => {
    const fake = await fakeCases(page, [fakeCase(1, "approved"), fakeCase(2, "review"), fakeCase(3, "draft")]);
    await openCases(page);
    await expect(page.getByRole("heading", { name: "Tapaus 3" })).toBeVisible();

    await page.getByRole("button", { name: "Poista tapaus 3" }).click();
    await page.getByTestId("case-remove-confirm").click();

    await expect(page.getByRole("heading", { name: "Tapaus 2" })).toBeVisible();
    await expect(page.getByTestId("case-review")).toBeVisible();
    expect(fake.removed).toEqual([caseId(3)]);
    expect(await rowNumbers(page)).toEqual(["2", "1"]);
    await expect(page.getByTestId("case-remove")).toHaveCount(0);
  });

  test("a case that was sent meanwhile is not removed: the refusal is shown and the list read again", async ({ page }) => {
    const fake = await fakeCases(page, [fakeCase(1, "approved"), fakeCase(2, "draft"), fakeCase(3, "draft")]);
    await openCases(page);
    await page.getByRole("button", { name: "Poista tapaus 2" }).click();
    // Sent from another tab while the question was open.
    Object.assign(fake.cases[1], fakeCase(2, "review"));

    await page.getByTestId("case-remove-confirm").click();

    await expect(problem(page)).toContainText("only a case still waiting for its input can be removed");
    expect(fake.removed).toEqual([]);
    await expect(page.getByTestId("case-row").filter({ hasText: "Tapaus 2" })).toContainText("Odottaa tarkistusta");
    await expect(page.getByRole("button", { name: "Poista tapaus 2" })).toHaveCount(0);
  });
});

test.describe("cases view: the decision", () => {
  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("running again needs no reason and leaves no notice at the input", async ({ page }) => {
    const fake = await fakeCases(page, [fakeCase(1, "review")]);
    await openCases(page);

    await page.getByTestId("case-return").click();
    await page.getByTestId("case-confirm").click();

    await expect(page.getByTestId("case-drop")).toBeVisible();
    await expect(page.getByTestId("case-returned")).toHaveCount(0);
    expect(fake.cases[0].status).toBe("returned");
    expect(fake.cases[0].comment).toBe("");
    expect(fake.cases[0].rerun).toBe(true);
    await expect(page.getByTestId("case-status")).toHaveText("Odottaa uutta syötettä, kierros 2");
  });

  test("a reviewer's return is told from a rerun by the api's word, not by the comment", async ({ page }) => {
    // A return whose comment happens to read like the old rerun text.
    const returned = Object.assign(fakeCase(1, "review"), { status: "returned", round: 2, steps_done: [], rerun: false, comment: "Ajetaan uudelleen." });
    returned.events.push({ at: "2026-11-12T09:00:00+00:00", role: "Työnjohtaja", action: "return", detail: returned.comment });
    await fakeCases(page, [returned]);
    await openCases(page);

    await expect(page.getByTestId("case-returned")).toContainText("Työnjohtaja palautti korjattavaksi");
    await expect(page.getByTestId("case-returned-comment")).toHaveText("Ajetaan uudelleen.");
  });

  test("a result is done or run again; each says what it leads to, on a wide and on a narrow screen", async ({ page }) => {
    await fakeCases(page, [fakeCase(1, "review")]);
    await openCases(page);

    const hints = page.getByTestId("case-decision-hints");
    await expect(hints.getByRole("listitem")).toHaveText([
      "Valmis: tulos tallentuu muutoksinesi ja sen voi viedä",
      "Aja uudelleen: palaat syötteeseen ja lähetät tapauksen uudelleen",
    ]);
    // Each line is its button's description, not only text near it.
    await expect(page.getByTestId("case-approve")).toHaveAccessibleDescription(/tulos tallentuu/);
    await expect(page.getByTestId("case-return")).toHaveAccessibleDescription(/palaat syötteeseen/);
    // Rejecting is the reviewer role's, behind "Muut", with what it leads to beside it.
    await expect(page.getByTestId("case-reject")).toBeHidden();
    await page.getByTestId("case-more").locator("summary").click();
    await expect(page.getByTestId("case-reject")).toHaveAccessibleDescription(/päättyy ilman tulosta/);

    await page.setViewportSize({ width: 390, height: 844 });
    await expect(hints).toBeVisible();
    await expect(page.getByTestId("case-reject")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });

  test("a case run again with a note offers the wizard, with the note as the quote", async ({ page }) => {
    await page.addInitScript(() => {
      // What the case page keeps for the chat, before the session page takes it.
      const store = window as unknown as { __kept: string[] };
      store.__kept = [];
      const setItem = Storage.prototype.setItem;
      Storage.prototype.setItem = function (key: string, value: string) {
        if (key.startsWith("gaik-wizard:pending-chat-reference:")) store.__kept.push(value);
        return setItem.call(this, key, value);
      };
    });
    await fakeCases(page, [fakeCase(1, "approved"), fakeCase(2, "review")]);
    await openCases(page);

    await page.getByTestId("case-return").click();
    await page.locator("#case-comment").fill('Kenttä "halli" puuttuu tuloksesta.');
    await page.getByTestId("case-confirm").click();

    // Back at the input step, with the comment and the way to the wizard beside it.
    const returned = page.getByTestId("case-returned");
    // "Aja uudelleen" is the person's own choice: the notice and the chat say so.
    await expect(returned).toContainText("Ajetaan uudelleen");
    await expect(returned).not.toContainText("palautti korjattavaksi");
    await expect(page.getByTestId("case-returned-comment")).toHaveText('Kenttä "halli" puuttuu tuloksesta.');
    // The file is in the form to be corrected, so it is not listed a second time beside it;
    // what the run made of it stays beside the form, to read the comment against.
    await expect(page.getByTestId("case-inputs")).toContainText("report.wav");
    await expect(page.locator("audio")).toHaveCount(1);
    await expect(page.getByTestId("case-source")).toContainText("Hallissa kolme on vuoto.");
    await expect(page.getByTestId("case-drop")).toBeVisible();
    await returned.getByTestId("case-ask-fix-returned").click();

    await page.waitForURL(`**/sessions/${SESSION}?tab=poc`);
    const kept = await page.evaluate(() => (window as unknown as { __kept: string[] }).__kept);
    expect(kept).toHaveLength(1);
    const reference = JSON.parse(kept[0]) as { label: string; prefix: string; draft?: string };
    expect(reference.label).toBe("Tapaus 2");
    expect(reference.prefix).toContain("tapaus ajetaan uudelleen");
    expect(reference.prefix).not.toContain("palautettiin korjattavaksi");
    expect(reference.prefix).toContain("\"Kenttä 'halli' puuttuu tuloksesta.\"");
    expect(reference.draft).toBe("Korjaa ratkaisu tämän palautteen mukaan.");
    // The chat opens with the case as its chip and the words ready to send.
    await expect(page.getByTestId("chat-reference")).toContainText("Tapaus 2");
    await expect(page.getByLabel("Viesti wizardille")).toHaveValue("Korjaa ratkaisu tämän palautteen mukaan.");
  });
});

// A solution that updates a user guide from release notes: long sentences,
// lists inside records, booleans and empty values (issue 166).
const GUIDE_MODEL = {
  ...MODEL,
  title: "Release User Guide Updater",
  spec: {
    schema_name: "GuideUpdate",
    fields: ["release", "breaking_changes", "reviewed", "audiences", "open_questions", "owner", "features", "contacts", "trace"],
  },
};

const GUIDE_RECORD = {
  release: 4.2,
  breaking_changes: false,
  reviewed: true,
  audiences: ["Admins", "Report users"],
  open_questions: [],
  owner: { name: "Docs team", on_call: false },
  features: [
    {
      feature: "Report export",
      summary: "Reports can now be exported as PDF or CSV from the Reports page, next to the Print button.",
      guide_section: "Reports",
      steps: ["Go to the Reports page.", "Click Export next to Print."],
      needs_screenshot: true,
      notes: [],
    },
    {
      feature: "Saved filters",
      summary: "A filter can be saved under a name and shared with the team.",
      guide_section: "Search",
      steps: ["Open the filter menu.", "Choose Save filter."],
      needs_screenshot: false,
      notes: null,
    },
  ],
  contacts: [
    { name: "A. Testaaja", role: "Writer" },
    { name: "B. Tarkastaja", role: "Reviewer" },
  ],
  trace: [1, { step: "parse" }],
};

function guideCase(validation: object | null = null): FakeCase {
  const done = fakeCase(1, "approved");
  done.record = GUIDE_RECORD;
  done.result = { record: GUIDE_RECORD, validation, transcript: "", files: ["guide_update.json"] };
  done.inputs = [{ name: "release-notes.pdf", bytes: 2048, task: "T_report" }];
  return done;
}

test.describe("cases view: a finished case's result", () => {
  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("a list, a boolean, a number and an empty value read as a person would write them", async ({ page }) => {
    await fakeCases(page, [guideCase()], GUIDE_MODEL);
    await openCases(page);
    const done = page.getByTestId("case-done");
    const value = (field: string) => done.locator(`[data-field="${field}"] > dd`);

    await expect(value("release")).toHaveText("4.2");
    await expect(value("breaking_changes")).toHaveText("Ei");
    await expect(value("reviewed")).toHaveText("Kyllä");
    await expect(value("audiences").getByRole("listitem")).toHaveText(["Admins", "Report users"]);
    // An empty list is said as none, apart from a missing value's dash.
    await expect(value("open_questions")).toHaveText("Ei yhtään");
    // An object is its fields as lines.
    await expect(value("owner").getByRole("listitem")).toHaveText(["Name: Docs team", "On call: Ei"]);
    // A shape with no plain reading is behind a disclosure, closed.
    const raw = value("trace").locator("details");
    await expect(raw.locator("summary")).toHaveText("Näytä raakadata");
    await expect(raw.locator("pre")).toBeHidden();
    // Nothing of JSON's own marks is on the page, nor a boolean as code.
    const shown = await done.evaluate((el) => (el as HTMLElement).innerText);
    expect(shown).not.toMatch(/[[\]{}"]/);
    expect(shown).not.toMatch(/\b(true|false|null)\b/);
    await raw.locator("summary").click();
    await expect(raw.locator("pre")).toContainText('"step": "parse"');
  });

  test("long or many fields are each record's label and value pairs under the field's name; short ones stay a table", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await fakeCases(page, [guideCase()], GUIDE_MODEL);
    await openCases(page);
    const done = page.getByTestId("case-done");
    const features = done.locator('[data-field="features"]');

    // The field's name is a heading above its records, as wide as they are.
    const heading = features.locator("> dt");
    await expect(heading).toHaveText("Features");
    const records = features.getByTestId("case-records");
    const headingBox = (await heading.boundingBox())!;
    const recordsBox = (await records.boundingBox())!;
    expect(headingBox.y + headingBox.height).toBeLessThanOrEqual(recordsBox.y);
    expect(Math.abs(headingBox.x - recordsBox.x)).toBeLessThan(2);

    // Two records, numbered, six pairs each, and no table for them.
    await expect(records.locator("> li")).toHaveCount(2);
    await expect(records.locator("> li > span").first()).toHaveText("1");
    const first = records.locator("> li").first();
    await expect(first.locator("dt")).toHaveText(["Feature", "Summary", "Guide section", "Steps", "Needs screenshot", "Notes"]);
    await expect(first.locator("dd").nth(3).getByRole("listitem")).toHaveText(["Go to the Reports page.", "Click Export next to Print."]);
    await expect(first.locator("dd").nth(4)).toHaveText("Kyllä");
    // Notes: an empty list in the first record, nothing in the second.
    await expect(first.locator("dd").nth(5)).toHaveText("Ei yhtään");
    await expect(records.locator("> li").nth(1).locator("dd").nth(5)).toHaveText("—");
    await expect(features.locator("table")).toHaveCount(0);
    // A sentence has room: the summary is on one or two lines, not a word a line.
    const summary = first.locator("dd").nth(1);
    expect((await summary.boundingBox())!.height).toBeLessThan(50);
    // At a wide width the label stands beside its value.
    const labelBox = (await first.locator("dt").nth(1).boundingBox())!;
    const summaryBox = (await summary.boundingBox())!;
    expect(labelBox.x + labelBox.width).toBeLessThanOrEqual(summaryBox.x);

    // Two short fields are a table.
    const contacts = done.locator('[data-field="contacts"]').getByTestId("case-records-table");
    await expect(contacts.getByRole("columnheader")).toHaveText(["Name", "Role"]);
    await expect(contacts.locator("tbody tr")).toHaveCount(2);

    // Nothing scrolls inside the page's own scroll.
    const boxes = await done.evaluate((el) =>
      [...el.querySelectorAll("*")].filter((n) => /auto|scroll/.test(getComputedStyle(n).overflowX + getComputedStyle(n).overflowY)).length,
    );
    expect(boxes).toBe(0);

    // On a phone the label is above its value, and the page does not scroll sideways.
    await page.setViewportSize({ width: 390, height: 844 });
    const narrowLabel = (await first.locator("dt").nth(1).boundingBox())!;
    const narrowSummary = (await summary.boundingBox())!;
    expect(narrowLabel.y + narrowLabel.height).toBeLessThanOrEqual(narrowSummary.y + 1);
    expect(narrowSummary.width).toBeGreaterThan(250);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });

  test("on a phone a table of four long field names stays inside its card", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const plan = [
      { implementation: "Phase 1", recommendation: "Adopt", responsibilities: "Docs team", dependencies: "None yet" },
      { implementation: "Phase 2", recommendation: "Pilot", responsibilities: "IT", dependencies: "SSO" },
    ];
    const done = fakeCase(1, "approved");
    done.record = { plan };
    done.result = { record: { plan }, validation: null, transcript: "", files: [] };
    await fakeCases(page, [done], { ...MODEL, spec: { schema_name: "Plan", fields: ["plan"] } });
    await openCases(page);

    const card = page.getByTestId("case-done");
    const table = card.getByTestId("case-records-table");
    await expect(table.getByRole("columnheader")).toHaveCount(4);
    const tableBox = (await table.boundingBox())!;
    const cardBox = (await card.boundingBox())!;
    expect(tableBox.x + tableBox.width).toBeLessThanOrEqual(cardBox.x + cardBox.width);
    // The page scrolls inside <main>: that is where a sideways scroll would show.
    expect(await page.locator("main").evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true);
  });

  test("the export controls are buttons with their file type's mark and a full name", async ({ page }) => {
    await fakeCases(page, [guideCase()], GUIDE_MODEL);
    await openCases(page);
    const exports = page.getByTestId("case-export");
    await expect(page.getByRole("group", { name: "Vie" })).toBeVisible();
    for (const [format, kind] of [["JSON", "json"], ["CSV", "csv"], ["PDF", "pdf"]]) {
      const button = exports.getByRole("button", { name: `Vie muodossa ${format}` });
      await expect(button).toHaveText(format);
      await expect(button.locator(`svg[data-file-kind="${kind}"]`)).toBeVisible();
    }
    await expect(exports.getByRole("button")).toHaveCount(3);

    // The file is the record, with lists as lists: the page's wording is the page's.
    const download = page.waitForEvent("download");
    await exports.getByRole("button", { name: "Vie muodossa JSON" }).click();
    expect((await download).suggestedFilename()).toBe("guideupdate.json");
  });

  test("the page says what it is once: the solution's name and New case, with no line repeating them", async ({ page }) => {
    await fakeCases(page, [guideCase()], GUIDE_MODEL);
    await openCases(page);
    await expect(page.getByRole("heading", { level: 2, name: "Release User Guide Updater" })).toBeVisible();
    await expect(page.getByTestId("case-new")).toHaveText("Uusi tapaus");
    await expect(page.locator("main")).not.toContainText("Kokeile ratkaisua omalla aineistolla");
    // The bar's heading is the session and leads back to it.
    await expect(page.getByTestId("session-bar").getByRole("link")).toHaveAttribute("href", `/sessions/${SESSION}?tab=poc`);
  });

  test("a session never named goes by its blueprint's name on the session page too", async ({ page }) => {
    await loginAsDev(page);
    const created = await page.request.post("/api/sessions", { data: {} });
    expect(created.ok()).toBe(true);
    const { id } = (await created.json()) as { id: string };
    const named = await page.request.patch(`/api/sessions/${id}/blueprint`, {
      data: {
        content: {
          name: "Release User Guide Updater",
          description: "",
          goal: "",
          steps: [{ id: "input", name: "Input", type: "io" }],
        },
      },
    });
    expect(named.ok()).toBe(true);

    // One name for the session, on its own page and on the cases page.
    await page.goto(`/sessions/${id}`);
    await expect(page.getByTestId("session-bar").getByRole("heading")).toHaveText("Release User Guide Updater");
    await page.goto(`/sessions/${id}/cases`);
    await expect(page.getByTestId("session-bar").getByRole("heading")).toHaveText("Release User Guide Updater");
  });

  test("a failed grounding check names the values it is about and says what to do", async ({ page }) => {
    await fakeCases(
      page,
      [
        guideCase({
          passed: false,
          hallucination_flags: [
            { field: "release", value: 4.2, severity: "high", reason: "The source names release 4.1." },
            { field: "features.guide_section", value: "Search", severity: "low", reason: "" },
          ],
        }),
      ],
      GUIDE_MODEL,
    );
    await openCases(page);
    const grounding = page.getByTestId("case-grounding");
    await expect(grounding).toContainText("Lähdetarkistus: mahdollisia keksittyjä arvoja");
    await expect(grounding.getByTestId("case-grounding-flags").getByRole("listitem")).toHaveText([
      "Release: 4.2The source names release 4.1.",
      "Features › Guide section: Search",
    ]);
    await expect(grounding).toContainText("Tarkista nämä arvot lähteestä ennen kuin käytät tulosta.");
  });

  test("a grounding check that names no values still says what to do, and a passed one says only that", async ({ page }) => {
    await fakeCases(page, [guideCase({ passed: true }), Object.assign(guideCase({ passed: false }), { id: caseId(2), number: 2 })], GUIDE_MODEL);
    await openCases(page);
    const grounding = page.getByTestId("case-grounding");
    await expect(page.getByRole("heading", { name: "Tapaus 2" })).toBeVisible();
    await expect(grounding).toContainText("Lähdetarkistus: mahdollisia keksittyjä arvoja");
    await expect(grounding.getByTestId("case-grounding-flags")).toHaveCount(0);
    await expect(grounding).toContainText("Tarkista tulos lähteestä ennen kuin käytät sitä.");

    await page.getByTestId("case-row").filter({ hasText: "Tapaus 1" }).click();
    await expect(page.getByRole("heading", { name: "Tapaus 1" })).toBeVisible();
    await expect(grounding).toHaveText("Lähdetarkistus läpi");
  });
});
