// The agent writes some values as identifiers ("knowledge_capture",
// "component_selection"). The interface shows words: the label the dictionary
// has for a known value, and an unknown identifier as readable text, never as
// a snake_case token.

// One token with an underscore in it. Underscores only: a hyphen is part of
// real words ("HR-hallinto", "e-lasku") and stays as it was written.
const isIdentifier = (text: string) => text.includes("_") && !/\s/.test(text);

const keyOf = (value: string) => value.trim().toLowerCase().replace(/[\s-]+/g, "_");

/**
 * The value in plain words. A value the map knows gets its label; another
 * identifier has its underscores turned into spaces; ordinary text (it has a
 * space or a hyphen, or is one word) is shown as it was written.
 */
export function plainLabel(value: string, labels: Record<string, string> = {}): string {
  const text = value.trim();
  const key = keyOf(text);
  if (Object.prototype.hasOwnProperty.call(labels, key)) return labels[key];
  return isIdentifier(text) ? text.replace(/_+/g, " ").trim() : text;
}

/** The same, starting with a capital letter: for a value that stands alone. */
export function plainLabelCapitalized(value: string, labels: Record<string, string> = {}): string {
  const label = plainLabel(value, labels);
  return label.charAt(0).toLocaleUpperCase() + label.slice(1);
}

/** Plain labels with repeats left out: two identifiers can share one label. */
export function plainLabels(values: string[], labels: Record<string, string> = {}): string[] {
  return [...new Set(values.map((value) => plainLabel(value, labels)))];
}
