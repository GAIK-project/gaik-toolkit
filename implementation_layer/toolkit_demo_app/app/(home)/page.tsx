import { getUserAccessStatus, getWizardAccess } from "@/lib/queries/access";
import dynamic from "next/dynamic";
import { Hero } from "./components/hero";
import { GetStarted } from "./components/get-started";
import { OwnDataCallout } from "./components/own-data-callout";

const DemoCards = dynamic(() =>
  import("./components/demo-cards").then((mod) => mod.DemoCards),
);

export default async function HomePage() {
  const { user, isUnlocked, isTrial } = await getUserAccessStatus();
  const hasWizardAccess = await getWizardAccess();

  return (
    <div className="space-y-16">
      <div className="space-y-4">
        <Hero isAuthenticated={Boolean(user)} />
        <OwnDataCallout />
      </div>
      <DemoCards
        isUnlocked={isUnlocked || isTrial}
        isAuthenticated={Boolean(user)}
      />
      <GetStarted
        hasWizardAccess={hasWizardAccess}
        isAuthenticated={Boolean(user)}
      />
    </div>
  );
}
