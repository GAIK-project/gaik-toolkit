// Cookie-based i18n (fi/en), works in server rendering.
// The locale is stored in a cookie and read in server components via getI18n().
// Switching happens via a server action (app/locale-actions.ts) + LocaleSwitcher.

import { cookies } from "next/headers";

export const LOCALES = ["fi", "en"] as const;
export type Locale = (typeof LOCALES)[number];
export const DEFAULT_LOCALE: Locale = "fi";
export const LOCALE_COOKIE = "gaik_locale";

// BCP-47 tag per locale for date formatting.
export const DATE_LOCALE: Record<Locale, string> = {
  fi: "fi-FI",
  en: "en-GB",
};

export type Dict = {
  appName: string;
  signOut: string;

  // login
  loginSubtitle: string;
  devHintPre: string;
  devHintPost: string;
  email: string;
  password: string;
  login: string;
  signup: string;

  // session list
  sessionsTitle: string;
  sessionsIntro: string;
  newSessionPlaceholder: string;
  startNew: string;
  previousSessions: string;
  noSessions: string;
  done: string;
  step: string;
  blueprintVersions: string;
  updated: string;

  // wizard
  backToSessions: string;
  chat: string;
  chatPlaceholder: string;
  chatGreeting: string;
  chatInputPlaceholder: string;
  chatSend: string;
  chatMockReplyPre: string;
  chatMockReplyPost: string;
  workspace: string;
  activeBlueprint: string;
  versions: string;
  phaseUpper: string;
  workspacePlaceholder: string;
  wsTabFlow: string;
  wsTabJson: string;
  wsTabPoc: string;
  wsBlueprintGoal: string;
  wsStepAi: string;
  wsStepHuman: string;
  wsStepIo: string;
  pocRun: string;
  pocRunning: string;
  pocRerun: string;
  pocIdle: string;
  pocSuccess: string;
  pocFailed: string;
  pocLogStart: string;
  pocLogDeps: string;
  pocLogStep: string;
  pocLogStepOk: string;
  pocLogValidate: string;
  pocLogDone: string;
  gateNotice: string;
  previous: string;
  nextPhase: string;
  approveGate: string;
  ready: string;
  phasesTitle: string;
  saved: string;
  gateWaiting: string;

  phases: string[]; // 13 vaihetta (GAIK V1 -malli + V2 Gate 4)
  gates: { locked: string; pending: string; approved: string; rejected: string };
};

const fi: Dict = {
  appName: "GAIK Solution Wizard",
  signOut: "Kirjaudu ulos",

  loginSubtitle: "Kirjaudu jatkaaksesi",
  devHintPre: "Dev-tila päällä. Kirjaudu tunnuksilla",
  devHintPost: "(esitäytetty alle).",
  email: "Sähköposti",
  password: "Salasana",
  login: "Kirjaudu",
  signup: "Rekisteröidy",

  sessionsTitle: "Wizard-sessiot",
  sessionsIntro:
    "Aloita uusi käyttötapaus tai jatka aiempaa siitä vaiheesta mihin jäit.",
  newSessionPlaceholder: "Uuden session nimi (esim. Asiakaspalvelun chatbot)",
  startNew: "Aloita uusi",
  previousSessions: "Aiemmat sessiot",
  noSessions: "Ei vielä sessioita. Aloita uusi yltä.",
  done: "Valmis",
  step: "Vaihe",
  blueprintVersions: "blueprint-versiota",
  updated: "Päivitetty",

  backToSessions: "← Sessiot",
  chat: "Keskustelu",
  chatPlaceholder:
    "Chat-paneeli (placeholder). Tähän tulevat vaatimuskeruu ja gate-hyväksynnät.",
  chatGreeting:
    "Hei! Kerro liiketoimintaongelmasta, niin autan muotoilemaan siitä GenAI-käyttötapauksen.",
  chatInputPlaceholder: "Kirjoita viesti…",
  chatSend: "Lähetä",
  chatMockReplyPre: "Kiitos viestistä. Kirjasin sen vaiheeseen ",
  chatMockReplyPost:
    ". (Mock-vastaus — varsinainen agentti kytketään myöhemmin.)",
  workspace: "Työtila",
  activeBlueprint: "Aktiivinen blueprint",
  versions: "versiota",
  phaseUpper: "VAIHE",
  workspacePlaceholder:
    "BPMN-canvas / JSON-blueprint / PoC / dokumentaatio (placeholder). Tämän vaiheen sisältö renderöityy tähän.",
  wsTabFlow: "Työnkulku",
  wsTabJson: "Blueprint (JSON)",
  wsTabPoc: "PoC",
  wsBlueprintGoal: "Tavoite",
  wsStepAi: "AI-vaihe",
  wsStepHuman: "Ihmistarkistus",
  wsStepIo: "I/O",
  pocRun: "Aja PoC",
  pocRunning: "Ajetaan…",
  pocRerun: "Aja PoC uudelleen",
  pocIdle: "PoC:tä ei ole vielä ajettu. Aja se nähdäksesi lokit ja tuloksen.",
  pocSuccess: "Onnistui",
  pocFailed: "Epäonnistui",
  pocLogStart: "Käynnistetään eristetty PoC-ympäristö…",
  pocLogDeps: "Asennetaan riippuvuudet…",
  pocLogStep: "Suoritetaan vaihe:",
  pocLogStepOk: "valmis",
  pocLogValidate: "Validoidaan tulokset…",
  pocLogDone: "PoC valmis.",
  gateNotice:
    "Tämä on gate-vaihe. Hyväksy jatkaaksesi seuraavaan vaiheeseen.",
  previous: "← Edellinen",
  nextPhase: "Seuraava vaihe →",
  approveGate: "Hyväksy gate →",
  ready: "Valmis",
  phasesTitle: "Vaiheet",
  saved: "Tallennettu",
  gateWaiting: "Gate odottaa hyväksyntää",

  phases: [
    "Session start",
    "Vaatimusten keruu",
    "Spesifikaatio",
    "Gate 1",
    "Skeeman suunnittelu",
    "Komponenttivalinta",
    "Blueprint-kokoaminen",
    "Visuaalinen työnkulku (BPMN)",
    "Gate 2",
    "PoC",
    "Gate 3",
    "Dokumentaatio",
    "Gate 4",
  ],
  gates: {
    locked: "Lukittu",
    pending: "Odottaa hyväksyntää",
    approved: "Hyväksytty",
    rejected: "Hylätty",
  },
};

const en: Dict = {
  appName: "GAIK Solution Wizard",
  signOut: "Sign out",

  loginSubtitle: "Sign in to continue",
  devHintPre: "Dev mode on. Sign in with",
  devHintPost: "(prefilled below).",
  email: "Email",
  password: "Password",
  login: "Sign in",
  signup: "Sign up",

  sessionsTitle: "Wizard sessions",
  sessionsIntro:
    "Start a new use case or continue an earlier one from where you left off.",
  newSessionPlaceholder: "New session name (e.g. Customer service chatbot)",
  startNew: "Start new",
  previousSessions: "Previous sessions",
  noSessions: "No sessions yet. Start a new one above.",
  done: "Done",
  step: "Step",
  blueprintVersions: "blueprint versions",
  updated: "Updated",

  backToSessions: "← Sessions",
  chat: "Chat",
  chatPlaceholder:
    "Chat panel (placeholder). Requirements gathering and gate approvals go here.",
  chatGreeting:
    "Hi! Describe your business problem and I'll help shape it into a GenAI use case.",
  chatInputPlaceholder: "Type a message…",
  chatSend: "Send",
  chatMockReplyPre: "Thanks for your message. I've logged it under step ",
  chatMockReplyPost:
    ". (Mock reply — the real agent will be wired in later.)",
  workspace: "Workspace",
  activeBlueprint: "Active blueprint",
  versions: "versions",
  phaseUpper: "STEP",
  workspacePlaceholder:
    "BPMN canvas / JSON blueprint / PoC / documentation (placeholder). This step's content renders here.",
  wsTabFlow: "Workflow",
  wsTabJson: "Blueprint (JSON)",
  wsTabPoc: "PoC",
  wsBlueprintGoal: "Goal",
  wsStepAi: "AI step",
  wsStepHuman: "Human review",
  wsStepIo: "I/O",
  pocRun: "Run PoC",
  pocRunning: "Running…",
  pocRerun: "Run PoC again",
  pocIdle: "PoC has not been run yet. Run it to see logs and the result.",
  pocSuccess: "Success",
  pocFailed: "Failed",
  pocLogStart: "Starting isolated PoC environment…",
  pocLogDeps: "Installing dependencies…",
  pocLogStep: "Running step:",
  pocLogStepOk: "done",
  pocLogValidate: "Validating results…",
  pocLogDone: "PoC complete.",
  gateNotice: "This is a gate step. Approve to continue to the next step.",
  previous: "← Previous",
  nextPhase: "Next step →",
  approveGate: "Approve gate →",
  ready: "Done",
  phasesTitle: "Steps",
  saved: "Saved",
  gateWaiting: "Gate awaiting approval",

  phases: [
    "Session start",
    "Requirements gathering",
    "Specification",
    "Gate 1",
    "Schema design",
    "Component selection",
    "Blueprint assembly",
    "Visual workflow (BPMN)",
    "Gate 2",
    "PoC",
    "Gate 3",
    "Documentation",
    "Gate 4",
  ],
  gates: {
    locked: "Locked",
    pending: "Awaiting approval",
    approved: "Approved",
    rejected: "Rejected",
  },
};

const DICTS: Record<Locale, Dict> = { fi, en };

export async function getLocale(): Promise<Locale> {
  const c = await cookies();
  const v = c.get(LOCALE_COOKIE)?.value;
  return v === "en" || v === "fi" ? v : DEFAULT_LOCALE;
}

export async function getI18n(): Promise<{ locale: Locale; t: Dict }> {
  const locale = await getLocale();
  return { locale, t: DICTS[locale] };
}
