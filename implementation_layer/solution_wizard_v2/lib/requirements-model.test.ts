import { describe, expect, it } from "vitest";
import {
  REQUIREMENT_POINTS,
  openingQuestion,
  nextQuestion,
} from "@/lib/requirements-model";

describe("requirements-model", () => {
  it("opens with the first point", () => {
    expect(openingQuestion()).toContain(REQUIREMENT_POINTS[0]);
  });

  it("asks the point after the one just answered", () => {
    // 1 answer recorded → next question is points[1].
    expect(nextQuestion(REQUIREMENT_POINTS, 1)).toContain(REQUIREMENT_POINTS[1]);
  });

  it("wraps up once every point has an answer", () => {
    const reply = nextQuestion(REQUIREMENT_POINTS, REQUIREMENT_POINTS.length);
    expect(reply).toContain("Gate 1");
    // No question text leaks into the wrap-up.
    expect(reply).not.toContain(REQUIREMENT_POINTS[0]);
  });
});
