"use client";

import { DemoPageHeader } from "@/components/demo/demo-page-header";
import { FeedbackButton } from "@/components/feedback";
import { WizardBanner } from "@/components/demo/wizard-banner";
import { Package } from "lucide-react";
import { UseCaseChooser } from "./use-case-chooser";

export default function LuvataOrderPage() {
  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      <DemoPageHeader
        icon={Package}
        title="Purchase Order Processing"
        description="Process purchase orders with BOM matching and automated pricing calculations"
      >
        <div className="mt-2 flex justify-end">
          <FeedbackButton demoType="luvata-order" />
        </div>
      </DemoPageHeader>

      {/* Two ways in: the built-in example, or your own documents and fields. */}
      <UseCaseChooser />

      <WizardBanner
        useCase="purchase order processing"
        image="/purchase-order-banner.jpg"
        imageAlt="A purchase order and a bill of materials on a desk, with a price list open on a laptop in a workshop"
        imagePosition="center"
      />
    </div>
  );
}
