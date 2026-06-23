"use client";

import { useState } from "react";
import type { ChatMessage } from "@/lib/mock-sessions";
import { ChatPanel } from "./chat-panel";
import { RobotHex } from "./robot-avatar";

// Chat dock on the right edge of the workspace. The handle (left edge)
// collapses the chat to a narrow rail, widening the workspace.
export function ChatDock({
  sessionId,
  initialMessages,
  chatTitle,
  greeting,
  inputPlaceholder,
  sendLabel,
  railBadge,
  userInitial,
}: {
  sessionId: string;
  initialMessages: ChatMessage[];
  chatTitle: string;
  greeting: string;
  inputPlaceholder: string;
  sendLabel: string;
  railBadge: string;
  userInitial: string;
}) {
  const [open, setOpen] = useState(true);

  return (
    <aside
      className={`chat-bg relative shrink-0 border-l border-border flex flex-col min-h-0 transition-[width] duration-200 ${
        open ? "w-[380px]" : "w-[52px]"
      }`}
    >
      {/* Handle on the left edge */}
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        title={open ? "Piilota keskustelu" : "Näytä keskustelu"}
        className="absolute -left-3 top-1/2 -translate-y-1/2 z-10 flex h-14 w-[22px] flex-col items-center justify-center gap-[3px] rounded-lg border border-border-strong bg-surface-muted text-text-muted shadow-[-2px_0_8px_rgba(0,0,0,0.35)] transition-colors hover:border-brand hover:text-brand-strong"
      >
        <span className="h-[3px] w-[3px] rounded-full bg-current opacity-60" />
        <span className="text-[13px] leading-none">{open ? "›" : "‹"}</span>
        <span className="h-[3px] w-[3px] rounded-full bg-current opacity-60" />
      </button>

      {open ? (
        <ChatPanel
          sessionId={sessionId}
          initialMessages={initialMessages}
          chatTitle={chatTitle}
          greeting={greeting}
          inputPlaceholder={inputPlaceholder}
          sendLabel={sendLabel}
          userInitial={userInitial}
        />
      ) : (
        /* Collapsed rail: robot mascot + vertical text + phase badge */
        <div className="flex h-full flex-col items-center gap-4 py-4">
          <RobotHex px={28} />
          <span className="[writing-mode:vertical-rl] text-xs font-semibold tracking-wide text-text-muted">
            {chatTitle}
          </span>
          <span className="[writing-mode:vertical-rl] rounded-full bg-brand-soft px-0.5 py-1.5 text-[9px] font-semibold text-brand-text">
            {railBadge}
          </span>
        </div>
      )}
    </aside>
  );
}
