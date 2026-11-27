import type { BaseLayoutProps } from "fumadocs-ui/layouts/shared";

export const DISCORD_URL = "https://discord.gg/sgEFy96vW3";

const DISCORD_PATH =
  "M20.317 4.37a19.8 19.8 0 0 0-4.885-1.515a.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.3 18.3 0 0 0-5.487 0a13 13 0 0 0-.617-1.25a.08.08 0 0 0-.079-.037A19.7 19.7 0 0 0 3.677 4.37a.1.1 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.08.08 0 0 0 .031.057a19.9 19.9 0 0 0 5.993 3.03a.08.08 0 0 0 .084-.028a14 14 0 0 0 1.226-1.994a.076.076 0 0 0-.041-.106a13 13 0 0 1-1.872-.892a.077.077 0 0 1-.008-.128a10 10 0 0 0 .372-.292a.07.07 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.07.07 0 0 1 .078.01q.181.149.373.292a.077.077 0 0 1-.006.127a12.3 12.3 0 0 1-1.873.892a.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.08.08 0 0 0 .084.028a19.8 19.8 0 0 0 6.002-3.03a.08.08 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.06.06 0 0 0-.031-.03M8.02 15.33c-1.182 0-2.157-1.085-2.157-2.419c0-1.333.956-2.419 2.157-2.419c1.21 0 2.176 1.096 2.157 2.42c0 1.333-.956 2.418-2.157 2.418m7.975 0c-1.183 0-2.157-1.085-2.157-2.419c0-1.333.955-2.419 2.157-2.419c1.21 0 2.176 1.096 2.157 2.42c0 1.333-.946 2.418-2.157 2.418";

/**
 * Shared layout configurations: nav title, header links and sidebar footer.
 *
 * Used by the DocsLayout in app/layout.tsx, which renders every page.
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
      {
        // AAIF Helsinki Hackathon server: the invite never expires and gives
        // the Participant role. Mark from Simple Icons (CC0), in text colour.
        text: (
          <>
            <svg
              viewBox="0 0 24 24"
              width="24"
              height="24"
              fill="currentColor"
              aria-hidden="true"
              style={{ display: "inline-block", marginRight: "6px", verticalAlign: "middle" }}
            >
              <path d={DISCORD_PATH} />
            </svg>
            Discord
          </>
        ),
        url: DISCORD_URL,
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

