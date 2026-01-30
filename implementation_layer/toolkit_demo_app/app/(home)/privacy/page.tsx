import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { PrivacyContent } from "@/components/privacy-content";

export const metadata: Metadata = {
  title: "Privacy Policy",
  description: "Privacy policy for GAIK Toolkit Demo",
};

export default function PrivacyPage() {
  return (
    <article className="prose dark:prose-invert mx-auto max-w-3xl">
      <Link
        href="/"
        className="text-muted-foreground hover:text-foreground mb-8 inline-flex items-center gap-2 text-sm no-underline"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to home
      </Link>

      <PrivacyContent />
    </article>
  );
}
