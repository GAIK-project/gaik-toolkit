import { getUserAccessStatus } from "@/lib/queries/access";
import { wizardV2Url } from "@/lib/wizard-v2-url";
import { connection } from "next/server";
import { SolutionWizardNotice, type WizardAccount } from "./notice";

export default async function SolutionWizardPage() {
  // Read per request, so WIZARD_V2_URL can be set on a deployment without a
  // rebuild (a NEXT_PUBLIC_ variable would be fixed when the image is built).
  await connection();
  // Wizard V2 opens with an approved demo account, so the page says where this
  // visitor's account stands. The first wizard runs in the browser for users an
  // admin has granted it (proxy.ts gates its API).
  let account: WizardAccount = "signed-out";
  let canRunFirstWizard = false;
  try {
    const access = await getUserAccessStatus();
    account = access.isUnlocked
      ? "approved"
      : access.user
        ? "pending"
        : "signed-out";
    canRunFirstWizard = access.wizardAccess;
  } catch {
    // Without a known state, the page reads as for a visitor who is signed out.
  }
  return (
    <SolutionWizardNotice
      wizardUrl={wizardV2Url(process.env.WIZARD_V2_URL)}
      account={account}
      canRunFirstWizard={canRunFirstWizard}
    />
  );
}
