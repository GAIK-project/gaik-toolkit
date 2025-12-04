"use client";

import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/cjs/styles/prism";

type Tab = {
  name: string;
  code: string;
  language?: string;
  highlightLines?: number[];
};

type CodeBlockProps = {
  language: string;
  filename?: string;
  highlightLines?: number[];
} & (
  | { code: string; tabs?: never }
  | { code?: never; tabs: Tab[] }
);

export function CodeBlock({
  language,
  filename,
  code,
  highlightLines = [],
  tabs = [],
}: CodeBlockProps) {
  const [copied, setCopied] = useState(false);
  const [activeTab, setActiveTab] = useState(0);

  const hasTabs = tabs.length > 0;

  const copyToClipboard = async () => {
    const textToCopy = hasTabs ? tabs[activeTab].code : code;
    if (textToCopy) {
      await navigator.clipboard.writeText(textToCopy);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const activeCode = hasTabs ? tabs[activeTab].code : code;
  const activeLanguage = hasTabs
    ? tabs[activeTab].language || language
    : language;
  const activeHighlightLines = hasTabs
    ? tabs[activeTab].highlightLines || []
    : highlightLines;

  return (
    <div className="relative w-full overflow-hidden rounded-lg border bg-zinc-950">
      <div className="flex items-center justify-between border-b bg-zinc-900 px-4 py-2">
        {hasTabs ? (
          <div className="flex gap-1">
            {tabs.map((tab, index) => (
              <button
                key={index}
                onClick={() => setActiveTab(index)}
                className={`rounded px-3 py-1 text-xs transition-colors ${
                  activeTab === index
                    ? "bg-zinc-800 text-white"
                    : "text-zinc-400 hover:text-zinc-200"
                }`}
              >
                {tab.name}
              </button>
            ))}
          </div>
        ) : (
          <span className="text-xs text-zinc-400">{filename || language}</span>
        )}
        <button
          onClick={copyToClipboard}
          className="flex items-center gap-1 rounded p-1 text-xs text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-zinc-200"
          aria-label="Copy code"
        >
          {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
        </button>
      </div>
      <SyntaxHighlighter
        language={activeLanguage}
        style={oneDark}
        customStyle={{
          margin: 0,
          padding: "1rem",
          background: "transparent",
          fontSize: "0.875rem",
        }}
        wrapLines
        showLineNumbers
        lineProps={(lineNumber) => ({
          style: {
            backgroundColor: activeHighlightLines.includes(lineNumber)
              ? "rgba(255,255,255,0.1)"
              : "transparent",
            display: "block",
            width: "100%",
          },
        })}
        PreTag="div"
      >
        {String(activeCode)}
      </SyntaxHighlighter>
    </div>
  );
}
