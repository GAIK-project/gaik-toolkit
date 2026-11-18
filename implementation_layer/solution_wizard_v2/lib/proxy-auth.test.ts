import { beforeEach, describe, expect, it } from "vitest";
import {
  proxyAuthConfig,
  proxyAuthEnabled,
  proxySignOutUrl,
  resetProxyAuthKeys,
  verifyAccessToken,
  type ProxyAuthConfig,
} from "./proxy-auth";

const ISSUER = "https://keycloak.example.test/realms/gaik";
const CONFIG: ProxyAuthConfig = {
  issuer: ISSUER,
  jwksUrl: "http://keycloak:8080/realms/gaik/protocol/openid-connect/certs",
  clientId: "wizard-v2",
  group: "wizard-user",
  logoutUrl: null,
};
const NOW_MS = Date.UTC(2026, 10, 18, 12, 0, 0);
const NOW_S = Math.floor(NOW_MS / 1000);

function b64url(bytes: Uint8Array | string): string {
  const raw = typeof bytes === "string" ? new TextEncoder().encode(bytes) : bytes;
  let binary = "";
  for (const b of raw) binary += String.fromCharCode(b);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function keyPair() {
  return (await crypto.subtle.generateKey(
    { name: "RSASSA-PKCS1-v1_5", modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: "SHA-256" },
    true,
    ["sign", "verify"],
  )) as CryptoKeyPair;
}

async function sign(privateKey: CryptoKey, claims: Record<string, unknown>, kid = "k1", alg = "RS256") {
  const head = b64url(JSON.stringify({ alg, kid, typ: "JWT" }));
  const body = b64url(JSON.stringify(claims));
  const sig = await crypto.subtle.sign(
    "RSASSA-PKCS1-v1_5",
    privateKey,
    new TextEncoder().encode(`${head}.${body}`),
  );
  return `${head}.${body}.${b64url(new Uint8Array(sig))}`;
}

function claims(overrides: Record<string, unknown> = {}) {
  return {
    iss: ISSUER,
    azp: "wizard-v2",
    aud: "account",
    exp: NOW_S + 300,
    iat: NOW_S - 10,
    email: "Ada@Example.test",
    email_verified: true,
    groups: ["/wizard-user"],
    ...overrides,
  };
}

let pair: CryptoKeyPair;
let fetches = 0;
async function jwksFetcher(publicKey: CryptoKey, kid = "k1"): Promise<typeof fetch> {
  const jwk = await crypto.subtle.exportKey("jwk", publicKey);
  return (async () => {
    fetches++;
    return new Response(JSON.stringify({ keys: [{ kid, kty: "RSA", alg: "RS256", use: "sig", n: jwk.n, e: jwk.e }] }));
  }) as unknown as typeof fetch;
}

beforeEach(async () => {
  resetProxyAuthKeys();
  fetches = 0;
  pair ??= await keyPair();
});

describe("verifyAccessToken", () => {
  it("returns the verified, lower-cased address of a valid token", async () => {
    const fetcher = await jwksFetcher(pair.publicKey);
    const token = await sign(pair.privateKey, claims());
    expect(await verifyAccessToken(token, CONFIG, { fetcher, nowMs: NOW_MS })).toEqual({
      email: "ada@example.test",
      groups: ["wizard-user"],
    });
  });

  it("refuses a token signed with another key", async () => {
    const other = await keyPair();
    const fetcher = await jwksFetcher(pair.publicKey);
    const token = await sign(other.privateKey, claims());
    expect(await verifyAccessToken(token, CONFIG, { fetcher, nowMs: NOW_MS })).toBeNull();
  });

  it("refuses a token whose claims were changed after signing", async () => {
    const fetcher = await jwksFetcher(pair.publicKey);
    const token = await sign(pair.privateKey, claims());
    const [h, , s] = token.split(".");
    const forged = `${h}.${b64url(JSON.stringify(claims({ email: "eve@example.test" })))}.${s}`;
    expect(await verifyAccessToken(forged, CONFIG, { fetcher, nowMs: NOW_MS })).toBeNull();
  });

  it("refuses an unsigned token (alg none)", async () => {
    const fetcher = await jwksFetcher(pair.publicKey);
    const head = b64url(JSON.stringify({ alg: "none", kid: "k1" }));
    const token = `${head}.${b64url(JSON.stringify(claims()))}.`;
    expect(await verifyAccessToken(token, CONFIG, { fetcher, nowMs: NOW_MS })).toBeNull();
  });

  it("refuses another issuer, another client and an expired token", async () => {
    const fetcher = await jwksFetcher(pair.publicKey);
    for (const bad of [
      claims({ iss: "https://other.example.test/realms/gaik" }),
      claims({ azp: "another-app", aud: "another-app" }),
      claims({ exp: NOW_S - 120 }),
      claims({ nbf: NOW_S + 120 }),
    ]) {
      const token = await sign(pair.privateKey, bad);
      expect(await verifyAccessToken(token, CONFIG, { fetcher, nowMs: NOW_MS })).toBeNull();
    }
  });

  it("refuses a token issued to another client even when its aud names this app", async () => {
    const fetcher = await jwksFetcher(pair.publicKey);
    const token = await sign(pair.privateKey, claims({ azp: "gaik-demo", aud: ["account", "wizard-v2"] }));
    expect(await verifyAccessToken(token, CONFIG, { fetcher, nowMs: NOW_MS })).toBeNull();
  });

  it("accepts a token issued to this app whatever its aud names", async () => {
    const fetcher = await jwksFetcher(pair.publicKey);
    const token = await sign(pair.privateKey, claims({ azp: "wizard-v2", aud: ["account", "gaik-demo"] }));
    expect(await verifyAccessToken(token, CONFIG, { fetcher, nowMs: NOW_MS })).not.toBeNull();
  });

  it("refuses a user outside the admitted group, such as one still pending", async () => {
    const fetcher = await jwksFetcher(pair.publicKey);
    for (const groups of [["/pending"], [], undefined]) {
      const token = await sign(pair.privateKey, claims({ groups }));
      expect(await verifyAccessToken(token, CONFIG, { fetcher, nowMs: NOW_MS })).toBeNull();
    }
  });

  it("refuses an address the identity provider has not confirmed", async () => {
    const fetcher = await jwksFetcher(pair.publicKey);
    for (const extra of [{ email_verified: false }, { email_verified: undefined }, { email: "" }]) {
      const token = await sign(pair.privateKey, claims(extra));
      expect(await verifyAccessToken(token, CONFIG, { fetcher, nowMs: NOW_MS })).toBeNull();
    }
  });

  it("signs nobody in without a token, without settings or when the keys cannot be fetched", async () => {
    const token = await sign(pair.privateKey, claims());
    const failing = (async () => new Response("down", { status: 503 })) as unknown as typeof fetch;
    expect(await verifyAccessToken(null, CONFIG)).toBeNull();
    expect(await verifyAccessToken("not-a-token", CONFIG)).toBeNull();
    expect(await verifyAccessToken(token, null)).toBeNull();
    expect(await verifyAccessToken(token, CONFIG, { fetcher: failing, nowMs: NOW_MS })).toBeNull();
  });

  it("fetches the keys once and again at most once a minute for an unknown key id", async () => {
    const fetcher = await jwksFetcher(pair.publicKey);
    const good = await sign(pair.privateKey, claims());
    const unknown = await sign(pair.privateKey, claims(), "rotated");
    await verifyAccessToken(good, CONFIG, { fetcher, nowMs: NOW_MS });
    await verifyAccessToken(good, CONFIG, { fetcher, nowMs: NOW_MS + 1000 });
    expect(fetches).toBe(1);
    await verifyAccessToken(unknown, CONFIG, { fetcher, nowMs: NOW_MS + 2000 });
    await verifyAccessToken(unknown, CONFIG, { fetcher, nowMs: NOW_MS + 3000 });
    expect(fetches).toBe(2);
  });
});

describe("when Keycloak cannot be reached", () => {
  it("keeps the keys it has and asks again at most once a minute", async () => {
    const good = await jwksFetcher(pair.publicKey);
    const token = await sign(pair.privateKey, claims({ exp: NOW_S + 3600 }));
    let down = 0;
    const failing = (async () => {
      down++;
      throw new Error("connection refused");
    }) as unknown as typeof fetch;
    expect(await verifyAccessToken(token, CONFIG, { fetcher: good, nowMs: NOW_MS })).not.toBeNull();
    // Past the 10-minute refresh, Keycloak is down: the cached key still verifies.
    const later = NOW_MS + 11 * 60 * 1000;
    expect(await verifyAccessToken(token, CONFIG, { fetcher: failing, nowMs: later })).not.toBeNull();
    expect(await verifyAccessToken(token, CONFIG, { fetcher: failing, nowMs: later + 1000 })).not.toBeNull();
    expect(down).toBe(1);
    // A minute on, it is asked again.
    await verifyAccessToken(token, CONFIG, { fetcher: failing, nowMs: later + 61 * 1000 });
    expect(down).toBe(2);
  });

  it("signs nobody in when it never had the keys", async () => {
    const token = await sign(pair.privateKey, claims());
    const failing = (async () => {
      throw new Error("connection refused");
    }) as unknown as typeof fetch;
    expect(await verifyAccessToken(token, CONFIG, { fetcher: failing, nowMs: NOW_MS })).toBeNull();
  });
});

describe("proxy auth settings", () => {
  it("is on only with WIZARD_AUTH_MODE=proxy", () => {
    expect(proxyAuthEnabled({ WIZARD_AUTH_MODE: "proxy" } as unknown as NodeJS.ProcessEnv)).toBe(true);
    expect(proxyAuthEnabled({} as unknown as NodeJS.ProcessEnv)).toBe(false);
    expect(proxyAuthEnabled({ WIZARD_AUTH_MODE: "dev" } as unknown as NodeJS.ProcessEnv)).toBe(false);
  });

  it("needs the issuer and the client id, and defaults the keys URL and the group", () => {
    expect(proxyAuthConfig({ WIZARD_OIDC_ISSUER: ISSUER } as unknown as NodeJS.ProcessEnv)).toBeNull();
    expect(
      proxyAuthConfig({ WIZARD_OIDC_ISSUER: `${ISSUER}/`, WIZARD_OIDC_CLIENT_ID: "wizard-v2" } as unknown as NodeJS.ProcessEnv),
    ).toEqual({
      issuer: ISSUER,
      jwksUrl: `${ISSUER}/protocol/openid-connect/certs`,
      clientId: "wizard-v2",
      group: "wizard-user",
      logoutUrl: null,
    });
  });

  it("signs out through the proxy and then Keycloak when a logout URL is set", () => {
    expect(proxySignOutUrl(CONFIG)).toBe("/oauth2/sign_out");
    const logoutUrl = `${ISSUER}/protocol/openid-connect/logout?client_id=wizard-v2`;
    expect(proxySignOutUrl({ ...CONFIG, logoutUrl })).toBe(`/oauth2/sign_out?rd=${encodeURIComponent(logoutUrl)}`);
  });
});
