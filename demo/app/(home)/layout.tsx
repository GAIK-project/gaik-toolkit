import type { ReactNode } from "react";
import { FooterServer } from "@/components/layout/footer-server";
import { SiteNavServer } from "@/components/layout/site-nav-server";

export default async function HomeLayout({
  children,
}: {
  children: ReactNode;
}) {
  return (
    <div className="flex min-h-screen flex-col">
      <SiteNavServer />
      <main className="mx-auto w-full max-w-6xl px-6 pt-24 pb-24 sm:px-8">
        {children}
      </main>
      <FooterServer />
    </div>
  );
}
