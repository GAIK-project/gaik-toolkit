import { describe, expect, it } from "vitest";
import {
  MAX_INPUT_BYTES,
  MULTIPART_ALLOWANCE_BYTES,
  declaredLengthProblem,
  fileSizeProblem,
} from "./upload-limits";

// The relay checked only a declared content-length: a chunked body skipped
// the check and was buffered whole (#297).

describe("declaredLengthProblem", () => {
  it("accepts a length within the limit", () => {
    expect(declaredLengthProblem("1024")).toBeNull();
    expect(declaredLengthProblem(String(MAX_INPUT_BYTES))).toBeNull();
  });

  it("refuses a request that does not say its length", () => {
    expect(declaredLengthProblem(null)?.status).toBe(411);
    expect(declaredLengthProblem("")?.status).toBe(411);
    expect(declaredLengthProblem("abc")?.status).toBe(411);
  });

  it("leaves room for the form around a file just under the limit", () => {
    // The declared length is the whole multipart request, not the file.
    expect(declaredLengthProblem(String(MAX_INPUT_BYTES + 300))).toBeNull();
    expect(fileSizeProblem(MAX_INPUT_BYTES)).toBeNull();
  });

  it("refuses a length over the limit, and names the limit", () => {
    const refused = declaredLengthProblem(String(MAX_INPUT_BYTES + MULTIPART_ALLOWANCE_BYTES + 1));
    expect(refused).toEqual({ status: 413, detail: "the file is larger than 50 MB" });
    expect(fileSizeProblem(MAX_INPUT_BYTES + 1)?.status).toBe(413);
    expect(fileSizeProblem(10)).toBeNull();
  });
});
