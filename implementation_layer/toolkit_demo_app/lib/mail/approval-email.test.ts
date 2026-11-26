import { afterEach, beforeEach, expect, test } from "bun:test";
import {
  addressOf,
  approvalEmail,
  DEMO_URL,
  getMailConfig,
  sendApprovalEmail,
  type MailConfig,
} from "./approval-email";

const VARS = [
  "MAIL_FROM",
  "MAIL_SENDER",
  "MAIL_REPLY_TO",
  "SMTP_HOST",
  "SMTP_PORT",
];
// Each test starts without the caller's mail settings and gives them back after.
let saved: Record<string, string | undefined> = {};
beforeEach(() => {
  saved = Object.fromEntries(VARS.map((v) => [v, process.env[v]]));
  for (const v of VARS) delete process.env[v];
});
afterEach(() => {
  for (const v of VARS) {
    if (saved[v] === undefined) delete process.env[v];
    else process.env[v] = saved[v];
  }
});

const CONFIG: MailConfig = {
  host: "smtp.pouta.csc.fi",
  port: 25,
  from: "GAIK Toolkit <team@example.org>",
  sender: "team@example.org",
};

test("without MAIL_FROM nothing is configured and nothing is sent", async () => {
  expect(getMailConfig()).toBeNull();
  let called = false;
  const result = await sendApprovalEmail("user@example.com", null, async () => {
    called = true;
  });
  expect(result).toBe("not-configured");
  expect(called).toBe(false);
});

test("the relay defaults to CSC's host and port 25, Sender to From's address", () => {
  process.env.MAIL_FROM = "GAIK Toolkit <team@example.org>";
  expect(getMailConfig()).toEqual({
    host: "smtp.pouta.csc.fi",
    port: 25,
    from: "GAIK Toolkit <team@example.org>",
    sender: "team@example.org",
    replyTo: undefined,
  });
});

test("SMTP_PORT that is not a number falls back to 25", () => {
  process.env.MAIL_FROM = "team@example.org";
  process.env.SMTP_PORT = "abc";
  expect(getMailConfig()?.port).toBe(25);
});

test("addressOf takes the address out of a display name", () => {
  expect(addressOf("GAIK <a@example.org>")).toBe("a@example.org");
  expect(addressOf(" a@example.org ")).toBe("a@example.org");
});

test("the message links the demo and carries the configured Sender", async () => {
  const sent: Record<string, unknown>[] = [];
  const result = await sendApprovalEmail(
    "user@example.com",
    CONFIG,
    async (m) => {
      sent.push(m as Record<string, unknown>);
    },
  );
  expect(result).toBe("sent");
  expect(sent[0]).toMatchObject({
    to: "user@example.com",
    from: CONFIG.from,
    sender: "team@example.org",
    subject: approvalEmail().subject,
  });
  expect(String(sent[0].text)).toContain(DEMO_URL);
});

test("SMTP MAIL FROM is the Sender mailbox, not the visible From", async () => {
  const sent: Record<string, unknown>[] = [];
  await sendApprovalEmail(
    "user@example.com",
    { ...CONFIG, sender: "bounces@example.org" },
    async (m) => {
      sent.push(m as Record<string, unknown>);
    },
  );
  expect(sent[0].envelope).toEqual({
    from: "bounces@example.org",
    to: "user@example.com",
  });
});

test("a failed send logs the SMTP code, never the relay's reply", async () => {
  const lines: string[] = [];
  const original = console.error;
  console.error = (line: string) => lines.push(line);
  try {
    await sendApprovalEmail("user@example.com", CONFIG, async () => {
      throw Object.assign(new Error("550 user@example.com: no such user"), {
        code: "EENVELOPE",
        responseCode: 550,
      });
    });
  } finally {
    console.error = original;
  }
  expect(lines.join("\n")).toContain("code=EENVELOPE status=550");
  expect(lines.join("\n")).not.toContain("user@example.com");
});

test("a relay error is reported as failed, not thrown", async () => {
  const result = await sendApprovalEmail(
    "user@example.com",
    CONFIG,
    async () => {
      throw new Error("connection refused");
    },
  );
  expect(result).toBe("failed");
});
