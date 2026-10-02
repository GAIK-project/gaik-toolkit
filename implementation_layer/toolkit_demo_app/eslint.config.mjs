// Flat config for ESLint 9 + Next.js 16. eslint-config-next ships a native flat
// config array (its "." export), so we spread it directly instead of bridging
// the legacy eslintrc presets through FlatCompat — the compat path crashes on a
// circular-JSON validation bug with the bundled react plugin.
import { plugin as shadcn } from "@shadcn/lint";
import next from "eslint-config-next";

const eslintConfig = [
  ...next,
  // @shadcn/lint design-system rules (https://github.com/shadcn-ui/lint#rules).
  // Only no-unknown-classes is on: it catches classes Tailwind cannot generate.
  // The stricter rules (no-raw-colors, no-restyle, ...) would flag most of the
  // existing code; add them here as the design system is tightened.
  {
    files: ["**/*.{js,jsx,ts,tsx}"],
    plugins: { shadcn },
    rules: { "shadcn/no-unknown-classes": "error" },
  },
  {
    ignores: [
      "node_modules/**",
      ".venv/**",
      ".next/**",
      "out/**",
      "build/**",
      "next-env.d.ts",
    ],
  },
];

export default eslintConfig;
