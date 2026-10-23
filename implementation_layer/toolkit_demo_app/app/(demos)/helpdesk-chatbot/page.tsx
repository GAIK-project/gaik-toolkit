"use client";

import { DemoPageHeader } from "@/components/demo/demo-page-header";
import { WizardBanner } from "@/components/demo/wizard-banner";
import { Headset } from "lucide-react";
import { HelpdeskChat } from "./helpdesk-chat";
import { HowItWorks } from "./how-it-works";

export default function HelpdeskChatbotPage() {
  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      <DemoPageHeader
        icon={Headset}
        title="Helpdesk Chatbot"
        description="A customer service assistant that answers from your organisation's own services and FAQ, shows its sources, and passes the question to a person when needed. The organisation here is fictional."
      >
        <div className="mt-3 flex justify-end">
          <HowItWorks />
        </div>
      </DemoPageHeader>

      <HelpdeskChat />

      <WizardBanner
        useCase="helpdesk chatbot"
        image="/helpdesk-chatbot-banner.jpg"
        imageAlt="A small-business owner asking a chat assistant questions on a laptop in a bright office"
      />
    </div>
  );
}
