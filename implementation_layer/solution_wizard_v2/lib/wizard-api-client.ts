import { TRACE_HEADER, getIncomingTraceId, getTraceId } from "@/lib/request-context";

const DEFAULT_API_URL = "http://localhost:8100";

/**
 * traceId for the outgoing wizard_api call (S3-10): prefer the
 * AsyncLocalStorage context withLogging set up (route handlers), falling
 * back to reading the header straight off the incoming request (Server
 * Actions, which never run inside that ALS scope).
 */
async function outgoingTraceId(): Promise<string> {
  return getTraceId() ?? (await getIncomingTraceId());
}

/** Shared service secret wizard_api checks on every call (#132). */
export const SERVICE_TOKEN_HEADER = "X-Wizard-Service-Token";

/**
 * The user this server-side call acts for (#134), as their owner id
 * (`lib/owner-id.ts`), never the e-mail address. wizard_api serves a
 * `/sessions/{id}/...` route only when the session belongs to this user, so
 * the proxy's own ownership check is no longer the last line.
 */
export const USER_ID_HEADER = "X-Wizard-User-Id";

async function currentUserIdForUpstream(): Promise<string | null> {
  try {
    // Lazy import: this module is also loaded where no request (and no cookie
    // store) exists — build steps, tests — and must not drag auth in there.
    const { getCurrentUser } = await import("@/lib/current-user");
    const user = await getCurrentUser();
    if (!user?.email) return null;
    const { ownerId } = await import("@/lib/owner-id");
    return ownerId(user.email);
  } catch {
    return null;
  }
}

/**
 * Headers every outgoing wizard_api call needs: the traceId (S3-10), the
 * service token (#132) and the user the call acts for (#134). Centralised so a new call site can't quietly omit the
 * token. When WIZARD_API_TOKEN is unset the header is simply absent, matching
 * the api's own "unconfigured = auth off" mode — that keeps local dev and the
 * docker stack working, and means this is inert until the deployment sets it.
 */
export async function outgoingHeaders(): Promise<Record<string, string>> {
  const headers: Record<string, string> = {
    [TRACE_HEADER]: await outgoingTraceId(),
  };
  const token = process.env.WIZARD_API_TOKEN?.trim();
  if (token) headers[SERVICE_TOKEN_HEADER] = token;
  const userId = await currentUserIdForUpstream();
  if (userId) headers[USER_ID_HEADER] = userId;
  return headers;
}

export function getWizardApiUrl(): string | null {
  const url = process.env.WIZARD_API_URL?.trim();
  return url || null;
}

export function wizardApiEnabled(): boolean {
  return Boolean(getWizardApiUrl());
}

/**
 * The wizard_api build version, read from its `/health` endpoint. The web image
 * carries its own NEXT_PUBLIC_APP_VERSION, but the backend that runs the agent
 * and scaffolds the PoC deploys independently, so the UI shows both. Best-effort:
 * returns null when the api is unset, unreachable, or slow, so the footer never
 * blocks a page render on it.
 */
export async function getApiVersion(): Promise<string | null> {
  const base = getWizardApiUrl() ?? DEFAULT_API_URL;
  try {
    const res = await fetch(`${base}/health`, {
      cache: "no-store",
      signal: AbortSignal.timeout(2000),
    });
    if (!res.ok) return null;
    const data = (await res.json()) as { version?: string };
    return data.version?.trim() || null;
  } catch {
    return null;
  }
}

// --- Agent chat (#29 frontend half) -----------------------------------------
//
// The live V1 agent runs in wizard_api (#29, backend — owned by wizard_api).
// This is only the FRONTEND consumer: when the agent chat endpoint is live we
// proxy the user's message to it and stream the reply straight through. It is
// gated behind an explicit opt-in flag so that, until that backend endpoint
// exists, dev/mock stays the default and nothing 404-spams.
//
// Proposed SSE contract (to confirm with wizard_api): the endpoint answers with
// `text/event-stream` frames identical to the UI's own chat SSE —
//   data: {"delta": "<token>"}   (repeated)
//   data: {"done": true}         (terminal)
//   data: {"error": true}        (on failure)
// so the route can pipe the upstream body through unchanged.

/** True when chat should be served by the wizard_api agent instead of the mock. */
export function wizardAgentChatEnabled(): boolean {
  return wizardApiEnabled() && process.env.WIZARD_AGENT_CHAT === "true";
}

/**
 * Open the upstream agent chat stream. Returns the raw fetch Response so the
 * caller can pipe `response.body` through as SSE. Never throws for HTTP errors —
 * the caller inspects `response.ok` and falls back to the mock on failure.
 */
export async function openAgentChatStream(
  id: string,
  message: string,
  locale?: string,
): Promise<Response> {
  const base = getWizardApiUrl() ?? DEFAULT_API_URL;
  return fetch(`${base}/sessions/${encodeURIComponent(id)}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      ...(await outgoingHeaders()),
    },
    // `locale` pins the agent's reply language to the UI locale (fi/en).
    body: JSON.stringify(locale ? { message, locale } : { message }),
    cache: "no-store",
  });
}

/**
 * Join the reply that is on its way for a session (GET /chat/stream): the
 * frames from the turn's first one. 204 when no turn is running. Returns the
 * raw Response, like openAgentChatStream.
 */
export async function openRunningChatStream(id: string): Promise<Response> {
  const base = getWizardApiUrl() ?? DEFAULT_API_URL;
  return fetch(`${base}/sessions/${encodeURIComponent(id)}/chat/stream`, {
    headers: { Accept: "text/event-stream", ...(await outgoingHeaders()) },
    cache: "no-store",
  });
}

async function wizardFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const base = getWizardApiUrl() ?? DEFAULT_API_URL;
  const res = await fetch(`${base}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(await outgoingHeaders()),
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new WizardApiError(res.status, path, text);
  }
  return res.json() as Promise<T>;
}

/**
 * A non-2xx answer from wizard_api; `code` is the `detail.error` of a
 * structured refusal and `reason` its `detail.reason`, where the api gives one
 * (a `gate_not_ready` for Gate 3 says `package_changed` when the package was
 * changed after the run that passed).
 */
export class WizardApiError extends Error {
  readonly status: number;
  readonly code: string | undefined;
  readonly reason: string | undefined;

  constructor(status: number, path: string, body: string) {
    super(`wizard_api ${status} ${path}: ${body}`);
    this.name = "WizardApiError";
    this.status = status;
    this.code = detailField(body, "error");
    this.reason = detailField(body, "reason");
  }
}

function detailField(body: string, field: "error" | "reason"): string | undefined {
  try {
    const detail = (JSON.parse(body) as { detail?: unknown }).detail;
    if (detail && typeof detail === "object" && field in detail) {
      const value = (detail as Record<string, unknown>)[field];
      return typeof value === "string" ? value : undefined;
    }
  } catch {
    // Not JSON: nothing to read.
  }
  return undefined;
}

export type ApiBlueprintVersion = {
  version: number;
  note: string;
  created_at: string;
};

export type ApiSessionDetail = {
  id: string;
  user_id: string;
  title: string;
  step: number;
  status: string;
  gate_statuses: Record<string, string>;
  metadata: Record<string, unknown>;
  output_dir: string;
  active_version: number;
  versions: ApiBlueprintVersion[];
  blueprint: {
    name: string;
    description: string;
    goal: string;
    steps: Array<{
      id: string;
      name: string;
      type: string;
      component?: string;
      description?: string;
    }>;
  };
  business_context?: {
    current_process: string;
    pain_points: string[];
    intended_users: string[];
    reviewers: string[];
    expected_value: string[];
    knowledge_processes: string[];
    domain: string;
  } | null;
  target_output_spec?: {
    schema_name: string;
    fields: string[];
    field_types: Record<string, string>;
    required_fields: string[];
    optional_fields: string[];
    field_descriptions: Record<string, string>;
    allowed_values: Record<string, string[]>;
    missing_value_policy: string;
    validation_rules: string[];
  } | null;
  assumptions?: Array<{
    id: string;
    text: string;
    status: string;
    impact: string;
  }>;
  messages: Array<{
    id: string;
    role: string;
    content: string;
    createdAt: string;
  }>;
  /** The message the wizard is answering right now; not in `messages` yet. */
  pending_turn?: { user_message: string; started_at: string } | null;
  /** Whether a wizard process is held for the session, or is starting, right now. */
  agent_live?: boolean;
  created_at: string;
  updated_at: string;
};

export type ApiSessionSummary = {
  id: string;
  user_id: string;
  step: number;
  gate_statuses: Record<string, string>;
  metadata: Record<string, unknown>;
  output_dir: string;
  active_version: number;
  created_at: string;
  updated_at: string;
};

export async function apiCreateSession(userId: string, title: string) {
  return wizardFetch<ApiSessionDetail>("/sessions", {
    method: "POST",
    body: JSON.stringify({ user_id: userId, title }),
  });
}

/** Raw Response: the caller tells a refusal (409) from a failure by its status. */
export async function apiDeleteSession(id: string): Promise<Response> {
  const base = getWizardApiUrl() ?? DEFAULT_API_URL;
  return fetch(`${base}/sessions/${encodeURIComponent(id)}`, {
    method: "DELETE",
    headers: await outgoingHeaders(),
    cache: "no-store",
  });
}

/** Raw Response so the route can relay the zip. */
export async function apiExportSession(id: string): Promise<Response> {
  const base = getWizardApiUrl() ?? DEFAULT_API_URL;
  return fetch(`${base}/sessions/${encodeURIComponent(id)}/export`, {
    headers: await outgoingHeaders(),
    cache: "no-store",
  });
}

/**
 * Moves the sessions saved under the user's e-mail address (before owner ids)
 * to their owner id. The header names the owner id; the count is how many moved.
 */
export async function apiClaimLegacySessions(legacyUserId: string) {
  const data = await wizardFetch<{ moved: number }>("/owners/claim", {
    method: "POST",
    body: JSON.stringify({ legacy_user_id: legacyUserId }),
  });
  return data.moved;
}

export async function apiListSessions(userId: string) {
  const data = await wizardFetch<{ sessions: ApiSessionSummary[] }>(
    `/sessions?user_id=${encodeURIComponent(userId)}`,
  );
  return data.sessions;
}

export async function apiGetSession(id: string) {
  return wizardFetch<ApiSessionDetail>(`/sessions/${encodeURIComponent(id)}`);
}

export async function apiPatchSession(
  id: string,
  body: {
    step?: number;
    gate_statuses?: Record<string, string>;
    metadata?: Record<string, unknown>;
  },
) {
  return wizardFetch<ApiSessionDetail>(`/sessions/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

/** Releases the agent held for a session (POST …/agent/end); the session stays. */
export async function apiEndAgent(id: string) {
  return wizardFetch<{ ended: boolean }>(`/sessions/${encodeURIComponent(id)}/agent/end`, {
    method: "POST",
  });
}

/** Takes back the approval of gate 1–4 and of the gates after it (POST …/reopen). */
export async function apiReopenGate(id: string, gate: number, reason = "") {
  return wizardFetch<ApiSessionDetail>(
    `/sessions/${encodeURIComponent(id)}/gates/${gate}/reopen`,
    { method: "POST", body: JSON.stringify({ reason }) },
  );
}

export async function apiPostMessages(
  id: string,
  userContent: string,
  assistantContent: string,
) {
  return wizardFetch<ApiSessionDetail>(`/sessions/${encodeURIComponent(id)}/messages`, {
    method: "POST",
    body: JSON.stringify({
      user_content: userContent,
      assistant_content: assistantContent,
    }),
  });
}

export async function apiPostVersion(
  id: string,
  note: string,
  content?: ApiSessionDetail["blueprint"],
) {
  return wizardFetch<ApiSessionDetail>(`/sessions/${encodeURIComponent(id)}/versions`, {
    method: "POST",
    body: JSON.stringify({ note, content }),
  });
}

export async function apiPatchBlueprint(
  id: string,
  content: ApiSessionDetail["blueprint"],
  note = "Blueprint päivitetty",
) {
  return wizardFetch<ApiSessionDetail>(`/sessions/${encodeURIComponent(id)}/blueprint`, {
    method: "PATCH",
    body: JSON.stringify({ content, note }),
  });
}

export async function apiGetSessionBpmn(id: string): Promise<string> {
  const base = getWizardApiUrl() ?? DEFAULT_API_URL;
  const res = await fetch(`${base}/sessions/${encodeURIComponent(id)}/bpmn`, {
    headers: await outgoingHeaders(),
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`wizard_api ${res.status} /sessions/${id}/bpmn: ${text}`);
  }
  return res.text();
}

export async function apiSyncSessionBpmn(id: string, xml: string) {
  return wizardFetch<ApiSessionDetail>(`/sessions/${encodeURIComponent(id)}/bpmn/sync`, {
    method: "POST",
    body: JSON.stringify({ xml }),
  });
}

export type ApiPocFiles = {
  generated: boolean;
  files: string[];
  /** Whether the files add up to a package worth handing over (wizard_api's package check). */
  ready?: boolean;
  /** What is missing when `ready` is false. */
  problems?: string[];
  /** Digest of the files a preflight reads; a new one means the package was rewritten. */
  version?: string;
  /**
   * Digest of the package as a test run is tied to it: the session's
   * `last_successful_run_package` is this value as it was when the run that
   * passed was started. Absent from an api that does not keep it.
   */
  package_digest?: string;
};

/** List the files the PoC scaffolder produced (empty until it has run). */
export async function apiGetPocFiles(id: string): Promise<ApiPocFiles> {
  return wizardFetch<ApiPocFiles>(`/sessions/${encodeURIComponent(id)}/poc/files`);
}

/** One file in the package's sample_input/, as wizard_api lists it (#95). */
/** `uploaded` is false for an example the wizard wrote there itself. */
export type ApiPocInput = { name: string; bytes: number; uploaded?: boolean };

export async function apiListPocInputs(id: string): Promise<{ files: ApiPocInput[] }> {
  return wizardFetch<{ files: ApiPocInput[] }>(`/sessions/${encodeURIComponent(id)}/poc/input`);
}

/**
 * Add one sample input file to the session's package (#95). The multipart body
 * is passed on as built by the route; no Content-Type here, fetch sets the
 * boundary. Raw Response: the route relays 201, and the api's 409 (no package
 * yet) and 422 (name or size refused) with their messages.
 */
export async function apiUploadPocInput(id: string, form: FormData): Promise<Response> {
  const base = getWizardApiUrl() ?? DEFAULT_API_URL;
  return fetch(`${base}/sessions/${encodeURIComponent(id)}/poc/input`, {
    method: "POST",
    headers: await outgoingHeaders(),
    body: form,
    cache: "no-store",
  });
}

export async function apiDeletePocInput(id: string, name: string): Promise<Response> {
  const base = getWizardApiUrl() ?? DEFAULT_API_URL;
  return fetch(
    `${base}/sessions/${encodeURIComponent(id)}/poc/input/${encodeURIComponent(name)}`,
    { method: "DELETE", headers: await outgoingHeaders(), cache: "no-store" },
  );
}

/**
 * The package as someone else receives it (#143): served by wizard_api only
 * after a run it recorded as successful, without sample input and run output.
 * Raw Response so the route can relay the zip, or the api's 409 saying why not.
 */
export async function apiGetDeployablePocZip(id: string): Promise<Response> {
  const base = getWizardApiUrl() ?? DEFAULT_API_URL;
  return fetch(`${base}/sessions/${encodeURIComponent(id)}/poc/deployable`, {
    headers: await outgoingHeaders(),
    cache: "no-store",
  });
}

/**
 * Fetch the generated PoC folder as a zip. Returns the raw Response so the route
 * can stream the bytes straight through; caller checks `response.ok`.
 */
/**
 * Ask wizard_api to scaffold the PoC package from the session's active
 * blueprint (#93). Deterministic and repeatable — a second call after a
 * blueprint change rewrites the package rather than leaving the old one.
 * Returns the raw Response so the caller can distinguish "not generated"
 * from a transport or auth failure.
 */
export async function apiGeneratePoc(id: string): Promise<Response> {
  const base = getWizardApiUrl() ?? DEFAULT_API_URL;
  return fetch(`${base}/sessions/${encodeURIComponent(id)}/poc/generate`, {
    method: "POST",
    headers: await outgoingHeaders(),
    cache: "no-store",
  });
}

export async function apiGetPocZip(id: string): Promise<Response> {
  const base = getWizardApiUrl() ?? DEFAULT_API_URL;
  // outgoingHeaders(), not just the trace id: ServiceTokenMiddleware exempts
  // only /health and OPTIONS, so without the service token this 401s on every
  // deployment where WIZARD_API_TOKEN is set.
  return fetch(`${base}/sessions/${encodeURIComponent(id)}/poc`, {
    headers: await outgoingHeaders(),
    cache: "no-store",
  });
}

// --- Sandbox PoC runs (#91 / #92 / #94) -------------------------------------

/** Start a sandbox run of the session's generated package. */
export async function apiCreatePocRun(id: string): Promise<Response> {
  const base = getWizardApiUrl() ?? DEFAULT_API_URL;
  return fetch(`${base}/sessions/${encodeURIComponent(id)}/runs`, {
    method: "POST",
    headers: await outgoingHeaders(),
    cache: "no-store",
  });
}

/** Start the preflight of the session's generated package (#252). */
export async function apiCreatePocCheck(id: string): Promise<Response> {
  const base = getWizardApiUrl() ?? DEFAULT_API_URL;
  return fetch(`${base}/sessions/${encodeURIComponent(id)}/poc/check`, {
    method: "POST",
    headers: await outgoingHeaders(),
    cache: "no-store",
  });
}

/** Follow one run's output. The response is an SSE stream to pipe through. */
export async function apiStreamPocRun(id: string, runId: string): Promise<Response> {
  const base = getWizardApiUrl() ?? DEFAULT_API_URL;
  return fetch(
    `${base}/sessions/${encodeURIComponent(id)}/runs/${encodeURIComponent(runId)}/stream`,
    { headers: await outgoingHeaders(), cache: "no-store" },
  );
}

/** What a finished run wrote to output/, read from its log between the markers. */
export async function apiGetPocRunOutput(id: string, runId: string): Promise<Response> {
  const base = getWizardApiUrl() ?? DEFAULT_API_URL;
  return fetch(
    `${base}/sessions/${encodeURIComponent(id)}/runs/${encodeURIComponent(runId)}/output`,
    { headers: await outgoingHeaders(), cache: "no-store" },
  );
}

/** One file a run wrote to output/, as it wrote it (a PDF report included). */
export async function apiGetPocRunFile(id: string, runId: string, name: string): Promise<Response> {
  const base = getWizardApiUrl() ?? DEFAULT_API_URL;
  return fetch(
    `${base}/sessions/${encodeURIComponent(id)}/runs/${encodeURIComponent(runId)}/files/${encodeURIComponent(name)}`,
    { headers: await outgoingHeaders(), cache: "no-store" },
  );
}

/** Where a run got to, for a client that is not following the stream. */
export async function apiGetPocRun(id: string, runId: string): Promise<Response> {
  const base = getWizardApiUrl() ?? DEFAULT_API_URL;
  return fetch(
    `${base}/sessions/${encodeURIComponent(id)}/runs/${encodeURIComponent(runId)}`,
    { headers: await outgoingHeaders(), cache: "no-store" },
  );
}

/**
 * Cases (the generated solution in use): one relay for every
 * `/sessions/{id}/cases/...` call. `subpath` is checked by the route against
 * the shapes the api serves, so a caller cannot reach another api path.
 * Raw Response: the route passes JSON, the api's errors and input files through.
 */
export async function apiCases(id: string, subpath: string, init: RequestInit = {}): Promise<Response> {
  const base = getWizardApiUrl() ?? DEFAULT_API_URL;
  const suffix = subpath ? `/${subpath}` : "";
  return fetch(`${base}/sessions/${encodeURIComponent(id)}/cases${suffix}`, {
    ...init,
    headers: { ...(await outgoingHeaders()), ...(init.headers as Record<string, string> | undefined) },
    cache: "no-store",
  });
}
