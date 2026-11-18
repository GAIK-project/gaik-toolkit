import { describe, expect, it } from "vitest";
import { blueprintFieldKey, fieldInPlainWords } from "@/lib/blueprint-field-names";
import { dictionary } from "@/lib/i18n";

describe("blueprint field names", () => {
  it("reads the field an operation refusal names", () => {
    expect(blueprintFieldKey("operations[2].step_id")).toBe("step_id");
    expect(blueprintFieldKey("after")).toBe("after");
    expect(blueprintFieldKey("operations[0]")).toBeNull();
    expect(blueprintFieldKey(undefined)).toBeNull();
  });

  it("says a step's fields in plain words, in both languages", () => {
    expect(fieldInPlainWords("operations[0].name", dictionary("en"))).toBe("step name");
    expect(fieldInPlainWords("operations[0].after", dictionary("fi"))).toBe("edeltävä vaihe");
    for (const key of ["step_id", "name", "after", "before", "source", "target", "type", "description"]) {
      expect(dictionary("fi").blueprintFieldNames[key], key).toBeTruthy();
      expect(dictionary("en").blueprintFieldNames[key], key).toBeTruthy();
    }
  });

  it("says the fields of a rework or rejection path in plain words, in both languages", () => {
    expect(fieldInPlainWords("operations[0].outcome", dictionary("en"))).toBe("where the path leads");
    for (const key of ["attached_to", "outcome", "exception_id"]) {
      expect(dictionary("fi").blueprintFieldNames[key], key).toBeTruthy();
      expect(dictionary("en").blueprintFieldNames[key], key).toBeTruthy();
    }
  });

  it("says the fields of a data object's edits in plain words, in both languages", () => {
    expect(fieldInPlainWords("operations[0].artifact_id", dictionary("en"))).toBe("data object");
    for (const key of ["artifact_id", "label", "role"]) {
      expect(dictionary("fi").blueprintFieldNames[key], key).toBeTruthy();
      expect(dictionary("en").blueprintFieldNames[key], key).toBeTruthy();
    }
  });

  it("is null for a field it has no words for", () => {
    expect(fieldInPlainWords("operations[0].mystery", dictionary("en"))).toBeNull();
  });
});
