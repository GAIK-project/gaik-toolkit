// Mock session model that locks the UI. Fields mirror the planned data model:
// a wizard session (id, user_id, step, gate status, metadata, output dir) and
// blueprint versions with an active version per session.
//
// NOTE: not persistent storage. Data lives in dev-server memory and resets on
// restart. Real persistence is wired to the same model later.

import {
  buildGateStatus,
  transition,
  GATE_STEPS,
  isGateStep,
  type GateStatus,
  type WizardEvent,
} from "./wizard-state-machine";
import { REQUIREMENT_POINTS, openingQuestion } from "./requirements-model";
import type { TargetOutputSpec } from "./target-output-spec";

// Re-export the state-machine structure so existing importers keep their path.
export { GATE_STEPS, isGateStep };
export type { GateStatus };

// Wizard phase model. Gates: Gate 1 requirement completeness (after
// Specification), Gate 2 workflow validation (after Blueprint+BPMN),
// Gate 3 PoC validation, Gate 4 runtime validation.
export const PHASES = [
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
] as const;

export const PHASE_COUNT = PHASES.length; // 13

/** 1-based step when BPMN visual workflow is generated (onboarding phase 8). */
export const BPMN_VISUAL_STEP = 8;

/** 1-based step when the PoC package is generated (onboarding phase 10). */
export const POC_STEP = 10;

export function isBpmnVisualPhase(step: number): boolean {
  return step >= BPMN_VISUAL_STEP;
}

export type BlueprintVersion = {
  version: number;
  createdAt: string;
  note: string;
};

// Blueprint content (mock): name, goal, and workflow steps. Rendered by the
// workspace panel.
export type BlueprintStepType = "io" | "ai" | "human_review";

export type BlueprintStep = {
  id: string;
  name: string;
  type: BlueprintStepType;
  component?: string;
  description?: string;
  /** Component configuration/settings (SME-4, #22 — not just names). */
  settings?: Record<string, string>;
};

export type Blueprint = {
  name: string;
  description: string;
  goal: string;
  steps: BlueprintStep[];
  /** Optional artifact label overrides synced from BPMN data objects. */
  data_objects?: Record<string, string>;
  /** Gateway snapshots synced from BPMN canvas (#48). */
  gateways?: { id: string; name: string; type: "exclusive" | "parallel" }[];
  /** Persistent systems → BPMN data stores (+ submit send task). */
  integration_targets?: string[];
};

export type ChatRole = "user" | "assistant";

export type ChatMessage = {
  id: string;
  role: ChatRole;
  content: string;
  createdAt: string;
};

export type WizardSession = {
  id: string;
  userId: string; // owner
  title: string;
  step: number; // 1..13 nykyinen vaihe
  gateStatus: Record<number, GateStatus>; // gate-vaihe -> status
  status: "active" | "done";
  outputDir: string; // output dir convention
  createdAt: string;
  updatedAt: string;
  versions: BlueprintVersion[]; // versions
  activeVersion: number;
  messages: ChatMessage[]; // chat-historia (mock)
  blueprint: Blueprint; // active version content (mock)
  // Requirement gathering state (steps 1–3). `points` are the questions the
  // backend is collecting (from requirements-model here; wizard_api later);
  // `answers` are the user's replies in order. The frontend renders these — it
  // never hardcodes the questions. The live agent (#29) replaces the source.
  requirements?: { points: string[]; answers: string[] };
  // Business framing the agent gathered into the V1 draft blueprint (surfaced
  // read-only at Gate 1). Present once gathering is complete; null otherwise.
  businessContext?: BusinessContext | null;
  /** Agreed output fields from the agent's draft blueprint (#141). */
  targetOutputSpec?: TargetOutputSpec | null;
  // Open assumptions the agent recorded into the draft blueprint (Gate 1).
  assumptions?: Assumption[];
  /** The sandbox run wizard_api recorded as successful (#143); the deployable
   *  package opens only once this is set. null until a run has passed. */
  lastSuccessfulRun?: string | null;
  /** The session's latest sandbox run, whatever its outcome; the PoC tab shows
   *  it again after a reload. null until a run has been started. */
  latestRun?: string | null;
  /** Digest of the package the latest run was started on; absent or null where
   *  wizard_api keeps none. */
  latestRunPackage?: string | null;
  /** That digest for `lastSuccessfulRun`. Gate 3 is refused while the package
   *  that is there now has another digest (lib/poc-result-state). */
  lastSuccessfulRunPackage?: string | null;
  /** The mock store only: the digest of the session's package as it is now.
   *  With wizard_api it is read from the package itself (lib/sessions
   *  getPackageDigest). */
  packageDigest?: string | null;
  /** The message the wizard is answering right now. It is not in `messages`
   *  yet, so a page loaded mid-reply shows it from here and joins the reply. */
  pendingTurn?: PendingTurn | null;
  /** Whether a wizard is held for the session as it was read. When none is,
   *  the next message starts one first (lib/wizard-start). Absent in the mock
   *  store, and null from a wizard_api that does not say. */
  agentLive?: boolean | null;
  /** The gate reopened for a change that still waits for its new approval. */
  gateReopened?: GateReopened | null;
  /** How far the files the wizard has written reach, as wizard_api reads them
   *  (lib/gate-decision). Absent here in the mock store: it has no wizard. */
  reachedStep?: number | null;
};

export type PendingTurn = { userMessage: string; startedAt: string };

/** A gate whose approval was taken back for a change; set until it is approved again. */
export type GateReopened = {
  gate: number;
  by: "user" | "agent" | "change";
  reason: string;
  /** When it was reopened: tells one reopening from the next. */
  at?: string;
};

/** Business-facing framing surfaced at Gate 1 (from the agent's draft blueprint). */
export type BusinessContext = {
  currentProcess: string;
  painPoints: string[];
  intendedUsers: string[];
  reviewers: string[];
  expectedValue: string[];
  knowledgeProcesses: string[];
  domain: string;
};

/** One open assumption from the draft blueprint's assumptions[]. */
export type Assumption = {
  id: string;
  text: string;
  status: string;
  impact: string;
};

/** Fresh gathering state for a new session. */
function newRequirements(): { points: string[]; answers: string[] } {
  return { points: REQUIREMENT_POINTS, answers: [] };
}

function outputDirFor(id: string): string {
  return `output/sessions/${id}/`;
}

/**
 * Dummy blueprint for a brand-new session (#74).
 * Gives BPMN a few editable elements until schema design (#25) supplies real fields.
 */
export function defaultBlueprint(title: string): Blueprint {
  return {
    name: title,
    description:
      "Placeholder blueprint until schema design — replace with the agreed output fields.",
    goal: "Draft flow so BPMN and JSON are editable from the first session.",
    steps: [
      {
        id: "input",
        name: "Input",
        type: "io",
        description: "User or system input (placeholder)",
      },
      {
        id: "process",
        name: "Process",
        type: "ai",
        component: "LLM",
        description: "Core GenAI step (placeholder)",
      },
      {
        id: "review",
        name: "Human review",
        type: "human_review",
        description: "Optional check before output (placeholder)",
      },
      {
        id: "output",
        name: "Output",
        type: "io",
        description: "Returned result (placeholder)",
      },
    ],
  };
}

// --- Mock store (in memory) -------------------------------------------------

const now = () => new Date().toISOString();

function seedSession(
  id: string,
  userId: string,
  title: string,
  step: number,
  versionCount: number,
  createdDaysAgo: number,
  blueprint: Blueprint,
  messages: ChatMessage[] = [],
): WizardSession {
  const created = new Date(
    Date.now() - createdDaysAgo * 24 * 60 * 60 * 1000,
  ).toISOString();
  const versions: BlueprintVersion[] = Array.from(
    { length: versionCount },
    (_, i) => ({
      version: i + 1,
      createdAt: created,
      note: i === 0 ? "Initial blueprint" : `Change #${i + 1}`,
    }),
  );
  // In gathering with an empty chat, the backend opens with the first question
  // as a real (persisted) message — not a derived, disappearing greeting.
  const gathering = step <= 3;
  const seededMessages =
    gathering && messages.length === 0
      ? [
          {
            id: `msg_open_${id}`,
            role: "assistant" as ChatRole,
            content: openingQuestion(),
            createdAt: created,
          },
        ]
      : messages;
  return {
    id,
    userId,
    title,
    step,
    gateStatus: buildGateStatus(step),
    status: step >= PHASE_COUNT ? "done" : "active",
    outputDir: outputDirFor(id),
    createdAt: created,
    updatedAt: created,
    versions,
    activeVersion: versionCount,
    messages: seededMessages,
    blueprint,
    requirements: newRequirements(),
  };
}

// Seed data: three sessions at different steps so the list and stepper show
// real content. Owner = dev account so it shows in dev mode.
const DEV_OWNER = "dev@gaik.local";

function buildSeedSessions(): WizardSession[] {
  return [
  seedSession(
    "ses_chatbot",
    DEV_OWNER,
    "Customer service chatbot",
    6,
    3,
    5,
    {
      name: "Customer service chatbot",
      description:
        "Answers customers' most common questions in the online store.",
      goal: "Reduce customer service load by automating common questions.",
      integration_targets: ["knowledge_base"],
      steps: [
        {
          id: "input",
          name: "Customer question",
          type: "io",
          description: "Chat input in the online store",
        },
        {
          id: "retrieve",
          name: "Retrieval (RAG)",
          type: "ai",
          component: "pgvector",
          description: "Fetch relevant help articles",
          settings: { top_k: "5", similarity_threshold: "0.75" },
        },
        {
          id: "generate",
          name: "Response generation",
          type: "ai",
          component: "Azure OpenAI",
          description: "Compose an answer from the retrieved content",
          settings: { model: "gpt-4o", temperature: "0.2" },
        },
        {
          id: "review",
          name: "Human review",
          type: "human_review",
          description: "Uncertain cases are routed to a human",
        },
        {
          id: "respond",
          name: "Reply to the customer",
          type: "io",
          description: "Send the answer to the chat",
        },
      ],
    },
    [
    {
      id: "msg_seed1",
      role: "user",
      content:
        "We'd like a chatbot that answers customers' most common questions in the online store.",
      createdAt: new Date(Date.now() - 5 * 86400000).toISOString(),
    },
    {
      id: "msg_seed2",
      role: "assistant",
      content:
        "Got it. I've noted customer service automation as the goal. What are the main question types the bot should answer?",
      createdAt: new Date(Date.now() - 5 * 86400000 + 60000).toISOString(),
    },
  ]),
  {
    // The fields this solution extracts, as wizard_api reads them from the
    // agent's draft blueprint: the Blueprint tab lists them.
    targetOutputSpec: {
      schemaName: "InvoiceClassification",
      fields: ["supplier_name", "invoice_number", "invoice_date", "total_amount", "cost_center", "account"],
      fieldTypes: {
        supplier_name: "str",
        invoice_number: "str",
        invoice_date: "date",
        total_amount: "decimal",
        cost_center: "str",
        account: "str",
      },
      requiredFields: ["supplier_name", "invoice_number", "invoice_date", "total_amount"],
      optionalFields: ["cost_center", "account"],
      fieldDescriptions: {
        supplier_name: "The supplier as written on the invoice.",
        total_amount: "The total with VAT, in the invoice's currency.",
      },
      allowedValues: { cost_center: ["Sales", "Production", "Administration"] },
      missingValuePolicy: "leave_empty",
      validationRules: [],
    },
    ...seedSession(
    "ses_laskut",
    DEV_OWNER,
    "Automatic invoice classification",
    11,
    7,
    12,
    {
      name: "Automatic invoice classification",
      description: "Classify incoming purchase invoices by cost center.",
      goal: "Speed up invoice handling with automatic pre-classification.",
      integration_targets: ["finance_system"],
      steps: [
        {
          id: "ingest",
          name: "Invoice intake",
          type: "io",
          description: "PDF/e-invoice in",
        },
        {
          id: "extract",
          name: "Data extraction",
          type: "ai",
          component: "docling",
          description: "Extract amounts, supplier, references",
        },
        {
          id: "classify",
          name: "Classification",
          type: "ai",
          component: "LLM",
          description: "Suggest cost center and account",
        },
        {
          id: "approve",
          name: "Approval",
          type: "human_review",
          description: "Accountant confirms the classification",
        },
        {
          id: "export",
          name: "Export to finance system",
          type: "io",
          description: "Transfer to the system",
        },
      ],
    },
  ),
  },
  seedSession("ses_cv", DEV_OWNER, "Recruitment CV screening", 2, 1, 1, {
    name: "Recruitment CV screening",
    description: "Screen applications against the open role's criteria.",
    goal: "Save recruiter time with pre-screening.",
    steps: [
      { id: "input", name: "Applications", type: "io", description: "CVs in" },
      {
        id: "score",
        name: "Scoring",
        type: "ai",
        component: "LLM",
        description: "Compare against criteria",
      },
      {
        id: "review",
        name: "Recruiter review",
        type: "human_review",
        description: "A human makes the final choice",
      },
      { id: "output", name: "Shortlist", type: "io", description: "Selected candidates forward" },
    ],
  }),
  // -- E2E-only fixtures below: dedicated, isolated sessions so gate-review
  // tests never mutate the three narrative fixtures above (and vice versa).
  {
    ...seedSession(
      "ses_gate1_ready",
      DEV_OWNER,
      "Gate 1 — ready to approve (e2e fixture)",
      4,
      1,
      0,
      {
        name: "Gate 1 ready fixture",
        description: "",
        goal: "",
        steps: [
          { id: "input", name: "Input", type: "io" },
          { id: "process", name: "Process", type: "ai", component: "LLM" },
        ],
      },
    ),
    businessContext: {
      currentProcess: "Three people manually review invoices every morning.",
      painPoints: ["Slow", "Error-prone"],
      intendedUsers: ["Finance team"],
      reviewers: ["Finance lead"],
      expectedValue: ["Faster processing", "Fewer manual errors"],
      // One identifier as the agent writes it, one in plain words.
      knowledgeProcesses: ["knowledge_capture", "Invoice review"],
      domain: "Finance",
    },
    assumptions: [
      {
        id: "a1",
        text: "Invoices arrive as PDF email attachments.",
        status: "confirmed",
        impact: "low",
      },
      {
        id: "a2",
        text: "Currency is always EUR.",
        status: "unconfirmed",
        impact: "medium",
      },
      // A long text, and impacts as the agent writes them: a known
      // identifier and one the interface has no label for.
      {
        id: "a3",
        text: "Scanned invoices from the two largest suppliers have handwritten corrections in the margins, and those corrections override the printed totals.",
        status: "unconfirmed",
        impact: "component_selection",
      },
      {
        id: "a4",
        text: "Approved invoices are kept for six years.",
        status: "confirmed",
        impact: "data_retention_policy",
      },
    ],
  },
  // businessContext intentionally omitted — approve must stay disabled.
  seedSession(
    "ses_gate1_blocked",
    DEV_OWNER,
    "Gate 1 — missing context (e2e fixture)",
    4,
    1,
    0,
    {
      name: "Gate 1 blocked fixture",
      description: "",
      goal: "",
      steps: [{ id: "input", name: "Input", type: "io" }],
    },
  ),
  seedSession(
    "ses_gate2_pending",
    DEV_OWNER,
    "Gate 2 — pending review (e2e fixture)",
    9,
    1,
    0,
    {
      name: "Gate 2 fixture",
      description: "",
      goal: "",
      steps: [
        { id: "input", name: "Input", type: "io" },
        { id: "process", name: "Process", type: "ai", component: "LLM" },
      ],
    },
  ),
  // e2e/chat-and-gates-sync.spec.ts: a page loaded while the wizard is replying.
  {
    ...seedSession(
      "ses_reply_pending",
      DEV_OWNER,
      "Reply pending (e2e fixture)",
      6,
      1,
      0,
      {
        name: "Reply pending fixture",
        description: "",
        goal: "",
        steps: [
          { id: "input", name: "Input", type: "io" },
          { id: "process", name: "Process", type: "ai", component: "LLM" },
        ],
      },
    ),
    pendingTurn: { userMessage: "Lisää tarkastusvaihe.", startedAt: new Date(0).toISOString() },
  },
  // e2e/chat-composer.spec.ts: a session whose wizard was released, as
  // wizard_api reports it (agent_live: false).
  {
    ...seedSession(
      "ses_wizard_released",
      DEV_OWNER,
      "Wizard released (e2e fixture)",
      6,
      1,
      0,
      {
        name: "Wizard released fixture",
        description: "",
        goal: "",
        steps: [
          { id: "input", name: "Input", type: "io" },
          { id: "process", name: "Process", type: "ai", component: "LLM" },
        ],
      },
    ),
    agentLive: false,
  },
  // The same spec: reopening an approved gate, the done card, the language button.
  seedSession(
    "ses_gates_sync",
    DEV_OWNER,
    "Gates in step (e2e fixture)",
    10,
    1,
    0,
    {
      name: "Gates fixture",
      description: "",
      goal: "",
      steps: [
        { id: "input", name: "Input", type: "io" },
        { id: "process", name: "Process", type: "ai", component: "LLM" },
      ],
    },
  ),
  // The same spec: the last gate, with every earlier one approved.
  seedSession(
    "ses_last_gate",
    DEV_OWNER,
    "Last gate (e2e fixture)",
    13,
    1,
    0,
    {
      name: "Last gate fixture",
      description: "",
      goal: "",
      steps: [
        { id: "input", name: "Input", type: "io" },
        { id: "process", name: "Process", type: "ai", component: "LLM" },
      ],
    },
  ),
  seedSession(
    "ses_ui_basics",
    DEV_OWNER,
    "UI basics (e2e fixture)",
    6,
    1,
    0,
    {
      name: "UI basics fixture",
      description: "",
      goal: "",
      steps: [
        { id: "input", name: "Input", type: "io" },
        { id: "process", name: "Process", type: "ai", component: "LLM" },
      ],
    },
    [
      {
        id: "msg_md_1",
        role: "user",
        content: "What components are involved?",
        createdAt: new Date(0).toISOString(),
      },
      {
        id: "msg_md_2",
        role: "assistant",
        // Markdown fixture: bold, a list item, and inline code — checks
        // renderMarkdown() actually produces HTML, not raw *­/`-`/`` ` ``.
        content:
          "Here's what's involved:\n\n- **Component A** handles intake\n- Component B does `lookup(id)`\n\n" +
          // GAIK components by name (e2e/chat-component-cards.spec.ts): in a
          // sentence, as inline code, twice, and in a table.
          "VisionExtractor reads the scanned invoices and `SchemaGenerator` proposes the fields. " +
          "VisionExtractor needs no separate parser.\n\n" +
          "| Step | Component |\n| --- | --- |\n| Check the result against the source document | SourceTracing |\n",
        createdAt: new Date(1).toISOString(),
      },
    ],
  ),
  ];
}

type MockGlobal = typeof globalThis & { __wizardMockSessions?: WizardSession[] };

const mockGlobal = globalThis as MockGlobal;
if (!mockGlobal.__wizardMockSessions) {
  mockGlobal.__wizardMockSessions = buildSeedSessions();
}
const sessions = mockGlobal.__wizardMockSessions;

/** Dev/test: restore seeded sessions (e.g. between E2E runs). */
export function resetMockSessions(): void {
  const fresh = buildSeedSessions();
  sessions.length = 0;
  sessions.push(...fresh);
}

// --- Read operations --------------------------------------------------------

export function deleteSession(id: string): void {
  const index = sessions.findIndex((s) => s.id === id);
  if (index >= 0) sessions.splice(index, 1);
}

export function listSessions(userId: string): WizardSession[] {
  return sessions
    .filter((s) => s.userId === userId)
    .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
}

export function getSession(id: string): WizardSession | undefined {
  return sessions.find((s) => s.id === id);
}

// --- Write operations (mutate the in-memory store) -------------------------

export function createSession(
  userId: string,
  title: string,
  options: { chatLed?: boolean } = {},
): WizardSession {
  const id = "ses_" + crypto.randomUUID().slice(0, 8);
  const ts = now();
  // Started from the user's first message, as the live wizard's sessions are:
  // the conversation begins with that message and there is no checklist.
  const chatLed = options.chatLed === true;
  const s: WizardSession = {
    id,
    userId,
    title: title.trim() || "Nimetön sessio",
    step: 1,
    gateStatus: buildGateStatus(1),
    status: "active",
    outputDir: outputDirFor(id),
    createdAt: ts,
    updatedAt: ts,
    versions: [{ version: 1, createdAt: ts, note: "Alustava blueprint" }],
    activeVersion: 1,
    // A new session starts in gathering: the backend opens with the first
    // question as a persisted assistant message.
    messages: chatLed
      ? []
      : [
          {
            id: `msg_open_${id}`,
            role: "assistant",
            content: openingQuestion(),
            createdAt: ts,
          },
        ],
    blueprint: defaultBlueprint(title.trim() || "Nimetön sessio"),
    requirements: chatLed ? { points: [], answers: [] } : newRequirements(),
  };
  sessions.push(s);
  return s;
}

/** A new name for the session; its blueprint keeps the one it was made with. */
export function renameSession(id: string, title: string): WizardSession | undefined {
  const s = getSession(id);
  if (!s) return undefined;
  s.title = title;
  s.updatedAt = now();
  return s;
}

// Append the user message + (mock) assistant reply to the chat history.
// The reply text is passed in so it can be localized via i18n.
export function postMessage(
  id: string,
  userContent: string,
  assistantContent: string,
): WizardSession | undefined {
  const s = getSession(id);
  if (!s) return undefined;
  const mkId = () => "msg_" + crypto.randomUUID().slice(0, 8);
  s.messages.push({
    id: mkId(),
    role: "user",
    content: userContent,
    createdAt: now(),
  });
  s.messages.push({
    id: mkId(),
    role: "assistant",
    content: assistantContent,
    createdAt: now(),
  });
  s.updatedAt = now();
  return s;
}

// --- State transitions (delegated to the wizard state machine) --------------

// Apply a state-machine event to a session in place, mirroring the transition's
// side effects: a step advance records a new blueprint version and `done` flips
// the status. A no-op transition leaves the session untouched.
function applyTransition(s: WizardSession, event: WizardEvent): WizardSession {
  const t = transition({ step: s.step, gateStatus: s.gateStatus }, event);
  if (t.noop) return s;
  s.step = t.state.step;
  s.gateStatus = t.state.gateStatus;
  if (t.advanced) {
    const v = s.versions.length + 1;
    s.versions.push({ version: v, createdAt: now(), note: `Vaihe ${s.step}` });
    s.activeVersion = v;
  }
  s.status = t.done ? "done" : "active";
  s.updatedAt = now();
  return s;
}

// Advance to the next step. On a gate step, blocked until approved.
/**
 * Dev/test only: put a session on a given step directly.
 *
 * Gathering (steps 1-3) deliberately has no UI affordance to advance — the
 * agent moves the session on once it has collected the requirements. E2E
 * specs that need a session further along therefore cannot click their way
 * there in mock mode, and this is how they say so instead. Guarded by
 * DEV_AUTH at the route.
 */
export function setSessionStep(
  id: string,
  step: number,
  /** Also record (a run id) or clear (null) the successful test run: the mock has no sandbox to make one. */
  successfulRun?: string | null,
  /** The digests wizard_api keeps of the package: the one the successful run tested, and the one there now. */
  digests: { testedPackage?: string | null; packageDigest?: string | null } = {},
): WizardSession | undefined {
  const s = getSession(id);
  if (!s) return undefined;
  s.step = Math.min(Math.max(1, Math.trunc(step)), PHASE_COUNT);
  if (successfulRun !== undefined) s.lastSuccessfulRun = successfulRun;
  if (digests.testedPackage !== undefined) s.lastSuccessfulRunPackage = digests.testedPackage;
  if (digests.packageDigest !== undefined) s.packageDigest = digests.packageDigest;
  s.updatedAt = new Date().toISOString();
  return s;
}

/**
 * Dev/test helper: make a mock session start as one of the live agent's does.
 * That agent asks in the chat and keeps no requirement checklist, and its
 * conversation begins with the user's first message; the mock store seeds a
 * checklist and an opening question instead. E2E specs use this to see the
 * page such a session opens on (lib/session-start). Guarded by DEV_AUTH at the
 * route.
 */
export function startWithoutChecklist(id: string): WizardSession | undefined {
  const s = getSession(id);
  if (!s) return undefined;
  s.requirements = { points: [], answers: [] };
  s.messages = [];
  s.updatedAt = new Date().toISOString();
  return s;
}

export function advanceSession(id: string): WizardSession | undefined {
  const s = getSession(id);
  if (!s) return s;
  return applyTransition(s, "ADVANCE");
}

// Go back one step (does not remove versions).
export function regressSession(id: string): WizardSession | undefined {
  const s = getSession(id);
  if (!s) return s;
  return applyTransition(s, "REGRESS");
}

// Approve the current gate and advance (final gate → session done).
export function approveGate(id: string): WizardSession | undefined {
  const s = getSession(id);
  if (!s) return s;
  const gateStep = s.step;
  const after = applyTransition(s, "APPROVE_GATE");
  const reopenedStep = after.gateReopened ? GATE_STEPS[after.gateReopened.gate - 1] : undefined;
  if (reopenedStep === gateStep && after.gateStatus[gateStep] === "approved") {
    after.gateReopened = null;
  }
  return after;
}

// Take back the approval of a gate and of the gates after it: the session
// goes back onto that gate's step. Undefined when the gate is not approved.
export function reopenGate(id: string, gate: number): WizardSession | undefined {
  const s = getSession(id);
  const gateStep = GATE_STEPS[gate - 1];
  if (!s || !gateStep || s.gateStatus[gateStep] !== "approved") return undefined;
  s.step = gateStep;
  s.gateStatus = buildGateStatus(gateStep);
  s.status = "active";
  s.gateReopened = { gate, by: "user", reason: "", at: new Date().toISOString() };
  s.updatedAt = now();
  return s;
}

// Reject the current gate: it stays on the gate step with a rejected status.
// The reason goes to the agent as a chat turn from the page, not from here.
export function rejectGate(id: string): WizardSession | undefined {
  const s = getSession(id);
  if (!s) return s;
  const t = transition({ step: s.step, gateStatus: s.gateStatus }, "REJECT_GATE");
  if (t.noop) return s;
  s.step = t.state.step;
  s.gateStatus = t.state.gateStatus;
  s.status = "active";
  s.updatedAt = now();
  return s;
}

// Record one gathered requirement answer (steps 1–3, in point order). When every
// point has an answer, the state machine advances to Gate 1.
export function recordRequirementAnswer(
  id: string,
  answer: string,
): WizardSession | undefined {
  const s = getSession(id);
  if (!s?.requirements) return s;
  const { points, answers } = s.requirements;
  if (answers.length >= points.length) return s;
  s.requirements = { points, answers: [...answers, answer.trim()] };
  s.updatedAt = now();
  if (s.requirements.answers.length >= points.length) {
    applyTransition(s, "REQUIREMENTS_COMPLETE");
  }
  return s;
}

export function updateBlueprint(
  id: string,
  blueprint: Blueprint,
  note = "BPMN canvas sync",
): WizardSession | undefined {
  const s = getSession(id);
  if (!s) return undefined;
  s.blueprint = blueprint;
  const v = s.versions.length + 1;
  s.versions.push({ version: v, createdAt: now(), note });
  s.activeVersion = v;
  s.updatedAt = now();
  return s;
}
