import { expect, test } from "bun:test";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { PrivacyContent } from "./privacy-content";
import { UPLOAD_REMINDER_TEXT, UploadReminder } from "./upload-reminder";

const notice = renderToStaticMarkup(createElement(PrivacyContent));

test("the notice covers sign-up details, uploads, services, logs and analytics", () => {
  for (const heading of [
    "Controller and legal basis",
    "Sign-up details",
    "Uploads and demo inputs",
    "AI model and processing services",
    "Logs and usage limits",
    "Analytics",
  ])
    expect(notice).toContain(heading);
  expect(notice).toContain('id="uploads"');
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

// Raw file pickers a page may have beyond its reminders, and why: they take back
// the demo's own output (a .zip from an earlier step) or a JSON settings file,
// sit next to a box that already shows the reminder, or take no files here.
const PICKERS_WITHOUT_OWN_REMINDER: Record<string, number> = {
  "app/(demos)/knowledge-curator/page.tsx": 1, // the Source Normalizer's .zip
  "app/(demos)/knowledge-synthesis/page.tsx": 1, // the Knowledge Curator's .zip
  "app/(demos)/luvata-order/custom-use-case.tsx": 1, // BOMs, by the FileUpload
  "app/(demos)/report-writer/page.tsx": 1, // sample report, by the sources box
  "app/(demos)/report-writer/components/config-actions.tsx": 1, // JSON config
  "app/(demos)/report-writer-v2/create-section.tsx": 1, // JSON report spec
  "components/ai-elements/prompt-input.tsx": 1, // chat composer, no files here
};

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sources(path);
    return path.endsWith(".tsx") ? [path] : [];
  });
}

const count = (text: string, needle: string) => text.split(needle).length - 1;

test("every upload box carries the reminder, the shared one included", () => {
  expect(readFileSync("components/demo/file-upload.tsx", "utf8")).toContain(
    "<UploadReminder />",
  );
  const unexplained = [...sources("app"), ...sources("components")].flatMap(
    (path) => {
      const text = readFileSync(path, "utf8");
      const extra =
        count(text, 'type="file"') -
        count(text, "<UploadReminder") -
        (PICKERS_WITHOUT_OWN_REMINDER[path] ?? 0);
      return extra > 0 ? [path] : [];
    },
  );
  expect(unexplained).toEqual([]);
});
