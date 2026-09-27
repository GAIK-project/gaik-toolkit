"use client";

import { useId, useState } from "react";
import type { ChatMessage } from "@/lib/mock-sessions";
import { ChatPanel } from "./chat-panel";
import { RobotHex } from "./robot-avatar";

export function ChatDock({
  sessionId,
  initialMessages,
  chatTitle,
  greeting,
  inputPlaceholder,
  inputLabel,
  sendLabel,
  streamFailedLabel,
  hideChatLabel,
  showChatLabel,
  railBadge,
  userInitial,
}: {
  sessionId: string;
  initialMessages: ChatMessage[];
  chatTitle: string;
  greeting: string;
  inputPlaceholder: string;
  inputLabel: string;
  sendLabel: string;
  streamFailedLabel: string;
  hideChatLabel: string;
  showChatLabel: string;
  railBadge: string;
  userInitial: string;
}) {
  const [open, setOpen] = useState(true);
  const panelId = useId();

  return (
    <aside
      aria-label={chatTitle}
      className={`chat-bg relative shrink-0 border-l border-border flex flex-col min-h-0 transition-[width] duration-200 motion-reduce:transition-none ${
        open ? "w-[var(--width-chat)]" : "w-[var(--width-chat-rail)]"
      }`}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-controls={panelId}
        aria-label={open ? hideChatLabel : showChatLabel}
        className="absolute -left-3 top-1/2 -translate-y-1/2 z-10 flex h-14 w-6 flex-col items-center justify-center gap-0.5 rounded-lg border border-border-strong bg-surface-muted text-text-muted shadow-[-2px_0_8px_rgba(0,0,0,0.35)] transition-colors hover:border-brand hover:text-brand-strong"
      >
        <span className="h-0.5 w-0.5 rounded-full bg-current opacity-60" aria-hidden />
        <span className="text-sm leading-none" aria-hidden>
          {open ? "›" : "‹"}
        </span>
        <span className="h-0.5 w-0.5 rounded-full bg-current opacity-60" aria-hidden />
      </button>

      {open ? (
        <ChatPanel
          id={panelId}
          sessionId={sessionId}
          initialMessages={initialMessages}
          chatTitle={chatTitle}
          greeting={greeting}
          inputPlaceholder={inputPlaceholder}
          inputLabel={inputLabel}
          sendLabel={sendLabel}
          streamFailedLabel={streamFailedLabel}
          userInitial={userInitial}
        />
      ) : (
        <div className="flex h-full flex-col items-center gap-4 py-4">
          <RobotHex px={28} />
          <span className="[writing-mode:vertical-rl] text-xs font-semibold tracking-wide text-text-muted">
            {chatTitle}
          </span>
          <span className="[writing-mode:vertical-rl] rounded-full bg-brand-soft px-0.5 py-1.5 text-xs font-semibold text-brand-text">
            {railBadge}
          </span>
        </div>
      )}
    </aside>
  );
}
