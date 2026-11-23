import { describe, expect, it } from "vitest";
import {
  GAIK_BPMN_COLORS,
  resolveEventRole,
  resolveShapeRole,
  resolveTaskRole,
  shapeColorsFor,
} from "./gaik-palette";

describe("resolveTaskRole", () => {
  it("treats ServiceTask/SendTask as processing by default", () => {
    expect(resolveTaskRole("bpmn:ServiceTask", "Extract data")).toBe("processing");
  });

  it("treats a submit/send-to-database task as output", () => {
    expect(resolveTaskRole("bpmn:SendTask", "Submit to database")).toBe("output");
  });

  it("treats a review-ish UserTask as human", () => {
    expect(resolveTaskRole("bpmn:UserTask", "Manager review")).toBe("human");
  });

  it("treats a plain UserTask as input", () => {
    expect(resolveTaskRole("bpmn:UserTask", "Customer question")).toBe("input");
  });

  it("defaults unknown task types to processing", () => {
    expect(resolveTaskRole(undefined, "Something")).toBe("processing");
  });
});

describe("resolveEventRole", () => {
  it("treats a reject/fail EndEvent as reject", () => {
    expect(resolveEventRole("bpmn:EndEvent", "Rejected")).toBe("reject");
  });

  it("treats a plain EndEvent as output", () => {
    expect(resolveEventRole("bpmn:EndEvent", "Done")).toBe("output");
  });

  it("treats everything else as input (e.g. StartEvent)", () => {
    expect(resolveEventRole("bpmn:StartEvent", "Begin")).toBe("input");
  });
});

describe("resolveShapeRole", () => {
  it("treats gateways as human", () => {
    expect(resolveShapeRole("bpmn:ExclusiveGateway")).toBe("human");
    expect(resolveShapeRole("bpmn:ParallelGateway")).toBe("human");
  });

  it("delegates events to resolveEventRole", () => {
    expect(resolveShapeRole("bpmn:EndEvent", "Rejected")).toBe("reject");
  });

  it("delegates tasks to resolveTaskRole", () => {
    expect(resolveShapeRole("bpmn:UserTask", "Approve")).toBe("human");
  });

  it("treats a data store reference as output", () => {
    expect(resolveShapeRole("bpmn:DataStoreReference")).toBe("output");
  });

  it("defaults unknown shapes to input", () => {
    expect(resolveShapeRole("bpmn:TextAnnotation")).toBe("input");
  });
});

describe("shapeColorsFor", () => {
  it("returns the palette entry matching the resolved role", () => {
    expect(shapeColorsFor("bpmn:DataStoreReference")).toEqual(GAIK_BPMN_COLORS.output);
    expect(shapeColorsFor("bpmn:ExclusiveGateway")).toEqual(GAIK_BPMN_COLORS.human);
  });
});
