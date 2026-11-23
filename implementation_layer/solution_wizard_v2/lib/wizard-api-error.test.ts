import { describe, expect, it } from "vitest";
import { WizardApiError } from "@/lib/wizard-api-client";

describe("WizardApiError", () => {
  it("reads the code of a structured refusal", () => {
    const body = JSON.stringify({
      detail: { error: "gate_not_ready", gate: "gate_2", missing: "the workflow diagram" },
    });
    const err = new WizardApiError(409, "/sessions/x", body);
    expect(err.status).toBe(409);
    expect(err.code).toBe("gate_not_ready");
    expect(err.message).toBe(`wizard_api 409 /sessions/x: ${body}`);
  });

  it("reads the reason of a refusal that gives one", () => {
    // Gate 3 with a successful run of a package that has changed since.
    const body = JSON.stringify({
      detail: {
        error: "gate_not_ready",
        gate: "gate_3",
        missing: "a successful sandbox run of the package as it is now",
        reason: "package_changed",
        message: "The package changed after the last successful test run. Run the test again, then approve.",
      },
    });
    const err = new WizardApiError(409, "/sessions/x", body);
    expect(err.code).toBe("gate_not_ready");
    expect(err.reason).toBe("package_changed");
    // A refusal without one, as every other gate_not_ready is.
    const plain = JSON.stringify({ detail: { error: "gate_not_ready", gate: "gate_3" } });
    expect(new WizardApiError(409, "/sessions/x", plain).reason).toBeUndefined();
    expect(new WizardApiError(409, "/sessions/x", JSON.stringify({ detail: { reason: 3 } })).reason).toBeUndefined();
    expect(new WizardApiError(502, "/x", "Bad Gateway").reason).toBeUndefined();
  });

  it("has no code for a plain or non-JSON body", () => {
    expect(new WizardApiError(404, "/x", JSON.stringify({ detail: "session not found" })).code).toBeUndefined();
    expect(new WizardApiError(502, "/x", "Bad Gateway").code).toBeUndefined();
  });
});
