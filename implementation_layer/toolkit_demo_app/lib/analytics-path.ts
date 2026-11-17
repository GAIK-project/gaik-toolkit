// PostHog is reached through this site: next.config.ts rewrites the paths below
// ANALYTICS_PATH to PostHog's hosts, and posthog-js sends there
// (instrumentation-client.ts). The browser attaches this site's cookies to those
// requests, and the rewrite would hand them on to PostHog: the Supabase session,
// admin_session and any other. proxy.ts forwards them without the Cookie header.

/** Where posthog-js sends; every rewrite to another host is below it. */
export const ANALYTICS_PATH = "/a";

/**
 * True for a path the PostHog rewrites match. Next.js matches rewrite sources
 * without regard to case, so "/A/e/" reaches PostHog too.
 */
export function isAnalyticsPath(pathname: string): boolean {
  const path = pathname.toLowerCase();
  return path === ANALYTICS_PATH || path.startsWith(`${ANALYTICS_PATH}/`);
}
