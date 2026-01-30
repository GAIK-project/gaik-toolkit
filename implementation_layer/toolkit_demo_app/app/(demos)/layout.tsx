import type { ReactNode } from "react";
import { MainLayout } from "@/components/layout/main-layout";

export default function DemosLayout({ children }: { children: ReactNode }) {
  return <MainLayout contentWrapper="spaced">{children}</MainLayout>;
}
