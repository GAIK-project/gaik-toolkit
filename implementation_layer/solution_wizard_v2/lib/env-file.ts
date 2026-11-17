/**
 * The variables a package's `.env.example` lists, and the `.env` made from it.
 *
 * The PoC tab asks for the values in a small form and writes `poc/.env` into
 * the downloaded package in the browser (lib/zip-env). Nothing here sends or
 * stores a value: the functions are pure and the form keeps what is typed in
 * React state only.
 */

export type EnvVariable = {
  name: string;
  /** The value `.env.example` gives (often empty, or a default such as an API version). */
  example: string;
  /** The comment lines right above the variable, as one line of help. */
  help: string;
  /** The line is commented out in `.env.example`: the package runs without it. */
  optional: boolean;
};

const NAME = "[A-Za-z_][A-Za-z0-9_]*";
const ASSIGNMENT = new RegExp(`^\\s*(?:export\\s+)?(${NAME})\\s*=(.*)$`);
const COMMENTED_ASSIGNMENT = new RegExp(`^\\s*#\\s*(?:export\\s+)?(${NAME})=(.*)$`);
export const ENV_NAME_RE = new RegExp(`^${NAME}$`);

/** A value as `.env.example` wrote it, without its quotes or a trailing comment. */
function plainValue(raw: string): string {
  const text = raw.trim();
  const quoted = /^(["'])(.*)\1\s*(?:#.*)?$/.exec(text);
  if (quoted) return quoted[2];
  return text.replace(/\s+#.*$/, "");
}

type Line =
  | { kind: "variable"; name: string; raw: string; optional: boolean }
  | { kind: "comment"; text: string }
  | { kind: "other" };

function readLine(line: string): Line {
  const commented = COMMENTED_ASSIGNMENT.exec(line);
  if (commented) return { kind: "variable", name: commented[1], raw: commented[2], optional: true };
  const assigned = ASSIGNMENT.exec(line);
  if (assigned) return { kind: "variable", name: assigned[1], raw: assigned[2], optional: false };
  const comment = /^\s*#\s?(.*)$/.exec(line);
  if (comment) return { kind: "comment", text: comment[1].trim() };
  return { kind: "other" };
}

/**
 * The variables of a `.env.example`, in its order, each once. `NAME=value`
 * and `export NAME=value` lines, and a commented `# NAME=value` as an
 * optional one. The comment lines directly above a variable are its help; a
 * blank line ends them.
 */
export function parseEnvExample(text: string): EnvVariable[] {
  const found: EnvVariable[] = [];
  const seen = new Set<string>();
  let help: string[] = [];
  for (const line of text.split(/\r?\n/)) {
    const read = readLine(line);
    if (read.kind === "comment") {
      // Rules such as "# -----" say nothing.
      if (/[A-Za-zÀ-ÿ0-9]/.test(read.text)) help.push(read.text);
      continue;
    }
    if (read.kind === "variable" && !seen.has(read.name)) {
      seen.add(read.name);
      found.push({
        name: read.name,
        example: plainValue(read.raw),
        help: help.join(" "),
        optional: read.optional,
      });
    }
    help = [];
  }
  return found;
}

/** A value as a `.env` line holds it: bare when plain, quoted when it has spaces or marks. */
export function envValue(value: string): string {
  if (/^[A-Za-z0-9_\-./:@+=,%~^]*$/.test(value)) return value;
  if (!value.includes("'")) return `'${value}'`;
  return `"${value.replace(/[\\"$`]/g, (ch) => `\\${ch}`)}"`;
}

export type ExtraVariable = { name: string; value: string };

/** Whether anything was typed: without a value the download stays as it is, with no `.env`. */
export function hasEnvValues(values: Record<string, string>, extra: readonly ExtraVariable[] = []): boolean {
  return (
    Object.values(values).some((value) => value.trim() !== "") ||
    extra.some((item) => ENV_NAME_RE.test(item.name.trim()) && item.value.trim() !== "")
  );
}

/**
 * The `.env` for the package: `.env.example` as it is, with the typed values
 * in place (a commented variable that got a value is uncommented), then the
 * variables the user added that it does not list. A line without a typed
 * value is kept as `.env.example` has it, the way `cp .env.example .env`
 * would leave it. A value never spans lines: a line break in one is dropped.
 */
export function composeEnv(
  exampleText: string,
  values: Record<string, string>,
  extra: readonly ExtraVariable[] = [],
): string {
  const typed = (name: string): string | null => {
    const value = (values[name] ?? "").replace(/[\r\n]+/g, "").trim();
    return value === "" ? null : value;
  };
  const written = new Set<string>();
  const lines = exampleText === "" ? [] : exampleText.replace(/\r\n/g, "\n").replace(/\n$/, "").split("\n");
  const out = lines.map((line) => {
    const read = readLine(line);
    if (read.kind !== "variable" || written.has(read.name)) return line;
    const value = typed(read.name);
    if (value === null) return line;
    written.add(read.name);
    return `${read.name}=${envValue(value)}`;
  });
  const listed = new Set(parseEnvExample(exampleText).map((v) => v.name));
  const added: string[] = [];
  for (const item of extra) {
    const name = item.name.trim();
    const value = item.value.replace(/[\r\n]+/g, "").trim();
    if (!ENV_NAME_RE.test(name) || value === "" || listed.has(name) || written.has(name)) continue;
    written.add(name);
    added.push(`${name}=${envValue(value)}`);
  }
  return [...out, ...added].join("\n") + "\n";
}
