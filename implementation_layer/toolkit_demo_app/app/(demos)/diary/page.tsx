"use client";

import { DemoPageHeader } from "@/components/demo/demo-page-header";
import { ExtractionCreateSection } from "@/components/demo/extraction/extraction-create-section";
import { ExtractionExampleSection } from "@/components/demo/extraction/extraction-example-section";
import { UseCaseChooser } from "@/components/demo/use-case-chooser";
import { WizardBanner } from "@/components/demo/wizard-banner";
import { FeedbackButton } from "@/components/feedback";
import { HardHat } from "lucide-react";
import { DIARY_CONFIG } from "./diary-config";

function ExampleSection({ onCreate }: { onCreate: () => void }) {
  return <ExtractionExampleSection config={DIARY_CONFIG} onCreate={onCreate} />;
}

function CreateSection() {
  return <ExtractionCreateSection demo={DIARY_CONFIG} />;
}

export default function DiaryPage() {
  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <DemoPageHeader
        icon={HardHat}
        iconClassName="h-8 w-8 text-amber-500"
        title="Construction diary"
        description="Turn typed or dictated construction site diaries into structured daily entries"
      >
        <div className="mt-2 flex justify-end">
          <FeedbackButton demoType="construction-diary" />
        </div>
      </DemoPageHeader>

      <UseCaseChooser
        exampleDescription="Try English and Finnish examples, including a diary that covers several days."
        createTitle="Test on your own data or examples"
        createDescription="Pick the fields and language for your daily entries, then download them as a PDF."
        ExampleSection={ExampleSection}
        CreateSection={CreateSection}
      />

      <WizardBanner
        useCase="construction diary"
        image="/construction-diary-v1.png"
        imageAlt="A phone showing a construction diary app next to a construction site"
        imagePosition="center 52%"
      />
    </div>
  );
}
