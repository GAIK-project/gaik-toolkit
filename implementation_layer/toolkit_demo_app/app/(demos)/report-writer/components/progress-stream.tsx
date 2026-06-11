"use client";

import { useEffect, useRef } from "react";
import { cn } from "@/lib/utils";
import { CheckCircle, Circle, Clock, Loader2 } from "lucide-react";

interface ProgressStreamProps {
  messages: string[];
  isRunning: boolean;
  className?: string;
}

/** Parse a section name from messages like "[Findings] ..." */
function parseSectionName(msg: string): string | null {
  const m = msg.match(/^\[([^\]]+)\]/);
  return m ? m[1] : null;
}

/** Classify message into a phase for visual grouping. */
function isNormalizationMessage(msg: string): boolean {
  return (
    msg.startsWith("Normalizing [") ||
    msg.startsWith("Evidence pack assembled") ||
    msg.startsWith("Transcribing") ||
    msg.startsWith("Chunking") ||
    msg.startsWith("Transcript")
  );
}

export function ProgressStream({
  messages,
  isRunning,
  className,
}: ProgressStreamProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  // Derive per-section status for the summary chips
  const sectionStatus: Record<
    string,
    "drafting" | "reviewing" | "done" | "curating"
  > = {};
  for (const msg of messages) {
    const name = parseSectionName(msg);
    if (!name) continue;
    if (msg.includes("done")) sectionStatus[name] = "done";
    else if (msg.includes("reviewer")) sectionStatus[name] = "reviewing";
    else if (msg.includes("draft written")) sectionStatus[name] = "reviewing";
    else if (msg.includes("curated evidence")) sectionStatus[name] = "drafting";
    else if (msg.includes("evidence loaded") && !(name in sectionStatus))
      sectionStatus[name] = "drafting";
    else if (msg.includes("curating") || msg.includes("curation"))
      sectionStatus[name] = "curating";
  }

  const normMessages = messages.filter(isNormalizationMessage);
  const writeMessages = messages.filter((m) => !isNormalizationMessage(m));

  return (
    <div
      className={cn(
        "rounded-lg border bg-zinc-950 text-zinc-100 font-mono text-xs overflow-hidden",
        className,
      )}
    >
      {/* Section status chips */}
      {Object.keys(sectionStatus).length > 0 && (
        <div className="flex flex-wrap gap-1.5 px-3 py-2 border-b border-zinc-800">
          {Object.entries(sectionStatus).map(([name, status]) => (
            <span
              key={name}
              className={cn(
                "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] border",
                status === "done"
                  ? "bg-green-950 border-green-700 text-green-400"
                  : status === "reviewing"
                    ? "bg-yellow-950 border-yellow-700 text-yellow-400"
                    : "bg-zinc-800 border-zinc-600 text-zinc-400",
              )}
            >
              {status === "done" ? (
                <CheckCircle className="h-2.5 w-2.5" />
              ) : status === "reviewing" ? (
                <Clock className="h-2.5 w-2.5" />
              ) : (
                <Loader2 className="h-2.5 w-2.5 animate-spin" />
              )}
              {name}
            </span>
          ))}
        </div>
      )}

      {/* Log */}
      <div className="max-h-80 overflow-y-auto p-3 space-y-0.5">
        {messages.length === 0 && isRunning && (
          <p className="text-zinc-500 flex items-center gap-2">
            <Loader2 className="h-3 w-3 animate-spin" />
            Starting…
          </p>
        )}

        {/* Normalization phase */}
        {normMessages.length > 0 && (
          <div className="mb-1">
            <p className="text-zinc-600 uppercase tracking-wider text-[9px] mb-1">
              — Input Normalization —
            </p>
            {normMessages.map((msg, i) => (
              <LogLine key={`n-${i}`} msg={msg} />
            ))}
          </div>
        )}

        {/* Writing phase */}
        {writeMessages.length > 0 && (
          <div>
            {normMessages.length > 0 && (
              <p className="text-zinc-600 uppercase tracking-wider text-[9px] mb-1 mt-2">
                — Report Writing —
              </p>
            )}
            {writeMessages.map((msg, i) => (
              <LogLine key={`w-${i}`} msg={msg} />
            ))}
          </div>
        )}

        {isRunning && (
          <p className="text-zinc-500 flex items-center gap-2 pt-0.5">
            <Loader2 className="h-3 w-3 animate-spin" />
            Processing…
          </p>
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  );
}

function LogLine({ msg }: { msg: string }) {
  const isDone = msg.includes("done") || msg.includes("assembled") || msg.includes("complete");
  const isError = msg.toLowerCase().includes("error") || msg.toLowerCase().includes("warning");
  const isPhase = msg.startsWith("Phase");

  return (
    <p
      className={cn(
        "leading-5 whitespace-pre-wrap break-all",
        isDone ? "text-green-400" : isError ? "text-red-400" : isPhase ? "text-blue-400 font-semibold" : "text-zinc-300",
      )}
    >
      {msg}
    </p>
  );
}
