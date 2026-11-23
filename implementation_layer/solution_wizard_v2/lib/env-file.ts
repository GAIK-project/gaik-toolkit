/**
 * The variables a package's `.env.example` lists, and the `.env` made from it.
 *
 * The PoC tab asks for the values in a small form and writes `poc/.env` into
 * the downloaded package in the browser (lib/zip-env). Nothing here sends or
 * stores a value: the functions are pure and the form keeps what is typed in
 * React state only.
 *
 * A generated `.env.example` lists every provider the toolkit knows, each
 * under a `# --- Name ---` line and all commented out (some twenty-five
 * variables). `envLayout` reads which provider the package's `config.yaml`
 * names and puts that provider's section, and the external services', in
 * front; the rest goes behind one disclosure.
 */

export type EnvVariable = {
  name: string;
  /** The value `.env.example` gives (often empty, or a default such as an API version). */
  example: string;
  /** The comment lines that belong to the variable, as one line of help. */
  help: string;
  /** The line is commented out in `.env.example`: the package runs without it. */
  optional: boolean;
  /** The line of `.env.example` the variable stands on, from 0. */
  line: number;
};

/** The variables under one `# --- Name ---` line; `title` null for those under none. */
export type EnvSection = { title: string | null; variables: EnvVariable[] };

const NAME = "[A-Za-z_][A-Za-z0-9_]*";
const ASSIGNMENT = new RegExp(`^\\s*(?:export\\s+)?(${NAME})\\s*=(.*)$`);
const COMMENTED_ASSIGNMENT = new RegExp(`^\\s*#\\s*(?:export\\s+)?(${NAME})=(.*)$`);
// "# --- Azure OpenAI ---", "# === Other ===", "# -- X": a comment framed by rules.
const HEADING = /^\s*#\s*[-=]{2,}\s*(.*?)\s*[-=]*\s*$/;
// A comment about another spelling of the variable above it: "AITTA_TOKEN is also accepted."
const ABOUT_A_NAME = /^[A-Z][A-Z0-9]*_[A-Z0-9_]+\b/;
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
  | { kind: "heading"; title: string }
  | { kind: "comment"; text: string }
  | { kind: "blank" }
  | { kind: "other" };

function readLine(line: string): Line {
  if (line.trim() === "") return { kind: "blank" };
  const commented = COMMENTED_ASSIGNMENT.exec(line);
  if (commented) return { kind: "variable", name: commented[1], raw: commented[2], optional: true };
  const assigned = ASSIGNMENT.exec(line);
  if (assigned) return { kind: "variable", name: assigned[1], raw: assigned[2], optional: false };
  const heading = HEADING.exec(line);
  // A bare rule ("# -----") is a heading with no name: it ends a section and starts none.
  if (heading) return { kind: "heading", title: heading[1].trim() };
  const comment = /^\s*#\s?(.*)$/.exec(line);
  if (comment) return { kind: "comment", text: comment[1].trim() };
  return { kind: "other" };
}

const linesOf = (text: string): string[] =>
  text === "" ? [] : text.replace(/\r\n/g, "\n").replace(/\n$/, "").split("\n");

/**
 * `.env.example` as its sections, in its order, with every occurrence of a
 * variable (the generated one lists `OPENAI_API_KEY` under two providers).
 *
 * - `NAME=value` and `export NAME=value` are variables; a commented
 *   `# NAME=value` is an optional one.
 * - `# --- Name ---` starts a section called "Name". A section ends at a
 *   blank line: what follows without a heading of its own is under none.
 * - The comment lines directly above a variable are its help. One that
 *   starts with another variable's name, right under a variable ("# AITTA_TOKEN
 *   is also accepted."), is about the one above it.
 * - A heading is never help.
 */
export function parseEnvSections(text: string): EnvSection[] {
  const sections: EnvSection[] = [];
  let current: EnvSection | null = null;
  let help: string[] = [];
  let previous: EnvVariable | null = null;
  const under = (title: string | null): EnvSection => {
    if (!current || current.title !== title) {
      current = { title, variables: [] };
      sections.push(current);
    }
    return current;
  };
  let title: string | null = null;
  linesOf(text).forEach((line, index) => {
    const read = readLine(line);
    if (read.kind === "heading") {
      title = read.title || null;
      current = null;
      help = [];
      previous = null;
    } else if (read.kind === "comment") {
      if (previous && help.length === 0 && ABOUT_A_NAME.test(read.text)) {
        previous.help = [previous.help, read.text].filter(Boolean).join(" ");
      } else if (/[A-Za-zÀ-ÿ0-9]/.test(read.text)) {
        help.push(read.text);
      }
    } else if (read.kind === "variable") {
      previous = {
        name: read.name,
        example: plainValue(read.raw),
        help: help.join(" "),
        optional: read.optional,
        line: index,
      };
      under(title).variables.push(previous);
      help = [];
    } else {
      // A blank line (or anything else) ends the help, and the section.
      if (read.kind === "blank") {
        title = null;
        current = null;
      }
      help = [];
      previous = null;
    }
  });
  return sections.filter((section) => section.variables.length > 0);
}

/** The variables of a `.env.example`, in its order, each once (its first occurrence). */
export function parseEnvExample(text: string): EnvVariable[] {
  const seen = new Set<string>();
  const found: EnvVariable[] = [];
  for (const section of parseEnvSections(text)) {
    for (const variable of section.variables) {
      if (seen.has(variable.name)) continue;
      seen.add(variable.name);
      found.push(variable);
    }
  }
  return found;
}

// A part of a name (between underscores) ending in one of these names a
// credential: AZURE_API_KEY, HF_TOKEN, CLIENT_SECRET, OPENAI_APIKEY. Not MAX_TOKENS.
const CREDENTIAL_WORDS = ["KEY", "SECRET", "TOKEN", "PASSWORD"];
// Credentials the generated `.env.example` lists under a name with no such part.
const CREDENTIAL_NAMES = new Set(["GOOGLE_SERVICE_ACCOUNT_JSON"]);

function isCredentialName(name: string): boolean {
  const upper = name.toUpperCase();
  if (CREDENTIAL_NAMES.has(upper)) return true;
  return upper.split("_").some((part) => part !== "" && CREDENTIAL_WORDS.some((word) => part.endsWith(word)));
}

/** A value that is plainly no key: empty, `<your key>`, `your-key-here`, `xxxx`. */
function isPlaceholder(value: string): boolean {
  const v = value.trim();
  if (v === "") return true;
  if (v.startsWith("<") && v.endsWith(">")) return true;
  if (v.toLowerCase().startsWith("your")) return true;
  return /^[xX*._-]+$/.test(v);
}

/**
 * The variables of a `.env.example` that give a credential a value, by name:
 * wizard_api refuses to keep such a file (`poc_service.env_example_key_values`,
 * the same rule), and the editor says so before the text leaves the browser.
 * A credential may stand there empty or with a placeholder, also commented
 * out; other variables keep their example values.
 */
export function envExampleKeyValues(text: string): string[] {
  const found: string[] = [];
  for (const line of linesOf(text)) {
    const match = COMMENTED_ASSIGNMENT.exec(line) ?? ASSIGNMENT.exec(line);
    if (!match) continue;
    const raw = match[2].trim();
    // `NAME=  # a comment`: no value.
    const value = raw.startsWith("#") ? "" : plainValue(raw);
    if (isCredentialName(match[1]) && !isPlaceholder(value) && !found.includes(match[1])) found.push(match[1]);
  }
  return found;
}

/**
 * The providers a package's `config.yaml` names: the top-level `provider` and
 * each stage's, lower-cased, each once. Read line by line (`provider: azure`,
 * quoted or not, with or without a trailing comment), which is all the
 * generated file needs and asks for no YAML parser in the browser.
 */
export function configProviders(configText: string): string[] {
  const found: string[] = [];
  for (const line of configText.split(/\r?\n/)) {
    const match = /^\s*(?:-\s*)?["']?provider["']?\s*:\s*["']?([A-Za-z][A-Za-z0-9_-]*)["']?\s*(?:#.*)?$/.exec(line);
    if (!match) continue;
    const provider = match[1].toLowerCase().replace(/-/g, "_");
    if (!found.includes(provider)) found.push(provider);
  }
  return found;
}

/** What a section's heading must say to be a provider's, and which of its variables are that provider's. */
type ProviderRule = { heading: RegExp; variables?: RegExp };

// By the provider names the scaffolder writes (solution_wizard's _PROVIDERS)
// and the older `azure_openai`; headings as the generated .env.example has
// them, matched loosely so a reworded one still fits.
const PROVIDER_RULES: Record<string, ProviderRule> = {
  azure: { heading: /\bazure\b/i },
  azure_openai: { heading: /\bazure\b/i },
  openai: { heading: /^openai\b(?!.*compatible)/i },
  openai_compatible: { heading: /openai.compatible/i },
  aitta: { heading: /\baitta\b/i },
  google: { heading: /\bgemini\b/i },
  gemini: { heading: /\bgemini\b/i },
  vertex: { heading: /\bvertex\b/i },
  vertex_ai: { heading: /\bvertex\b/i },
  anthropic: { heading: /\banthropic\b/i, variables: /^(?!.*FOUNDRY)/ },
  anthropic_foundry: { heading: /\banthropic\b/i, variables: /FOUNDRY/ },
  litellm: { heading: /\blitellm\b/i },
};
const EXTERNAL_SERVICES = /external services/i;

/** A name that holds a credential, or an example that is a placeholder to replace. */
function isNeeded(variable: EnvVariable): boolean {
  if (/(_KEY|_TOKEN|_PASSWORD|_SECRET)$/.test(variable.name)) return true;
  return /\byour-|\bexample\.(com|org|net)\b|\/absolute\/path/i.test(variable.example);
}

export type EnvLayout =
  | { kind: "flat"; variables: EnvVariable[] }
  | {
      kind: "grouped";
      /** The sections of the providers the package uses, and the external services'. */
      shown: EnvSection[];
      /** The names in `shown` the package cannot run without. */
      needed: string[];
      /** Everything else, each variable once, under its own heading. */
      rest: EnvSection[];
      restCount: number;
    };

/**
 * How the form lays the variables out. Grouped when `config.yaml` names at
 * least one provider whose section `.env.example` has; flat (every variable,
 * as before) when the config cannot be read, names no provider this knows, or
 * the example has no such section.
 */
export function envLayout(exampleText: string, configText: string | null): EnvLayout {
  const flat: EnvLayout = { kind: "flat", variables: parseEnvExample(exampleText) };
  if (configText === null) return flat;
  const rules = configProviders(configText)
    .map((provider) => PROVIDER_RULES[provider])
    .filter((rule): rule is ProviderRule => rule !== undefined);
  if (rules.length === 0) return flat;

  const sections = parseEnvSections(exampleText);
  const shown: EnvSection[] = [];
  const shownNames = new Set<string>();
  let providerFound = false;
  for (const section of sections) {
    const title = section.title ?? "";
    const matching = rules.filter((rule) => rule.heading.test(title));
    const external = EXTERNAL_SERVICES.test(title);
    if (matching.length === 0 && !external) continue;
    const variables = section.variables.filter(
      (variable) =>
        !shownNames.has(variable.name) &&
        (external || matching.some((rule) => !rule.variables || rule.variables.test(variable.name))),
    );
    if (variables.length === 0) continue;
    if (matching.length > 0) providerFound = true;
    variables.forEach((variable) => shownNames.add(variable.name));
    shown.push({ title: section.title, variables });
  }
  if (!providerFound) return flat;

  const rest: EnvSection[] = [];
  const restNames = new Set<string>();
  for (const section of sections) {
    const variables = section.variables.filter(
      (variable) => !shownNames.has(variable.name) && !restNames.has(variable.name),
    );
    if (variables.length === 0) continue;
    variables.forEach((variable) => restNames.add(variable.name));
    rest.push({ title: section.title, variables });
  }
  return {
    kind: "grouped",
    shown,
    needed: shown.flatMap((section) => section.variables.filter(isNeeded).map((v) => v.name)),
    rest,
    restCount: restNames.size,
  };
}

/** Every variable of a layout, in the order the form shows them. */
export function layoutVariables(layout: EnvLayout): EnvVariable[] {
  if (layout.kind === "flat") return layout.variables;
  return [...layout.shown, ...layout.rest].flatMap((section) => section.variables);
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
 *
 * A variable listed more than once gets its value on the line the form showed
 * (`shown`, the variables as laid out), or on its first line without that.
 */
export function composeEnv(
  exampleText: string,
  values: Record<string, string>,
  extra: readonly ExtraVariable[] = [],
  shown: readonly EnvVariable[] = [],
): string {
  const typed = (name: string): string | null => {
    const value = (values[name] ?? "").replace(/[\r\n]+/g, "").trim();
    return value === "" ? null : value;
  };
  const lineOf = new Map(shown.map((variable) => [variable.name, variable.line]));
  const written = new Set<string>();
  const out = linesOf(exampleText).map((line, index) => {
    const read = readLine(line);
    if (read.kind !== "variable" || written.has(read.name)) return line;
    const at = lineOf.get(read.name);
    if (at !== undefined && at !== index) return line;
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
