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
  Monitor,
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
          Controller: Haaga-Helia University of Applied Sciences Ltd (business
          ID 2029188-8), Ratapihantie 13, 00520 Helsinki, Finland, which leads
          the GAIK project. Contact for the demo: the project team below or{" "}
          <a
            href="https://gaik.ai/contact-info/"
            className="text-teal-600 hover:underline dark:text-teal-400"
          >
            gaik.ai/contact-info
          </a>
          . Data protection officer:{" "}
          <a
            href="mailto:dpo@haaga-helia.fi"
            className="text-teal-600 hover:underline dark:text-teal-400"
          >
            dpo@haaga-helia.fi
          </a>
          , who also handles requests to use the rights listed below.
        </p>
        <p className="mt-2">Legal basis:</p>
        <ul className="mt-1 list-inside list-disc space-y-1">
          <li>
            your account, access record, uploads and demo inputs: your consent,
            given when you request access and run a demo; you can withdraw it by
            asking us to delete your account
          </li>
          <li>
            logs and usage limits: our legitimate interest in keeping the demo
            secure and preventing misuse
          </li>
          <li>
            analytics: our legitimate interest in improving the demos; Do Not
            Track opts you out
          </li>
        </ul>
      </Section>

      <Section icon={Eye} title="Account details and feedback">
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
            status of your access request, whether you may use the first
            Solution Wizard or write more reports than usual, and how many
            reports you have written, the model tokens they used and when you
            wrote the last one
          </li>
          <li>
            <strong className="text-foreground">Demo feedback</strong> — the
            rating and comment you give a demo
          </li>
        </ul>
        <p className="mt-2">
          They are used to handle your access request, give you access to the
          demo and, for feedback, improve the demos. They are stored with your
          account in Supabase, hosted on AWS in the EU (Stockholm, Sweden), for
          the duration of the GAIK project (until January 2027) or until you
          request deletion.
        </p>
      </Section>

      <Section id="uploads" icon={Upload} title="Uploads and demo inputs">
        <p>
          The files you upload and the text, questions, web addresses and
          recordings you enter go to the demo&apos;s server on CSC&apos;s Rahti
          service, which checks that each file&apos;s type and content match,
          and from there to the services below. The server reads each file in
          memory or in a temporary file, and most demos drop it when the request
          ends. Some keep what you enter or what they produce for a while, so
          you can go on working with it. The longest the server keeps them:
        </p>
        <ul className="mt-1 list-inside list-disc space-y-1">
          <li>
            documents indexed in RAG Builder: until you clear them, or 70
            minutes after you last use them
          </li>
          <li>tables in Tabular Agent: 35 minutes after you last use them</li>
          <li>PDF reports: 70 minutes after they are made</li>
          <li>generated subtitles: two hours after they are made</li>
          <li>
            Luvata order drafts: you can download them for an hour, and they are
            kept until the next order is processed or the server restarts
          </li>
          <li>
            the extraction prompts and field descriptions you write, and the
            schemas made from them: until the server restarts
          </li>
          <li>
            a note of which account made each result: two days, and then until
            the next run or the server restarts
          </li>
        </ul>
        <p className="mt-2">
          What the first Solution Wizard keeps is described below.
        </p>
        <p className="mt-2">{UPLOAD_REMINDER_TEXT}</p>
      </Section>

      <Section icon={Cpu} title="AI model and processing services">
        <p>
          Uploads and inputs are processed by the provider of the model in use:
          Microsoft Azure (OpenAI&apos;s and Anthropic&apos;s models), Google
          Vertex AI (Gemini models) or CSC&apos;s Aitta service in Finland (open
          models such as Gemma and gpt-oss). With an Aitta model picked, audio
          is also transcribed and RAG Builder documents are indexed on Aitta.
          Documents read with HH Parser go to Haaga-Helia&apos;s document
          parsing service, and audio transcribed with Haaga-Helia&apos;s Whisper
          server to that server. If you enter your own model key, they go to the
          provider of that key, on its terms.
        </p>
        <p className="mt-2">How long these services keep them:</p>
        <ul className="mt-1 list-inside list-disc space-y-1">
          <li>
            Azure OpenAI (GPT models): the model keeps nothing between requests.
            Microsoft&apos;s abuse monitoring may store a prompt and its output
            for human review, in the same geography, and they are not used to
            train models.
          </li>
          <li>
            Claude models in Microsoft Foundry: Anthropic processes prompts and
            outputs as an independent processor, under its commercial terms and
            data processing addendum.
          </li>
          <li>
            Gemini on Vertex AI: Google may cache inputs and outputs for up to
            24 hours and log prompts for abuse monitoring for up to 90 days, and
            does not use them to train models without permission.
          </li>
          <li>CSC Aitta: prompts and responses are not stored permanently.</li>
          <li>
            HH Parser and Haaga-Helia&apos;s Whisper server:{" "}
            <ToBeFilled what="how long these Haaga-Helia services keep files" />
          </li>
        </ul>
      </Section>

      <Section icon={ScrollText} title="Logs and usage limits">
        <p>
          The server logs each request: its time, path and outcome, and for some
          requests a file name or an error message. Each demo run also leaves
          one line with your account id, the feature, the time and whether it
          succeeded, never what you uploaded or asked; it is used to look into
          misuse and to answer your requests about your data. Helpdesk Chatbot
          and EU AI Act Screening run in the web app and leave no such line.
        </p>
        <p className="mt-2">
          The usage limits count admin sign-in attempts and requests per IP
          address, and runs per account, in Upstash Redis; each count expires
          when its window ends, at the latest after a day. Upstash Redis also
          keeps, for each account that uses the first Solution Wizard, how many
          sessions it started, how many messages it sent and when it last used
          the wizard. These counts do not expire.
        </p>
        <p className="mt-2">
          Upstash Redis is hosted on AWS in London, United Kingdom, a country
          the EU recognises as protecting personal data adequately.
        </p>
        <p className="mt-2">
          How long logs are kept: the server&apos;s own log is kept until the
          server is next restarted or updated. The project&apos;s monitoring
          service keeps error lines, with a few lines around each, for 30 days,
          and records of each request&apos;s path, outcome and duration for 90
          days.
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
          How long analytics data is kept: one year, PostHog&apos;s retention
          period for our plan.
        </p>
      </Section>

      <Section icon={Database} title="Solution Wizard">
        <p>
          The first Solution Wizard in the browser keeps your conversation, with
          the text of the files you attach, and the files it generates only
          while the session runs: they are removed when you leave the page or
          restart, or after about 30 minutes without activity. Its use is
          counted per account (see Logs and usage limits), but what you write is
          not recorded: the optional diagnostics pilot that recorded sessions
          was switched off on 4 November 2026, and the sessions it stored are
          being deleted. Contact the project team below with any questions about
          them.
        </p>
        <p className="mt-2">
          Solution Wizard V2, which this demo links to, is a separate service.
        </p>
      </Section>

      <Section icon={Monitor} title="In your browser">
        <p>
          Your browser keeps, until you clear them: the model and reasoning
          effort you picked, the rating and comment you gave each demo, the
          names of the documents you indexed in RAG Builder, and whether you
          have seen the tour. A Source Normalizer or Knowledge Curator result
          you pass on to the next page waits in that browser tab until the next
          page opens it or the tab is closed.
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
