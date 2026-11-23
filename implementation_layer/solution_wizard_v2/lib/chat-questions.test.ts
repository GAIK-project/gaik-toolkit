import { describe, expect, it } from "vitest";
import { answersMessage, questionsIn } from "./chat-questions";

const ROUND = `Kiitos! Aloitetaan liiketoimintakontekstista:

- Millaisessa muodossa ostotilaukset saapuvat (esim. **PDF**, Word)? Tulevatko ne
  yhdeltä vai usealta toimittajalta?
- Miten ostotilaukset käsitellään nyt?
- Taustaksi: tiedot menevät ERP:hen.
1. Mitä tulosta haluat (esim. [JSON](https://example.com))?

Vastaa niihin, joihin osaat.`;

const texts = (markdown: string) => questionsIn(markdown).map((q) => q.text);
const numbers = (markdown: string) => questionsIn(markdown).map((q) => q.n);

describe("questionsIn", () => {
  it("takes the list items that ask something, wrapped lines included", () => {
    expect(texts(ROUND)).toEqual([
      "Millaisessa muodossa ostotilaukset saapuvat (esim. PDF, Word)? Tulevatko ne yhdeltä vai usealta toimittajalta?",
      "Miten ostotilaukset käsitellään nyt?",
      "Mitä tulosta haluat (esim. JSON)?",
    ]);
  });

  it("finds nothing in a message without a list", () => {
    expect(questionsIn("Mitä haluat ratkaista? Kerro vapaasti.")).toEqual([]);
  });

  it("leaves out what is inside a fenced code block", () => {
    const reply = [
      "- Missä muodossa tilaukset saapuvat?",
      "",
      "```bash",
      "- curl https://example.com/haku?q=tilaus",
      "1. echo valmis?",
      "```",
      "~~~",
      "- onko tämä kysymys?",
      "~~~",
      "- Kuka tilaukset käsittelee?",
    ].join("\n");
    expect(texts(reply)).toEqual(["Missä muodossa tilaukset saapuvat?", "Kuka tilaukset käsittelee?"]);
  });

  it("does not take a question mark in inline code or a web address for a question", () => {
    const reply = [
      "- Haku tehdään kutsulla `GET /haku?q=tilaus`.",
      "- Ohje on osoitteessa https://example.com/ohje?kieli=fi.",
      "- Katso myös [ohje](https://example.com/ohje?kieli=fi) ja <https://example.com/?a=1>.",
      "- Onko `status?`-kenttä pakollinen?",
      "- Onko oikea osoite https://example.com/haku?",
    ].join("\n");
    expect(texts(reply)).toEqual([
      "Onko status?-kenttä pakollinen?",
      "Onko oikea osoite https://example.com/haku?",
    ]);
  });

  it("keeps the agent's own numbers when its list is numbered", () => {
    const reply = [
      "1. Taustaksi: tiedot menevät ERP:hen.",
      "2. Missä muodossa tilaukset saapuvat?",
      "3. Kuka tilaukset käsittelee?",
    ].join("\n");
    expect(numbers(reply)).toEqual([2, 3]);
    expect(numbers("4) Montako tilausta päivässä?\n5) Millä kielellä?")).toEqual([4, 5]);
  });

  it("numbers from 1 when the list is bulleted, mixed or repeats a number", () => {
    expect(numbers(ROUND)).toEqual([1, 2, 3]);
    expect(numbers("1. Mitä?\n2. Miksi?\n\nJa vielä:\n\n1. Milloin?")).toEqual([1, 2, 3]);
  });
});

describe("answersMessage", () => {
  const template = { intro: "Vastaukseni:", line: '{n}. "{question}": {answer}', skip: "skip" };

  it("numbers the answers as the questions are, quotes each question on one line and skips the empty ones", () => {
    expect(
      answersMessage(
        [
          { n: 2, text: 'Kysymys "A"\nrivi kaksi?' },
          { n: 3, text: "Kysymys B?" },
        ],
        ["  PDF   sähköpostilla ", " \n "],
        template,
      ),
    ).toBe("Vastaukseni:\n2. \"Kysymys 'A' rivi kaksi?\": PDF sähköpostilla\n3. \"Kysymys B?\": skip");
  });

  it("keeps the line breaks of an answer, its later lines indented under the first", () => {
    expect(answersMessage([{ n: 1, text: "Mitkä järjestelmät?" }], ["SAP  \n\n  Lemonsoft\nM-Files"], template)).toBe(
      'Vastaukseni:\n1. "Mitkä järjestelmät?": SAP\n   Lemonsoft\n   M-Files',
    );
  });
});

describe("a question that carries a number of its own", () => {
  it("drops the number inside the item, so the form shows one", () => {
    expect(questionsIn("- 1. Miten viat käsitellään nyt?\n- 2. Ketkä tarkastavat tiketit?")).toEqual([
      { n: 1, text: "Miten viat käsitellään nyt?" },
      { n: 2, text: "Ketkä tarkastavat tiketit?" },
    ]);
    expect(questionsIn("1. **1.** Missä muodossa?\n2. **2)** Kuinka monta?")).toEqual([
      { n: 1, text: "Missä muodossa?" },
      { n: 2, text: "Kuinka monta?" },
    ]);
  });

  it("keeps a number that is part of the question", () => {
    expect(questionsIn("- 24/7-päivystys vai arkisin?\n- 2 vai 3 hyväksyjää?")).toEqual([
      { n: 1, text: "24/7-päivystys vai arkisin?" },
      { n: 2, text: "2 vai 3 hyväksyjää?" },
    ]);
  });

  it("keeps an ordinal that opens the question", () => {
    // "15." is a date here, not the question's number.
    expect(questionsIn("1. 15. päivä vai kuun loppu eräpäiväksi?\n2. 3. osapuolen laskut mukaan?")).toEqual([
      { n: 1, text: "15. päivä vai kuun loppu eräpäiväksi?" },
      { n: 2, text: "3. osapuolen laskut mukaan?" },
    ]);
    expect(questionsIn("- 15. päivä vai kuun loppu?")).toEqual([
      { n: 1, text: "15. päivä vai kuun loppu?" },
    ]);
  });
});

describe("the options a question lists", () => {
  const options = (markdown: string) => questionsIn(markdown).map((q) => q.options);

  it("takes the plain bullets under a question, and leaves them out of its text", () => {
    const reply = [
      "1. Missä muodossa tilaukset saapuvat?",
      "   - **PDF** sähköpostilla",
      "   - Excel-liitteenä.",
      "   - a) EDI-sanomana",
      "2. Kuka tilaukset käsittelee?",
    ].join("\n");
    expect(questionsIn(reply)).toEqual([
      {
        n: 1,
        text: "Missä muodossa tilaukset saapuvat?",
        options: ["PDF sähköpostilla", "Excel-liitteenä", "EDI-sanomana"],
      },
      { n: 2, text: "Kuka tilaukset käsittelee?" },
    ]);
  });

  it("takes them after a blank line and from deeper indents too", () => {
    expect(questionsIn("- Which format?\n\n    - PDF\n    - Word\n- Who reads them?")).toEqual([
      { n: 1, text: "Which format?", options: ["PDF", "Word"] },
      { n: 2, text: "Who reads them?" },
    ]);
  });

  it("takes a lettered or numbered list in the question's own line", () => {
    expect(questionsIn("- Which format? (a) PDF, (b) Word, or (c) both\n- Who reads them?")[0]).toEqual({
      n: 1,
      text: "Which format?",
      options: ["PDF", "Word", "both"],
    });
    // The question is not whole without its list: the line stays as written.
    expect(questionsIn("- Tuleeko tulos a) JSON-tiedostona vai b) Excel-taulukkona?\n- Kenelle?")[0]).toEqual({
      n: 1,
      text: "Tuleeko tulos a) JSON-tiedostona vai b) Excel-taulukkona?",
      options: ["JSON-tiedostona", "Excel-taulukkona"],
    });
    expect(options("- Pick one: (1) nightly (2) hourly?\n- Why?")).toEqual([["nightly", "hourly"], undefined]);
    // Lettered lines under the question are part of its item.
    expect(questionsIn("1. Which format?\n   a) PDF\n   b) Word\n2. Why?")[0]).toEqual({
      n: 1,
      text: "Which format?",
      options: ["PDF", "Word"],
    });
  });

  it("does not guess options from prose", () => {
    expect(options("- PDF vai Word?\n- Tulevatko ne sähköpostilla, portaalista tai EDI:nä?")).toEqual([
      undefined,
      undefined,
    ]);
    // Marks that do not run in order from the first are not a list.
    expect(options("- Onko kohta (b) pakollinen, ja entä (d)?\n- Miksi?")).toEqual([undefined, undefined]);
    expect(options("- Koskeeko tämä liitettä b) vai c) ?\n- Miksi?")).toEqual([undefined, undefined]);
  });

  it("offers nothing for one bullet, long bullets, or bullets that ask something", () => {
    expect(options("- Missä muodossa?\n  - PDF\n- Miksi?")).toEqual([undefined, undefined]);
    const long = "x".repeat(61);
    expect(options(`- Missä muodossa?\n  - ${long}\n  - PDF\n- Miksi?`)).toEqual([undefined, undefined]);
    // A bullet that asks is a question of its own, as before. The plain
    // bullets beside it are no options, and stay under their question.
    expect(questionsIn("- Missä muodossa?\n  - PDF\n  - Onko skannattuja?\n  - Word")).toEqual([
      { n: 1, text: "Missä muodossa?", details: ["PDF", "Word"] },
      { n: 2, text: "Onko skannattuja?" },
    ]);
  });
});

describe("what stands under a question and is no option", () => {
  it("keeps the fields a question ending in a colon lists in its bullets", () => {
    const reply = [
      "1. Missä muodossa laskut saapuvat?",
      "2. Kuka laskut tarkastaa?",
      "3. **Which fields do you need?** My default is:",
      "   - `supplier_name`: the supplier as written on the invoice",
      "   - Invoice number",
      "   - Invoice date",
      "   - Due date",
      "   - Total with VAT",
      "   - VAT amount",
      "   - Currency",
      "4. How should the result be delivered?",
    ].join("\n");
    expect(questionsIn(reply)[2]).toEqual({
      n: 3,
      text: "Which fields do you need? My default is:",
      details: [
        "supplier_name: the supplier as written on the invoice",
        "Invoice number",
        "Invoice date",
        "Due date",
        "Total with VAT",
        "VAT amount",
        "Currency",
      ],
    });
    expect(numbers(reply)).toEqual([1, 2, 3, 4]);
  });

  it("keeps bullets written at the margin right after a numbered question", () => {
    const reply = [
      "1. Which fields do you need? My default is:",
      "",
      "- the supplier's name and business ID, as they are written on the invoice",
      "- the invoice number",
      "",
      "2. Who checks the result?",
    ].join("\n");
    expect(questionsIn(reply)).toEqual([
      {
        n: 1,
        text: "Which fields do you need? My default is:",
        details: ["the supplier's name and business ID, as they are written on the invoice", "the invoice number"],
      },
      { n: 2, text: "Who checks the result?" },
    ]);
    // A bulleted list keeps its plain items apart: which question one belongs to would be a guess.
    expect(texts(ROUND)).toHaveLength(3);
    expect(questionsIn(ROUND).every((q) => q.details === undefined)).toBe(true);
  });

  it("keeps an indented line that continues the question", () => {
    // After a colon each line is one thing the question lists.
    expect(
      questionsIn(
        "1. Mitkä kentät tarvitset? Oletukseni on:\n   toimittaja, laskun numero, päiväys\n   loppusumma\n2. Miksi?",
      )[0],
    ).toEqual({
      n: 1,
      text: "Mitkä kentät tarvitset? Oletukseni on:",
      details: ["toimittaja, laskun numero, päiväys", "loppusumma"],
    });
    // After a blank line it is a paragraph of the same item; its wrapped line stays with it.
    expect(
      questionsIn(
        "- Which fields do you need?\n\n  By default I take the supplier, the date\n  and the total.\n- Why?",
      )[0],
    ).toEqual({
      n: 1,
      text: "Which fields do you need?",
      details: ["By default I take the supplier, the date and the total."],
    });
    // A sentence that wraps is still one sentence.
    expect(texts("- Which fields do you need,\n  and in which order?\n- Why?")[0]).toBe(
      "Which fields do you need, and in which order?",
    );
  });

  it("still offers short lines under a question as options", () => {
    expect(questionsIn("1. Which format do you want? Pick one:\n   a) PDF\n   b) Word\n2. Why?")[0]).toEqual({
      n: 1,
      text: "Which format do you want? Pick one:",
      options: ["PDF", "Word"],
    });
  });
});

describe("the message shape the chat draws as one numbered list", () => {
  it("still gives three questions under their own numbers, the bullets as options", () => {
    expect(questionsIn("1. Q?\n   - a\n   - b\n2. Q2?\n   - c\n3. Q3?")).toEqual([
      { n: 1, text: "Q?", options: ["a", "b"] },
      // One bullet is not a choice: it stays with its question as written.
      { n: 2, text: "Q2?", details: ["c"] },
      { n: 3, text: "Q3?" },
    ]);
  });
});
