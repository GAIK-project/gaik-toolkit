import { describe, expect, test } from "bun:test";
import { intakeProblems, userTextsOf } from "./verify";

const intake = (description: string, answers: string[]) => ({
  description,
  questions: answers.map((answer, i) => ({
    id: `Q${i + 1}`,
    question: "q",
    answer,
  })),
});

describe("intakeProblems", () => {
  const texts = [
    "We use an AI tool to read CVs.\n\nStage: In regular use.",
    "Only our own staff.",
  ];

  test("accepts the user's own words, whitespace aside", () => {
    expect(
      intakeProblems(
        intake("We use an AI tool   to read CVs.\nStage: In regular use.", [
          "Only our own staff.",
          "unknown",
        ]),
        texts,
      ),
    ).toEqual([]);
  });

  test("rejects a description the user did not write", () => {
    const problems = intakeProblems(intake("It ranks applicants.", []), texts);
    expect(problems).toHaveLength(1);
    expect(problems[0]).toContain("description");
  });

  test("rejects an answer the user did not give", () => {
    const problems = intakeProblems(
      intake("We use an AI tool to read CVs.", ["Yes, we told everyone."]),
      texts,
    );
    expect(problems[0]).toContain("Q1");
  });

  test("an empty description is a problem", () => {
    expect(intakeProblems(intake("  ", []), texts)[0]).toContain("empty");
  });
});

describe("userTextsOf", () => {
  test("keeps only the text parts of user messages", () => {
    expect(
      userTextsOf([
        { role: "user", parts: [{ type: "text", text: "hello" }] },
        { role: "assistant", parts: [{ type: "text", text: "no" }] },
        {
          role: "user",
          parts: [{ type: "tool-x" }, { type: "text", text: "b" }],
        },
      ]),
    ).toEqual(["hello", "b"]);
  });
});
