"use client";

import { useEffect, useRef, useState } from "react";
import type { ChatMessage, ChatRole } from "@/lib/mock-sessions";
import { RobotHex, UserAvatar } from "./robot-avatar";

function MessageRow({
  role,
  userInitial,
  children,
}: {
  role: ChatRole;
  userInitial: string;
  children: React.ReactNode;
}) {
  const isUser = role === "user";
  return (
    <div className={`flex items-end gap-2 ${isUser ? "flex-row-reverse" : ""}`}>
      {isUser ? <UserAvatar initial={userInitial} /> : <RobotHex px={28} />}
      <div
        className={`max-w-[82%] rounded-2xl px-3.5 py-2 text-[13px] leading-relaxed whitespace-pre-wrap shadow-xs ${
          isUser
            ? "bg-brand text-[#06231f] font-medium rounded-br-md"
            : "bg-surface/55 backdrop-blur-md text-text-secondary border border-white/10 rounded-bl-md"
        }`}
      >
        {children}
      </div>
    </div>
  );
}

export function ChatPanel({
  sessionId,
  initialMessages,
  chatTitle,
  greeting,
  inputPlaceholder,
  sendLabel,
  userInitial,
}: {
  sessionId: string;
  initialMessages: ChatMessage[];
  chatTitle: string;
  greeting: string;
  inputPlaceholder: string;
  sendLabel: string;
  userInitial: string;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);

  // Scroll to bottom when messages change (including during streaming).
  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [messages]);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || streaming) return;

    const ts = new Date().toISOString();
    const userId = crypto.randomUUID();
    const asstId = crypto.randomUUID();

    setInput("");
    setMessages((prev) => [
      ...prev,
      { id: userId, role: "user", content: text, createdAt: ts },
      { id: asstId, role: "assistant", content: "", createdAt: ts },
    ]);
    setStreaming(true);

    try {
      const res = await fetch(`/api/sessions/${sessionId}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
      });
      if (!res.ok || !res.body) throw new Error("stream failed");

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // SSE frames are separated by a blank line.
        const frames = buffer.split("\n\n");
        buffer = frames.pop() ?? "";
        for (const frame of frames) {
          const line = frame.startsWith("data: ") ? frame.slice(6) : frame;
          if (!line.trim()) continue;
          const evt = JSON.parse(line);
          if (evt.delta) {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === asstId ? { ...m, content: m.content + evt.delta } : m,
              ),
            );
          }
        }
      }
    } catch {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === asstId && !m.content
            ? { ...m, content: "⚠︎ Vastauksen striimaus epäonnistui." }
            : m,
        ),
      );
    } finally {
      setStreaming(false);
    }
  }

  return (
    <div className="flex flex-col h-full min-h-0">
      <h2 className="shrink-0 h-11 px-5 flex items-center gap-2 border-b border-border text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">
        <RobotHex px={22} />
        {chatTitle}
      </h2>

      <div ref={listRef} className="flex-1 overflow-auto px-4 py-4 space-y-3">
        {/* Greeting hero: hexagon robot image (transparent corners) */}
        <div className="flex flex-col items-center text-center gap-2.5 pt-1 pb-3">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/robot-hero.png"
            alt="GAIK Wizard -robotti"
            className="h-[124px] w-auto drop-shadow-[0_0_16px_rgba(214,184,120,0.3)]"
          />
          <div className="text-sm font-semibold text-text">GAIK Wizard</div>
        </div>

        {/* Persistent localized greeting (not stored in history) */}
        <MessageRow role="assistant" userInitial={userInitial}>
          {greeting}
        </MessageRow>

        {messages.map((m) => (
          <MessageRow key={m.id} role={m.role} userInitial={userInitial}>
            {m.content ||
              (streaming ? (
                <span className="text-brand animate-pulse">▍</span>
              ) : (
                ""
              ))}
          </MessageRow>
        ))}
      </div>

      <form
        onSubmit={send}
        className="shrink-0 flex items-end gap-2 px-4 py-3 border-t border-white/10 bg-surface/40 backdrop-blur-md"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          type="text"
          autoComplete="off"
          placeholder={inputPlaceholder}
          className="w-full rounded-md bg-surface-muted border border-border-strong px-3 py-2 text-sm text-text placeholder:text-text-muted shadow-xs transition-colors hover:border-text-muted focus:outline-none focus:border-brand"
        />
        <button
          type="submit"
          disabled={streaming || !input.trim()}
          className="inline-flex items-center justify-center gap-1.5 rounded-md bg-brand px-3 py-2 text-sm font-medium text-[#06231f] shadow-xs transition-colors hover:bg-brand-hover active:bg-brand-active disabled:opacity-40 disabled:cursor-not-allowed disabled:shadow-none"
        >
          {sendLabel}
        </button>
      </form>
    </div>
  );
}
