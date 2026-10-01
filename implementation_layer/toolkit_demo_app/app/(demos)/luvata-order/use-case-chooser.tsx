"use client";

import { UseCaseChooser as Chooser } from "@/components/demo/use-case-chooser";
import { CustomUseCase } from "./custom-use-case";
import { ExampleShowcase } from "./example-showcase";

/** The two ways into the demo: the built-in example, or your own documents and fields. */
export function UseCaseChooser() {
  return (
    <Chooser
      exampleDescription="Nothing to prepare. Run a built-in purchase order and see what the demo does."
      examplePoints={[
        "Browse a ready-made purchase order, its BOMs and a price list",
        "See which fields are read from each document",
        "Process them in one click and explore the result",
      ]}
      createTitle="Test with your own data or examples (extraction only)"
      createDescription="Try the extraction on your own purchase orders, with the fields you need."
      createPoints={[
        "Upload your own purchase order, with or without BOMs",
        "Choose the fields to extract, or write your own prompt",
        "Generate a schema and test the extraction on your documents",
      ]}
      ExampleSection={ExampleShowcase}
      CreateSection={CustomUseCase}
    />
  );
}
