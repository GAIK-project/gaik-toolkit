import { beforeEach, describe, expect, it, vi } from "vitest";
import { GATE_STEPS, isGateStep } from "@/lib/wizard-state-machine";

const PHASE_COUNT = 13;

const mockFns = vi.hoisted(() => ({
  listSessions: vi.fn(),
  getSession: vi.fn(),
  createSession: vi.fn(),
  postMessage: vi.fn(),
  advanceSession: vi.fn(),
  regressSession: vi.fn(),
  approveGate: vi.fn(),
  recordRequirementAnswer: vi.fn(),
  updateBlueprint: vi.fn(),
  renameSession: vi.fn(),
}));

vi.mock("@/lib/mock-sessions", () => ({
  PHASE_COUNT: 13,
  GATE_STEPS,
  isGateStep,
  PHASES: [],
  BPMN_VISUAL_STEP: 8,
  isBpmnVisualPhase: (step: number) => step >= 8,
  listSessions: mockFns.listSessions,
  getSession: mockFns.getSession,
  createSession: mockFns.createSession,
  postMessage: mockFns.postMessage,
  advanceSession: mockFns.advanceSession,
  regressSession: mockFns.regressSession,
  approveGate: mockFns.approveGate,
  recordRequirementAnswer: mockFns.recordRequirementAnswer,
  updateBlueprint: mockFns.updateBlueprint,
  renameSession: mockFns.renameSession,
}));

const apiFns = vi.hoisted(() => ({
  apiClaimLegacySessions: vi.fn(),
  apiCreateSession: vi.fn(),
  apiGetSession: vi.fn(),
  apiListSessions: vi.fn(),
  apiPatchSession: vi.fn(),
  apiPatchBlueprint: vi.fn(),
  apiPostMessages: vi.fn(),
  apiPostVersion: vi.fn(),
  apiGetPocFiles: vi.fn(),
}));

const wizardApiState = vi.hoisted(() => ({ enabled: false }));

vi.mock("@/lib/wizard-api-client", async (original) => ({
  // The real error class: the mock store refuses as wizard_api does.
  WizardApiError: (await original<typeof import("@/lib/wizard-api-client")>()).WizardApiError,
  apiGetPocFiles: apiFns.apiGetPocFiles,
  apiClaimLegacySessions: apiFns.apiClaimLegacySessions,
  apiCreateSession: apiFns.apiCreateSession,
  apiGetSession: apiFns.apiGetSession,
  apiListSessions: apiFns.apiListSessions,
  apiPatchSession: apiFns.apiPatchSession,
  apiPatchBlueprint: apiFns.apiPatchBlueprint,
  apiPostMessages: apiFns.apiPostMessages,
  apiPostVersion: apiFns.apiPostVersion,
  wizardApiEnabled: () => wizardApiState.enabled,
}));

import {
  advanceSession,
  approveGate,
  createSession,
  getPackageDigest,
  getSession,
  listSessions,
  patchSessionBlueprint,
  postMessage,
  recordRequirementAnswer,
  regressSession,
  renameSessionTitle,
  resetClaimedOwnersForTests,
  saveBlueprintAfterBpmnSync,
} from "@/lib/sessions";
import { ownerId } from "@/lib/owner-id";

const ADDRESS = "alice@example.test";

const blueprint = { name: "Demo", description: "", goal: "", steps: [] };

function apiDetail(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: "s1",
    user_id: "u1",
    title: "Demo",
    step: 4,
    status: "active",
    gate_statuses: {},
    metadata: {},
    output_dir: "output/s1/",
    active_version: 1,
    versions: [],
    blueprint,
    messages: [],
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  wizardApiState.enabled = false;
  resetClaimedOwnersForTests();
});

describe("sessions.ts — mock mode (WIZARD_API_URL unset)", () => {
  beforeEach(() => {
    wizardApiState.enabled = false;
  });

  it("listSessions delegates to the mock store", async () => {
    mockFns.listSessions.mockResolvedValue([]);
    await listSessions("u1");
    expect(mockFns.listSessions).toHaveBeenCalledWith("u1");
    expect(apiFns.apiListSessions).not.toHaveBeenCalled();
  });

  it("getSession delegates to the mock store", async () => {
    mockFns.getSession.mockResolvedValue(undefined);
    await getSession("s1");
    expect(mockFns.getSession).toHaveBeenCalledWith("s1");
    expect(apiFns.apiGetSession).not.toHaveBeenCalled();
  });

  it("approveGate refuses Gate 3 as wizard_api does when the package changed after the run", async () => {
    mockFns.getSession.mockReturnValue({ step: 11, packageDigest: "d2", lastSuccessfulRunPackage: "d1" });
    await expect(approveGate("s1", 11)).rejects.toMatchObject({
      status: 409,
      code: "gate_not_ready",
      reason: "package_changed",
    });
    expect(mockFns.approveGate).not.toHaveBeenCalled();

    // The run tested this package, or no digest is kept: approved as before.
    mockFns.getSession.mockReturnValue({ step: 11, packageDigest: "d1", lastSuccessfulRunPackage: "d1" });
    await approveGate("s1", 11);
    mockFns.getSession.mockReturnValue({ step: 11 });
    await approveGate("s1", 11);
    // Another gate is not about a test run.
    mockFns.getSession.mockReturnValue({ step: 9, packageDigest: "d2", lastSuccessfulRunPackage: "d1" });
    await approveGate("s1", 9);
    expect(mockFns.approveGate).toHaveBeenCalledTimes(3);
  });

  it("getPackageDigest is the mock session's own, or null", async () => {
    mockFns.getSession.mockReturnValue({ packageDigest: "d2" });
    expect(await getPackageDigest("s1")).toBe("d2");
    mockFns.getSession.mockReturnValue({});
    expect(await getPackageDigest("s1")).toBeNull();
    mockFns.getSession.mockReturnValue(undefined);
    expect(await getPackageDigest("s1")).toBeNull();
    expect(apiFns.apiGetPocFiles).not.toHaveBeenCalled();
  });

  it("createSession delegates to the mock store", async () => {
    mockFns.createSession.mockResolvedValue({ id: "s1" });
    await createSession("u1", "Demo");
    expect(mockFns.createSession).toHaveBeenCalledWith("u1", "Demo");
    expect(apiFns.apiCreateSession).not.toHaveBeenCalled();
  });

  it("createSession hands the mock store a start from the first message", async () => {
    mockFns.createSession.mockResolvedValue({ id: "s1" });
    await createSession("u1", "Demo", { chatLed: true });
    expect(mockFns.createSession).toHaveBeenCalledWith("u1", "Demo", { chatLed: true });
  });

  it("renameSessionTitle renames in the mock store and says when the session is gone", async () => {
    mockFns.renameSession.mockReturnValueOnce({ id: "s1" });
    expect(await renameSessionTitle("s1", "Uusi nimi")).toBe(true);
    expect(mockFns.renameSession).toHaveBeenCalledWith("s1", "Uusi nimi");
    mockFns.renameSession.mockReturnValueOnce(undefined);
    expect(await renameSessionTitle("gone", "Uusi nimi")).toBe(false);
    expect(apiFns.apiPatchSession).not.toHaveBeenCalled();
  });

  it("recordRequirementAnswer delegates to the mock store", async () => {
    mockFns.recordRequirementAnswer.mockResolvedValue(undefined);
    await recordRequirementAnswer("s1", "answer");
    expect(mockFns.recordRequirementAnswer).toHaveBeenCalledWith("s1", "answer");
  });
});

describe("sessions.ts — wizard_api mode (WIZARD_API_URL set)", () => {
  beforeEach(() => {
    wizardApiState.enabled = true;
  });

  it("listSessions maps API summaries to WizardSession shape", async () => {
    apiFns.apiListSessions.mockResolvedValue([
      {
        id: "s1",
        user_id: "u1",
        step: 2,
        gate_statuses: {},
        metadata: {},
        output_dir: "output/s1/",
        active_version: 1,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    ]);
    const result = await listSessions(ADDRESS);
    expect(mockFns.listSessions).not.toHaveBeenCalled();
    expect(apiFns.apiListSessions).toHaveBeenCalledWith(ownerId(ADDRESS));
    expect(result[0].id).toBe("s1");
    expect(result[0].title).toBe("Nimetön sessio");
    expect(result[0].status).toBe("active");
  });

  it("sends wizard_api the owner id, never the address, and moves the old sessions once", async () => {
    apiFns.apiListSessions.mockResolvedValue([]);
    apiFns.apiClaimLegacySessions.mockResolvedValue(2);
    await listSessions(ADDRESS);
    await listSessions(ADDRESS);
    expect(apiFns.apiClaimLegacySessions).toHaveBeenCalledTimes(1);
    expect(apiFns.apiClaimLegacySessions).toHaveBeenCalledWith(ADDRESS);
    expect(apiFns.apiListSessions).toHaveBeenCalledWith(ownerId(ADDRESS));
    expect(JSON.stringify(apiFns.apiListSessions.mock.calls)).not.toContain("alice");
  });

  it("lists the sessions when moving the old ones fails, and tries the move again next time", async () => {
    apiFns.apiListSessions.mockResolvedValue([]);
    apiFns.apiClaimLegacySessions.mockRejectedValueOnce(new Error("404")).mockResolvedValue(0);
    await listSessions(ADDRESS);
    await listSessions(ADDRESS);
    expect(apiFns.apiClaimLegacySessions).toHaveBeenCalledTimes(2);
    expect(apiFns.apiListSessions).toHaveBeenCalledTimes(2);
  });

  it("getSession maps a full API detail and returns undefined on error", async () => {
    apiFns.apiGetSession.mockResolvedValueOnce(apiDetail());
    const found = await getSession("s1");
    expect(found?.id).toBe("s1");
    expect(found?.gateStatus[4]).toBe("pending"); // step=4 is Gate 1, no gate_statuses.gate_1 set

    apiFns.apiGetSession.mockRejectedValueOnce(new Error("404"));
    const missing = await getSession("missing");
    expect(missing).toBeUndefined();
  });

  it("createSession posts to the API and maps the result", async () => {
    apiFns.apiCreateSession.mockResolvedValue(apiDetail());
    const session = await createSession(ADDRESS, "Demo");
    expect(apiFns.apiCreateSession).toHaveBeenCalledWith(ownerId(ADDRESS), "Demo");
    expect(session.title).toBe("Demo");
  });

  it("createSession sends the live API no start option: every session there starts from the chat", async () => {
    apiFns.apiCreateSession.mockResolvedValue(apiDetail());
    await createSession(ADDRESS, "Demo", { chatLed: true });
    expect(apiFns.apiCreateSession).toHaveBeenCalledWith(ownerId(ADDRESS), "Demo");
  });

  it("renameSessionTitle patches the title in the session's metadata", async () => {
    apiFns.apiPatchSession.mockResolvedValueOnce(apiDetail());
    expect(await renameSessionTitle("s1", "Uusi nimi")).toBe(true);
    expect(apiFns.apiPatchSession).toHaveBeenCalledWith("s1", { metadata: { title: "Uusi nimi" } });
    apiFns.apiPatchSession.mockRejectedValueOnce(new Error("boom"));
    expect(await renameSessionTitle("s1", "Uusi nimi")).toBe(false);
    expect(mockFns.renameSession).not.toHaveBeenCalled();
  });

  it("postMessage posts and returns undefined on failure instead of throwing", async () => {
    apiFns.apiPostMessages.mockRejectedValueOnce(new Error("boom"));
    const result = await postMessage("s1", "hi", "hello");
    expect(result).toBeUndefined();
  });

  it("advanceSession patches the step and adds no version, since nothing in the blueprint changed", async () => {
    apiFns.apiGetSession.mockResolvedValue(apiDetail({ step: 1 }));
    await advanceSession("s1");
    expect(apiFns.apiPatchSession).toHaveBeenCalledWith("s1", { step: 2 });
    expect(apiFns.apiPostVersion).not.toHaveBeenCalled();
  });

  it("advanceSession is a no-op past the last step", async () => {
    apiFns.apiGetSession.mockResolvedValue(apiDetail({ step: PHASE_COUNT }));
    const result = await advanceSession("s1");
    expect(apiFns.apiPatchSession).not.toHaveBeenCalled();
    expect(result?.step).toBe(PHASE_COUNT);
  });

  it("regressSession patches the step back and reactivates the session", async () => {
    apiFns.apiGetSession.mockResolvedValue(apiDetail({ step: 2 }));
    await regressSession("s1");
    expect(apiFns.apiPatchSession).toHaveBeenCalledWith("s1", {
      step: 1,
      metadata: { status: "active" },
    });
  });

  it("approveGate patches gate_statuses and advances past a non-final gate", async () => {
    // First fetch (inside approveGate): gate not yet approved. Second fetch
    // (inside the advanceSession it triggers): as if the PATCH already landed.
    apiFns.apiGetSession
      .mockResolvedValueOnce(apiDetail({ step: 4, gate_statuses: {} }))
      .mockResolvedValueOnce(apiDetail({ step: 4, gate_statuses: { gate_1: "approved" } }));
    await approveGate("s1");
    expect(apiFns.apiPatchSession).toHaveBeenCalledWith("s1", {
      gate_statuses: { gate_1: "approved" },
    });
    // advanceSession runs next and issues a second patch for the step move.
    expect(apiFns.apiPatchSession).toHaveBeenCalledTimes(2);
    expect(apiFns.apiPatchSession).toHaveBeenCalledWith("s1", { step: 5 });
  });

  it("approveGate moves to the step after its own gate when another approval moved it first", async () => {
    // Two tabs approve Gate 1 at about the same time. This one read step 4; by the
    // time it moves on, the other has already put the session on step 5. It must
    // write step 5 again, not move on to step 6.
    apiFns.apiGetSession
      .mockResolvedValueOnce(apiDetail({ step: 4, gate_statuses: {} }))
      .mockResolvedValue(apiDetail({ step: 5, gate_statuses: { gate_1: "approved" } }));
    await approveGate("s1");
    expect(apiFns.apiPatchSession).toHaveBeenCalledWith("s1", { step: 5 });
    expect(apiFns.apiPatchSession).not.toHaveBeenCalledWith("s1", { step: 6 });
  });

  it("advanceSession from a given step moves nothing when the session has left that step", async () => {
    // A second approval of Gate 3 read the session on step 10; the first has
    // taken it to step 12 since. Moving "one step on" from there would put it
    // on Gate 4.
    apiFns.apiGetSession.mockResolvedValue(apiDetail({ step: 12 }));
    const result = await advanceSession("s1", 10);
    expect(apiFns.apiPatchSession).not.toHaveBeenCalled();
    expect(result?.step).toBe(12);

    apiFns.apiGetSession.mockResolvedValue(apiDetail({ step: 10 }));
    await advanceSession("s1", 10);
    expect(apiFns.apiPatchSession).toHaveBeenCalledWith("s1", { step: 11 });
  });

  it("approveGate for a given gate leaves another gate alone", async () => {
    apiFns.apiGetSession.mockResolvedValue(apiDetail({ step: 13 }));
    await approveGate("s1", 11);
    expect(apiFns.apiPatchSession).not.toHaveBeenCalled();
  });

  it("approveGate on the final gate marks the session done in one patch", async () => {
    apiFns.apiGetSession.mockResolvedValue(apiDetail({ step: PHASE_COUNT }));
    apiFns.apiPatchSession.mockResolvedValue(apiDetail({ step: PHASE_COUNT, status: "done" }));
    await approveGate("s1");
    expect(apiFns.apiPatchSession).toHaveBeenCalledWith("s1", {
      gate_statuses: { gate_4: "approved" },
      metadata: { status: "done" },
    });
  });

  it("approveGate is a no-op when the current step is not a gate step", async () => {
    apiFns.apiGetSession.mockResolvedValue(apiDetail({ step: 2 }));
    await approveGate("s1");
    expect(apiFns.apiPatchSession).not.toHaveBeenCalled();
  });

  it("getSession carries the digests kept with the runs, and null from an api without them", async () => {
    apiFns.apiGetSession.mockResolvedValue(
      apiDetail({
        metadata: {
          last_successful_run: "run-1",
          latest_run: "run-2",
          latest_run_package: "d2",
          last_successful_run_package: "d1",
          latest_run_inputs: ["order.pdf", 3, "scan.png"],
        },
      }),
    );
    expect(await getSession("s1")).toMatchObject({
      lastSuccessfulRun: "run-1",
      latestRun: "run-2",
      latestRunPackage: "d2",
      lastSuccessfulRunPackage: "d1",
      latestRunInputs: ["order.pdf", "scan.png"],
    });

    // wizard_api clears them with the runs when a gate is reopened (null), and
    // one without the change sends neither.
    apiFns.apiGetSession.mockResolvedValue(
      apiDetail({ metadata: { latest_run_package: null, last_successful_run_package: "" } }),
    );
    expect(await getSession("s1")).toMatchObject({ latestRunPackage: null, lastSuccessfulRunPackage: null });
    apiFns.apiGetSession.mockResolvedValue(apiDetail());
    expect(await getSession("s1")).toMatchObject({
      latestRunPackage: null,
      lastSuccessfulRunPackage: null,
      latestRunInputs: null,
    });
  });

  it("getPackageDigest reads the package's digest from its file list, and is null without one", async () => {
    apiFns.apiGetPocFiles.mockResolvedValue({ generated: true, files: [], version: "v1", package_digest: "d2" });
    expect(await getPackageDigest("s1")).toBe("d2");
    expect(apiFns.apiGetPocFiles).toHaveBeenCalledWith("s1");
    // An api that gives none, and one that cannot be read.
    apiFns.apiGetPocFiles.mockResolvedValue({ generated: true, files: [], version: "v1" });
    expect(await getPackageDigest("s1")).toBeNull();
    apiFns.apiGetPocFiles.mockRejectedValue(new Error("wizard_api 502"));
    expect(await getPackageDigest("s1")).toBeNull();
  });

  it("recordRequirementAnswer just re-fetches the session in API mode (agent owns gathering)", async () => {
    apiFns.apiGetSession.mockResolvedValue(apiDetail());
    await recordRequirementAnswer("s1", "answer");
    expect(mockFns.recordRequirementAnswer).not.toHaveBeenCalled();
    expect(apiFns.apiGetSession).toHaveBeenCalled();
  });

  it("patchSessionBlueprint / saveBlueprintAfterBpmnSync PATCH the blueprint and return undefined on failure", async () => {
    apiFns.apiPatchBlueprint.mockResolvedValueOnce(apiDetail());
    const saved = await patchSessionBlueprint("s1", blueprint, "note");
    expect(apiFns.apiPatchBlueprint).toHaveBeenCalledWith("s1", blueprint, "note");
    expect(saved?.id).toBe("s1");

    apiFns.apiPatchBlueprint.mockRejectedValueOnce(new Error("boom"));
    const failed = await saveBlueprintAfterBpmnSync("s1", blueprint);
    expect(failed).toBeUndefined();
  });
});
