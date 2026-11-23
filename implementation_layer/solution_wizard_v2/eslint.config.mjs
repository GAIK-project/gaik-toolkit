// Flat config for the ESLint CLI: Next.js 16 has no `next lint`, and
// eslint-config-next 16 ships flat configs. The same two presets as the old
// .eslintrc.json ("next/core-web-vitals", "next/typescript").
import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // eslint-plugin-react-hooks 7 (with eslint-config-next 16) adds the React
  // Compiler rules to the same preset. They are new to this code, which does
  // not use the compiler, and it has about forty findings in six components:
  // they show as warnings until those are worked through, and are then errors
  // again by removing this block.
  {
    rules: {
      "react-hooks/immutability": "warn",
      "react-hooks/refs": "warn",
      "react-hooks/set-state-in-effect": "warn",
    },
  },
  // Giving globalIgnores replaces the defaults of eslint-config-next, so its
  // four come first; the rest is what this app generates.
  globalIgnores([
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    ".venv/**",
    "coverage/**",
    "test-results/**",
    "playwright-report/**",
    "blob-report/**",
  ]),
]);

export default eslintConfig;
