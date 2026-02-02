import { getUserAccessStatus } from "@/lib/queries/access";
import { DemoCards } from "./components/demo-cards";
import { Hero } from "./components/hero";
import { InstallSnippet } from "./components/install-snippet";

export default async function HomePage() {
  const { isUnlocked } = await getUserAccessStatus();

  return (
    <div className="space-y-24">
      <Hero />
      <DemoCards isUnlocked={isUnlocked} />
      <InstallSnippet />
    </div>
  );
}
