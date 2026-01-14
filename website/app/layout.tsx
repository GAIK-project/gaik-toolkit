import '@/app/global.css';
import { RootProvider } from 'fumadocs-ui/provider/next';
import { DocsLayout } from 'fumadocs-ui/layouts/docs';
import { Inter } from 'next/font/google';
import type { Metadata } from 'next';
import { baseOptions } from '@/lib/layout.shared';
import { source } from '@/lib/source';

const inter = Inter({
  subsets: ['latin'],
});

export const metadata: Metadata = {
  title: {
    default: 'GAIK - Generative AI-Enhanced Knowledge Management',
    template: '%s | GAIK Documentation',
  },
  description: 'Multi-provider AI toolkit for Python with structured data extraction and document parsing. Bridging research, technology and real-world business applications.',
  keywords: [
    'generative AI',
    'knowledge management',
    'business AI',
    'research',
    'open source',
    'AI toolkit',
    'Python',
    'data extraction',
    'PDF parsing',
    'OpenAI',
    'Anthropic',
    'Google AI',
    'Azure',
    'Pydantic',
    'structured output',
  ],
  authors: [
    {
      name: 'GAIK Consortium',
      url: 'https://www.haaga-helia.fi',
    },
  ],
  metadataBase: new URL('https://gaik-project.github.io/gaik-toolkit'),
  openGraph: {
    type: 'website',
    locale: 'en_US',
    url: 'https://gaik-project.github.io/gaik-toolkit',
    siteName: 'GAIK Documentation',
    title: 'GAIK - Generative AI-Enhanced Knowledge Management',
    description: 'Multi-provider AI toolkit for Python with structured data extraction and document parsing. Bridging research, technology and real-world business applications.',
    images: [
      {
        url: '/gaik-toolkit/logos/gaik_logo_medium.png',
        width: 512,
        height: 512,
        alt: 'GAIK - Generative AI-Enhanced Knowledge Management',
      },
    ],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'GAIK - Generative AI-Enhanced Knowledge Management',
    description: 'Multi-provider AI toolkit for Python with structured data extraction and document parsing.',
    images: ['/gaik-toolkit/logos/gaik_logo_medium.png'],
  },
};

export default function Layout({ children }: LayoutProps<'/'>) {
  return (
    <html lang="en" className={inter.className} suppressHydrationWarning>
      <body className="flex flex-col min-h-screen">
        <RootProvider
          search={{
            options: {
              type: 'static',
              api: '/gaik-toolkit/api/search',
            },
          }}
        >
          <DocsLayout tree={source.pageTree} {...baseOptions()}>
            {children}
          </DocsLayout>
        </RootProvider>
      </body>
    </html>
  );
}
