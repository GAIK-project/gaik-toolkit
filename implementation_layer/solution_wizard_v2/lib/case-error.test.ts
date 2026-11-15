import { describe, expect, it } from "vitest";
import { acceptAttribute, acceptedPhrase, caseErrorText, type AcceptedInput } from "./case-error";
import { CASE_STRINGS } from "./case-strings";

const fi = CASE_STRINGS.fi;
const en = CASE_STRINGS.en;
const BUSY = "busy text";
const AUDIO: AcceptedInput[] = [
  { kind: "wav", label: "WAV", extensions: [".wav"] },
  { kind: "mp3", label: "MP3", extensions: [".mp3"] },
  { kind: "m4a", label: "M4A", extensions: [".m4a"] },
  { kind: "json", label: "JSON", extensions: [".json"] },
];
const refusal = (error: string, message = "the api's own words") => ({ detail: { error, message } });

describe("caseErrorText", () => {
  it("says a refused file type in the page's language and names the accepted ones", () => {
    const body = refusal(
      "input_type_not_accepted",
      "this file type is not accepted here; accepted types: WAV, MP3, M4A, JSON",
    );

    const text = caseErrorText(415, body, fi, BUSY, AUDIO);

    expect(text).toBe("Tätä tiedostotyyppiä ei voi käyttää tässä. Hyväksytyt tiedostotyypit: WAV, MP3, M4A tai JSON.");
    expect(text).not.toContain("not accepted here");
    expect(caseErrorText(415, body, en, BUSY, AUDIO)).toContain("WAV, MP3, M4A or JSON");
  });

  it("still says the type is refused when the api named no accepted types", () => {
    expect(caseErrorText(415, refusal("input_type_not_accepted"), fi, BUSY)).toBe(fi.errors.typeNotAccepted);
  });

  it("reads the accepted types from the refusal when the model did not carry them", () => {
    const body = refusal("input_type_not_accepted", "this file type is not accepted here; accepted types: PDF, JSON");

    expect(caseErrorText(415, body, fi, BUSY)).toBe(
      "Tätä tiedostotyyppiä ei voi käyttää tässä. Hyväksytyt tiedostotyypit: PDF tai JSON.",
    );
  });

  it("tells a file whose content is not what its extension says from a refused type", () => {
    const body = refusal(
      "input_type_not_accepted",
      "the file's content does not match its .wav extension; accepted types: WAV, MP3, M4A, JSON",
    );

    const text = caseErrorText(415, body, fi, BUSY, AUDIO);

    expect(text).toContain(fi.errors.contentMismatch);
    expect(text).not.toContain(fi.errors.typeNotAccepted);
    expect(text).toContain("WAV, MP3, M4A tai JSON");
  });

  it("gives the size limit for a file that is too large, from the api or from the relay", () => {
    const fromApi = caseErrorText(413, refusal("input_too_large", "the file is larger than 50 MB"), fi, BUSY);
    const fromRelay = caseErrorText(413, { detail: "the file is larger than 50 MB" }, fi, BUSY);

    expect(fromApi).toContain("50");
    expect(fromApi).not.toContain("{mb}");
    expect(fromRelay).toBe(fromApi);
  });

  it("tells the case's and the session's total from the file's own size", () => {
    // The api gives one code for all three; only the file's own limit is cured by a smaller file.
    const ofCase = caseErrorText(413, refusal("input_too_large", "the case's input would exceed 200 MB in all"), fi, BUSY);
    const ofSession = caseErrorText(
      413,
      refusal("input_too_large", "the session's case input would exceed 1024 MB in all"),
      fi,
      BUSY,
    );

    expect(ofCase).toBe(fi.errors.caseFull.replace("{mb}", "200"));
    expect(ofSession).toBe(fi.errors.sessionFull.replace("{mb}", "1024"));
    expect(ofCase).not.toContain("50");
  });

  it("says a file with the same name is already there", () => {
    expect(caseErrorText(409, refusal("input_exists"), fi, BUSY)).toBe(fi.errors.exists);
  });

  it("shows the localized busy text for a full sandbox", () => {
    expect(caseErrorText(429, refusal("sandbox_busy"), fi, BUSY)).toBe(BUSY);
    expect(caseErrorText(429, {}, fi, BUSY)).toBe(BUSY);
  });

  it("keeps the api's words for a refusal about the case's own state", () => {
    expect(caseErrorText(409, refusal("case_state", "the case is already submitted"), fi, BUSY)).toBe(
      "the case is already submitted",
    );
    expect(caseErrorText(404, { detail: "not found" }, fi, BUSY)).toBe("not found");
    expect(caseErrorText(502, null, fi, BUSY)).toBe("HTTP 502");
  });
});

describe("refusals from the malware check and a document's own content", () => {
  it.each([
    ["the file was refused by the malware check", fi.errors.unsafe],
    ["files with macros are not accepted; save the document without macros", fi.errors.macros],
    ["PDF files that contain JavaScript are not accepted", fi.errors.activeContent],
    ["password-protected or encrypted files are not accepted; upload an unprotected copy", fi.errors.encrypted],
    ["the PDF is too complex to be checked", fi.errors.uncheckable],
  ])("says %s in the page's language", (message, expected) => {
    expect(caseErrorText(422, refusal("input_unsafe", message), fi, BUSY)).toBe(expected);
  });

  it("says the upload was not stored while files cannot be checked", () => {
    expect(caseErrorText(503, refusal("scanner_unavailable"), en, BUSY)).toBe(en.errors.scanUnavailable);
  });
});

describe("accepted types", () => {
  it("joins the labels as one phrase", () => {
    expect(acceptedPhrase(AUDIO, "tai")).toBe("WAV, MP3, M4A tai JSON");
    expect(acceptedPhrase(AUDIO.slice(0, 2), "or")).toBe("WAV or MP3");
    expect(acceptedPhrase(AUDIO.slice(0, 1), "tai")).toBe("WAV");
    expect(acceptedPhrase([], "tai")).toBe("");
  });

  it("gives the file picker every extension, and nothing when no type is named", () => {
    expect(acceptAttribute([...AUDIO, { label: "JPEG", extensions: [".jpg", ".jpeg"] }])).toBe(
      ".wav,.mp3,.m4a,.json,.jpg,.jpeg",
    );
    expect(acceptAttribute([])).toBe("");
  });
});
