"use client";

import { DemoPageHeader } from "@/components/demo/demo-page-header";
import { UseCaseChooser } from "@/components/demo/use-case-chooser";
import { WizardBanner } from "@/components/demo/wizard-banner";
import { Headset } from "lucide-react";
import { HelpdeskCreateSection } from "./helpdesk-create-section";
import { HelpdeskExampleSection } from "./helpdesk-example-section";
import { HowItWorks } from "./how-it-works";

export default function HelpdeskChatbotPage() {
  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      <DemoPageHeader
        icon={Headset}
        title="Helpdesk Chatbot"
        description="A customer service assistant that answers from an organisation's own services and FAQ, shows its sources, and passes the question to a person when needed."
      >
        <div className="mt-3 flex justify-end">
          <HowItWorks />
        </div>
      </DemoPageHeader>

      <UseCaseChooser
        exampleDescription="Nothing to prepare. Pick a helpdesk and ask it a question, or watch a scripted conversation."
        examplePoints={[
          "Two helpdesks: a regional AI hub and a company's IT and HR desk",
          "Answers come only from the helpdesk's own services and FAQ, with the sources shown",
          "When a person is needed, the assistant asks before it opens a contact form",
        ]}
        createTitle="Test on your own data"
        createDescription="Upload your own documents and ask a helpdesk built only from them."
        createPoints={[
          "Upload Markdown, text, PDF or Word documents, and a CSV or Excel list of services, products or prices",
          "Ask questions in English or Finnish; the sources are shown",
          "Nothing is saved: your data stays in this session",
        ]}
        ExampleSection={HelpdeskExampleSection}
        CreateSection={HelpdeskCreateSection}
      />

      <WizardBanner
        useCase="helpdesk chatbot"
        image="/helpdesk-chatbot-banner.jpg"
        imageAlt="A small-business owner asking a chat assistant questions on a laptop in a bright office"
      />
    </div>
  );
}
