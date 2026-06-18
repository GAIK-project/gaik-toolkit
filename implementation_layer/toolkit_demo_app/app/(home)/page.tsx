import { getUserAccessStatus, getWizardAccess } from "@/lib/queries/access";
import dynamic from "next/dynamic";
import { Hero } from "./components/hero";
import { InstallSnippet } from "./components/install-snippet";

const DemoCards = dynamic(() =>
  import("./components/demo-cards").then((mod) => mod.DemoCards),
);

export default async function HomePage() {
  const { isUnlocked } = await getUserAccessStatus();
  const hasWizardAccess = await getWizardAccess();

  return (
    <div className="space-y-24">
      <Hero hasWizardAccess={hasWizardAccess} />
      <DemoCards isUnlocked={isUnlocked} />
      <InstallSnippet />
    </div>
  );
}
