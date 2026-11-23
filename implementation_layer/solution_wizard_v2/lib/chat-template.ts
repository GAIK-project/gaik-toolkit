/**
 * Fills "{name}" placeholders in one pass. A value goes in as it is: a "$&"
 * in it stays "$&", and a "{answer}" inside the quoted point is not filled in
 * turn, as it was by a chain of .replace() calls.
 */
export function fillTemplate(template: string, values: Record<string, string>): string {
  return template.replace(/\{(\w+)\}/g, (placeholder, name: string) =>
    Object.prototype.hasOwnProperty.call(values, name) ? values[name] : placeholder,
  );
}

/**
 * Text for a quote on one line: line breaks and runs of space become one
 * space, a double quote becomes a single one, and a long text is cut. A
 * checklist point is written by the agent, partly from uploaded material, so
 * it travels as a marked quote (data), never as lines of the user's message.
 */
export function quoteOneLine(text: string, max = 300): string {
  const line = text.replace(/\s+/g, " ").replace(/"/g, "'").trim();
  return line.length > max ? `${line.slice(0, max - 1).trimEnd()}…` : line;
}
