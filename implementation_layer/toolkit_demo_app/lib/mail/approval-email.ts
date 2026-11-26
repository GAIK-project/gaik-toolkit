import nodemailer, { type SendMailOptions } from "nodemailer";

// The e-mail an approved user gets, sent through CSC's relay (smtp.pouta.csc.fi:25).
// The relay takes no login and admits Rahti's egress addresses, so it works from the
// pod but not from a workstation. It checks the `Sender` address, which must be a real
// mailbox that receives bounces, in a domain whose SPF allows CSC (haaga-helia.fi does;
// gaik.ai does not). Without MAIL_FROM nothing is sent and approval works as before.

export const DEMO_URL = "https://gaik-demo.2.rahtiapp.fi/";

export interface MailConfig {
  host: string;
  port: number;
  /** The visible From, e.g. `GAIK Toolkit <someone@haaga-helia.fi>`. */
  from: string;
  /** The mailbox the relay checks and bounces go to; defaults to From's address. */
  sender: string;
  replyTo?: string;
}

/** The address inside `Name <address>`, or the value itself. */
export function addressOf(value: string): string {
  const match = value.match(/<([^<>\s]+@[^<>\s]+)>\s*$/);
  return (match ? match[1] : value).trim();
}

/** Read at call time so `oc set env` changes apply after a rollout. */
export function getMailConfig(): MailConfig | null {
  const from = process.env.MAIL_FROM?.trim();
  if (!from) return null;
  const port = Number.parseInt(process.env.SMTP_PORT ?? "", 10);
  return {
    host: process.env.SMTP_HOST?.trim() || "smtp.pouta.csc.fi",
    port: Number.isFinite(port) && port > 0 ? port : 25,
    from,
    sender: process.env.MAIL_SENDER?.trim() || addressOf(from),
    replyTo: process.env.MAIL_REPLY_TO?.trim() || undefined,
  };
}

export function approvalEmail(): { subject: string; text: string } {
  return {
    subject: "Your GAIK Toolkit access is approved",
    text: `Hello,

Your access to the GAIK Toolkit demo has been approved.

Access the demo here:
${DEMO_URL}

Log in with your registered credentials. If you have not confirmed your e-mail address yet, open the confirmation link we sent you first.

We'd love your feedback: use the "Rate this" section on each demo page or contact us by email.

Our GAIK team also supports toolkit integrations tailored to your company's needs.
Learn more:
https://gaik.ai/news/newsletter-5-april-2026/

Best regards,

Akseli Leskinen
AI Developer, GAIK Project
`,
  };
}

export type ApprovalEmailResult = "sent" | "not-configured" | "failed";

type Send = (message: SendMailOptions) => Promise<unknown>;

function relaySend(config: MailConfig): Send {
  const transport = nodemailer.createTransport({
    host: config.host,
    port: config.port,
    secure: false,
    connectionTimeout: 10_000,
    greetingTimeout: 10_000,
    socketTimeout: 20_000,
  });
  return (message) => transport.sendMail(message);
}

/** Send the approval e-mail. Never throws: a failed send must not undo the approval. */
export async function sendApprovalEmail(
  to: string,
  config: MailConfig | null = getMailConfig(),
  send: Send | null = null,
): Promise<ApprovalEmailResult> {
  if (!config) return "not-configured";
  const { subject, text } = approvalEmail();
  try {
    await (send ?? relaySend(config))({
      from: config.from,
      sender: config.sender,
      replyTo: config.replyTo,
      to,
      subject,
      text,
      // Nodemailer takes SMTP MAIL FROM from `from`, not `sender`: set it, so
      // bounces and the relay's SPF check use the sender mailbox.
      envelope: { from: config.sender, to },
    });
    return "sent";
  } catch (error) {
    // The relay's reply can echo the recipient, so log its code and status only.
    const { code, responseCode } = (error ?? {}) as {
      code?: string;
      responseCode?: number;
    };
    console.error(
      `[mail] approval e-mail failed: code=${code ?? "unknown"} status=${responseCode ?? "-"}`,
    );
    return "failed";
  }
}
