import { Shield, Database, Eye, Scale, Mail, Building2 } from "lucide-react";

function Section({
  icon: Icon,
  title,
  children,
}: {
  icon: React.ElementType;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-2">
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

export function PrivacyContent() {
  return (
    <div className="space-y-5">
      <p className="text-muted-foreground text-sm leading-relaxed">
        This privacy policy explains how the GAIK Toolkit Demo application
        collects and processes your personal data.
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

      <Section icon={Eye} title="Data We Collect">
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
        </ul>
      </Section>

      <Section icon={Shield} title="How We Use Your Data">
        <ul className="list-inside list-disc space-y-1">
          <li>Process and respond to your access request</li>
          <li>Provide you access to the GAIK Toolkit demo</li>
          <li>Improve the toolkit based on usage patterns (anonymized)</li>
        </ul>
      </Section>

      <Section icon={Database} title="Data Storage">
        <p>
          Your data is stored securely using Supabase, hosted on AWS in the EU
          (Stockholm, Sweden). We retain your data only for the duration of the
          GAIK project (until January 2027) or until you request deletion.
        </p>
      </Section>

      <Section icon={Scale} title="Your Rights">
        <p className="mb-1">Under GDPR, you have the right to:</p>
        <ul className="list-inside list-disc space-y-1">
          <li>Access your personal data</li>
          <li>Correct inaccurate data</li>
          <li>Request deletion of your data</li>
          <li>Withdraw consent at any time</li>
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
