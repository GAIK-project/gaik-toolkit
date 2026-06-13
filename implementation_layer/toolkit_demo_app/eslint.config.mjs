// Flat config for ESLint 9 + Next.js 16. eslint-config-next ships a native flat
// config array (its "." export), so we spread it directly instead of bridging
// the legacy eslintrc presets through FlatCompat — the compat path crashes on a
// circular-JSON validation bug with the bundled react plugin.
import next from "eslint-config-next";

const eslintConfig = [
  ...next,
  {
    ignores: [
      "node_modules/**",
      ".next/**",
      "out/**",
      "build/**",
      "next-env.d.ts",
    ],
  },
];

export default eslintConfig;
