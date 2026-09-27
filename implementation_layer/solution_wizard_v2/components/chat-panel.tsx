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
        className={`max-w-[82%] rounded-2xl px-3.5 py-2 text-sm leading-relaxed whitespace-pre-wrap shadow-xs ${
          isUser
            ? "bg-brand text-on-brand font-medium rounded-br-md"
            : "bg-surface/55 backdrop-blur-md text-text-secondary border border-white/10 rounded-bl-md"
        }`}
      >
        {children}
      </div>
    </div>
  );
}

export function ChatPanel({
  id,
  sessionId,
  initialMessages,
  chatTitle,
  greeting,
  inputPlaceholder,
  inputLabel,
  sendLabel,
  streamFailedLabel,
  userInitial,
}: {
  id: string;
  sessionId: string;
  initialMessages: ChatMessage[];
  chatTitle: string;
  greeting: string;
  inputPlaceholder: string;
  inputLabel: string;
  sendLabel: string;
  streamFailedLabel: string;
  userInitial: string;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  const inputId = `${id}-input`;

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
            ? { ...m, content: `⚠︎ ${streamFailedLabel}` }
            : m,
        ),
      );
    } finally {
      setStreaming(false);
    }
  }

  return (
    <div id={id} className="flex flex-col h-full min-h-0">
      <h2 className="shrink-0 h-11 px-5 flex items-center gap-2 border-b border-border text-xs font-semibold uppercase tracking-wider text-text-muted">
        <RobotHex px={22} />
        {chatTitle}
      </h2>

      <div
        ref={listRef}
        aria-live="polite"
        aria-relevant="additions text"
        aria-label={chatTitle}
        className="flex-1 overflow-auto px-4 py-4 space-y-3"
      >
        <div className="flex flex-col items-center text-center gap-2.5 pt-1 pb-3">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/robot-hero.png"
            alt="GAIK Wizard robot"
            className="h-32 w-auto drop-shadow-[0_0_16px_rgba(214,184,120,0.3)]"
          />
          <div className="text-sm font-semibold text-text">GAIK Wizard</div>
        </div>

        <MessageRow role="assistant" userInitial={userInitial}>
          {greeting}
        </MessageRow>

        {messages.map((m) => (
          <MessageRow key={m.id} role={m.role} userInitial={userInitial}>
            {m.content ||
              (streaming ? <span className="stream-cursor">▍</span> : "")}
          </MessageRow>
        ))}
      </div>

      <form
        onSubmit={send}
        className="shrink-0 flex items-end gap-2 px-4 py-3 border-t border-white/10 bg-surface/40 backdrop-blur-md"
      >
        <label htmlFor={inputId} className="sr-only">
          {inputLabel}
        </label>
        <input
          id={inputId}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          type="text"
          autoComplete="off"
          placeholder={inputPlaceholder}
          className="input-field"
        />
        <button
          type="submit"
          disabled={streaming || !input.trim()}
          className="btn-brand px-3"
        >
          {sendLabel}
        </button>
      </form>
    </div>
  );
}
