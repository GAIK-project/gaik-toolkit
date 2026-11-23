/**
 * A microphone recording as a WAV file.
 *
 * A browser records WebM (Chrome, Edge), Ogg (Firefox) or MP4 (Safari). The
 * input check accepts WAV, MP3 and M4A, so a recording made in Chrome or
 * Firefox was refused as "this file type is not accepted here". The recording
 * is decoded in the browser and written as 16 kHz mono 16-bit PCM, which every
 * transcriber reads and which is about 2 MB a minute.
 */

export const WAV_SAMPLE_RATE = 16000;
const HEADER_BYTES = 44;

/** Mono samples in -1..1 as a 16-bit PCM WAV file. */
export function encodeWav(samples: Float32Array, sampleRate: number = WAV_SAMPLE_RATE): ArrayBuffer {
  const dataBytes = samples.length * 2;
  const buffer = new ArrayBuffer(HEADER_BYTES + dataBytes);
  const view = new DataView(buffer);
  const ascii = (offset: number, text: string) => {
    for (let i = 0; i < text.length; i += 1) view.setUint8(offset + i, text.charCodeAt(i));
  };
  ascii(0, "RIFF");
  view.setUint32(4, 36 + dataBytes, true);
  ascii(8, "WAVE");
  ascii(12, "fmt ");
  view.setUint32(16, 16, true); // the fmt chunk's size
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // one channel
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); // bytes a second
  view.setUint16(32, 2, true); // bytes a sample frame
  view.setUint16(34, 16, true); // bits a sample
  ascii(36, "data");
  view.setUint32(40, dataBytes, true);
  for (let i = 0; i < samples.length; i += 1) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(HEADER_BYTES + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return buffer;
}

/** The file name a recording gets, from when it was stopped. */
export function recordingName(at: Date = new Date()): string {
  return `recording-${at.toISOString().slice(0, 19).replace(/[:T]/g, "-")}.wav`;
}

/** A recorded blob, decoded and written as a WAV file. Browser only. */
export async function recordingToWav(blob: Blob, name: string = recordingName()): Promise<File> {
  const AudioCtx: typeof AudioContext =
    window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
  const context = new AudioCtx();
  try {
    const decoded = await context.decodeAudioData(await blob.arrayBuffer());
    const frames = Math.max(1, Math.ceil(decoded.duration * WAV_SAMPLE_RATE));
    const offline = new OfflineAudioContext(1, frames, WAV_SAMPLE_RATE);
    const source = offline.createBufferSource();
    source.buffer = decoded;
    source.connect(offline.destination);
    source.start();
    const rendered = await offline.startRendering();
    return new File([encodeWav(rendered.getChannelData(0))], name, { type: "audio/wav" });
  } finally {
    void context.close();
  }
}

/** Seconds as m:ss, for the recording and the run clocks. */
export function clock(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}
