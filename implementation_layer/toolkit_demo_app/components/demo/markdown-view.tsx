"use client";

import {
  parseInline,
  splitByQuery,
  type Block,
} from "@/app/(demos)/parser/parser-data";
import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

/** Text with the matches of the search marked. */
function Marked({ text, query }: { text: string; query: string }) {
  return (
    <>
      {splitByQuery(text, query).map((part, index) =>
        part.hit ? (
          <mark
            key={index}
            data-hit
            className="rounded bg-amber-200 px-0.5 text-inherit"
          >
            {part.text}
          </mark>
        ) : (
          part.text
        ),
      )}
    </>
  );
}

function Inlines({ text, query }: { text: string; query: string }) {
  return (
    <>
      {parseInline(text).map((part, index) => {
        const inner = <Marked text={part.text} query={query} />;
        switch (part.t) {
          case "bold":
            return <strong key={index}>{inner}</strong>;
          case "italic":
            return <em key={index}>{inner}</em>;
          case "code":
            return (
              <code
                key={index}
                className="bg-muted rounded px-1 py-0.5 font-mono text-[0.85em]"
              >
                {inner}
              </code>
            );
          case "link":
            return (
              <a
                key={index}
                href={part.href}
                target="_blank"
                rel="noreferrer"
                className="text-primary underline underline-offset-2"
              >
                {inner}
              </a>
            );
          default:
            return <span key={index}>{inner}</span>;
        }
      })}
    </>
  );
}

const HEADING_CLASS = [
  "",
  "text-2xl font-bold",
  "text-xl font-semibold",
  "text-lg font-semibold",
  "text-base font-semibold",
  "text-sm font-semibold",
  "text-sm font-medium",
];

/** The blocks of a parsed document, drawn the way the markdown reads. */
export function MarkdownView({
  blocks,
  query = "",
  idPrefix = "",
  className,
}: {
  blocks: Block[];
  query?: string;
  /** Put in front of every heading id, so two views of a page keep their ids apart. */
  idPrefix?: string;
  className?: string;
}) {
  return (
    <div className={cn("space-y-3 text-sm leading-relaxed", className)}>
      {blocks.map((block, index): ReactNode => {
        switch (block.type) {
          case "heading": {
            const Tag = `h${Math.min(block.level, 6)}` as "h1";
            return (
              <Tag
                key={index}
                id={`${idPrefix}${block.id}`}
                className={cn("scroll-mt-4 pt-2", HEADING_CLASS[block.level])}
              >
                <Inlines text={block.text} query={query} />
              </Tag>
            );
          }
          case "paragraph":
            return (
              <p key={index}>
                <Inlines text={block.text} query={query} />
              </p>
            );
          case "quote":
            return (
              <blockquote
                key={index}
                className="text-muted-foreground border-l-4 pl-3 italic"
              >
                <Inlines text={block.text} query={query} />
              </blockquote>
            );
          case "code":
            return (
              <pre
                key={index}
                className="bg-muted/50 overflow-x-auto rounded-md p-3 font-mono text-xs"
              >
                <code>
                  <Marked text={block.text} query={query} />
                </code>
              </pre>
            );
          case "hr":
            return <hr key={index} />;
          case "list": {
            const List = block.ordered ? "ol" : "ul";
            return (
              <List
                key={index}
                className={cn(
                  "space-y-1 pl-5",
                  block.ordered ? "list-decimal" : "list-disc",
                )}
              >
                {block.items.map((item, itemIndex) => (
                  <li
                    key={itemIndex}
                    style={{ marginLeft: `${item.depth * 1.25}rem` }}
                  >
                    <Inlines text={item.text} query={query} />
                  </li>
                ))}
              </List>
            );
          }
          case "table":
            return (
              <div key={index} className="overflow-x-auto rounded-md border">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="bg-muted/50">
                      {block.header.map((cell, cellIndex) => (
                        <th key={cellIndex} className="px-3 py-2 font-medium">
                          <Inlines text={cell} query={query} />
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {block.rows.map((row, rowIndex) => (
                      <tr key={rowIndex} className="hover:bg-muted/30 border-t">
                        {row.map((cell, cellIndex) => (
                          <td key={cellIndex} className="px-3 py-2 align-top">
                            <Inlines text={cell} query={query} />
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
        }
      })}
    </div>
  );
}
