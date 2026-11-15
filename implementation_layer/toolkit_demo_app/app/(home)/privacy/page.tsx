import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import {
  PRIVACY_LAST_UPDATED,
  PrivacyContent,
} from "@/components/privacy-content";

export const metadata: Metadata = {
  title: "Privacy Notice",
  description: "How the GAIK Toolkit Demo processes personal data",
};

export default function PrivacyPage() {
  return (
    <article className="mx-auto max-w-3xl">
      <Link
        href="/"
        className="text-muted-foreground hover:text-foreground mb-8 inline-flex items-center gap-2 text-sm no-underline"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to home
      </Link>

      <h1 className="mb-1 text-2xl font-semibold">Privacy Notice</h1>
      <p className="text-muted-foreground mb-6 text-sm">
        GAIK Toolkit Demo — Last updated {PRIVACY_LAST_UPDATED}
      </p>
      <PrivacyContent />
    </article>
  );
}
