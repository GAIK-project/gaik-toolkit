"use client";

import { DemoPageHeader } from "@/components/demo/demo-page-header";
import { PageTransition } from "@/components/demo/page-transition";
import { UseCaseChooser } from "@/components/demo/use-case-chooser";
import { WizardBanner } from "@/components/demo/wizard-banner";
import { FeedbackButton } from "@/components/feedback";
import { FilePen } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useContext } from "react";
import { ReportWriterCreateSection } from "./create-section";
import { ReportWriterExampleSection } from "./example-section";
import { ReportWriterContext, useReportWriter } from "./use-report-writer";

function ExampleSection({ onCreate }: { onCreate: () => void }) {
  const rw = useContext(ReportWriterContext);
  return rw ? <ReportWriterExampleSection rw={rw} onCreate={onCreate} /> : null;
}

function CreateSection() {
  const rw = useContext(ReportWriterContext);
  return rw ? <ReportWriterCreateSection rw={rw} /> : null;
}

function ReportWriterPage() {
  const rw = useReportWriter();
  // The Construction Report Writing use case links here with ?example=<id>.
  const opensExample = useSearchParams().has("example");

  return (
    <ReportWriterContext.Provider value={rw}>
      <PageTransition>
        <div className="space-y-6">
          <DemoPageHeader
            icon={FilePen}
            title="Report Writer"
            description="Write a source-grounded report from recordings and documents, in three stages: normalize, curate and synthesize"
            className="mb-0"
          >
            <div className="mt-2 flex justify-end">
              <FeedbackButton demoType="report-writer-v2" />
            </div>
          </DemoPageHeader>

          <UseCaseChooser
            initialChoice={opensExample ? "example" : null}
            exampleDescription="Nothing to prepare. Write a construction report from site recordings and customer documents, and check where every statement comes from."
            examplePoints={[
              "Play the three site recordings and open the five customer documents",
              "See the seven sections the report will have",
              "Write the report and read the evidence behind each section",
            ]}
            createTitle="Test on your own data or examples"
            createDescription="Write a report from your own sources, with the sections and rules you define."
            createPoints={[
              "Add documents, spreadsheets, images or recordings",
              "Define the sections, the rules and an optional sample report",
              "Run the stages one at a time and correct the files in between",
            ]}
            ExampleSection={ExampleSection}
            CreateSection={CreateSection}
          />

          <WizardBanner
            useCase="construction report writing"
            image="/report-writer-banner.jpg"
            imageAlt="A site manager compares printed site photos with the report draft on a laptop in a site office"
            imagePosition="center 35%"
          />
        </div>
      </PageTransition>
    </ReportWriterContext.Provider>
  );
}

export default function ReportWriterV2Page() {
  return (
    <Suspense>
      <ReportWriterPage />
    </Suspense>
  );
}
