import { wizardV2Url } from "@/lib/wizard-v2-url";
import { connection } from "next/server";
import { SolutionWizardNotice } from "./notice";

export default async function SolutionWizardPage() {
  // Read per request, so WIZARD_V2_URL can be set on a deployment without a
  // rebuild (a NEXT_PUBLIC_ variable would be fixed when the image is built).
  await connection();
  return (
    <SolutionWizardNotice wizardUrl={wizardV2Url(process.env.WIZARD_V2_URL)} />
  );
}
