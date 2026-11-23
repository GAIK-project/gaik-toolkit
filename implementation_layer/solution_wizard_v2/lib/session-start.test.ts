import { describe, expect, it } from "vitest";
import { chatLeads, exampleIn, examplesOffered, toggleExample } from "./session-start";

const prompts = ["We turn voice messages into tickets.", "We extract invoice fields."];

describe("chatLeads", () => {
  it("is on while the wizard gathers requirements and keeps no checklist", () => {
    expect(chatLeads(1, [])).toBe(true);
    expect(chatLeads(2, [])).toBe(true);
  });

  it("is off where the workspace has a view of its own", () => {
    // The specification's fields, Gate 1 and everything after it.
    expect(chatLeads(3, [])).toBe(false);
    expect(chatLeads(4, [])).toBe(false);
    // The mock store's checklist.
    expect(chatLeads(1, ["What is the input?"])).toBe(false);
  });

  it("is off once the wizard has recorded something to review, whatever the step", () => {
    // Stepped back from Gate 1: the requirements are there, the step is not.
    expect(chatLeads(2, [], { gathered: true })).toBe(false);
    expect(chatLeads(1, [], { gathered: true })).toBe(false);
    expect(chatLeads(2, [], { gathered: false })).toBe(true);
  });

  it("is never on while a gate waits for the user's decision", () => {
    expect(chatLeads(2, [], { gateWaiting: true })).toBe(false);
    expect(chatLeads(1, [], { gathered: true, gateWaiting: true })).toBe(false);
  });
});

describe("examples in the message field", () => {
  it("puts an example into an empty field", () => {
    expect(toggleExample("", prompts[0], prompts)).toBe(prompts[0]);
    expect(exampleIn(prompts[0], prompts)).toBe(0);
  });

  it("fills the field with the example's prompt and nothing else", () => {
    // Who the user is is a choice beside the field, not text in it.
    const picked = toggleExample("   ", prompts[1], prompts);
    expect(picked).toBe(prompts[1]);
    expect(exampleIn(picked, prompts)).toBe(1);
  });

  it("replaces one example with another, and takes a pressed one out again", () => {
    const first = toggleExample("", prompts[0], prompts);
    const second = toggleExample(first, prompts[1], prompts);
    expect(second).toBe(prompts[1]);
    expect(toggleExample(second, prompts[1], prompts)).toBe("");
  });

  it("leaves the user's own words alone and offers no example over them", () => {
    const own = "We sort customer e-mails by hand.";
    expect(examplesOffered(own, prompts)).toBe(false);
    expect(toggleExample(own, prompts[0], prompts)).toBe(own);
    expect(exampleIn(own, prompts)).toBeNull();
  });

  it("offers examples for an empty field and a picked example", () => {
    expect(examplesOffered("", prompts)).toBe(true);
    expect(examplesOffered("  \n", prompts)).toBe(true);
    expect(examplesOffered(`${prompts[0]} `, prompts)).toBe(true);
    // An example the user went on to edit is their own text.
    expect(examplesOffered(`${prompts[0]} In Finnish.`, prompts)).toBe(false);
  });
});
