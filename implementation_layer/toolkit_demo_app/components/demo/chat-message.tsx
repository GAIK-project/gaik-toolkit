/**
 * Simple chat message component with source citations.
 *
 * Note: For production use with AI SDK, prefer Message from @/components/ai-elements/message
 * which provides markdown rendering, branch navigation, and better integration with useChat.
 *
 * This component is kept as a simpler alternative for basic chat UIs.
 */
"use client";

import { useState } from "react";
import { motion } from "motion/react";
import { Bot, User, FileText, Copy, Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { type Source } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import toast from "react-hot-toast";

// Re-export Source for backward compatibility
export type { Source } from "@/lib/types";

interface ChatMessageProps {
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  isStreaming?: boolean;
  className?: string;
}

export function ChatMessage({
  role,
  content,
  sources = [],
  isStreaming = false,
  className,
}: ChatMessageProps) {
  const [copied, setCopied] = useState(false);
  const isUser = role === "user";

  async function handleCopy(): Promise<void> {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      toast.success("Copied to clipboard");
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error("Failed to copy");
    }
  }

  // Group sources by document
  const groupedSources = sources.reduce<Record<string, Source[]>>(
    (acc, source) => {
      const key = source.documentName;
      if (!acc[key]) acc[key] = [];
      acc[key].push(source);
      return acc;
    },
    {},
  );

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn(
        "flex gap-3",
        isUser ? "flex-row-reverse" : "flex-row",
        className,
      )}
    >
      {/* Avatar */}
      <div
        className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-muted text-muted-foreground",
        )}
      >
        {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
      </div>

      {/* Message bubble */}
      <div
        className={cn(
          "group relative max-w-[80%] rounded-2xl px-4 py-3",
          isUser ? "bg-primary text-primary-foreground" : "bg-muted",
        )}
      >
        {/* Message content */}
        <div className="text-sm leading-relaxed whitespace-pre-wrap">
          {content}
          {isStreaming && (
            <motion.span
              animate={{ opacity: [1, 0] }}
              transition={{ duration: 0.5, repeat: Infinity }}
              className={cn(
                "ml-0.5 inline-block h-4 w-2",
                isUser ? "bg-primary-foreground" : "bg-primary",
              )}
            />
          )}
        </div>

        {/* Sources */}
        {!isUser && sources.length > 0 && (
          <div className="border-border/50 mt-3 border-t pt-3">
            <div className="text-muted-foreground mb-2 flex items-center gap-1.5 text-xs">
              <FileText className="h-3 w-3" />
              <span>Sources</span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(groupedSources).map(([docName, docSources]) => (
                <Badge
                  key={docName}
                  variant="secondary"
                  className="text-xs font-normal"
                >
                  {docName}
                  {docSources.length > 1 && ` (${docSources.length})`}
                </Badge>
              ))}
            </div>
          </div>
        )}

        {/* Copy button for assistant messages */}
        {!isUser && !isStreaming && (
          <Button
            variant="ghost"
            size="icon"
            onClick={handleCopy}
            className="absolute top-1 -right-10 h-8 w-8 opacity-0 transition-opacity group-hover:opacity-100"
          >
            {copied ? (
              <Check className="h-3.5 w-3.5 text-green-600" />
            ) : (
              <Copy className="h-3.5 w-3.5" />
            )}
          </Button>
        )}
      </div>
    </motion.div>
  );
}

interface StreamingMessageProps {
  chunks: string[];
  sources?: Source[];
  className?: string;
}

export function StreamingMessage({
  chunks,
  sources = [],
  className,
}: StreamingMessageProps) {
  const content = chunks.join("");

  return (
    <ChatMessage
      role="assistant"
      content={content}
      sources={sources}
      isStreaming={true}
      className={className}
    />
  );
}
