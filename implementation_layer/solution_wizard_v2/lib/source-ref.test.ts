import { describe, expect, it } from "vitest";
import { shortTime, sourceRef, sourceRefPlace } from "@/lib/source-ref";

describe("sourceRef", () => {
  it("reads a recording with its from and to", () => {
    const ref = sourceRef("project_nimbus_meeting.wav|00:00:00|00:01:12");
    expect(ref).toEqual({ file: "project_nimbus_meeting.wav", page: null, from: "0:00", to: "1:12" });
    expect(sourceRefPlace(ref!, "p. {n}")).toBe("0:00–1:12");
  });

  it("reads a document with its page, in the page's words", () => {
    const ref = sourceRef("project_nimbus_agenda.pdf|2");
    expect(ref).toEqual({ file: "project_nimbus_agenda.pdf", page: 2, from: null, to: null });
    expect(sourceRefPlace(ref!, "p. {n}")).toBe("p. 2");
    expect(sourceRefPlace(ref!, "s. {n}")).toBe("s. 2");
  });

  it("reads one moment of a recording", () => {
    const ref = sourceRef("call.mp3 | 01:02:03");
    expect(ref).toEqual({ file: "call.mp3", page: null, from: "1:02:03", to: null });
    expect(sourceRefPlace(ref!, "p. {n}")).toBe("1:02:03");
  });

  it("leaves any other shape as it was written", () => {
    for (const written of [
      "project_nimbus_agenda.pdf",
      "a | b",
      "yes|no",
      "notes|2",
      "agenda.pdf|two",
      "agenda.pdf|0",
      "agenda.pdf|2|3",
      "meeting.wav|00:00:00|later",
      "meeting.wav|00:00:00|00:01:12|x",
      "meeting.wav|00:75",
      "|2",
      "agenda.pdf|2\nagenda.pdf|3",
    ]) {
      expect(sourceRef(written)).toBeNull();
    }
  });
});

describe("shortTime", () => {
  it("drops the empty hour and the leading zero, and keeps a real hour", () => {
    expect(shortTime("00:00:00")).toBe("0:00");
    expect(shortTime("00:01:12")).toBe("1:12");
    expect(shortTime("12:05")).toBe("12:05");
    expect(shortTime("01:02:03.250")).toBe("1:02:03");
    expect(shortTime("1h")).toBeNull();
  });
});
