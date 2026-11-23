import { describe, expect, it } from "vitest";
import { clock, encodeWav, recordingName } from "./recording-wav";

const text = (view: DataView, offset: number, length: number) =>
  String.fromCharCode(...Array.from({ length }, (_, i) => view.getUint8(offset + i)));

describe("encodeWav", () => {
  it("writes a header the input check reads as WAV: RIFF, WAVE, PCM mono 16 kHz", () => {
    const view = new DataView(encodeWav(new Float32Array(160)));

    expect(text(view, 0, 4)).toBe("RIFF");
    expect(text(view, 8, 4)).toBe("WAVE");
    expect(text(view, 12, 4)).toBe("fmt ");
    expect(view.getUint16(20, true)).toBe(1);
    expect(view.getUint16(22, true)).toBe(1);
    expect(view.getUint32(24, true)).toBe(16000);
    expect(view.getUint16(34, true)).toBe(16);
    expect(text(view, 36, 4)).toBe("data");
  });

  it("states the sizes the file has", () => {
    const buffer = encodeWav(new Float32Array(100));
    const view = new DataView(buffer);

    expect(buffer.byteLength).toBe(44 + 200);
    expect(view.getUint32(4, true)).toBe(buffer.byteLength - 8);
    expect(view.getUint32(40, true)).toBe(200);
  });

  it("writes each sample as 16 bits and clips what is louder than full scale", () => {
    const view = new DataView(encodeWav(new Float32Array([0, 1, -1, 2, -2, 0.5])));
    const sample = (i: number) => view.getInt16(44 + i * 2, true);

    expect([sample(0), sample(1), sample(2), sample(3), sample(4)]).toEqual([0, 32767, -32768, 32767, -32768]);
    expect(sample(5)).toBe(16383);
  });
});

describe("recordingName", () => {
  it("is a .wav name with the time, without characters a file name cannot have", () => {
    expect(recordingName(new Date("2026-11-11T08:04:59.123Z"))).toBe("recording-2026-11-11-08-04-59.wav");
  });
});

describe("clock", () => {
  it("shows seconds as m:ss", () => {
    expect([clock(0), clock(7.9), clock(60), clock(125), clock(-3)]).toEqual(["0:00", "0:07", "1:00", "2:05", "0:00"]);
  });
});
