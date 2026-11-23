/** Machine-readable marks on what the wizard hands out (EU AI Act art. 50(2)). */

export const AI_GENERATOR = "GAIK Solution Wizard";

/** Per record, beside review_status, so JSON and CSV exports carry it alike. */
export const AI_RECORD_MARK = { ai_generated: true, ai_generator: AI_GENERATOR };

/** The header that opens a Markdown export. */
export const AI_FRONT_MATTER = `---\nai_generated: true\nai_generator: ${AI_GENERATOR}\n---\n\n`;

const HEADERS = ["X-AI-Generated", "X-AI-Model"];

/** The api's marks on a download, passed on to the browser. */
export function aiHeaders(upstream: Response): Record<string, string> {
  const out: Record<string, string> = {};
  for (const name of HEADERS) {
    const value = upstream.headers.get(name);
    if (value) out[name] = value;
  }
  return out;
}

/** The model named on a download, for the audit trail. */
export const aiModel = (upstream: Response) => upstream.headers.get("X-AI-Model") ?? undefined;
