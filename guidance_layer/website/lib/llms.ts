import type { Item, Node } from 'fumadocs-core/page-tree';
import { getLLMText, markdownUrl, SITE_URL, source } from '@/lib/source';

const DEMO_URL = 'https://gaik-demo.2.rahtiapp.fi';

const HEADER = `# GAIK Toolkit

> Open-source (MIT) toolkit for generative-AI knowledge work from the GAIK project at Haaga-Helia: the \`gaik\` Python package (document parsing, transcription, field extraction with the quote each value rests on, hybrid document search, classification, source-cited reports), an MCP server that gives agents these operations as tools, agent skills, a browser demo, and guidance from choosing a use case to evaluating it.

For agents:

- To set GAIK up for a user (the package, the MCP server and the agent skills), fetch ${SITE_URL}/agent-setup.md and follow it.
- Before you write install commands or code, look up the current gaik version on PyPI (https://pypi.org/pypi/gaik/json). Do not use a version from your training data.
- Each link below is its page as markdown. The whole documentation in one file: ${SITE_URL}/llms-full.txt`;

const START_HERE = `## Start here

- [Set up GAIK with your coding agent](${SITE_URL}/agent-setup.md): what a coding agent follows to add gaik to a project, connect the GAIK MCP server and install the agent skills
- [gaik on PyPI](https://pypi.org/project/gaik/): the package, its versions and extras
- [Source on GitHub](https://github.com/GAIK-project/gaik-toolkit): the code, runnable examples in implementation_layer/examples and the agent skills plugin
- [Toolkit demo](${DEMO_URL}/): every component and use case in the browser; running them needs an account
- [Agent skills](${DEMO_URL}/skills): the GAIK skills, to install as one plugin or download one by one
- [Prompts](${DEMO_URL}/prompts): ready-made prompts for the use cases, to paste into any chat assistant`;

/** The pages under a node in the order the sidebar shows them, a folder's index first. */
function pagesIn(node: Node): Item[] {
  if (node.type === 'page') return [node];
  if (node.type === 'folder') return [...(node.index ? [node.index] : []), ...node.children.flatMap(pagesIn)];
  return [];
}

function line(item: Item): string | null {
  const page = source.getNodePage(item);
  if (!page) return null;
  const description = page.data.description ? `: ${page.data.description}` : '';
  return `- [${page.data.title}](${markdownUrl(page)})${description}`;
}

/** llms.txt (https://llmstxt.org): what GAIK is, where an agent starts, and every page. */
export function llmsIndex(): string {
  const tree = source.pageTree.children;
  const topLevel = tree.filter((node) => node.type === 'page').flatMap(pagesIn);
  const sections = [
    HEADER,
    START_HERE,
    ['## Documentation', '', ...topLevel.map(line).filter(Boolean)].join('\n'),
    ...tree
      .filter((node) => node.type === 'folder')
      .map((folder) =>
        [`## ${String(folder.name)}`, '', ...pagesIn(folder).map(line).filter(Boolean)].join('\n'),
      ),
    `## Optional\n\n- [All documentation in one file](${SITE_URL}/llms-full.txt): every page above as markdown`,
  ];
  return `${sections.join('\n\n')}\n`;
}

/** llms-full.txt: every page as markdown, in the sidebar's order. */
export async function llmsFull(): Promise<string> {
  const pages = source.pageTree.children
    .flatMap(pagesIn)
    .map((item) => source.getNodePage(item))
    .filter((page) => page !== undefined);
  const texts = await Promise.all(pages.map(getLLMText));
  return `${HEADER}\n\n${texts.join('\n\n---\n\n')}\n`;
}
