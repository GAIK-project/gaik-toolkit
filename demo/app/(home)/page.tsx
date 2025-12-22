import { DemoCards } from "./components/demo-cards";
import { Hero } from "./components/hero";
import { InstallSnippet } from "./components/install-snippet";

export default function HomePage() {
  return (
    <div className="space-y-24">
      <Hero />
      <DemoCards />
      <InstallSnippet />
    </div>
  );
}
