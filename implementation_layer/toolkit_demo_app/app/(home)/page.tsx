import { getUserAccessStatus } from "@/lib/queries/access";
import dynamic from "next/dynamic";
import { Hero } from "./components/hero";
import { GetStarted } from "./components/get-started";
import { OwnDataCallout } from "./components/own-data-callout";
import { SolutionTools } from "./components/solution-tools";

const DemoCards = dynamic(() =>
  import("./components/demo-cards").then((mod) => mod.DemoCards),
);

export default async function HomePage() {
  const { user, isUnlocked, isTrial } = await getUserAccessStatus();
  const canRunDemos = isUnlocked || isTrial;

  return (
    <div className="space-y-16">
      <div className="space-y-4">
        <Hero isAuthenticated={Boolean(user)} />
        <SolutionTools canRunDemos={canRunDemos} />
        <OwnDataCallout />
      </div>
      <DemoCards isUnlocked={canRunDemos} isAuthenticated={Boolean(user)} />
      <GetStarted />
    </div>
  );
}
