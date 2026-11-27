import { getLLMText, source } from '@/lib/source';
import { notFound } from 'next/navigation';

// Written to out/md/<page>.md at build time: GitHub Pages serves it as markdown.
export const dynamic = 'force-static';

export async function GET(_request: Request, context: RouteContext<'/md/[...slug]'>) {
  const { slug } = await context.params;
  const last = slug.at(-1) ?? '';
  if (!last.endsWith('.md')) notFound();
  const slugs = [...slug.slice(0, -1), last.slice(0, -'.md'.length)];
  const page = source.getPage(slugs.length === 1 && slugs[0] === 'index' ? [] : slugs);
  if (!page) notFound();

  return new Response(await getLLMText(page), {
    headers: { 'Content-Type': 'text/markdown; charset=utf-8' },
  });
}

export function generateStaticParams() {
  return source.getPages().map((page) => {
    const slugs = page.slugs.length ? page.slugs : ['index'];
    return { slug: [...slugs.slice(0, -1), `${slugs.at(-1)}.md`] };
  });
}
