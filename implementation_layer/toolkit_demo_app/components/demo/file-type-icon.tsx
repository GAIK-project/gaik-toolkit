import { File as FileIcon } from "lucide-react";
import Image from "next/image";

/** File-type marks from vscode-icons (MIT), kept as static files in public/icons. */
const FILE_TYPES: [RegExp, string][] = [
  [/\.pdf$/i, "pdf"],
  [/\.docx?$/i, "word"],
  [/\.(png|jpe?g|gif|webp|tiff?|bmp)$/i, "image"],
  [/\.(xlsx?|csv)$/i, "excel"],
];

/** The mark of a file's type, by its name; a plain file glyph for any other type. */
export function FileTypeIcon({ name }: { name: string }) {
  const type = FILE_TYPES.find(([pattern]) => pattern.test(name))?.[1];
  if (!type) {
    return (
      <FileIcon className="text-muted-foreground size-4 shrink-0" aria-hidden />
    );
  }
  return (
    <Image
      src={`/icons/file-${type}.svg`}
      alt=""
      width={16}
      height={16}
      unoptimized
      className="size-4 shrink-0"
    />
  );
}
