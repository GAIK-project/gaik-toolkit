import fs from "node:fs";
import path from "node:path";
import { test, expect } from "@playwright/test";
import { waitForApiHealthy } from "./helpers/api";
import { agentE2eEnabled, createSessionViaApi, sendChatViaApi } from "./helpers/agent-api";

/**
 * Local-only live-agent E2E (not CI) — verifies the SKILL.md rule added after
 * the 28 Aug customer review: blueprint identifiers (workflow.steps[].id/name,
 * component names) stay in one language, English, even when the whole
 * conversation is conducted in Finnish. Human-readable prose fields are not
 * checked here — they're explicitly allowed to follow the conversation.
 *
 * Request-only (no browser page): this tests agent/prompt behaviour against
 * wizard_api directly, not UI wiring, and skips the Next.js proxy layer.
 *
 * Prerequisites:
 *   - wizard_api on :8100 with Claude ambient auth (`claude auth status` → loggedIn)
 *   - Postgres up, migrations applied
 *
 * Run:
 *   PLAYWRIGHT_AGENT_E2E=true PLAYWRIGHT_SKIP_WEBSERVER=true \
 *   WIZARD_API_URL=http://127.0.0.1:8100 \
 *   npx playwright test e2e/local-agent-blueprint-language.spec.ts --workers=1
 *
 * Runs the real wizard conversation in Finnish through to blueprint assembly
 * (Phase 6) — this is a full multi-phase run, not a shortcut, because the
 * rule being tested only has something to check once workflow.steps exists.
 * Can take several minutes; budgeted generously below.
 */

// Finnish letters/diacritics that essentially never appear in an English
// technical identifier. Cheap, specific, and directly targets the customer's
// exact complaint (English/Finnish mixed unpredictably within one field) —
// deliberately not a full language-detection heuristic.
const FINNISH_MARKERS = /[äöåÄÖÅ]/;

// A generic "proceed, use your judgement" nudge for whatever the agent asks
// next — the conversation can't be fully scripted turn-by-turn since the
// exact follow-up questions vary, but every phase accepts "here's more detail,
// otherwise use sensible defaults and move on" as a valid answer.
const CONTINUE_NUDGE =
  "Kyllä, se on oikein. Käytä antamiani tietoja ja parhaita oletuksiasi kaikkeen " +
  "mitä en ole vielä maininnut, kirjaa ne assumptions-kenttään, ja jatka seuraavaan " +
  "vaiheeseen ilman lisäkysymyksiä.";

function findBlueprintFile(outputDir: string): string {
  return path.join(outputDir, "use_case.blueprint.json");
}

function readWorkflowSteps(
  outputDir: string,
): Array<{ id?: string; name?: string; component?: string }> | null {
  const file = findBlueprintFile(outputDir);
  if (!fs.existsSync(file)) return null;
  const parsed = JSON.parse(fs.readFileSync(file, "utf-8")) as {
    workflow?: { steps?: Array<{ id?: string; name?: string; component?: string }> };
  };
  const steps = parsed.workflow?.steps;
  return steps && steps.length > 0 ? steps : null;
}

test.describe("Live agent — blueprint identifiers stay in one language (SKILL.md)", () => {
  test.skip(
    !agentE2eEnabled(),
    "local only: PLAYWRIGHT_AGENT_E2E=true (requires Claude login + wizard_api on WIZARD_API_URL)",
  );

  test.beforeAll(async ({ request }) => {
    await waitForApiHealthy(request);
  });

  test("workflow.steps ids/names/components have no Finnish leaking in", async ({
    request,
  }) => {
    test.setTimeout(25 * 60_000); // full multi-phase live conversation

    const session = await createSessionViaApi(
      request,
      "agent-e2e-lang@gaik.local",
      `Language E2E ${Date.now()}`,
    );

    // Turn 1 — Phase 1.2 use-case description. Front-loads Round 1 (business)
    // fields too, so the agent has less to ask about later.
    const msg1 =
      "Haluamme GenAI-ratkaisun joka poimii ostolaskuista toimittajan nimen ja " +
      "loppusumman. Nykyisin talousassistentti avaa jokaisen PDF-laskun käsin ja " +
      "kirjaa tiedot Exceliin, mikä on hidasta ja altista virheille. Syötteenä on " +
      "PDF-laskuja, tulosteena rakenteinen JSON toimittajan nimellä ja summalla. " +
      "Käyttäjinä on kolme talousassistenttia, tarkastajana talouspäällikkö. " +
      "Onnistumisen mittari on käsittelyajan lyheneminen ja virheiden väheneminen. " +
      "Ensimmäisen PoC:n tavoite on osoittaa että testilaskuista saadaan oikeat " +
      "tiedot poimittua luotettavasti.";
    let reply = await sendChatViaApi(request, session.id, msg1);
    expect(reply.length).toBeGreaterThan(20);

    // Turn 2 — Round 2/3 (technical + target-output spec), also front-loaded.
    const msg2 =
      "Tekniset tiedot: syöte on PDF (skannattu tai natiivi), tuloste JSON. Kieli on " +
      "suomi. Erikoissanastoa ei tarvita. Ulkoisia tietolähteitä ei ole, laskut " +
      "ladataan käyttöliittymän kautta. Mallin tarjoaja saa olla mikä tahansa sopiva, " +
      "käytä oletusasetuksia. Ei erityisiä tietoturvarajoitteita. Integraatioita ei " +
      "tarvita nyt. Ihmistarkistus on käytössä epävarmoissa tapauksissa. Arviointi: " +
      "tarkkuus vähintään 90% testilaskuista. Käyttöliittymä on tämä web-wizard. " +
      "Tavoiteltu skeema: nimi invoice_extraction, kentät toimittaja (pakollinen, " +
      "teksti) ja summa (pakollinen, numero, euroina). Ei sallittuja arvolistoja. " +
      "Jos kenttää ei löydy, jätä tyhjäksi äläkä arvaa.";
    reply = await sendChatViaApi(request, session.id, msg2);
    expect(reply.length).toBeGreaterThan(20);

    // From here the exact remaining turns vary (gate confirmation, optional
    // business-process elicitation, schema/component proposals). Keep nudging
    // forward, polling the filesystem after every turn — stop as soon as
    // workflow.steps actually exists, which is the only thing this test needs.
    let steps = readWorkflowSteps(session.outputDir);
    let turns = 0;
    const MAX_TURNS = 14;
    while (!steps && turns < MAX_TURNS) {
      reply = await sendChatViaApi(request, session.id, CONTINUE_NUDGE);
      expect(reply.length, `turn ${turns + 3} produced an empty reply`).toBeGreaterThan(0);
      steps = readWorkflowSteps(session.outputDir);
      turns += 1;
    }

    expect(
      steps,
      `workflow.steps never appeared after ${turns + 2} turns — ` +
        `blueprint file: ${findBlueprintFile(session.outputDir)}`,
    ).not.toBeNull();
    expect(steps!.length).toBeGreaterThan(0);

    const offenders = steps!
      .flatMap((s) => [
        { field: "id", value: s.id ?? "" },
        { field: "name", value: s.name ?? "" },
        { field: "component", value: s.component ?? "" },
      ])
      .filter((f) => FINNISH_MARKERS.test(f.value));

    expect(
      offenders,
      `Finnish characters leaked into blueprint identifiers: ${JSON.stringify(offenders)}`,
    ).toEqual([]);
  });
});
