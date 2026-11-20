import { describe, expect, it } from "vitest";
import { classifyLogLine, runLogLineFilter, runProgressStage } from "@/lib/poc-run-log";

// The run log showed the base64 copy of every output file the sandbox Job
// prints for downloads (#314). The block must not reach the displayed log;
// what the run printed before and after it must.

function shown(lines: string[]): string[] {
  const keep = runLogLineFilter();
  return lines.filter(keep);
}

describe("runLogLineFilter", () => {
  it("hides the files block and its markers", () => {
    expect(
      shown([
        "Processing invoice.pdf",
        "=== POC OUTPUT BEGIN === r1",
        '{"total": 12}',
        "=== POC OUTPUT END === r1",
        "=== POC FILES BEGIN === r1",
        "--- file result.json 13 --- r1",
        "eyJ0b3RhbCI6IDEyfQo=",
        "--- skipped big.pdf 9999999 --- r1",
        "=== POC FILES END === r1",
      ]),
    ).toEqual([
      "Processing invoice.pdf",
      "=== POC OUTPUT BEGIN === r1",
      '{"total": 12}',
      "=== POC OUTPUT END === r1",
    ]);
  });

  it("shows lines after the block ends", () => {
    expect(
      shown(["=== POC FILES BEGIN === ", "QUJD", "=== POC FILES END === ", "after"]),
    ).toEqual(["after"]);
  });

  it("keeps hiding a block that has not ended yet", () => {
    expect(shown(["before", "=== POC FILES BEGIN === r2", "QUJD", "REVG"])).toEqual([
      "before",
    ]);
  });

  it("leaves a log without the block as it is", () => {
    expect(shown(["a", "b"])).toEqual(["a", "b"]);
  });
});

describe("classifyLogLine", () => {
  it("does not treat TranscriptEnhancer progress wording as an error (#252)", () => {
    expect(classifyLogLine("Fixing transcription errors with TranscriptEnhancer...")).toBe("normal");
    expect(classifyLogLine("0 errors found")).toBe("normal");
  });

  it("flags real failures and exceptions as error", () => {
    expect(classifyLogLine("ValueError: missing audio stream")).toBe("error");
    expect(classifyLogLine("Traceback (most recent call last):")).toBe("error");
    expect(classifyLogLine("ERROR: model call failed")).toBe("error");
    expect(classifyLogLine("✗ extraction failed")).toBe("error");
    // A real failure stays red even when the line also mentions fixing errors.
    expect(classifyLogLine("ERROR: failed to fix 3 errors in transcript")).toBe("error");
    expect(classifyLogLine("Traceback: no module errors")).toBe("error");
  });

  it("marks success lines as ok", () => {
    expect(classifyLogLine("✓ Done successfully")).toBe("ok");
  });
});

describe("runProgressStage", () => {
  it("maps audio pipeline logs to plain-language stages", () => {
    expect(runProgressStage("pending", [])).toBe("queued");
    expect(runProgressStage("running", [])).toBe("starting");
    expect(runProgressStage("running", ["Transcribing sample.wav with Whisper..."])).toBe("transcribing");
    expect(runProgressStage("running", ["Transcribing report.wav with Whisper..."])).toBe("transcribing");
    expect(runProgressStage("running", ["Generating report PDF..."])).toBe("finalizing");
    expect(
      runProgressStage("running", [
        "Transcribing sample.wav...",
        "Fixing transcription errors with TranscriptEnhancer...",
      ]),
    ).toBe("enhancing");
    expect(
      runProgressStage("running", [
        "Fixing transcription errors with TranscriptEnhancer...",
        "Running Extractor on enhanced transcript...",
      ]),
    ).toBe("extracting");
    expect(
      runProgressStage("running", [
        "Running Extractor...",
        "Validating grounding against source transcript...",
      ]),
    ).toBe("validating");
  });
});
