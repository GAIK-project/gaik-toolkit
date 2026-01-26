/**
 * Simple chat input component.
 *
 * Note: For production use, prefer PromptInput from @/components/ai-elements/prompt-input
 * which provides more features like file attachments, paste handling, and better accessibility.
 *
 * This component is kept as a simpler alternative for basic use cases.
 */
"use client";

import { useRef, useState } from "react";
import { Send, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

interface ChatInputProps {
  onSubmit: (message: string) => void;
  disabled?: boolean;
  isLoading?: boolean;
  placeholder?: string;
  className?: string;
}

export function ChatInput({
  onSubmit,
  disabled = false,
  isLoading = false,
  placeholder = "Ask a question about your documents...",
  className,
}: ChatInputProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  function handleSubmit(): void {
    const trimmed = value.trim();
    if (!trimmed || disabled || isLoading) return;

    onSubmit(trimmed);
    setValue("");

    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>): void {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }

  function handleInput(e: React.ChangeEvent<HTMLTextAreaElement>): void {
    setValue(e.target.value);

    // Auto-resize textarea
    const textarea = e.target;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
  }

  const isDisabled = disabled || isLoading;
  const canSubmit = value.trim().length > 0 && !isDisabled;

  return (
    <div className={cn("relative", className)}>
      <div className="focus-within:ring-ring flex items-end gap-2 rounded-2xl border bg-white p-2 shadow-sm focus-within:ring-2 focus-within:ring-offset-2">
        <Textarea
          ref={textareaRef}
          value={value}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={isDisabled}
          rows={1}
          className="max-h-[200px] min-h-[40px] resize-none border-0 bg-transparent px-2 py-2 focus-visible:ring-0 focus-visible:ring-offset-0"
        />
        <Button
          onClick={handleSubmit}
          disabled={!canSubmit}
          size="icon"
          className="h-10 w-10 shrink-0 rounded-xl"
        >
          {isLoading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Send className="h-4 w-4" />
          )}
        </Button>
      </div>
      <p className="text-muted-foreground mt-2 text-center text-xs">
        Press Enter to send, Shift+Enter for new line
      </p>
    </div>
  );
}
