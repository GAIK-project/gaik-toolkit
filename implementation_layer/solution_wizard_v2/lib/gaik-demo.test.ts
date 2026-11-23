import { describe, expect, it } from "vitest";
import { gaikDemoUrl } from "./gaik-demo";

describe("gaikDemoUrl", () => {
  it("links to the GAIK demos when nothing is set", () => {
    expect(gaikDemoUrl(undefined)).toBe("https://gaik-demo.2.rahtiapp.fi/");
  });

  it("takes the address an instance sets", () => {
    expect(gaikDemoUrl(" https://gaik-demo-staging.2.rahtiapp.fi ")).toBe(
      "https://gaik-demo-staging.2.rahtiapp.fi/",
    );
    expect(gaikDemoUrl("http://localhost:3000")).toBe("http://localhost:3000/");
  });

  it("hides the link when the value is empty", () => {
    expect(gaikDemoUrl("")).toBeNull();
    expect(gaikDemoUrl("   ")).toBeNull();
  });

  it("hides the link for anything but an http(s) address", () => {
    expect(gaikDemoUrl("javascript:alert(1)")).toBeNull();
    expect(gaikDemoUrl("gaik-demo.2.rahtiapp.fi")).toBeNull();
  });
});
