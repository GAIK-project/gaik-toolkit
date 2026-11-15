import type { ReactNode } from "react";
import { MainLayout } from "@/components/layout/main-layout";

// The Solution Wizard page only points to where the wizard runs: nothing on it
// runs a model, so it has neither the demos' AI notice nor their sign-in notice.
export default function WizardLayout({ children }: { children: ReactNode }) {
  return <MainLayout contentWrapper="spaced">{children}</MainLayout>;
}
