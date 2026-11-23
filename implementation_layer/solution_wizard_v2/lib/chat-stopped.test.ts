import { describe, expect, it } from "vitest";
import { STOPPED_NOTE, shownReply, withStoppedNote } from "@/lib/chat-stopped";

describe("a stopped reply", () => {
  it("is stored with the note after what was written", () => {
    expect(withStoppedNote("Aloitan työn ", STOPPED_NOTE.fi)).toBe("Aloitan työn\n\n(Pysäytetty)");
  });

  it("is the note alone when nothing was written", () => {
    expect(withStoppedNote("  ", STOPPED_NOTE.en)).toBe("(Stopped)");
  });

  it("is shown without the note it was stored with", () => {
    const stored = { content: "Aloitan työn\n\n(Pysäytetty)", stopped: true, stoppedNote: "(Pysäytetty)" };
    expect(shownReply(stored)).toBe("Aloitan työn");
    // Stopped before its first word: nothing but the mark is shown.
    expect(shownReply({ content: "(Pysäytetty)", stopped: true, stoppedNote: "(Pysäytetty)" })).toBe("");
  });

  it("keeps a note in the language it was stored in, whatever the interface's is now", () => {
    const stored = { content: "I will start\n\n(Stopped)", stopped: true, stoppedNote: "(Stopped)" };
    expect(shownReply(stored)).toBe("I will start");
  });

  it("leaves the text alone while the reply is on the page it was stopped on", () => {
    // The stream's stopped frame marks the message; its text has no note yet.
    expect(shownReply({ content: "Aloitan työn", stopped: true })).toBe("Aloitan työn");
    expect(shownReply({ content: "Aloitan työn", stopped: true, stoppedNote: "(Pysäytetty)" })).toBe("Aloitan työn");
  });

  it("leaves a reply that only quotes the note alone", () => {
    expect(shownReply({ content: "Näet merkinnän (Pysäytetty)" })).toBe("Näet merkinnän (Pysäytetty)");
  });
});
