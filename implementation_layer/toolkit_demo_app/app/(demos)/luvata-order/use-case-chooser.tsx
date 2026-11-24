"use client";

import { UseCaseChooser as Chooser } from "@/components/demo/use-case-chooser";
import { CustomUseCase } from "./custom-use-case";
import { ExampleShowcase } from "./example-showcase";

/** The two ways into the demo: the built-in example, or your own documents and fields. */
export function UseCaseChooser() {
  return (
    <Chooser
      exampleDescription="A single-file extraction, or a multi-file order priced from a price list."
      createDescription="Extraction only: pick the fields to read from your purchase order, with optional bills of materials."
      ExampleSection={ExampleShowcase}
      CreateSection={CustomUseCase}
    />
  );
}
