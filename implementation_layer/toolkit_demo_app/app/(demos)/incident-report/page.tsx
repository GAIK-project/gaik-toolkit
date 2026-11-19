"use client";

import { DemoPageHeader } from "@/components/demo/demo-page-header";
import { UseCaseChooser } from "@/components/demo/use-case-chooser";
import { WizardBanner } from "@/components/demo/wizard-banner";
import { FeedbackButton } from "@/components/feedback";
import { AlertTriangle } from "lucide-react";
import { ExtractionCreateSection } from "@/components/demo/extraction/extraction-create-section";
import { ExtractionExampleSection } from "@/components/demo/extraction/extraction-example-section";
import { INCIDENT_CONFIG } from "./incident-config";

function ExampleSection({ onCreate }: { onCreate: () => void }) {
  return (
    <ExtractionExampleSection config={INCIDENT_CONFIG} onCreate={onCreate} />
  );
}

function CreateSection() {
  return <ExtractionCreateSection demo={INCIDENT_CONFIG} />;
}

export default function IncidentReportPage() {
  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <DemoPageHeader
        icon={AlertTriangle}
        iconClassName="h-8 w-8 text-amber-500"
        title="Incident reporting"
        description="Turn incident reports, logs, recordings and photos of paper forms into structured reports"
      >
        <div className="mt-2 flex justify-end">
          <FeedbackButton demoType="incident-report" />
        </div>
      </DemoPageHeader>

      <UseCaseChooser
        exampleDescription="Try a shift log with two incidents, a Finnish report or a recording."
        createTitle="Test on your own data or examples"
        createDescription="Pick the fields and language for your reports, then download them as a PDF."
        ExampleSection={ExampleSection}
        CreateSection={CreateSection}
      />

      <WizardBanner
        useCase="incident reporting"
        image="/incident-report-banner.jpg"
        imageAlt="A worker phones in an incident report while a colleague picks up fallen boxes in a warehouse"
        imagePosition="30% 40%"
      />
    </div>
  );
}
