// Sign-in through an OIDC proxy (oauth2-proxy in front of the web app, Keycloak
// behind it). Selected at run time with WIZARD_AUTH_MODE=proxy; it then takes
// precedence over the dev login and Supabase.
//
// The proxy signs the user in and forwards the identity provider's access token
// in X-Forwarded-Access-Token. The app does not take the proxy's word for who the
// user is: it checks the token's signature against the issuer's published keys
// (JWKS), its issuer, the client it was issued to, its expiry and the group that
// may use this app. A request that reaches the app past the proxy, with a header
// written by hand, therefore signs nobody in.
//
// Web Crypto only, RS256 only (Keycloak's default): this runs in the proxy
// (proxy.ts) as well as in Server Actions and route handlers.

export const ACCESS_TOKEN_HEADER = "x-forwarded-access-token";

/** Clock difference between Keycloak and this pod that a token's times may have. */
const CLOCK_SKEW_S = 30;
/** How long fetched signing keys are used before they are fetched again. */
const JWKS_TTL_MS = 10 * 60 * 1000;
/** At most one fetch per this interval for a key id the cached set does not have. */
const JWKS_MISS_REFETCH_MS = 60 * 1000;

export type ProxyAuthConfig = {
  issuer: string;
  jwksUrl: string;
  clientId: string;
  group: string;
  logoutUrl: string | null;
};

export function proxyAuthEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  return env.WIZARD_AUTH_MODE?.trim() === "proxy";
}

/**
 * The proxy sign-in settings, or null when one is missing. A missing setting
 * means nobody is signed in, never that the checks are skipped.
 */
export function proxyAuthConfig(env: NodeJS.ProcessEnv = process.env): ProxyAuthConfig | null {
  const issuer = env.WIZARD_OIDC_ISSUER?.trim().replace(/\/+$/, "");
  const clientId = env.WIZARD_OIDC_CLIENT_ID?.trim();
  if (!issuer || !clientId) return null;
  return {
    issuer,
    // In the cluster the keys are fetched from Keycloak's Service, not over the
    // public route; the issuer in the token stays the public address.
    jwksUrl: env.WIZARD_OIDC_JWKS_URL?.trim() || `${issuer}/protocol/openid-connect/certs`,
    clientId,
    group: env.WIZARD_OIDC_GROUP?.trim() || "wizard-user",
    logoutUrl: env.WIZARD_OIDC_LOGOUT_URL?.trim() || null,
  };
}

type Jwk = { kid?: string; kty?: string; alg?: string; use?: string; n?: string; e?: string };
type KeyCache = { url: string; keys: Map<string, CryptoKey>; fetchedAt: number; missAt: number };
let keyCache: KeyCache | null = null;

/** For tests: forget the fetched keys. */
export function resetProxyAuthKeys(): void {
  keyCache = null;
}

async function fetchKeys(url: string, fetcher: typeof fetch): Promise<Map<string, CryptoKey>> {
  const response = await fetcher(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`JWKS fetch failed: ${response.status}`);
  const body = (await response.json()) as { keys?: Jwk[] };
  const keys = new Map<string, CryptoKey>();
  for (const jwk of body.keys ?? []) {
    if (jwk.kty !== "RSA" || !jwk.kid || !jwk.n || !jwk.e) continue;
    if (jwk.use && jwk.use !== "sig") continue;
    if (jwk.alg && jwk.alg !== "RS256") continue;
    const key = await crypto.subtle.importKey(
      "jwk",
      { kty: "RSA", n: jwk.n, e: jwk.e, alg: "RS256", ext: true },
      { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
      false,
      ["verify"],
    );
    keys.set(jwk.kid, key);
  }
  return keys;
}

async function signingKey(
  kid: string,
  url: string,
  fetcher: typeof fetch,
  now: number,
): Promise<CryptoKey | null> {
  const cached = keyCache?.url === url ? keyCache : null;
  if (!cached || now - cached.fetchedAt > JWKS_TTL_MS) {
    // A failed refresh keeps the keys already fetched: Keycloak restarting for a
    // minute must not sign every user out while its key has not changed. The next
    // attempt waits a minute, so an unreachable Keycloak is not asked on every
    // request. Without keys at all nobody is signed in.
    if (cached && now - cached.missAt < JWKS_MISS_REFETCH_MS) {
      // A refresh failed a moment ago; use what we have.
    } else {
      try {
        keyCache = { url, keys: await fetchKeys(url, fetcher), fetchedAt: now, missAt: 0 };
      } catch (error) {
        if (!cached) throw error;
        keyCache = { ...cached, missAt: now };
      }
    }
  }
  const current = keyCache as KeyCache;
  const known = current.keys.get(kid);
  if (known) return known;
  // Keycloak rotated its key: fetch once more, but not on every request that
  // names an unknown key id.
  if (now - current.missAt < JWKS_MISS_REFETCH_MS) return null;
  keyCache = { url, keys: await fetchKeys(url, fetcher), fetchedAt: now, missAt: now };
  return keyCache.keys.get(kid) ?? null;
}

function base64UrlDecode(part: string): Uint8Array {
  const base64 = part.replace(/-/g, "+").replace(/_/g, "/");
  const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4);
  const binary = atob(padded);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

function decodeJson(part: string): Record<string, unknown> | null {
  try {
    const value = JSON.parse(new TextDecoder().decode(base64UrlDecode(part)));
    return value && typeof value === "object" && !Array.isArray(value) ? value : null;
  } catch {
    return null;
  }
}

export type ProxyUser = { email: string; groups: string[] };

/**
 * The user a forwarded access token stands for, or null when the token is
 * missing, not signed by the issuer's key, expired, issued to another client,
 * or for a user outside the group this app admits.
 */
export async function verifyAccessToken(
  token: string | null | undefined,
  config: ProxyAuthConfig | null = proxyAuthConfig(),
  options: { fetcher?: typeof fetch; nowMs?: number } = {},
): Promise<ProxyUser | null> {
  if (!token || !config) return null;
  const parts = token.split(".");
  if (parts.length !== 3) return null;
  const header = decodeJson(parts[0]);
  const claims = decodeJson(parts[1]);
  if (!header || !claims) return null;
  if (header.alg !== "RS256" || typeof header.kid !== "string") return null;

  const nowMs = options.nowMs ?? Date.now();
  let key: CryptoKey | null;
  try {
    key = await signingKey(header.kid, config.jwksUrl, options.fetcher ?? fetch, nowMs);
  } catch {
    return null;
  }
  if (!key) return null;

  let signatureOk = false;
  try {
    signatureOk = await crypto.subtle.verify(
      "RSASSA-PKCS1-v1_5",
      key,
      base64UrlDecode(parts[2]) as BufferSource,
      new TextEncoder().encode(`${parts[0]}.${parts[1]}`) as BufferSource,
    );
  } catch {
    return null;
  }
  if (!signatureOk) return null;

  const now = Math.floor(nowMs / 1000);
  if (claims.iss !== config.issuer) return null;
  if (typeof claims.exp !== "number" || claims.exp + CLOCK_SKEW_S < now) return null;
  if (typeof claims.nbf === "number" && claims.nbf - CLOCK_SKEW_S > now) return null;
  // Keycloak names the client a token was issued to in azp. The proxy signs in
  // as this app's own client, so a token issued to any other client is refused,
  // even when its aud also names this app.
  if (claims.azp !== config.clientId) return null;

  const email = typeof claims.email === "string" ? claims.email.trim().toLowerCase() : "";
  // An address the identity provider has not confirmed is only a claim.
  if (!email || claims.email_verified !== true) return null;

  const groups = Array.isArray(claims.groups)
    ? claims.groups.filter((g): g is string => typeof g === "string").map((g) => g.replace(/^\//, ""))
    : [];
  if (!groups.includes(config.group)) return null;
  return { email, groups };
}

/**
 * Where "Sign out" sends the browser: the proxy's sign-out, which clears its
 * cookie and then ends the Keycloak session too when a logout URL is set.
 */
export function proxySignOutUrl(config: ProxyAuthConfig | null = proxyAuthConfig()): string {
  const logout = config?.logoutUrl;
  return logout ? `/oauth2/sign_out?rd=${encodeURIComponent(logout)}` : "/oauth2/sign_out";
}
