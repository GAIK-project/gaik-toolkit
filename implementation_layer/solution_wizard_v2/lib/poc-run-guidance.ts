import type { PocInputFile } from "@/lib/poc-auto-run";

export type PocActionEmphasis = {
  /** True when adding a test file is the single primary next action (#252). */
  uploadPrimary: boolean;
  /** True when the manual Run / Run again button should carry primary emphasis. */
  runPrimary: boolean;
  /** True when the manual Run button should wait (uploading or an auto-run is starting now). */
  runQueued: boolean;
  /** Names of the wizard's ready sample files in sample_input/. */
  sampleNames: string[];
  /** Names of the user's own uploaded test files in sample_input/. */
  ownNames: string[];
};

/**
 * Decides which PoC step owns the primary button so "Add test file" and "Run
 * the test" never compete as two primary actions at the same time (#252).
 */
export function pocActionEmphasis(input: {
  pocGenerated: boolean;
  pocReady: boolean;
  checkFailed: boolean;
  runPhase: string;
  autoRunDecision: "run" | "adopt" | "wait";
  autoRunNeedsInput: boolean;
  autoRunComing: boolean;
  autoRunWaiting: boolean;
  inputBusy: boolean;
  pocInputs: readonly PocInputFile[];
  ownInputs: readonly PocInputFile[];
}): PocActionEmphasis {
  const sampleNames = input.pocInputs.filter((f) => f.uploaded === false).map((f) => f.name);
  const ownNames = input.ownInputs.map((f) => f.name);

  const packageUsable = input.pocGenerated && input.pocReady && !input.checkFailed;
  const uploadPrimary = packageUsable && input.autoRunNeedsInput && input.runPhase === "idle";
  const runQueued =
    input.runPhase === "idle" &&
    (input.autoRunDecision === "run" || (input.inputBusy && input.autoRunNeedsInput));
  const runPrimary =
    packageUsable &&
    input.runPhase !== "succeeded" &&
    !uploadPrimary &&
    !runQueued &&
    !input.autoRunComing &&
    !input.autoRunWaiting &&
    input.pocInputs.length > 0;

  return { uploadPrimary, runPrimary, runQueued, sampleNames, ownNames };
}
