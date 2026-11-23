import { describe, expect, it } from "vitest";
import { KNOWLEDGE_PROCESSES, known, knownList, knowledgeProcess } from "./known-values";

describe("known values", () => {
  it.each(["unknown", "Unknown", " UNKNOWN ", "n/a", "N/A", "na", "none", "TBD", "-", "tuntematon", "Ei tiedossa", "Ei vielä tiedossa", "Unknown.", "not known yet", ""])(
    "reads %j as not known",
    (value) => {
      expect(known(value)).toBeNull();
    },
  );

  it("keeps a real answer, also one that mentions the word", () => {
    expect(known("Three people review invoices by hand")).toBe("Three people review invoices by hand");
    expect(known("unknown suppliers are flagged")).toBe("unknown suppliers are flagged");
    expect(known(undefined)).toBeNull();
    expect(known(null)).toBeNull();
  });

  it("drops the placeholders from a list", () => {
    expect(knownList(["unknown", "Finance team", "n/a"])).toEqual(["Finance team"]);
    expect(knownList(undefined)).toEqual([]);
  });
});

describe("knowledge processes", () => {
  it("are the wizard's own three", () => {
    expect(KNOWLEDGE_PROCESSES).toEqual(["knowledge_capture", "knowledge_access", "knowledge_synthesis"]);
  });

  it.each([
    ["knowledge_capture", "knowledge_capture"],
    ["Knowledge capture", "knowledge_capture"],
    [" knowledge-access ", "knowledge_access"],
    ["synthesis", "knowledge_synthesis"],
  ] as const)("reads %j as %s", (value, process) => {
    expect(knowledgeProcess(value)).toBe(process);
  });

  it("has none for another value", () => {
    expect(knowledgeProcess("audit_trail")).toBeNull();
    expect(knowledgeProcess("Invoice review")).toBeNull();
    expect(knowledgeProcess("")).toBeNull();
  });
});
