import { describe, expect, test } from "bun:test";
import { failureMessage } from "./api-client";

describe("failureMessage", () => {
  test("shows the proxy's reason for a refused run", async () => {
    const response = Response.json(
      { error: "Sign in to use this feature." },
      { status: 401 },
    );
    expect(await failureMessage(response, "Failed to process the report")).toBe(
      "Sign in to use this feature.",
    );
  });

  test("prefers the backend's detail", async () => {
    const response = Response.json(
      { detail: "The file is empty.", error: "other" },
      { status: 400 },
    );
    expect(await failureMessage(response, "fallback")).toBe(
      "The file is empty.",
    );
  });

  test("falls back when the body is not JSON or has no reason", async () => {
    expect(
      await failureMessage(new Response("<html>", { status: 502 }), "fallback"),
    ).toBe("fallback");
    expect(
      await failureMessage(
        Response.json({ detail: [{ msg: "x" }] }, { status: 422 }),
        "fallback",
      ),
    ).toBe("fallback");
  });
});
