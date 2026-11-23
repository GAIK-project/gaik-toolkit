import { describe, expect, it } from "vitest";
import { blueprintFieldKey, fieldInPlainWords, fieldName } from "@/lib/blueprint-field-names";
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

describe("fieldName", () => {
  it("fieldName names a step's dependency in both languages", () => {
    expect(fieldName("workflow.steps[3].depends_on", "en")).toBe("Step 4: comes after");
    expect(fieldName("workflow.steps[3].depends_on", "fi")).toBe("Vaihe 4: tulee jälkeen");
    // wizard_api names an invalid draft's field as pydantic does, dotted.
    expect(fieldName("workflow.steps.3.depends_on", "en")).toBe("Step 4: comes after");
  });

  it("fieldName returns an unknown path unchanged", () => {
    expect(fieldName("mystery.thing[2]", "en")).toBe("mystery.thing[2]");
    expect(fieldName("", "fi")).toBe("");
  });

  it("names every section of the blueprint in both languages", () => {
    const sections = [
      "blueprint_version", "metadata", "use_case", "business_spec", "technical_spec", "target_output_spec",
      "assumptions", "artifacts", "inputs", "outputs", "schemas", "components", "workflow", "business_process",
      "prompts", "models", "validation", "evaluation", "governance", "runtime", "package", "visualizations",
      "traceability", "change_log",
    ];
    for (const section of sections) {
      expect(fieldName(section, "en"), section).not.toBe(section);
      expect(fieldName(section, "fi"), section).not.toBe(section);
    }
    expect(fieldName("metadata", "en")).toBe("Metadata");
    expect(fieldName("use_case.name", "en")).toBe("Use case: name");
    expect(fieldName("use_case.name", "fi")).toBe("Käyttötapaus: nimi");
  });

  it("names the items of the lists and maps inside the sections", () => {
    expect(fieldName("artifacts.invoice.produced_by", "en")).toBe('Data object "invoice": made by');
    expect(fieldName("business_process.decision_points[1].branches[0].target", "en")).toBe(
      "Decision 2, branch 1: leads to",
    );
    expect(fieldName("business_process.participants.0.name", "fi")).toBe("Kaista 1: nimi");
    expect(fieldName("business_process.exceptions[0].outcome", "en")).toBe("Path 1: where the path leads");
    expect(fieldName("assumptions.2.text", "en")).toBe("Assumption 3: text");
    expect(fieldName("workflow.steps[0]", "en")).toBe("Step 1");
  });

  it("keeps what it has no words for as written, after the words it has", () => {
    expect(fieldName("models.extract.model", "en")).toBe("Models: extract › model");
    expect(fieldName("workflow.steps[1].mystery", "en")).toBe("Step 2: mystery");
    expect(fieldName("workflow.steps[1].depends_on[0]", "en")).toBe("Step 2: comes after [1]");
  });
});
