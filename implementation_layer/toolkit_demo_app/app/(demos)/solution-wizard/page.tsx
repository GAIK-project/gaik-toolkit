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
  PromptInputButton,
  PromptInputFooter,
  PromptInputHeader,
  PromptInputSubmit,
  PromptInputTextarea,
  usePromptInputAttachments,
} from "@/components/ai-elements/prompt-input";
import { Reasoning } from "@/components/ai-elements/reasoning";
import { Shimmer } from "@/components/ai-elements/shimmer";
import { PageTransition } from "@/components/demo/page-transition";
import { WizardFileBrowser } from "@/components/demo/wizard-file-browser";
import { WizardStartScreen } from "@/components/demo/wizard-start-screen";
import { deriveWizardStage, WizardProgress } from "@/components/demo/wizard-progress";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { apiFetch } from "@/lib/api-client";
import { processSSEStream, type SSEEvent } from "@/lib/sse";
import type { FileUIPart } from "ai";
import { Download, Loader2, Paperclip, RotateCcw, Wand2, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  /** Extended-thinking trace captured for this turn (assistant only). */
  reasoning?: string;
}

const nextId = () => crypto.randomUUID();

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

const MAX_ATTACHMENTS = 5;

const SUPPORTED_FORMATS = [
  { label: "Documents", exts: ".pdf .docx .txt .md" },
  { label: "Spreadsheets", exts: ".xlsx .xls .csv" },
  { label: "Images", exts: ".jpg .jpeg .png .webp .tiff .gif" },
  { label: "Audio / Video", exts: ".mp3 .mp4 .wav .m4a .ogg .webm .flac .mpeg" },
];

function AttachButton({ disabled }: { disabled: boolean }) {
  const { openFileDialog, files } = usePromptInputAttachments();
  const atLimit = files.length >= MAX_ATTACHMENTS;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <PromptInputButton
          aria-label="Attach file"
          disabled={disabled || atLimit}
          onClick={openFileDialog}
        >
          <Paperclip className="size-4" />
        </PromptInputButton>
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-56">
        {atLimit ? (
          <p>Maximum {MAX_ATTACHMENTS} attachments per message</p>
        ) : (
          <div className="space-y-1">
            <p className="font-medium">Attach files (max {MAX_ATTACHMENTS})</p>
            {SUPPORTED_FORMATS.map(({ label, exts }) => (
              <p key={label}>
                <span className="font-medium">{label}:</span> {exts}
              </p>
            ))}
          </div>
        )}
      </TooltipContent>
    </Tooltip>
  );
}

function AttachedFileChips() {
  const { files, remove } = usePromptInputAttachments();
  if (files.length === 0) return null;
  return (
    <PromptInputHeader>
      {files.map((f) => (
        <span
          key={f.id}
          className="bg-muted text-muted-foreground inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs"
        >
          {f.filename ?? "file"}
          <button
            type="button"
            aria-label={`Remove ${f.filename}`}
            className="hover:text-foreground ml-0.5"
            onClick={() => remove(f.id)}
          >
            <X className="size-3" />
          </button>
        </span>
      ))}
    </PromptInputHeader>
  );
}

export default function SolutionWizardPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streamingText, setStreamingText] = useState("");
  const [thinkingText, setThinkingText] = useState("");
  const [activity, setActivity] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [files, setFiles] = useState<string[]>([]);
  // Surfaced on the start screen with a retry, so a failed bootstrap does not
  // leave the user staring at a skeleton that never resolves.
  const [startError, setStartError] = useState<string | null>(null);

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

  // Finalize the live turn into a history message and clear the live buffers.
  // Appends only when there is assistant text; the buffers are always reset so
  // the next turn starts clean. (Activity is cleared by the callers.)
  const finalizeAssistantMessage = useCallback(() => {
    const text = streamRef.current.trim();
    const reasoning = thinkingRef.current.trim();
    if (text) {
      setMessages((prev) => [
        ...prev,
        { id: nextId(), role: "assistant", content: text, reasoning: reasoning || undefined },
      ]);
    }
    streamRef.current = "";
    thinkingRef.current = "";
    setStreamingText("");
    setThinkingText("");
  }, []);

  /** Consume one SSE turn: append deltas, show tool activity, finalize on done.
   *  `gen` is the generation id at call time; if genRef.current has moved on
   *  (Restart was clicked) all state mutations become no-ops. */
  const consumeTurn = useCallback(
    async (
      response: Response,
      gen: number,
      opts: { suppressReasoning?: boolean; suppressText?: boolean } = {},
    ) => {
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
            // The bootstrap turn's visible text is the wizard restating its
            // own intro. The start screen already says that, better, so it is
            // dropped rather than duplicated as the first chat bubble.
            if (opts.suppressText) return;
            streamRef.current += (event.data.text as string) ?? "";
            setStreamingText(streamRef.current);
            setActivity("");
          } else if (event.type === "thinking_delta") {
            // The startup turn's "thinking" is internal bootstrap (the agent
            // loading SKILL.md and reacting to the /solution-wizard prompt) —
            // never surface it. Real conversation turns keep their reasoning.
            if (opts.suppressReasoning) return;
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
            finalizeAssistantMessage();
            setActivity("");
          }
        },
      });

      if (genRef.current !== gen) return; // stale after stream closed
      // Flush partial text if the stream closed without an explicit done.
      finalizeAssistantMessage();
      setActivity("");
      const sid = sessionRef.current;
      if (sid) void refreshFiles(sid);
    },
    [finalizeAssistantMessage, refreshFiles],
  );

  const startSession = useCallback(async () => {
    const gen = genRef.current; // capture before any await
    setBusy(true);
    setFiles([]);
    // No injected welcome message: the start screen owns the introduction, so
    // an empty `messages` means "no conversation yet" and nothing in the chat
    // log is anything other than a real turn.
    setMessages([]);
    setStartError(null);
    try {
      const res = await apiFetch("/api/wizard/start", { method: "POST" });
      if (!res.ok) {
        const detail = await res.text();
        if (genRef.current === gen) setStartError(detail || `Request failed (${res.status}).`);
        toast.error(`Could not start the wizard: ${detail}`, { duration: 10000 });
        return;
      }
      await consumeTurn(res, gen, { suppressReasoning: true, suppressText: true });
    } catch (err) {
      const detail = err instanceof Error ? err.message : "Failed to start session";
      if (genRef.current === gen) {
        setStartError(detail);
        toast.error(detail);
      }
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
    async (text: string, attachedFiles: FileUIPart[] = []) => {
      const sid = sessionRef.current;
      if (!sid || busy || (!text.trim() && attachedFiles.length === 0)) return;
      const gen = genRef.current; // capture before any await
      const fileNames = attachedFiles.map((f) => f.filename ?? "file").join(", ");
      const userContent = attachedFiles.length
        ? text.trim()
          ? `${text}\n\n*Attached: ${fileNames}*`
          : `*Attached: ${fileNames}*`
        : text;
      setMessages((prev) => [
        ...prev,
        { id: nextId(), role: "user", content: userContent },
      ]);
      setBusy(true);
      try {
        const files = attachedFiles.map((f) => ({
          name: f.filename ?? "file",
          mime_type: f.mediaType ?? "application/octet-stream",
          data: f.url,
        }));
        const res = await apiFetch(`/api/wizard/message/${sid}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text, files }),
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

  const downloadConversation = useCallback((format: "md" | "txt") => {
    const date = new Date().toISOString().split("T")[0];
    const lines: string[] = [];
    if (format === "md") {
      lines.push("# GAIK Solution Configuration Wizard — Conversation", `*Exported: ${date}*`, "");
      for (const msg of messages) {
        lines.push("---", "");
        lines.push(`**${msg.role === "user" ? "User" : "Wizard"}**`, "");
        if (msg.reasoning) {
          lines.push("<details>", "<summary>Reasoning</summary>", "", msg.reasoning, "", "</details>", "");
        }
        lines.push(msg.content, "");
      }
    } else {
      lines.push("GAIK Solution Configuration Wizard — Conversation", `Exported: ${date}`, "");
      for (const msg of messages) {
        lines.push("---", `${msg.role === "user" ? "User" : "Wizard"}:`, "");
        if (msg.reasoning) {
          lines.push("[Reasoning]", msg.reasoning, "");
        }
        lines.push(msg.content, "");
      }
    }
    const blob = new Blob([lines.join("\n")], { type: format === "md" ? "text/markdown" : "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `wizard-conversation-${date}.${format}`;
    a.click();
    URL.revokeObjectURL(url);
  }, [messages]);

  const hasConversation = messages.length > 0;
  // Progress is read off the generated artifacts, so it advances on real work
  // rather than on how the wizard happens to word a turn.
  const stage = deriveWizardStage(files);

  // One composer instance, rendered either centered on the start screen or
  // pinned under the conversation.
  const composer = (
    <PromptInput
      accept=".txt,.md,.docx,.pdf,.csv,.xlsx,.xls,.jpg,.jpeg,.png,.webp,.tiff,.gif,.mp3,.mp4,.wav,.m4a,.ogg,.webm,.flac,.mpeg,.mpga"
      multiple
      onSubmit={({ text, files: attached }) => {
        if (text || attached.length > 0) void sendMessage(text, attached);
      }}
    >
      <AttachedFileChips />
      <PromptInputBody>
        <PromptInputTextarea
          className="min-h-11"
          placeholder={
            !sessionId
              ? "Connecting to the wizard…"
              : hasConversation
                ? "Reply to the wizard…"
                : "Describe your use case…"
          }
          disabled={!sessionId || busy}
        />
      </PromptInputBody>
      <PromptInputFooter>
        <AttachButton disabled={!sessionId || busy} />
        <PromptInputSubmit
          status={busy ? "streaming" : "ready"}
          disabled={!sessionId || busy}
        />
      </PromptInputFooter>
    </PromptInput>
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
            From a plain-language use case to a validated blueprint, workflow
            diagrams, docs, and a runnable PoC — streamed live.
          </p>
        </div>
        <div className="flex items-center gap-2">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="outline"
              size="sm"
              disabled={messages.length === 0}
            >
              <Download className="mr-1 h-4 w-4" />
              Download chat
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => downloadConversation("md")}>
              Download as .md
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => downloadConversation("txt")}>
              Download as .txt
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
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
      </div>

      <div className="grid h-[calc(100dvh-220px)] min-h-[420px] gap-4 lg:grid-cols-[1fr_320px]">
        {/* Chat column (bounded height so the conversation scrolls internally).
            min-w-0 is essential: without it this grid item's automatic minimum
            width equals its widest content (a long code line in a <pre>), which
            forces the 1fr track to grow and widens the whole chat for the rest
            of the session. min-w-0 lets the track stay fixed and the code block
            scroll horizontally inside the message instead. */}
        <div className="flex min-h-0 min-w-0 flex-col">
          {hasConversation && (
            <WizardProgress stage={stage} className="mb-3 px-1" />
          )}
          {!hasConversation ? (
            <div className="flex min-h-0 flex-1 rounded-xl border bg-white">
              <WizardStartScreen
                connecting={!sessionId || busy}
                disabled={!sessionId || busy}
                error={startError}
                onRetry={() => {
                  genRef.current += 1;
                  void startSession();
                }}
                onPickExample={(prompt) => void sendMessage(prompt)}
                composer={composer}
              />
            </div>
          ) : (
            <>
          <Conversation className="min-h-0 flex-1 rounded-xl border bg-white">
            <ConversationContent className="p-4">
              {messages.map((message) => (
                <Message key={message.id} from={message.role}>
                  <MessageContent>
                    {message.role === "assistant" && message.reasoning && (
                      <Reasoning>{message.reasoning}</Reasoning>
                    )}
                    <MessageResponse>{message.content}</MessageResponse>
                  </MessageContent>
                </Message>
              ))}

              {/* Live extended-thinking trace: open for the whole turn (so a long
                  wait shows progress) and capped + scrollable so it never shoves
                  the chat around. Finalized into the message on done. */}
              {thinkingText.length > 0 && (
                <Reasoning isStreaming={busy}>{thinkingText}</Reasoning>
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
              {busy &&
                !activity &&
                streamingText.length === 0 &&
                thinkingText.length === 0 && (
                  <Shimmer
                    color="var(--color-primary)"
                    shimmerColor="var(--color-primary-foreground)"
                    spread={4}
                    className="text-muted-foreground text-sm"
                  >
                    Thinking…
                  </Shimmer>
                )}
            </ConversationContent>
            <ConversationScrollButton />
          </Conversation>

              <div className="mt-2">{composer}</div>
            </>
          )}
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
