import { describe, expect, it } from "vitest";
import {
  activityText,
  addStep,
  elapsedText,
  liveSteps,
  parseActivity,
  stepLine,
  type ChatActivityLabels,
  type TurnStep,
} from "./chat-activity";

const labels: ChatActivityLabels = {
  write: "Writing a file",
  writeFile: "Writing {file}",
  read: "Reading a file",
  readFile: "Reading {file}",
  run: "Running a check",
  search: "Looking something up",
  work: "Working on it",
  elapsed: "{s} s",
  steps: "What the wizard did ({n})",
  files: { "use_case.blueprint.json": "the solution plan", "output_schema.py": "the fields to extract" },
  diagram: "Diagram",
  diagramSteps: "Diagram, steps in order: {steps}",
  diagramDrawing: "Drawing the diagram",
  diagramExpand: "Enlarge",
  diagramClose: "Close",
  panel: {
    gatePlaceholder: "",
    referenceRemove: "",
    stop: "",
    stopping: "",
    stopped: "",
    background: "",
    nonTechnical: "",
    nonTechnicalText: "",
    nonTechnicalHint: "",
    technicalHint: "",
    quickHint: "",
    thoroughHint: "",
    technical: "",
    technicalText: "",
    pace: "",
    quick: "",
    quickText: "",
    thorough: "",
    thoroughText: "",
    start: { title: "", lede: "", placeholder: "", examples: "", exampleList: [] },
    gateApproved: "",
    languageOffer: { fi: { label: "", message: "" }, en: { label: "", message: "" } },
  },
};

describe("chat activity", () => {
  it("reads the activity of a stream event and ignores anything else", () => {
    expect(parseActivity({ activity: { kind: "write", file: "output_schema.py" } })).toEqual({
      kind: "write",
      file: "output_schema.py",
    });
    expect(parseActivity({ activity: { kind: "run", file: null } })).toEqual({ kind: "run", file: null });
    expect(parseActivity({ delta: "hi" })).toBeNull();
    expect(parseActivity({ heartbeat: true })).toBeNull();
    expect(parseActivity({ activity: { kind: "delete", file: "x" } })).toBeNull();
    expect(parseActivity(null)).toBeNull();
  });

  it("names the file when there is one, in plain words when it is one the wizard writes", () => {
    expect(activityText({ kind: "write", file: "output_schema.py" }, labels)).toBe("Writing the fields to extract");
    expect(activityText({ kind: "read", file: "use_case.blueprint.json" }, labels)).toBe("Reading the solution plan");
    expect(activityText({ kind: "write", file: null }, labels)).toBe("Writing a file");
    expect(activityText({ kind: "read", file: "a.json" }, labels)).toBe("Reading a.json");
    expect(activityText({ kind: "read", file: "raportti.pdf" }, labels)).toBe("Reading raportti.pdf");
    // A name is a key of the map only when it is one of its own entries.
    expect(activityText({ kind: "read", file: "constructor" }, labels)).toBe("Reading constructor");
    expect(activityText({ kind: "write", file: "$&.py" }, labels)).toBe("Writing $&.py");
    expect(activityText({ kind: "run", file: null }, labels)).toBe("Running a check");
    expect(activityText({ kind: "work", file: null }, labels)).toBe("Working on it");
  });

  it("shows the time only once a step has run for more than ten seconds", () => {
    expect(elapsedText(3, labels)).toBeNull();
    expect(elapsedText(10, labels)).toBeNull();
    expect(elapsedText(10.4, labels)).toBe("10 s");
    expect(elapsedText(45.7, labels)).toBe("45 s");
    expect(elapsedText(Number.NaN, labels)).toBeNull();
  });

  it("counts a step taken again straight away instead of listing it twice", () => {
    let steps: TurnStep[] = [];
    for (const text of ["Reading a.json", "Running a check", "Running a check", "Running a check", "Reading a.json"]) {
      steps = addStep(steps, text);
    }
    expect(steps.map(stepLine)).toEqual(["Reading a.json", "Running a check ×3", "Reading a.json"]);
  });

  it("shows the running step and the last two finished ones, newest first", () => {
    expect(liveSteps([])).toEqual({ current: null, finished: [] });
    let steps = addStep([], "Reading a.json");
    expect(liveSteps(steps)).toEqual({ current: "Reading a.json", finished: [] });
    for (const text of ["Running a check", "Running a check", "Writing a file", "Looking something up"]) {
      steps = addStep(steps, text);
    }
    expect(liveSteps(steps)).toEqual({
      current: "Looking something up",
      finished: [
        { at: 2, text: "Writing a file" },
        { at: 1, text: "Running a check ×2" },
      ],
    });
  });
});
