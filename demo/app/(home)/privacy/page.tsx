import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";

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

      <h1 className="text-foreground">Privacy Policy</h1>

      <p className="lead text-muted-foreground">
        This privacy policy explains how the GAIK Toolkit Demo application
        collects and processes your personal data.
      </p>

      <section>
        <h2 className="text-foreground">About GAIK Project</h2>
        <p>
          GAIK (Generative AI for Knowledge Management) is a research project
          funded by the European Regional Development Fund (ERDF). The project
          is led by Haaga-Helia University of Applied Sciences in collaboration
          with University of Helsinki, Tampere University, and industry
          partners.
        </p>
      </section>

      <section>
        <h2 className="text-foreground">Data We Collect</h2>
        <p>When you request access to the demo, we collect:</p>
        <ul>
          <li>
            <strong>Contact information:</strong> name and email address
          </li>
          <li>
            <strong>Optional information:</strong> company name and intended use
            case
          </li>
          <li>
            <strong>Account credentials:</strong> password (stored securely
            hashed)
          </li>
        </ul>
      </section>

      <section>
        <h2 className="text-foreground">How We Use Your Data</h2>
        <p>Your data is used exclusively to:</p>
        <ul>
          <li>Process and respond to your access request</li>
          <li>Provide you access to the GAIK Toolkit demo</li>
          <li>Contact you about the demo and related updates</li>
          <li>Improve the toolkit based on usage patterns (anonymized)</li>
        </ul>
      </section>

      <section>
        <h2 className="text-foreground">Data Storage</h2>
        <p>
          Your data is stored securely using Supabase, hosted in the EU. We
          retain your data only for the duration of the GAIK project (until
          January 2027) or until you request deletion.
        </p>
      </section>

      <section>
        <h2 className="text-foreground">Your Rights</h2>
        <p>Under GDPR, you have the right to:</p>
        <ul>
          <li>Access your personal data</li>
          <li>Correct inaccurate data</li>
          <li>Request deletion of your data</li>
          <li>Withdraw consent at any time</li>
        </ul>
      </section>

      <section>
        <h2 className="text-foreground">Contact</h2>
        <p>
          For questions about your data or to exercise your rights, contact the
          GAIK project team at Haaga-Helia University of Applied Sciences.
        </p>
      </section>

      <footer className="border-border mt-12 border-t pt-6">
        <p className="text-muted-foreground text-sm">
          Last updated: January 2025
        </p>
      </footer>
    </article>
  );
}
