// File-type marks from Catppuccin Icons (https://github.com/catppuccin/vscode-icons,
// MIT licence, Copyright (c) 2023 Catppuccin and thang-nm), in the set's Latte
// colours, which are drawn for a light ground. Inlined, like the UI icons in
// components/icons, so the wizard needs no icon package. 16 px grid, 1 px
// stroke: a line family like the Lucide icons beside them, with a colour per
// file type. Each mark keeps the set's own colours.
import type { ReactNode, SVGProps } from "react";
import { fileKind, fileKindInText, type FileKind } from "@/lib/file-kind";
import { Icon } from "@/components/icons";

const MARKS: Record<FileKind, ReactNode> = {
  json: (
    <><path fill="none" stroke="#df8e1d" strokeLinecap="round" strokeLinejoin="round" d="M4.5 2.5H4c-.75 0-1.5.75-1.5 1.5v2c0 1.1-1 2-1.83 2 .83 0 1.83.9 1.83 2v2c0 .75.75 1.5 1.5 1.5h.5m7-11h.5c.75 0 1.5.75 1.5 1.5v2c0 1.1 1 2 1.83 2-.83 0-1.83.9-1.83 2v2c0 .74-.75 1.5-1.5 1.5h-.5m-6.5-3a.5.5 0 100-1 .5.5 0 000 1m3 0a.5.5 0 100-1 .5.5 0 000 1m3 0a.5.5 0 100-1 .5.5 0 000 1" /></>
  ),
  pdf: (
    <><path fill="none" stroke="#d20f39" strokeLinecap="round" strokeLinejoin="round" d="M2.8 14.34c1.81-1.25 3.02-3.16 3.91-5.5.9-2.33 1.86-4.33 1.44-6.63-.06-.36-.57-.73-.83-.7-1.02.06-.95 1.21-.85 1.9.24 1.71 1.56 3.7 2.84 5.56 1.27 1.87 2.32 2.16 3.78 2.26.5.03 1.25-.14 1.37-.58.77-2.8-9.02-.54-12.28 2.08-.4.33-.86 1-.6 1.46.2.36.87.4 1.23.15h0Z" /></>
  ),
  word: (
    <><g fill="none" stroke="#1e66f5" strokeLinecap="round" strokeLinejoin="round"><path d="M2.5 3.13c0-.77.86-1.63 1.62-1.63h9.76c.76 0 1.62.86 1.62 1.63v9.75c0 .76-.86 1.62-1.62 1.62H4.13c-.77 0-1.63-.86-1.63-1.62" /><path d="m.5 5.5 1 5 1-5 1 5 .97-5m3.03 1h4m-4 3h4" /></g></>
  ),
  excel: (
    <><g fill="none" stroke="#40a02b" strokeLinecap="round" strokeLinejoin="round"><path d="M2.5 3.13c0-.77.86-1.63 1.62-1.63h9.76c.76 0 1.62.86 1.62 1.63v9.75c0 .76-.86 1.62-1.62 1.62H4.13c-.77 0-1.63-.86-1.63-1.62M.5 5.5l4 5m0-5-4 5" /><path d="M7.5 5.5h5v5h-5zm2 0v5m-2-3h5" /></g></>
  ),
  csv: (
    <><path fill="none" stroke="#40a02b" strokeLinecap="round" strokeLinejoin="round" d="M1.5 3.5c0-.54.48-1 1.08-1H6.5l1.54 1h5.38c.6 0 1.08.44 1.08.98l-.09 9.04c0 .54-.48.98-1.08.98H2.58c-.6 0-1.08-.44-1.08-.98zm2 4v4m3-4v4m3-4v4m3-4v4m-9 0h9m-9-2h9m-9-2h9" /></>
  ),
  markdown: (
    <><path fill="none" stroke="#209fb5" strokeLinecap="round" strokeLinejoin="round" d="m9.25 8.25 2.25 2.25 2.25-2.25M3.5 11V5.5l2.04 3 1.96-3V11m4-.5V5M1.65 2.5h12.7c.59 0 1.15.49 1.15 1v9c0 .51-.56 1-1.15 1H1.65c-.59 0-1.15-.49-1.15-1V3.58c0-.5.56-1.08 1.15-1.08" /></>
  ),
  python: (
    <><g fill="none" strokeLinecap="round" strokeLinejoin="round"><path stroke="#1e66f5" d="M8.5 5.5h-3m6 0V3c0-.8-.7-1.5-1.5-1.5H7c-.8 0-1.5.7-1.5 1.5v2.5H3c-.8 0-1.5.7-1.5 1.5v2c0 .8.7 1.5 1.48 1.5" /><path stroke="#df8e1d" d="M10.5 10.5h-3m-3 0V13c0 .8.7 1.5 1.5 1.5h3c.8 0 1.5-.7 1.5-1.5v-2.5H13c.8 0 1.5-.7 1.5-1.5V7c0-.8-.7-1.5-1.48-1.5H11.5c0 1.5 0 2-1 2h-2" /><path stroke="#1e66f5" d="M2.98 10.5H4.5c0-1.5 0-2 1-2h2M7.5 3.5v0" /><path stroke="#df8e1d" d="m 8.5,12.5 v 0" /></g></>
  ),
  zip: (
    <><path fill="none" stroke="#4c4f69" strokeLinejoin="round" d="m5.5 10v1m1-2v1m-1-2v1m1-2v1m-1-2v1m1-2v1m-1-2v1m0-3v1m1 0v1m7 2.5v6c0 1.105-0.8954 2-2 2h-7c-1.105 0-2-0.8954-2-2v-9c0-1.1 0.9-2 2-2h4.01m-0.01 0 5 5h-4c-0.5523 0-1-0.4477-1-1z" /></>
  ),
  text: (
    <><g fill="none" stroke="#4c4f69" strokeLinecap="round" strokeLinejoin="round"><path d="M13.5 6.5v6a2 2 0 01-2 2h-7a2 2 0 01-2-2v-9c0-1.1.9-2 2-2h4.01" /><path d="m8.5 1.5 5 5h-4a1 1 0 01-1-1zm-3 10h5m-5-3h5m-5-3h1" /></g></>
  ),
  audio: (
    <><g fill="none" stroke="#e64553" strokeLinecap="round" strokeLinejoin="round"><path d="M5.5 12.5a2 2 0 01-2 2 2 2 0 01-2-2 2 2 0 012-2 2 2 0 012 2m9-2a2 2 0 01-2 2 2 2 0 01-2-2 2 2 0 012-2 2 2 0 012 2" /><path d="M5.5 12.5V5c0-.54.44-1.21 1.35-1.5l6.3-2c.9 0 1.35.88 1.35 1.5v7.58m-9-3.08 9-3" /></g></>
  ),
  image: (
    <><g fill="none" strokeLinecap="round" strokeLinejoin="round"><path stroke="#df8e1d" d="M11.5 6A1.5 1.5 0 0110 7.5 1.5 1.5 0 018.5 6 1.5 1.5 0 0110 4.5 1.5 1.5 0 0111.5 6" /><path stroke="#40a02b" d="M7.5 13.5 11 10c.5-.5 1.5-.5 2 0l1.5 1.5" /><path stroke="#40a02b" d="m1.5 9.5 2-2C4 7 5 7 5.5 7.5l4 4" /><path stroke="#209fb5" d="M3 2.5h10c.83 0 1.5.67 1.5 1.5v8c0 .83-.67 1.5-1.5 1.5H3A1.5 1.5 0 011.5 12V4c0-.83.67-1.5 1.5-1.5" /></g></>
  ),
};

type FileIconProps = {
  /** The file's name or media type; its kind is read from it. */
  name?: string | null;
  /** The kind itself, where no file name stands for it (the output schema is JSON). */
  kind?: FileKind | null;
  size?: number;
} & Omit<SVGProps<SVGSVGElement>, "name">;

/**
 * The mark of a file's type, beside the file's name. Decorative: the name (or
 * the heading) next to it is the text, so the mark is hidden from assistive
 * tech. A kind without a mark of its own gets the plain file icon.
 */
export function FileIcon({ name, kind, size = 16, className, ...rest }: FileIconProps) {
  const known = kind ?? fileKind(name);
  if (!known) return <Icon name="file" size={size} className={`text-text-muted ${className ?? ""}`} />;
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 16 16"
      aria-hidden
      focusable="false"
      data-file-kind={known}
      className={`shrink-0 ${className ?? ""}`}
      {...rest}
    >
      {MARKS[known]}
    </svg>
  );
}

/**
 * A line of text that may name a file ("Kirjoitetaan output_schema.json"):
 * the file's mark goes in front of it. A line that names none is the text alone.
 */
export function FileMention({ text, size = 13 }: { text: string; size?: number }) {
  const kind = fileKindInText(text);
  if (!kind) return <>{text}</>;
  return (
    <>
      <FileIcon kind={kind} size={size} className="mr-1 inline-block align-[-2px]" />
      {text}
    </>
  );
}
