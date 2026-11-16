import { describe, expect, it } from "vitest";
import { BACKGROUND_SENTENCES, PACE_SENTENCES, withStartLines } from "./chat-background";
import { DERIVED_TITLE_MAX, sessionTitleFrom, shownSessionTitle, titleExampleIn } from "./session-title";

const sentences = BACKGROUND_SENTENCES.fi;
const pace = PACE_SENTENCES.fi;
const source = {
  examples: [
    { title: "Laskun kentät", prompt: "Haluamme poimia toimittajien PDF-laskuista keskeiset kentät." },
    { title: "Kysymykset ohjeista", prompt: "Haluamme avustajan, joka vastaa kysymyksiin ohjeidemme pohjalta." },
  ],
  fallback: "Nimetön sessio",
};

describe("sessionTitleFrom", () => {
  it("names a session by the example it was started from", () => {
    expect(sessionTitleFrom(source.examples[0].prompt, source)).toBe("Laskun kentät");
  });

  it("finds the example behind the background and pace lines", () => {
    const message = withStartLines(source.examples[1].prompt, [sentences.technical, pace.quick]);
    expect(sessionTitleFrom(message, source)).toBe("Kysymykset ohjeista");
    expect(titleExampleIn(message, source)).toBe(1);
    expect(titleExampleIn("Jotain muuta", source)).toBeNull();
  });

  it("leaves the background and pace lines out of the name", () => {
    const message = withStartLines("Luokittele saapuvat sähköpostit", [sentences.nonTechnical, pace.thorough]);
    expect(sessionTitleFrom(message, source)).toBe("Luokittele saapuvat sähköpostit");
    // The pace line alone, when no background was chosen.
    expect(sessionTitleFrom(withStartLines("Luokittele laskut", [pace.quick]), source)).toBe(
      "Luokittele laskut",
    );
    // Also lines in the other language, and a sentence that stood on the message's own line.
    expect(
      sessionTitleFrom(
        withStartLines("Tiivistä kokousmuistiot", [BACKGROUND_SENTENCES.en.technical, PACE_SENTENCES.en.quick]),
        source,
      ),
    ).toBe("Tiivistä kokousmuistiot");
    expect(sessionTitleFrom(`${sentences.technical} Luokittele laskut`, source)).toBe("Luokittele laskut");
  });

  it("takes the first sentence of the first line that says something", () => {
    expect(sessionTitleFrom("\n\n  Tiivistä kokousmuistiot. Niitä on satoja.\nToinen rivi", source)).toBe(
      "Tiivistä kokousmuistiot",
    );
  });

  it("keeps a short opening together with what follows it", () => {
    // "Hei." alone would name nothing.
    expect(sessionTitleFrom("Hei. Tarvitsen apua laskuissa", source)).toBe("Hei. Tarvitsen apua laskuissa");
  });

  it("does not cut at a full stop inside a word", () => {
    expect(sessionTitleFrom("Vie data tiedostoon raportti.xlsx joka viikko", source)).toBe(
      "Vie data tiedostoon raportti.xlsx joka",
    );
  });

  it("cuts a long line at a word, with no ellipsis", () => {
    const title = sessionTitleFrom(
      "Haluamme koota moniosaisen raportin dokumenteista ja litteroinneista",
      source,
    );
    expect(title).toBe("Haluamme koota moniosaisen raportin");
    expect(title.length).toBeLessThanOrEqual(DERIVED_TITLE_MAX);
  });

  it("cuts a word longer than the limit where the limit falls", () => {
    const title = sessionTitleFrom("x".repeat(90), source);
    expect(title).toBe("x".repeat(DERIVED_TITLE_MAX));
  });

  it("collapses whitespace and drops closing punctuation", () => {
    expect(sessionTitleFrom("Luokittele   laskut\tnopeasti?!", source)).toBe("Luokittele laskut nopeasti");
  });

  it("falls back when nothing is left to name the session by", () => {
    expect(sessionTitleFrom("   ", source)).toBe("Nimetön sessio");
    expect(sessionTitleFrom(sentences.technical, source)).toBe("Nimetön sessio");
    expect(sessionTitleFrom(`${sentences.technical}\n${pace.quick}`, source)).toBe("Nimetön sessio");
    expect(sessionTitleFrom("?!", source)).toBe("Nimetön sessio");
  });
});

describe("shownSessionTitle", () => {
  const placeholders = ["Nimetön sessio", "Untitled session"];

  it("keeps a session's own name", () => {
    expect(shownSessionTitle("Laskujen luokittelu", "Invoice classifier", placeholders)).toBe("Laskujen luokittelu");
  });

  it("shows the blueprint's name for a session that was never named, in either language", () => {
    expect(shownSessionTitle("Untitled session", "Release User Guide Updater", placeholders)).toBe("Release User Guide Updater");
    expect(shownSessionTitle("Nimetön sessio", " Release User Guide Updater ", placeholders)).toBe("Release User Guide Updater");
  });

  it("leaves the placeholder when the blueprint has no name of its own either", () => {
    expect(shownSessionTitle("Untitled session", "Nimetön sessio", placeholders)).toBe("Untitled session");
    expect(shownSessionTitle("Untitled session", "", placeholders)).toBe("Untitled session");
    expect(shownSessionTitle("Untitled session", undefined, placeholders)).toBe("Untitled session");
  });
});
