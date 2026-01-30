import type { ReactNode } from "react";
import { MainLayout } from "@/components/layout/main-layout";

export default function HomeLayout({ children }: { children: ReactNode }) {
  return <MainLayout>{children}</MainLayout>;
}
