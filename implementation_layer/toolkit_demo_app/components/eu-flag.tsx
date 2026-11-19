import Image from "next/image";

/**
 * The flag of Europe at its specified 3:2 (public domain; a static file in
 * public/icons). It marks the EU's AI Act as the subject of an entry, always
 * beside a label that names the Act, and is decorative for that reason. It fits
 * an icon slot at a fixed size, so it takes no class name.
 */
export function EuFlag() {
  return (
    <Image
      src="/icons/flag-eu.svg"
      alt=""
      width={21}
      height={14}
      unoptimized
      className="shrink-0"
    />
  );
}
