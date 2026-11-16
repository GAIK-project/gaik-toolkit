import type { ReactNode } from "react";
import { MainLayout } from "@/components/layout/main-layout";

// The Solution Wizard page only offers the two wizards: nothing on it runs a
// model, so it has neither the demos' AI notice nor their sign-in notice. The
// first wizard's chat is a demo page, app/(demos)/solution-wizard/first.
export default function WizardLayout({ children }: { children: ReactNode }) {
  return <MainLayout contentWrapper="spaced">{children}</MainLayout>;
}
