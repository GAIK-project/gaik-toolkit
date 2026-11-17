import { getUserAccessStatus } from "@/lib/queries/access";
import { wizardV2Url } from "@/lib/wizard-v2-url";
import { connection } from "next/server";
import { SolutionWizardNotice } from "./notice";

export default async function SolutionWizardPage() {
  // Read per request, so WIZARD_V2_URL can be set on a deployment without a
  // rebuild (a NEXT_PUBLIC_ variable would be fixed when the image is built).
  await connection();
  // The first wizard runs in the browser for users an admin has granted it
  // (proxy.ts gates its API); everyone else is shown how to ask.
  let canRunFirstWizard = false;
  try {
    canRunFirstWizard = (await getUserAccessStatus()).wizardAccess;
  } catch {
    // Without a known state, offer the request instead of a button that fails.
  }
  return (
    <SolutionWizardNotice
      wizardUrl={wizardV2Url(process.env.WIZARD_V2_URL)}
      canRunFirstWizard={canRunFirstWizard}
    />
  );
}
