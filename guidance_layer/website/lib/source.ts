import { docs } from '@/.source/server';
import { type InferPageType, loader } from 'fumadocs-core/source';
import { lucideIconsPlugin } from 'fumadocs-core/source/lucide-icons';

// See https://fumadocs.dev/docs/headless/source-api for more info
export const source = loader({
  baseUrl: '/',
  source: docs.toFumadocsSource(),
  plugins: [lucideIconsPlugin()],
});

export function getPageImage(page: InferPageType<typeof source>) {
  const segments = [...page.slugs, 'image.png'];

  return {
    segments,
    url: `/og/${segments.join('/')}`,
  };
}

/** Where the site is published; the markdown for agents carries absolute links. */
export const SITE_URL = 'https://gaik-project.github.io/gaik-toolkit';

type DocsPage = InferPageType<typeof source>;

/** The page as HTML: `/toolkit/x` is served at `<site>/toolkit/x/`. */
export function pageUrl(page: DocsPage): string {
  return `${SITE_URL}${page.url === '/' ? '/' : `${page.url}/`}`;
}

/** The page as markdown, from app/md/[...slug]/route.ts: `<site>/md/toolkit/x.md`. */
export function markdownUrl(page: DocsPage): string {
  return `${SITE_URL}/md/${page.slugs.length ? page.slugs.join('/') : 'index'}.md`;
}

/**
 * The pages' own links are site-relative (`/toolkit/x`, `/images/y.png`) and the site
 * sits under a base path, so a markdown file read on its own needs them absolute.
 */
export function absoluteLinks(markdown: string): string {
  return markdown
    .replace(/\]\(\/(?!\/)/g, `](${SITE_URL}/`)
    .replace(/(src|href)="\/(?!\/)/g, `$1="${SITE_URL}/`);
}

/**
 * Drops the heading ids the processed text carries (`## Title [#title]`) and the runs of
 * blank lines left where imports were. Two blank lines stay, as Python code has them.
 */
function tidy(markdown: string): string {
  return markdown
    .replace(/^(#{1,6} .*?) \[#[^\]\s]+\]$/gm, '$1')
    .replace(/\n{4,}/g, '\n\n')
    .trim();
}

export async function getLLMText(page: DocsPage) {
  const processed = await page.data.getText('processed');
  const description = page.data.description ? `\n\n> ${page.data.description}` : '';

  return `# ${page.data.title}${description}

Source: ${pageUrl(page)}. Every page of these docs as markdown: ${SITE_URL}/llms.txt

${tidy(absoluteLinks(processed))}
`;
}
