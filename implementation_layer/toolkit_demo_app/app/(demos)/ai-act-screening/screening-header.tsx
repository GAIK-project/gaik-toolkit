"use client";

import { DemoPageHeader } from "@/components/demo/demo-page-header";
import { Scale } from "lucide-react";

// A client component, because the header takes an icon component as a prop.
export function ScreeningHeader() {
  return (
    <DemoPageHeader
      icon={Scale}
      title="EU AI Act screening"
      description="Describe any AI use case, planned or already in use. An agent asks a few follow-up questions, then shows the risk class, what you must do and by when."
    />
  );
}
