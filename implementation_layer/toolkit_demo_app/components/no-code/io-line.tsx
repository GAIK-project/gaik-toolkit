import Image from "next/image";

/** File-type marks from vscode-icons (MIT), kept as static files in public/icons. */
const fileTypes: [RegExp, string][] = [
  [/audio|recording/i, "audio"],
  [/pdf/i, "pdf"],
  [/word|\.docx/i, "word"],
  [/json/i, "json"],
  [/markdown/i, "markdown"],
];

function Icons({ text }: { text: string }) {
  const found = fileTypes.filter(([pattern]) => pattern.test(text));
  return found.map(([, name]) => (
    <Image
      key={name}
      src={`/icons/file-${name}.svg`}
      alt=""
      width={16}
      height={16}
      unoptimized
      className="mr-1 inline-block size-4 align-[-2px]"
    />
  ));
}

/** "Audio recording → Word (.docx)" with a file-type icon before each side. */
export function IoLine({ input, output }: { input: string; output: string }) {
  return (
    <p className="text-sm">
      <Icons text={input} />
      {input} <span aria-label="to">→</span> <Icons text={output} />
      {output}
    </p>
  );
}
