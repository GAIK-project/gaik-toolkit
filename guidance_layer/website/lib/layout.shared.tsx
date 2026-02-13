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
            width="56"
            height="56"
            style={{ display: "inline-block", marginRight: "8px" }}
          />
          GAIK
        </>
      ),
    },
    // see https://fumadocs.dev/docs/ui/navigation/links
    links: [
      {
        text: (
          <>
            <img
              src="/gaik-toolkit/logos/github.png"
              alt="GitHub"
              width="24"
              height="24"
              style={{ display: "inline-block", marginRight: "6px", verticalAlign: "middle" }}
            />
            GitHub
          </>
        ),
        url: "https://github.com/GAIK-project/gaik-toolkit",
      },
      {
        text: (
          <>
            <img
              src="/gaik-toolkit/logos/pypi.png"
              alt="PyPI"
              width="24"
              height="24"
              style={{ display: "inline-block", marginRight: "6px", verticalAlign: "middle" }}
            />
            PyPI
          </>
        ),
        url: "https://pypi.org/project/gaik/",
      },
      {
        text: (
          <>
            <img
              src="/gaik-toolkit/images/toolkit.png"
              alt="Toolkit Demo"
              width="24"
              height="24"
              style={{ display: "inline-block", marginRight: "6px", verticalAlign: "middle" }}
            />
            Toolkit Demo
          </>
        ),
        url: "https://gaik-demo.2.rahtiapp.fi/",
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

