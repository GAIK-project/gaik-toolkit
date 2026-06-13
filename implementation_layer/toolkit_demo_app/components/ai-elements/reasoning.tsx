"use client";

import { MessageResponse } from "@/components/ai-elements/message";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";
import { BrainIcon, ChevronDownIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";

interface ReasoningProps {
  /** Streamed reasoning text (markdown). */
  children: string;
  /** True while reasoning tokens are still arriving (keeps it open + autoscrolls). */
  isStreaming?: boolean;
  className?: string;
}

/**
 * Collapsible reasoning trace (ai-elements style). Deliberately lightweight:
 * small muted text, no background, and a fixed-height scroll area so a long
 * thinking stream scrolls *inside* the box instead of pushing the rest of the
 * chat around. It auto-opens while the model is thinking (so a long wait still
 * shows live progress) and stays put once the answer begins — it does not
 * collapse mid-turn, which is what made the layout jump. In history it renders
 * collapsed; click to re-read the chain of thought.
 */
export function Reasoning({ children, isStreaming, className }: ReasoningProps) {
  const [open, setOpen] = useState(Boolean(isStreaming));
  const [userToggled, setUserToggled] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Follow the stream (open while thinking) unless the user took manual control.
  useEffect(() => {
    if (!userToggled) setOpen(Boolean(isStreaming));
  }, [isStreaming, userToggled]);

  // Keep the newest thinking in view while it streams into the capped box.
  useEffect(() => {
    if (isStreaming && open && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [children, isStreaming, open]);

  if (!children.trim()) return null;

  return (
    <Collapsible
      open={open}
      onOpenChange={(next) => {
        setUserToggled(true);
        setOpen(next);
      }}
      className={cn("not-prose text-muted-foreground mb-2 text-xs", className)}
    >
      <CollapsibleTrigger className="hover:text-foreground flex items-center gap-1.5 transition-colors">
        <BrainIcon className="h-3.5 w-3.5" />
        <span>{isStreaming ? "Reasoning…" : "Reasoning"}</span>
        <ChevronDownIcon
          className={cn("h-3.5 w-3.5 transition-transform", open && "rotate-180")}
        />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div
          ref={scrollRef}
          className="mt-1.5 max-h-44 overflow-y-auto border-l border-border pl-3 leading-5 [&_*]:text-xs"
        >
          <MessageResponse>{children}</MessageResponse>
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}
