import { expect, test } from "bun:test";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, sep } from "node:path";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { PrivacyContent } from "./privacy-content";
import { UPLOAD_REMINDER_TEXT, UploadReminder } from "./upload-reminder";

const notice = renderToStaticMarkup(createElement(PrivacyContent));

test("the notice covers the account, uploads, services, logs, analytics and the browser", () => {
  for (const heading of [
    "Controller and legal basis",
    "Account details and feedback",
    "Uploads and demo inputs",
    "AI model and processing services",
    "Logs and usage limits",
    "Analytics",
    "In your browser",
  ])
    expect(notice).toContain(heading);
  expect(notice).toContain('id="uploads"');
});

// Facts of the code: each one is said, with how long it is kept where the code sets it.
test("the notice names the services and stores the code uses", () => {
  for (const fact of [
    "Aitta", // a server-offered model, transcription and embedding provider
    "Demo feedback", // rated in Supabase with the account
    "These counts do not expire", // the first wizard's use, in Upstash
    "until the server restarts", // extraction prompts and schemas
    "until the next order is processed", // Luvata order drafts
    "Helpdesk Chatbot and EU AI Act Screening", // no audit line
  ])
    expect(notice).toContain(fact);
  expect(notice).not.toContain(
    "the longest time the server keeps uploads and results",
  );
});

// The owner replaces them with the facts; until then each one says it is open.
test("an open fact is shown as a placeholder, never as a value", () => {
  const placeholders =
    notice.match(/<mark data-placeholder=""[^>]*>[\s\S]*?<\/mark>/g) ?? [];
  for (const p of placeholders)
    expect(p).toContain("[To be filled in by the project owner: ");
});

test("the reminder names what not to upload and links to the notice", () => {
  for (const item of [
    "synthetic or anonymised",
    "special categories of personal data",
    "personal identity numbers",
    "card or bank account numbers",
    "passwords or keys",
    "real customer or confidential documents",
  ])
    expect(UPLOAD_REMINDER_TEXT).toContain(item);
  const html = renderToStaticMarkup(createElement(UploadReminder));
  expect(html).toContain('href="/privacy#uploads"');
  expect(notice).toContain(UPLOAD_REMINDER_TEXT);
});

test("the footer and the sign-up form link to the notice", () => {
  expect(readFileSync("components/layout/footer.tsx", "utf8")).toContain(
    'href="/privacy"',
  );
  const signUp = readFileSync("app/(auth)/sign-up/page.tsx", "utf8");
  expect(signUp).toContain("<PrivacyDialog>");
  expect(readFileSync("app/(home)/privacy/page.tsx", "utf8")).toContain(
    "<PrivacyContent />",
  );
});

// File pickers a file may have beyond its reminders, and why.
const PICKERS_WITHOUT_OWN_REMINDER: Record<string, number> = {
  // The BOM picker, beside the purchase order box and its reminder.
  "app/(demos)/luvata-order/custom-use-case.tsx": 1,
  // The sample report, in the Input Files card under the sources box's reminder.
  "app/(demos)/report-writer/page.tsx": 1,
  // The sample report, right under the source files' reminder.
  "app/(demos)/report-writer-v2/components/source-list.tsx": 1,
  // A use case config (.json) the browser reads into the form; nothing is uploaded.
  "app/(demos)/report-writer/components/config-actions.tsx": 1,
  // A report spec (.json) the browser reads into the form; nothing is uploaded.
  "app/(demos)/report-writer-v2/create-section.tsx": 1,
  // The composer's hidden picker. A page that takes attachments passes accept=,
  // which counts as a picker on that page; the composers without it send only
  // the text, whatever is dropped on them.
  "components/ai-elements/prompt-input.tsx": 1,
};

// Components that show the reminder themselves, so a page that uses them needs none.
const SHOWS_ITS_OWN_REMINDER: Record<string, string> = {
  FileUpload: "components/demo/file-upload.tsx",
  DocumentUpload: "app/(demos)/extractor/document-upload.tsx",
};

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sources(path);
    // Forward slashes on every system, so the keys above match on Windows too.
    return path.endsWith(".tsx") ? [path.split(sep).join("/")] : [];
  });
}

const count = (text: string, needle: string) => text.split(needle).length - 1;
const matches = (text: string, pattern: RegExp) =>
  text.match(pattern)?.length ?? 0;

const RAW_PICKER = /\btype=\{?["'`]file["'`]\}?|\buseDropzone\(/g;
// A component given accept= opens a file picker, e.g. <PromptInput accept="…">.
const TAKES_FILES = /<([A-Z][\w.]*)\b[^<]*?\saccept=/g;
// A component defined in the file, up to the line that holds only its closing brace.
const LOCAL_COMPONENT =
  /^(?:export (?:default )?)?function ([A-Z]\w*)\b[\s\S]*?^\}\r?$/gm;

/** The file pickers a source file shows; a local picker component counts per use. */
function pickers(text: string): number {
  let n = matches(text, RAW_PICKER);
  const local = new Set<string>();
  for (const [body, name] of text.matchAll(LOCAL_COMPONENT)) {
    const raw = matches(body, RAW_PICKER);
    const uses = matches(text, new RegExp(`<${name}\\b`, "g"));
    // A page, or a component used in other files: its pickers are counted once.
    if (raw === 0 || uses === 0) continue;
    local.add(name);
    if (!body.includes("<UploadReminder")) n += raw * (uses - 1);
  }
  for (const [, name] of text.matchAll(TAKES_FILES))
    if (!(name in SHOWS_ITS_OWN_REMINDER) && !local.has(name)) n += 1;
  return n;
}

const ALL_SOURCES = [...sources("app"), ...sources("components")];

test("the picker count sees raw inputs, dropzones, accept= and local pickers", () => {
  expect(pickers(`<input type='file' />`)).toBe(1);
  expect(pickers(`const d = useDropzone({ onDrop });`)).toBe(1);
  expect(pickers(`<PromptInput\n  accept=".pdf"\n  multiple\n>`)).toBe(1);
  expect(pickers(`<FileUpload accept=".pdf" />`)).toBe(0);
  const picker = `function Pick() {\n  return <input type="file" />;\n}\n`;
  expect(pickers(`${picker}<Pick /><Pick />`)).toBe(2);
});

test("every upload box carries the reminder, the shared ones included", () => {
  for (const path of Object.values(SHOWS_ITS_OWN_REMINDER))
    expect(readFileSync(path, "utf8")).toContain("<UploadReminder />");
  const unexplained = ALL_SOURCES.flatMap((path) => {
    const text = readFileSync(path, "utf8");
    const extra =
      pickers(text) -
      count(text, "<UploadReminder") -
      (PICKERS_WITHOUT_OWN_REMINDER[path] ?? 0);
    return extra > 0 ? [path] : [];
  });
  expect(unexplained).toEqual([]);
});

test("no exemption outlives its picker", () => {
  const stale = Object.entries(PICKERS_WITHOUT_OWN_REMINDER).flatMap(
    ([path, n]) => {
      const text = readFileSync(path, "utf8");
      return pickers(text) - count(text, "<UploadReminder") < n ? [path] : [];
    },
  );
  expect(stale).toEqual([]);
});

// Inside a label, the reminder's link would open the file picker instead.
test("no reminder sits inside a label", () => {
  const inLabel = ALL_SOURCES.filter((path) =>
    (
      readFileSync(path, "utf8").match(/<(label|Label)\b[\s\S]*?<\/\1>/g) ?? []
    ).some((label) => label.includes("<UploadReminder")),
  );
  expect(inLabel).toEqual([]);
});
