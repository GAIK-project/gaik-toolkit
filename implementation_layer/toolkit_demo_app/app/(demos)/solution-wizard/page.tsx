"use client";

import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
} from "@/components/ai-elements/conversation";
import {
  Message,
  MessageContent,
  MessageResponse,
} from "@/components/ai-elements/message";
import {
  PromptInput,
  PromptInputBody,
  PromptInputFooter,
  PromptInputSubmit,
  PromptInputTextarea,
} from "@/components/ai-elements/prompt-input";
import { Reasoning } from "@/components/ai-elements/reasoning";
import { Shimmer } from "@/components/ai-elements/shimmer";
import { PageTransition } from "@/components/demo/page-transition";
import { WizardFileBrowser } from "@/components/demo/wizard-file-browser";
import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api-client";
import { processSSEStream, type SSEEvent } from "@/lib/sse";
import { Loader2, RotateCcw, Wand2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
}

let messageCounter = 0;
const nextId = () => `m${++messageCounter}`;

/**
 * Translate a raw tool invocation into a friendly, user-facing progress label.
 * The internal command details (script paths, file edits) are noise for an
 * end user, so we surface the *phase* of work instead.
 */
function friendlyActivity(name: string, summary: string): string {
  const text = `${name} ${summary}`.toLowerCase();
  if (text.includes("check_requirements")) return "Checking requirement completeness…";
  if (text.includes("validate_blueprint")) return "Validating the blueprint…";
  if (text.includes("generate_bpmn")) return "Generating the BPMN diagram…";
  if (text.includes("generate_mermaid")) return "Generating the workflow diagram…";
  if (text.includes("generate_docs")) return "Writing the documentation…";
  if (text.includes("generate_schema")) return "Designing the extraction schema…";
  if (text.includes("scaffold_poc")) return "Scaffolding the proof of concept…";
  if (text.includes("run_poc") || text.includes("requirements.txt"))
    return "Preparing the package…";
  if (text.includes("skill.md")) return "Loading wizard instructions…";
  if (name === "Write" || name === "Edit") return "Updating generated files…";
  if (name === "Read" || name === "Grep" || name === "Glob") return "Preparing…";
  if (name === "Bash") return "Running a configuration step…";
  return "Working…";
}

export default function SolutionWizardPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streamingText, setStreamingText] = useState("");
  const [thinkingText, setThinkingText] = useState("");
  const [activity, setActivity] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [files, setFiles] = useState<string[]>([]);

  const sessionRef = useRef<string | null>(null);
  const streamRef = useRef("");
  const thinkingRef = useRef("");
  const startedRef = useRef(false);
  // Incremented on every restart so stale consumeTurn callbacks from the
  // previous session become no-ops and cannot pollute the new session's state.
  const genRef = useRef(0);

  // Keep a ref in sync so the unmount handler sees the latest id.
  useEffect(() => {
    sessionRef.current = sessionId;
  }, [sessionId]);

  const refreshFiles = useCallback(async (sid: string) => {
    try {
      const res = await apiFetch(`/api/wizard/files/${sid}`);
      if (res.ok) {
        const data = (await res.json()) as { files: string[] };
        setFiles(data.files ?? []);
      }
    } catch {
      /* non-fatal */
    }
  }, []);

  /** Consume one SSE turn: append deltas, show tool activity, finalize on done.
   *  `gen` is the generation id at call time; if genRef.current has moved on
   *  (Restart was clicked) all state mutations become no-ops. */
  const consumeTurn = useCallback(
    async (response: Response, gen: number) => {
      streamRef.current = "";
      thinkingRef.current = "";
      setStreamingText("");
      setThinkingText("");
      setActivity("");

      await processSSEStream(response, {
        onError: (message) => {
          if (genRef.current !== gen) return;
          toast.error(message, { duration: 8000 });
        },
        onCustomEvent: (event: SSEEvent) => {
          if (genRef.current !== gen) return; // stale — Restart was clicked
          if (event.type === "session") {
            const sid = event.data.session_id as string;
            setSessionId(sid);
            sessionRef.current = sid;
          } else if (event.type === "text_delta") {
            streamRef.current += (event.data.text as string) ?? "";
            setStreamingText(streamRef.current);
            setActivity("");
          } else if (event.type === "thinking_delta") {
            thinkingRef.current += (event.data.text as string) ?? "";
            setThinkingText(thinkingRef.current);
          } else if (event.type === "tool_use") {
            const name = event.data.name as string;
            const summary = (event.data.summary as string) ?? "";
            setActivity(friendlyActivity(name, summary));
            // Generated files appear mid-turn; refresh the browser as the
            // wizard writes them instead of waiting for the turn to finish.
            if (
              (name === "Write" || name === "Edit" || name === "Bash") &&
              sessionRef.current
            ) {
              void refreshFiles(sessionRef.current);
            }
          } else if (event.type === "done") {
            const text = streamRef.current.trim();
            if (text) {
              setMessages((prev) => [
                ...prev,
                { id: nextId(), role: "assistant", content: text },
              ]);
            }
            streamRef.current = "";
            setStreamingText("");
            setActivity("");
          }
        },
      });

      if (genRef.current !== gen) return; // stale after stream closed
      // Flush partial text if stream closed without an explicit done.
      if (streamRef.current.trim()) {
        const text = streamRef.current.trim();
        setMessages((prev) => [
          ...prev,
          { id: nextId(), role: "assistant", content: text },
        ]);
        streamRef.current = "";
        setStreamingText("");
      }
      setActivity("");
      const sid = sessionRef.current;
      if (sid) void refreshFiles(sid);
    },
    [refreshFiles],
  );

  const startSession = useCallback(async () => {
    const gen = genRef.current; // capture before any await
    setBusy(true);
    setFiles([]);
    // Show a helpful welcome immediately so the user isn't staring at a blank
    // loading state. The backend's real greeting streams in right after.
    setMessages([
      {
        id: nextId(),
        role: "assistant",
        content: [
          "## Welcome to the GAIK Solution Configuration Wizard",
          "",
          "I'll guide you from your business idea to a fully validated **GenAI solution** — including a blueprint, BPMN workflow diagram, documentation, and a runnable proof of concept.",
          "",
          "**To get started, describe your use case in plain language.** For example:",
          '- *"We receive voice recordings from field technicians and turn them into structured maintenance tickets."*',
          '- *"We need to extract key fields from incoming supplier PDF invoices."*',
          '- *"We want a Q&A assistant over our internal policy documents."*',
          "",
          "Give as much or as little context as you like — I'll ask follow-up questions to fill in the details.",
        ].join("\n"),
      },
    ]);
    try {
      const res = await apiFetch("/api/wizard/start", { method: "POST" });
      if (!res.ok) {
        const detail = await res.text();
        toast.error(`Could not start the wizard: ${detail}`, { duration: 10000 });
        return;
      }
      await consumeTurn(res, gen);
    } catch (err) {
      if (genRef.current === gen)
        toast.error(err instanceof Error ? err.message : "Failed to start session");
    } finally {
      if (genRef.current === gen) setBusy(false);
    }
  }, [consumeTurn]);

  // Start a session on mount (guard against React strict-mode double-invoke).
  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    void startSession();
  }, [startSession]);

  // End the session when leaving the page.
  useEffect(() => {
    return () => {
      const sid = sessionRef.current;
      if (sid) {
        // keepalive so the request survives navigation/unload.
        void fetch(`/api/wizard/end/${sid}`, { method: "DELETE", keepalive: true });
      }
    };
  }, []);

  const sendMessage = useCallback(
    async (text: string) => {
      const sid = sessionRef.current;
      if (!sid || busy || !text.trim()) return;
      const gen = genRef.current; // capture before any await
      setMessages((prev) => [
        ...prev,
        { id: nextId(), role: "user", content: text },
      ]);
      setBusy(true);
      try {
        const res = await apiFetch(`/api/wizard/message/${sid}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text }),
        });
        if (!res.ok) {
          const detail = await res.text();
          if (genRef.current === gen)
            toast.error(`Message failed: ${detail}`, { duration: 8000 });
          return;
        }
        await consumeTurn(res, gen);
      } catch (err) {
        if (genRef.current === gen)
          toast.error(err instanceof Error ? err.message : "Message failed");
      } finally {
        if (genRef.current === gen) setBusy(false);
      }
    },
    [busy, consumeTurn],
  );

  return (
    <PageTransition>
      {/* Break out of the layout's max-w-6xl: the chat + file browser benefit
          from extra width on large screens. Centered on the viewport (the
          parent container is itself centered), capped at 1400px. */}
      <div className="relative left-1/2 w-[min(100vw-3rem,87.5rem)] -translate-x-1/2">
      <div className="mb-4 flex items-center justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold">
            <Wand2 className="h-6 w-6 text-primary" />
            Solution Configuration Wizard
          </h1>
          <p className="text-muted-foreground mt-1 text-sm">
            Describe your use case in plain language. The wizard collects
            requirements, selects GAIK components, and generates a validated
            blueprint, workflow diagrams, and documentation — streamed live.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            // 1. Invalidate any in-flight consumeTurn from the old session so
            //    it cannot overwrite the state we're about to reset.
            genRef.current += 1;
            // 2. End the old backend session (best-effort, fire-and-forget).
            const sid = sessionRef.current;
            if (sid)
              void fetch(`/api/wizard/end/${sid}`, { method: "DELETE", keepalive: true });
            // 3. Reset ALL visible state synchronously — the user sees a clean
            //    slate immediately, before the new session even starts.
            sessionRef.current = null;
            setSessionId(null);
            setMessages([]);
            setFiles([]);
            setStreamingText("");
            setThinkingText("");
            setActivity("");
            setBusy(false);
            streamRef.current = "";
            thinkingRef.current = "";
            // 4. Start a new session (startSession reads genRef.current internally).
            startedRef.current = false;
            void startSession().then(() => { startedRef.current = true; });
          }}
          disabled={busy}
        >
          <RotateCcw className="mr-1 h-4 w-4" />
          Restart
        </Button>
      </div>

      <div className="grid h-[calc(100dvh-220px)] min-h-[420px] gap-4 lg:grid-cols-[1fr_320px]">
        {/* Chat column (bounded height so the conversation scrolls internally).
            min-w-0 is essential: without it this grid item's automatic minimum
            width equals its widest content (a long code line in a <pre>), which
            forces the 1fr track to grow and widens the whole chat for the rest
            of the session. min-w-0 lets the track stay fixed and the code block
            scroll horizontally inside the message instead. */}
        <div className="flex min-h-0 min-w-0 flex-col">
          <Conversation className="min-h-0 flex-1 rounded-xl border bg-white">
            <ConversationContent className="p-4">
              {messages.map((message) => (
                <Message key={message.id} from={message.role}>
                  <MessageContent>
                    <MessageResponse>{message.content}</MessageResponse>
                  </MessageContent>
                </Message>
              ))}

              {/* Extended-thinking trace (collapsible, opt-in to read) */}
              {thinkingText.length > 0 && (
                <Reasoning
                  isStreaming={busy && streamingText.length === 0}
                >
                  {thinkingText}
                </Reasoning>
              )}

              {/* Live streaming assistant message */}
              {streamingText.length > 0 && (
                <Message from="assistant">
                  <MessageContent>
                    <MessageResponse>{streamingText}</MessageResponse>
                  </MessageContent>
                </Message>
              )}

              {/* Progress indicator: friendly phase label while a tool runs,
                  shimmer while waiting for the next tokens. */}
              {busy && activity && (
                <div className="text-muted-foreground flex items-center gap-2 text-sm">
                  <Loader2 className="text-primary h-4 w-4 animate-spin" />
                  <span>{activity}</span>
                </div>
              )}
              {busy && !activity && streamingText.length === 0 && (
                <div className="bg-muted w-fit rounded-2xl px-4 py-3">
                  <Shimmer
                    color="var(--color-primary)"
                    shimmerColor="var(--color-primary-foreground)"
                    spread={4}
                    className="text-sm"
                  >
                    Thinking…
                  </Shimmer>
                </div>
              )}
            </ConversationContent>
            <ConversationScrollButton />
          </Conversation>

          <PromptInput
            onSubmit={({ text }) => {
              if (text) void sendMessage(text);
            }}
            className="mt-2"
          >
            <PromptInputBody>
              <PromptInputTextarea
                placeholder={
                  sessionId
                    ? "Reply to the wizard…"
                    : "Connecting to the wizard…"
                }
                disabled={!sessionId || busy}
              />
            </PromptInputBody>
            <PromptInputFooter>
              <div />
              <PromptInputSubmit
                status={busy ? "streaming" : "ready"}
                disabled={!sessionId || busy}
              />
            </PromptInputFooter>
          </PromptInput>
        </div>

        {/* Generated files browser */}
        <aside className="min-h-0 overflow-hidden rounded-xl border bg-white p-4">
          <WizardFileBrowser files={files} sessionId={sessionId} />
        </aside>
      </div>
      </div>
    </PageTransition>
  );
}
