import { plugin, prompts, skills } from "@/lib/no-code/catalog";

/** The demo's public address, as in app/layout.tsx. */
const DEMO_URL = "https://gaik-demo.2.rahtiapp.fi";
const DOCS_URL = "https://gaik-project.github.io/gaik-toolkit";

/** The guide a coding agent follows: guidance_layer/website/content/docs/agent-setup.mdx. */
export const AGENT_SETUP_URL = `${DOCS_URL}/agent-setup.md`;

/** What "Onboard your agent" copies, in the shape Vercel and others use. */
export const ONBOARD_PROMPT = `Set up GAIK for me. Fetch ${AGENT_SETUP_URL} and follow it.`;

/**
 * The demo's llms.txt (https://llmstxt.org): where an agent starts, and the
 * no-code assets this site serves, from the same catalog as /skills and /prompts.
 */
export function llmsText(): string {
  const skillLines = skills.map(
    (skill) =>
      `- [${skill.title}](${DEMO_URL}${skill.zip}): ${skill.tagline} Source: ${skill.githubUrl}`,
  );
  const promptLines = prompts.map(
    (prompt) => `- [${prompt.title}](${prompt.githubUrl}): ${prompt.tagline}`,
  );

  return `# GAIK Toolkit demo

> A browser demo of the GAIK toolkit, the open-source (MIT) Python package gaik for generative-AI knowledge work: every component, module and use case runs here on examples or the visitor's own files. Running a demo needs an account; the pages, the agent skills and the prompts are open.

For agents: to set GAIK up for a user (the gaik package, the GAIK MCP server and the agent skills), fetch ${AGENT_SETUP_URL} and follow it. The documentation, every page as markdown: ${DOCS_URL}/llms.txt

## Start here

- [Set up GAIK with your coding agent](${AGENT_SETUP_URL}): what a coding agent follows to add gaik to a project, connect the MCP server and install the agent skills
- [Documentation for agents](${DOCS_URL}/llms.txt): the index of the GAIK documentation
- [gaik on PyPI](https://pypi.org/project/gaik/): the package and its extras
- [Demo home](${DEMO_URL}/): the components, modules and use cases to try

## Agent skills

The ${plugin.name} plugin (version ${plugin.version}) holds every skill below. Install it from the marketplace ${plugin.marketplace}: in Claude Code \`claude plugin marketplace add ${plugin.marketplace}\` and \`claude plugin install ${plugin.name}@${plugin.name}\`; in Codex \`codex plugin marketplace add ${plugin.marketplace}\` and \`codex plugin add ${plugin.name}@${plugin.name}\`. Each link below is one skill as a zip file. The page: ${DEMO_URL}/skills

${skillLines.join("\n")}

## Prompts

Ready-made prompts to paste into a chat assistant; no install. The page: ${DEMO_URL}/prompts

${promptLines.join("\n")}
`;
}
