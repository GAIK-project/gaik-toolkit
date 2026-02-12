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
            alt="GAIK logo"
            width="44"
            height="44"
            style={{ display: "inline-block", marginRight: "8px" }}
          />
          GAIK
        </>
      ),
    },
    // see https://fumadocs.dev/docs/ui/navigation/links
    links: [
      {
        text: "GitHub",
        url: "https://github.com/GAIK-project/gaik-toolkit",
      },
    ],
    sidebar: {
      footer: (
        <img
          src="/gaik-toolkit/logos/eu_logo.png"
          alt="Co-funded by European Union"
          style={{ width: "100%", height: "auto" }}
        />
      ),
    },
  } as BaseLayoutProps;
}

