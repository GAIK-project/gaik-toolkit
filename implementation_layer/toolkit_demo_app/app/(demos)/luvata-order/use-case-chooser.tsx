"use client";

import { UseCaseChooser as Chooser } from "@/components/demo/use-case-chooser";
import { CustomUseCase } from "./custom-use-case";
import { ExampleShowcase } from "./example-showcase";

/** The two ways into the demo: the built-in example, or your own documents and fields. */
export function UseCaseChooser() {
  return (
    <Chooser
      exampleDescription="Choose a single-file extraction or a multi-file order with pricing."
      createTitle="Test with your own data or examples (extraction only)"
      createDescription="Choose the fields to extract from a purchase order, with optional bills of materials."
      ExampleSection={ExampleShowcase}
      CreateSection={CustomUseCase}
    />
  );
}
