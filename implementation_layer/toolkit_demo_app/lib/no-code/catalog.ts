import catalog from "./catalog.generated.json";

/**
 * The skills and prompts shown on /skills and /prompts.
 *
 * `catalog.generated.json` and `public/downloads/skills/*.zip` are built from
 * implementation_layer/no-code-assets by scripts/build_no_code_catalog.py; edit
 * the sources there, not the generated files.
 */
export interface Skill {
  id: string;
  group: "no-code" | "developer";
  title: string;
  tagline: string;
  description: string;
  input: string;
  output: string;
  needs: string[];
  setup: string[];
  kit: { zip: string; zipBytes: number } | null;
  tryPrompt: string;
  files: string[];
  zip: string;
  zipBytes: number;
  githubUrl: string;
  guideUrl: string | null;
}

export interface PromptVariant {
  label: string;
  file: string;
  text: string;
}

export interface Prompt {
  id: string;
  title: string;
  tagline: string;
  input: string;
  output: string;
  then: string;
  variants: PromptVariant[];
  githubUrl: string;
}

export const plugin = catalog.plugin;
export const skills = catalog.skills as Skill[];
export const prompts = catalog.prompts as Prompt[];

export const noCodeSkills = skills.filter((s) => s.group === "no-code");
export const developerSkills = skills.filter((s) => s.group === "developer");

const encode = encodeURIComponent;

/**
 * Deep links that pre-fill a prompt without sending it. Only schemes the
 * vendors document are used; each app shows the text for review first.
 */
export const launch = {
  /** Claude Desktop, https://support.claude.com/en/articles/14729294 */
  claude: (prompt: string) => `claude://claude.ai/new?q=${encode(prompt)}`,
  /** Claude Desktop's Code tab, same page as above */
  claudeDesktopCode: (prompt: string) =>
    `claude://code/new?q=${encode(prompt)}`,
  /** Claude Code on the web, https://support.claude.com/en/articles/14898120 (needs Claude Code access) */
  claudeCodeWeb: (prompt: string) =>
    `https://claude.ai/code/new?q=${encode(prompt)}`,
  /** Claude Code in a terminal, https://code.claude.com/docs/en/deep-links (5,000 characters at most) */
  claudeCode: (prompt: string) => `claude-cli://open?q=${encode(prompt)}`,
  /** Cursor, https://cursor.com/docs/reference/deeplinks */
  cursor: (prompt: string) =>
    `cursor://anysphere.cursor-deeplink/prompt?text=${encode(prompt)}`,
};

/**
 * Chat apps. `?q=` pre-fills the prompt box: tested with a 7,400-character
 * prompt on ChatGPT, which also sends it at once. Claude's `?q=` is not
 * documented for the web app, so the button copies the prompt too.
 */
export const chatApps = {
  chatgpt: (prompt: string) => `https://chatgpt.com/?q=${encode(prompt)}`,
  claude: (prompt: string) => `https://claude.ai/new?q=${encode(prompt)}`,
};

export const installTabs = [
  {
    name: "Claude Desktop",
    language: "bash",
    code: `# Customize → Plugins → Add → Add marketplace → Add from a repository\n${plugin.marketplace}\n# Sync, then add Gaik toolkit from the Discover tab`,
    copy: plugin.marketplace,
  },
  {
    name: "Claude Code",
    language: "bash",
    code: `/plugin marketplace add ${plugin.marketplace}\n/plugin install ${plugin.name}@${plugin.name}`,
  },
  {
    name: "Codex",
    language: "bash",
    code: `codex plugin marketplace add ${plugin.marketplace}\ncodex plugin add ${plugin.name}@${plugin.name}`,
  },
  {
    name: "Copilot CLI",
    language: "bash",
    code: `copilot plugin marketplace add ${plugin.marketplace}\ncopilot plugin install ${plugin.name}@${plugin.name}`,
  },
];

export function formatBytes(bytes: number): string {
  return bytes < 1024 * 1024
    ? `${Math.max(1, Math.round(bytes / 1024))} kB`
    : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
