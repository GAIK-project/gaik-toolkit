import type { BaseLayoutProps } from "fumadocs-ui/layouts/shared";

/**
 * Shared layout configurations
 *
 * you can customise layouts individually from:
 * Home Layout: app/(home)/layout.tsx
 * Docs Layout: app/docs/layout.tsx
 */
export function baseOptions(): BaseLayoutProps {
  return {
    nav: {
      title: (
        <>
          <img
            src="/gaik-toolkit/logos/gaik-logo-letter-only.png"
            alt="Logo"
            width="24"
            height="24"
            style={{ display: 'inline-block', marginRight: '8px' }}
          />
          GAIK
        </>
      ),
    },
    // see https://fumadocs.dev/docs/ui/navigation/links
    links: [
      {
        text: 'GitHub',
        url: 'https://github.com/GAIK-project/gaik-toolkit',
      },
    ],
  };
}
