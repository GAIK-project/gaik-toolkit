// What the Text-to-Speech demo works with: the voices, the example, and how a text is
// prepared for speech (split into parts the server accepts, and timed).

export const MAX_PART_CHARACTERS = 1000;
export const MAX_PARTS = 3;
export const MAX_CHARACTERS = MAX_PART_CHARACTERS * MAX_PARTS;
export const MAX_COMPARE_VOICES = 3;

export type Language = "fi" | "en";

export const LANGUAGES: { id: Language; label: string }[] = [
  { id: "fi", label: "Finnish" },
  { id: "en", label: "English" },
];

export const VOICES = [
  { id: "alloy", note: "Neutral and balanced. A safe choice for any text." },
  { id: "echo", note: "Calm and even, a lower voice." },
  { id: "fable", note: "Warm and expressive, like a storyteller." },
  { id: "onyx", note: "Deep and firm, with some authority." },
  { id: "nova", note: "Friendly and bright." },
  { id: "shimmer", note: "Soft and clear." },
] as const;

export type VoiceId = (typeof VOICES)[number]["id"];

export interface TtsExample {
  title: string;
  summary: string;
  tags: string[];
  language: Language;
  voices: VoiceId[];
  text: string;
}

// A site diary entry: numbers, dates, names and a list make it a good test of a voice.
const DIARY: TtsExample = {
  title: "A site diary read aloud",
  summary:
    "A Finnish diary entry with dates, numbers and place names. It comes with three voices to compare, so you can hear which one reads it best.",
  tags: ["Finnish", "3 voices to compare", "numbers and names"],
  language: "fi",
  voices: ["alloy", "nova", "onyx"],
  text: `Päivämäärä 10.04.2025. Kohde: 4120-01 Revontulentie 3, 02100 Espoo, Toimistotalo Revontuli, osittainen purku. Työviikko 4.
Sää: +6 astetta, puolipilvistä, tuuli noin 4 m/s.
Resurssit: työnjohtajia 1 henkilö, omia työntekijöitä 3 henkilöä, asbestipurku-urakoitsijan työntekijöitä 4 henkilöä, muita alihankkijoita 2 henkilöä. Yhteensä 10 henkilöä.
Päivän työt: asbestipurku jatkui kellarikerroksen teknisissä tiloissa suunnitelman mukaisesti. Sisäpurkua tehtiin kolmannessa kerroksessa; käytävätilojen väliseinät, lasiseinät ja vanhat toimistokalusteet purettiin.
Päivän tapahtumat: kolmannen kerroksen keittiötilasta löytyi avauksen yhteydessä asbestia sisältävä vanha putkieriste, jota ei ollut alkuperäisessä kartoituksessa. Alue eristettiin välittömästi ja työ siellä keskeytettiin.`,
};

const TOOLBOX_TALK: TtsExample = {
  title: "A safety briefing read aloud",
  summary:
    "A long English briefing, over 1,000 characters, so it is read in two parts and joined into one file. Two voices to compare.",
  tags: ["English", "2 voices to compare", "read in parts"],
  language: "en",
  voices: ["fable", "shimmer"],
  text: `Good morning, everyone, and thank you for coming. This is today's safety briefing for the east wing, and it takes about five minutes.
First, the weather. Snow fell overnight and the temperature is minus three degrees. The scaffolding on the north side has been cleared, but the walkways on levels two and three are slippery, so please use the marked routes only and wear your anti-slip shoe covers.
Second, the work. The roofing crew will lift new tiles with the crane between nine and eleven. The area below the south slope is closed during the lifts. Nobody enters the barrier, even for a minute, and the signaller has the final word on every lift.
Third, what we found yesterday. Water damage was discovered behind the old cladding on the east wall, about two square metres. The area is marked with red tape. Please do not remove the cladding around it until the inspector has taken photographs.
Fourth, hot work. Two hot work permits are active today, both on level one. Fire extinguishers must stay within ten metres of the work, and the fire watch stays for one hour after the work ends.
Finally, the first aid kit has been refilled and moved to the site office. If you see something unsafe, stop work and tell your supervisor straight away. Nobody will ever be criticised for stopping work to ask. Thank you, and have a safe day.`,
};

export const EXAMPLES: TtsExample[] = [DIARY, TOOLBOX_TALK];

// ---------------------------------------------------------------------------
// Preparing a text
// ---------------------------------------------------------------------------

/** The sentences of a text: split after . ! ? when a space follows (so 10.04.2025 stays whole), or at a line end. */
function pieces(text: string): string[] {
  return text
    .replace(/\r\n?/g, "\n")
    .split(/(?<=[.!?])\s+|\n+/)
    .map((piece) => piece.trim())
    .filter(Boolean);
}

/**
 * The text in parts of at most `max` characters, each ending where a sentence ends when it
 * can. A sentence longer than `max` is cut at a space.
 */
export function splitForSpeech(
  text: string,
  max: number = MAX_PART_CHARACTERS,
): string[] {
  const parts: string[] = [];
  let current = "";
  const push = () => {
    if (current.trim()) parts.push(current.trim());
    current = "";
  };
  for (const piece of pieces(text.trim())) {
    if (piece.length > max) {
      push();
      let rest = piece;
      while (rest.length > max) {
        const cut = rest.lastIndexOf(" ", max);
        const at = cut > 0 ? cut : max;
        parts.push(rest.slice(0, at).trim());
        rest = rest.slice(at).trim();
      }
      current = rest;
      continue;
    }
    if (current && current.length + 1 + piece.length > max) push();
    current = current ? `${current} ${piece}` : piece;
  }
  push();
  return parts;
}

export const wordCount = (text: string): number =>
  text.trim() === "" ? 0 : text.trim().split(/\s+/).length;

/** About how long the speech lasts, in seconds, at a normal pace. */
export function estimateSeconds(text: string, language: Language): number {
  // Finnish words are long: fewer of them are said a minute.
  const wordsPerMinute = language === "fi" ? 125 : 150;
  return Math.round((wordCount(text) / wordsPerMinute) * 60);
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds))
    return "–";
  const total = Math.round(seconds);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

/** The bytes of the parts of an audio file, one after the other. */
export function joinBytes(parts: Uint8Array[]): Uint8Array {
  const out = new Uint8Array(parts.reduce((sum, part) => sum + part.length, 0));
  let at = 0;
  for (const part of parts) {
    out.set(part, at);
    at += part.length;
  }
  return out;
}

export function bytesFromBase64(base64: string): Uint8Array {
  const binary = atob(base64);
  return Uint8Array.from(binary, (char) => char.charCodeAt(0));
}
