import { describe, expect, it } from "vitest";
import { choiceChanged, choiceCorrection, pickedInOrder, type ChangeChoices } from "./change-choice";

const processes: ChangeChoices = {
  legend: "Which of these apply?",
  multiple: true,
  options: [
    { value: "knowledge_capture", label: "Capturing knowledge", sent: "capturing knowledge (knowledge capture)" },
    { value: "knowledge_access", label: "Finding knowledge", sent: "finding knowledge (knowledge access)" },
    { value: "knowledge_synthesis", label: "Combining knowledge" },
  ],
  selected: ["knowledge_capture"],
  message: "The right knowledge processes: {choice}",
  other: "Something else",
};

const holds: ChangeChoices = {
  legend: "Does the assumption hold?",
  options: [
    { value: "yes", label: "It holds", sent: "The assumption holds. Mark it confirmed." },
    { value: "no", label: "It does not hold", sent: "The assumption does not hold." },
  ],
  message: "{choice}",
  other: "What is correct?",
};

describe("a correction made by choosing", () => {
  it("has nothing to send while the choice is what holds now and nothing is written", () => {
    expect(choiceChanged(processes, ["knowledge_capture"])).toBe(false);
    expect(choiceCorrection(processes, ["knowledge_capture"], "  ")).toBe("");
    expect(choiceCorrection(holds, [], "")).toBe("");
  });

  it("says the choice in the options' order and in the words meant for the wizard", () => {
    expect(pickedInOrder(processes, ["knowledge_synthesis", "knowledge_capture", "other"])).toEqual([
      "knowledge_capture",
      "knowledge_synthesis",
    ]);
    expect(choiceCorrection(processes, ["knowledge_synthesis", "knowledge_capture"], "")).toBe(
      "The right knowledge processes: capturing knowledge (knowledge capture), Combining knowledge",
    );
  });

  it("puts what the user wrote under the choice", () => {
    expect(choiceCorrection(holds, ["no"], " Also SEK and NOK. ")).toBe(
      "The assumption does not hold.\nAlso SEK and NOK.",
    );
    expect(choiceCorrection(holds, ["yes"], "")).toBe("The assumption holds. Mark it confirmed.");
  });

  it("sends the written words alone when nothing was chosen, or nothing changed", () => {
    expect(choiceCorrection(holds, [], "Also SEK and NOK.")).toBe("Also SEK and NOK.");
    expect(choiceCorrection(processes, ["knowledge_capture"], "It is the incident reports.")).toBe(
      "It is the incident reports.",
    );
    // Every option unticked says nothing by itself.
    expect(choiceCorrection(processes, [], "")).toBe("");
  });
});
