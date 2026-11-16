import {
  Shield,
  Database,
  Eye,
  Scale,
  Mail,
  Building2,
  BarChart3,
  Cpu,
  ScrollText,
  Upload,
} from "lucide-react";
import { UPLOAD_REMINDER_TEXT } from "@/components/upload-reminder";

export const PRIVACY_LAST_UPDATED = "November 2026";

function Section({
  id,
  icon: Icon,
  title,
  children,
}: {
  id?: string;
  icon: React.ElementType;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-24 space-y-2">
      <h3 className="flex items-center gap-2 text-sm font-semibold tracking-wide text-slate-900 dark:text-slate-100">
        <Icon className="h-4 w-4 text-teal-600 dark:text-teal-400" />
        {title}
      </h3>
      <div className="text-muted-foreground pl-6 text-sm leading-relaxed">
        {children}
      </div>
    </section>
  );
}

/** A fact the project owner has yet to state. Shown as such, never as a value. */
function ToBeFilled({ what }: { what: string }) {
  return (
    <mark
      data-placeholder=""
      className="rounded bg-amber-100 px-1 text-amber-900 dark:bg-amber-950 dark:text-amber-200"
    >
      [To be filled in by the project owner: {what}]
    </mark>
  );
}

export function PrivacyContent() {
  return (
    <div className="space-y-5">
      <p className="text-muted-foreground text-sm leading-relaxed">
        This privacy notice explains what personal data the GAIK Toolkit Demo
        processes, who processes it and how long it is kept.
      </p>

      <Section icon={Building2} title="About GAIK Project">
        <p>
          GAIK (Generative AI for Knowledge Management) is a research project
          funded by the European Regional Development Fund (ERDF). The project
          is led by Haaga-Helia University of Applied Sciences in collaboration
          with University of Helsinki, Tampere University, and industry
          partners.
        </p>
      </Section>

      <Section icon={Scale} title="Controller and legal basis">
        <p>
          Controller:{" "}
          <ToBeFilled what="the controller of this demo and its contact details" />
        </p>
        <p className="mt-2">
          Legal basis:{" "}
          <ToBeFilled what="the legal basis for each kind of processing above" />
        </p>
      </Section>

      <Section icon={Eye} title="Sign-up details">
        <ul className="list-inside list-disc space-y-1">
          <li>
            <strong className="text-foreground">Contact information</strong> —
            name and email address
          </li>
          <li>
            <strong className="text-foreground">Optional information</strong> —
            company name and intended use case
          </li>
          <li>
            <strong className="text-foreground">Account credentials</strong> —
            password (stored securely hashed)
          </li>
          <li>
            <strong className="text-foreground">Access record</strong> — the
            status of your access request, and how many reports you have
            written, the model tokens they used and when you wrote the last one
          </li>
        </ul>
        <p className="mt-2">
          They are used to handle your access request and give you access to the
          demo. They are stored in Supabase, hosted on AWS in the EU (Stockholm,
          Sweden), for the duration of the GAIK project (until January 2027) or
          until you request deletion.
        </p>
      </Section>

      <Section id="uploads" icon={Upload} title="Uploads and demo inputs">
        <p>
          The files you upload and the text, questions, web addresses and
          recordings you enter go to the demo&apos;s server on CSC&apos;s Rahti
          service, and from there to the services below. The server reads each
          file in memory or in a temporary file, and most demos drop it when the
          request ends. Some keep what you enter or what they produce for a
          while, so you can go on working with it: documents indexed in RAG
          Builder, tables in Tabular Agent, generated subtitles and PDF reports,
          and the field descriptions you write for an extraction schema. They
          are removed when you clear them, after a time without use, or when the
          server restarts.
        </p>
        <p className="mt-2">
          The longest the server keeps them:{" "}
          <ToBeFilled what="the longest time the server keeps uploads and results" />
        </p>
        <p className="mt-2">{UPLOAD_REMINDER_TEXT}</p>
      </Section>

      <Section icon={Cpu} title="AI model and processing services">
        <p>
          Uploads and inputs are processed by the provider of the model in use:
          Microsoft Azure (OpenAI&apos;s and Anthropic&apos;s models) or Google
          Vertex AI (Gemini models). Documents read with HH Parser go to
          Haaga-Helia&apos;s document parsing service, and audio transcribed
          with Haaga-Helia&apos;s Whisper server to that server. If you enter
          your own model key, they go to the provider of that key, on its terms.
        </p>
        <p className="mt-2">
          How long these services keep them:{" "}
          <ToBeFilled what="each service's retention period for prompts and files" />
        </p>
      </Section>

      <Section icon={ScrollText} title="Logs and usage limits">
        <p>
          The server logs each request: its time, path and outcome, and for some
          requests a file name or an error message. The usage limits count admin
          sign-in attempts and requests per IP address, and runs per account, in
          Upstash Redis; each count expires when its window ends, at the latest
          after a day.
        </p>
        <p className="mt-2">
          Where Upstash Redis is hosted:{" "}
          <ToBeFilled what="the Upstash Redis region" />
        </p>
        <p className="mt-2">
          How long logs are kept: <ToBeFilled what="the log retention period" />
        </p>
      </Section>

      <Section icon={BarChart3} title="Analytics">
        <p>
          We use PostHog for usage analytics to improve our service. PostHog is
          hosted in the EU (Frankfurt, Germany) and collects:
        </p>
        <ul className="mt-1 list-inside list-disc space-y-1">
          <li>Page views and feature usage</li>
          <li>Technical information (browser type, screen size)</li>
        </ul>
        <p className="mt-2">
          Analytics data is used solely to improve the demo application. You can
          opt out by enabling Do Not Track in your browser settings.
        </p>
        <p className="mt-2">
          How long analytics data is kept:{" "}
          <ToBeFilled what="the analytics retention period" />
        </p>
      </Section>

      <Section icon={Database} title="Solution Wizard">
        <p>
          Solution Wizard V2, which this demo links to, is a separate service.
          The Solution Wizard in this demo no longer records sessions: the
          optional diagnostics pilot was switched off on 4 November 2026, and
          the sessions it stored are being deleted. Contact the project team
          below with any questions about them.
        </p>
      </Section>

      <Section icon={Shield} title="Your Rights">
        <p className="mb-1">Under GDPR, you have the right to:</p>
        <ul className="list-inside list-disc space-y-1">
          <li>Access your personal data</li>
          <li>Correct inaccurate data</li>
          <li>Request deletion of your data</li>
          <li>Withdraw consent, where the processing is based on it</li>
          <li>
            Lodge a complaint with a data protection authority; in Finland, the
            Data Protection Ombudsman
          </li>
        </ul>
      </Section>

      <Section icon={Mail} title="Contact">
        <div className="space-y-1">
          <p>
            <strong className="text-foreground">Project manager:</strong> Anne
            Wuokko —{" "}
            <a
              href="mailto:anne.wuokko@haaga-helia.fi"
              className="text-teal-600 hover:underline dark:text-teal-400"
            >
              anne.wuokko@haaga-helia.fi
            </a>
          </p>
          <p>
            <strong className="text-foreground">
              Research and development:
            </strong>{" "}
            Dmitry Kudryavtsev —{" "}
            <a
              href="mailto:dmitry.kudryavtsev@haaga-helia.fi"
              className="text-teal-600 hover:underline dark:text-teal-400"
            >
              dmitry.kudryavtsev@haaga-helia.fi
            </a>
          </p>
        </div>
      </Section>
    </div>
  );
}
