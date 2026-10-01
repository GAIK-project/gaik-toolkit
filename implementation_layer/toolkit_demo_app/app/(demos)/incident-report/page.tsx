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
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      <DemoPageHeader
        icon={AlertTriangle}
        iconClassName="h-8 w-8 text-amber-500"
        title="Incident Reporting"
        description="Turn incident reports, logs, recordings and photos of paper forms into structured reports"
      >
        <div className="mt-2 flex justify-end">
          <FeedbackButton demoType="incident-report" />
        </div>
      </DemoPageHeader>

      <UseCaseChooser
        exampleDescription="Nothing to prepare. Pick a ready-made incident report and see what the demo does."
        examplePoints={[
          "Text reports, a log with two incidents, a Finnish report and a spoken one",
          "See which details are read from each",
          "Click a value to see where it comes from in the source",
        ]}
        createTitle="Test on your own data or examples"
        createDescription="Try the extraction on your own reports, with the fields and language you need."
        createPoints={[
          "Type text, add a recording, or a photo or scan of a form",
          "Choose fields, add your own, or write the prompt",
          "Get one report for each incident, with a PDF you can download",
        ]}
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
