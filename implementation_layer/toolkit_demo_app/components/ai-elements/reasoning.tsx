"use client";

import { MessageResponse } from "@/components/ai-elements/message";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";
import { BrainIcon, ChevronDownIcon } from "lucide-react";
import { useEffect, useState } from "react";

interface ReasoningProps {
  /** Streamed reasoning text (markdown). */
  children: string;
  /** True while reasoning tokens are still arriving. */
  isStreaming?: boolean;
  className?: string;
}

/**
 * Collapsible reasoning block (ai-elements style): auto-opens while the model
 * is thinking, auto-closes when the answer starts streaming. The user can
 * re-open it at any time to inspect the chain of thought.
 */
export function Reasoning({ children, isStreaming, className }: ReasoningProps) {
  const [open, setOpen] = useState(true);
  const [userToggled, setUserToggled] = useState(false);

  // Follow the stream unless the user has taken manual control.
  useEffect(() => {
    if (!userToggled) setOpen(Boolean(isStreaming));
  }, [isStreaming, userToggled]);

  if (!children.trim()) return null;

  return (
    <Collapsible
      open={open}
      onOpenChange={(next) => {
        setUserToggled(true);
        setOpen(next);
      }}
      className={cn("not-prose text-muted-foreground mb-2 text-sm", className)}
    >
      <CollapsibleTrigger className="hover:text-foreground flex items-center gap-2 transition-colors">
        <BrainIcon className="h-4 w-4" />
        <span>{isStreaming ? "Reasoning…" : "Reasoning"}</span>
        <ChevronDownIcon
          className={cn("h-4 w-4 transition-transform", open && "rotate-180")}
        />
      </CollapsibleTrigger>
      <CollapsibleContent className="mt-2 border-l-2 pl-3 text-sm leading-6">
        <MessageResponse>{children}</MessageResponse>
      </CollapsibleContent>
    </Collapsible>
  );
}
