import { getLLMText, source } from '@/lib/source';

// The page a coding agent follows to set GAIK up (content/docs/agent-setup.mdx), at the
// address the demo's "Onboard your agent" prompt names: <site>/agent-setup.md.
export const dynamic = 'force-static';

export async function GET() {
  const page = source.getPage(['agent-setup']);
  if (!page) throw new Error('content/docs/agent-setup.mdx is missing');

  return new Response(await getLLMText(page), {
    headers: { 'Content-Type': 'text/markdown; charset=utf-8' },
  });
}
