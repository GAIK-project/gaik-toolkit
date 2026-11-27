import { describe, expect, test } from "bun:test";
import { AGENT_SETUP_URL, ONBOARD_PROMPT, llmsText } from "./agent-setup";
import { plugin, prompts, skills } from "./no-code/catalog";

describe("agent setup", () => {
  test("the onboarding prompt names the guide on the docs site", () => {
    expect(AGENT_SETUP_URL).toBe(
      "https://gaik-project.github.io/gaik-toolkit/agent-setup.md",
    );
    expect(ONBOARD_PROMPT).toBe(
      `Set up GAIK for me. Fetch ${AGENT_SETUP_URL} and follow it.`,
    );
  });

  test("llms.txt starts with its title and summary, then sends agents to the guide", () => {
    const lines = llmsText().split("\n");
    expect(lines[0]).toBe("# GAIK Toolkit demo");
    expect(lines[2].startsWith("> ")).toBe(true);
    expect(lines[4]).toContain(AGENT_SETUP_URL);
  });

  test("llms.txt links every skill's zip and every prompt in the catalog", () => {
    const text = llmsText();
    for (const skill of skills) {
      expect(text).toContain(
        `[${skill.title}](https://gaik-demo.2.rahtiapp.fi${skill.zip})`,
      );
    }
    for (const prompt of prompts) {
      expect(text).toContain(`[${prompt.title}](${prompt.githubUrl})`);
    }
    expect(text).toContain(`version ${plugin.version}`);
  });
});
