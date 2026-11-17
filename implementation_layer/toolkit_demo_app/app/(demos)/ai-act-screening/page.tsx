import { ScreeningDemo } from "./screening-demo";
import { ScreeningHeader } from "./screening-header";

export const metadata = {
  title: "EU AI Act screening",
};

export default function AiActScreeningPage() {
  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      <ScreeningHeader />
      <ScreeningDemo />
    </div>
  );
}
