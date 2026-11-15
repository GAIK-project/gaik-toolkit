import { BASE_CSP_DIRECTIVES } from "./csp";

// Sent with every page, API response and file. The PDF previews frame this
// site's own URLs only, so framing stays same-origin. Pages also get a nonce
// policy with script-src from proxy.ts, which repeats these directives
// (lib/csp.ts).
export const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "SAMEORIGIN" },
  {
    key: "Content-Security-Policy",
    value: BASE_CSP_DIRECTIVES.join("; "),
  },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Strict-Transport-Security", value: "max-age=31536000" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
  },
];
