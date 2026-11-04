/* The official mark (svgl) uses masks and filters with fixed ids; an <img> keeps
   each copy in its own document, so several on one page do not clash. */
const Gemini = ({
  className,
}: {
  className?: string;
  "aria-hidden"?: boolean;
}) => (
  // eslint-disable-next-line @next/next/no-img-element
  <img src="/logos/gemini.svg" alt="" aria-hidden className={className} />
);

export { Gemini };
