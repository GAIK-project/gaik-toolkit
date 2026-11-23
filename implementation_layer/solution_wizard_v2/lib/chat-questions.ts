import { fillTemplate, quoteOneLine } from "./chat-template";

/**
 * A question the agent asked, and the number its answer goes back under.
 * `options` are the answers the question itself lists, when it lists them in a
 * form that can be told apart from prose (see `listedOptions` and `subOptions`).
 * `details` is what the agent wrote under the question that did not become
 * options: the list a question ending "My default is:" points at, a line that
 * continues it after a blank line. The form shows them under the question, so
 * nothing the question refers to is missing from it.
 */
export type Question = { n: number; text: string; options?: string[]; details?: string[] };

/**
 * Inline markdown reduced to its text: emphasis, code and links. An
 * underscore inside a word is part of it ("supplier_name"), not emphasis.
 */
function plainText(markdown: string): string {
  return markdown
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/(\*\*|\*|`)/g, "")
    .replace(/(?<![\p{L}\p{N}])_{1,2}|_{1,2}(?![\p{L}\p{N}])/gu, "")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * A question's text without its own number repeated in front. The agent
 * sometimes numbers inside the item as well ("- 1. Where…?", "1. **1.**
 * Where…?"), and the form puts the question's number before the text, so it
 * read "1. 1. …". Only the question's own number is dropped: another number
 * there is part of the question ("15. päivä vai kuun loppu?").
 */
function withoutOwnNumber(text: string, n: number): string {
  const own = text.match(/^(\d{1,2})[.)]\s+(?=\S)/);
  return own && Number(own[1]) === n ? text.slice(own[0].length) : text;
}

/**
 * Whether a list item asks something: a "?" in its own words. One inside
 * inline code or a web address (a query string) does not count; the mark
 * that ends a sentence after an address does.
 */
function asksSomething(markdown: string): boolean {
  return markdown
    .replace(/(`+).*?\1(?!`)/g, " ")
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/(?:https?:\/\/|www\.)[^\s<>]*[^\s<>?.,!;:'")\]]/gi, " ")
    .includes("?");
}

/** An option as a chip says it: no list letter in front, no comma or stop after. */
function optionText(markdown: string): string {
  return plainText(markdown)
    .replace(/^\(?[a-z\d]\)\s+/i, "")
    .replace(/[\s,;.]+$/, "");
}

const MAX_OPTIONS = 6;
const MAX_OPTION_CHARS = 60;

/** Two to six short, different options, or nothing. */
function reliable(options: string[]): string[] | undefined {
  const short = options.every((option) => option.length > 0 && option.length <= MAX_OPTION_CHARS);
  const different = new Set(options.map((option) => option.toLowerCase())).size === options.length;
  return options.length >= 2 && options.length <= MAX_OPTIONS && short && different ? options : undefined;
}

/**
 * The options in the bullets or lines under a question: plain, short items,
 * none of which asks something itself.
 */
function subOptions(subs: string[]): string[] | undefined {
  return reliable(subs.map(optionText));
}

/**
 * The options a question lists in its own line with letters or numbers in
 * brackets: "(a) PDF, (b) Word or (c) both", "a) … b) …", "(1) … (2) …". The
 * marks must run in order from "a" or "1". Returns the options and where the
 * list starts in the text. "PDF or Word?" in prose is not such a list: which
 * words are the options there would be a guess.
 */
function listedOptions(text: string): { options: string[]; at: number } | undefined {
  const marks = [...text.matchAll(/(?:^|\s)\(?([a-h]|[1-8])\)\s+/gi)];
  if (marks.length < 2) return undefined;
  const first = marks[0][1].toLowerCase();
  if (first !== "a" && first !== "1") return undefined;
  const inOrder = marks.every(
    (mark, i) => mark[1].toLowerCase().charCodeAt(0) === first.charCodeAt(0) + i,
  );
  if (!inOrder) return undefined;
  const options = marks.map((mark, i) => {
    const from = (mark.index ?? 0) + mark[0].length;
    const to = i + 1 < marks.length ? marks[i + 1].index : text.length;
    return text
      .slice(from, to)
      .replace(/[\s,;.?]+$/, "")
      .replace(/\s+(?:or|and|tai|vai|ja|sekä)$/i, "")
      .replace(/[\s,;]+$/, "");
  });
  const found = reliable(options);
  return found ? { options: found, at: marks[0].index ?? 0 } : undefined;
}

/** `line`: no bullet. `listed`: one of the lines after a colon, each a thing of its own. */
type Sub = { text: string; line?: true; listed?: true };

type Item = {
  number: number | null;
  text: string;
  indent: number;
  /**
   * What stands under the item, in order and as written: its plain bullets,
   * and the lines that are no bullets (`line`).
   */
  subs: Sub[];
  /** A bullet under the item asks something itself: its bullets are no options. */
  mixed: boolean;
};

/**
 * Whether an indented line after `open` is a line of its own rather than the
 * rest of a wrapped sentence: the item's own text ends in a colon, or the
 * line before it was already such a line.
 */
function continuesAsLines(open: Sub | Item, owner: Item): boolean {
  if (open === owner) return /[:：]\s*(\*\*|__|\*|_)?$/.test(owner.text.trim());
  return "listed" in open && open.listed === true;
}

/**
 * The questions in an assistant message: the list items (bulleted or
 * numbered) that ask something. The agent asks a round of requirement
 * questions as such a list, and an answer field per question makes it plain
 * which answer goes with which question. Nothing inside a fenced code block
 * is a question. A question keeps the agent's own number when every question
 * found has one and no two share it; otherwise they are numbered from 1.
 *
 * A question's options come from the plain bullets under it, or from a
 * lettered list in its own line. A bullet under a question that asks
 * something is a question of its own. Whatever else stands under a question
 * stays with it as its `details`: bullets that are no options (too many, too
 * long, or beside a bullet that asks), bullets right after a numbered
 * question at the margin, the lines after a question that ends in a colon,
 * and an indented paragraph after a blank line.
 */
export function questionsIn(markdown: string): Question[] {
  const items: Item[] = [];
  // The item the bullets below belong to, and the text a wrapped line continues.
  let owner: Item | null = null;
  let open: Sub | Item | null = null;
  let fence: string | null = null;
  for (const line of markdown.split(/\r?\n/)) {
    const mark = line.match(/^(\s*)(`{3,}|~{3,})/);
    if (fence !== null) {
      // The block ends at a fence of the same kind, at least as long.
      if (mark && mark[2][0] === fence[0] && mark[2].length >= fence.length) fence = null;
      continue;
    }
    if (mark) {
      // An indented block belongs to the item above it; any other ends it.
      if (mark[1].length < 2) {
        owner = null;
        open = null;
      }
      fence = mark[2];
      continue;
    }
    const item = line.match(/^(\s*)(?:[-*+]|(\d{1,2})[.)])\s+(.*)$/);
    const indent = item ? item[1].length : 0;
    const under: boolean = item !== null && owner !== null && indent >= owner.indent + 2;
    // A bullet at the margin right after a numbered question: Markdown draws
    // it as a list of its own under that question, which is what it is.
    const after: boolean =
      item !== null &&
      !under &&
      owner !== null &&
      item[2] === undefined &&
      owner.number !== null &&
      indent <= owner.indent + 1 &&
      asksSomething(owner.text);
    if (item && (under || after) && owner && !asksSomething(item[3])) {
      const sub = { text: item[3] };
      owner.subs.push(sub);
      open = sub;
    } else if (item && (under || indent <= 3)) {
      if (under && owner) owner.mixed = true;
      const next: Item = {
        number: !under && item[2] ? Number(item[2]) : null,
        text: item[3],
        indent,
        subs: [],
        mixed: false,
      };
      items.push(next);
      // A question under a question stays under it: the bullets after it are its siblings.
      if (!under) owner = next;
      open = next;
    } else if (owner !== null && /^\s{2,}\S/.test(line) && (open === null || continuesAsLines(open, owner))) {
      // A line of its own under the item: a paragraph after a blank line
      // (the lines after it are its wrapped rest), or a line after an item
      // that ends in a colon ("My default is:"), where each line is one
      // thing it lists.
      const sub: Sub = { text: line.trim(), line: true, ...(open === null ? {} : { listed: true }) };
      owner.subs.push(sub);
      open = sub;
    } else if (open !== null && /^\s{2,}\S/.test(line)) {
      // A wrapped line of the same item.
      open.text += ` ${line.trim()}`;
    } else if (line.trim() === "") {
      // A blank line ends the item's text; bullets after it may still be its own.
      open = null;
    } else {
      owner = null;
      open = null;
    }
  }
  const asked = items.filter((item) => asksSomething(item.text));
  const numbers = asked.map((item) => item.number);
  const agentNumbered =
    numbers.every((n) => n !== null) && new Set(numbers).size === numbers.length;
  return asked.map((item, i) => {
    const n = agentNumbered ? (item.number as number) : i + 1;
    const text = withoutOwnNumber(plainText(item.text), n);
    // Bullets are options when they read as such; lines only when each is
    // marked as one ("a) PDF"): plain lines after a colon are what it lists.
    const optionLike = item.subs.every((sub) => !sub.line || /^\(?[a-z\d]\)\s+/i.test(sub.text));
    const below = !item.mixed && optionLike ? subOptions(item.subs.map((sub) => sub.text)) : undefined;
    if (below) return { n, text, options: below };
    // What is under the question and did not become options stays with it.
    const lines = item.subs.map((sub) => plainText(sub.text)).filter(Boolean);
    const details = lines.length ? { details: lines } : {};
    const listed = listedOptions(text);
    if (!listed) return { n, text, ...details };
    // A question that is whole before its list is shown without it: the chips
    // say the rest. Otherwise the line stays as the agent wrote it.
    const lead = text.slice(0, listed.at).trim();
    return { n, text: lead.includes("?") ? lead : text, options: listed.options, ...details };
  });
}

export type AnswerTemplate = {
  /** The first line of the message. */
  intro: string;
  /** One line per question: "{n}", "{question}" (quoted) and "{answer}". */
  line: string;
  /** The answer sent for a question left empty. */
  skip: string;
};

/**
 * An answer as it was typed: its line breaks stay (a list of systems, say),
 * with the later lines indented under the first so the whole answer stays
 * with its number. Blank lines and space at the ends of lines are dropped.
 */
function answerText(raw: string): string {
  return raw
    .split(/\r?\n/)
    .map((line) => line.replace(/\s+/g, " ").trim())
    .filter(Boolean)
    .join("\n   ");
}

/**
 * The chat message for answers given one by one. Each question goes back as
 * a quote on one line with its number, so the agent's own text (partly from
 * uploaded material) reaches it as data; the answers are the user's words.
 */
export function answersMessage(questions: Question[], answers: string[], template: AnswerTemplate): string {
  const lines = questions.map((question, i) =>
    fillTemplate(template.line, {
      n: String(question.n),
      question: quoteOneLine(question.text, 160),
      answer: answerText(answers[i] ?? "") || template.skip,
    }),
  );
  return [template.intro, ...lines].join("\n");
}
