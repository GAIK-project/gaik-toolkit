"use client";

import { FileUpload } from "@/components/demo/file-upload";
import {
  DocumentList,
  type IndexedDocument,
} from "@/components/demo/document-list";
import { type Source } from "@/lib/types";
import {
  ChatMessage as ChatMessageBubble,
  StreamingMessage,
} from "@/components/demo/chat-message";
import { ChatInput } from "@/components/demo/chat-input";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { parseSSEEvents, type SSEStep } from "@/lib/sse";
import {
  FileText,
  Library,
  Loader2,
  MessageSquare,
  Plus,
  Settings2,
  Sparkles,
  Trash2,
  Upload,
} from "lucide-react";
import { motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  timestamp: Date;
}

export default function RAGPage() {
  // Collection state
  const [collectionId, setCollectionId] = useState<string | null>(null);
  const [indexedDocuments, setIndexedDocuments] = useState<IndexedDocument[]>(
    [],
  );

  // Upload state
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [isIndexing, setIsIndexing] = useState(false);
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false);

  // Chat state
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isQuerying, setIsQuerying] = useState(false);
  const [streamingAnswer, setStreamingAnswer] = useState<string[]>([]);
  const [streamingSources, setStreamingSources] = useState<Source[]>([]);
  const [querySteps, setQuerySteps] = useState<SSEStep[]>([]);

  // Settings state
  const [topK, setTopK] = useState(5);
  const [searchType, setSearchType] = useState<"semantic" | "hybrid">(
    "semantic",
  );

  const abortControllerRef = useRef<AbortController | null>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop =
        chatContainerRef.current.scrollHeight;
    }
  }, [messages, streamingAnswer]);

  const indexedCount = indexedDocuments.filter(
    (d) => d.status === "indexed",
  ).length;
  const hasDocuments = indexedCount > 0;

  function handleFileSelect(file: File): void {
    if (!pendingFiles.some((f) => f.name === file.name)) {
      setPendingFiles([...pendingFiles, file]);
    }
  }

  function handleFileRemove(): void {
    setPendingFiles([]);
  }

  async function handleIndexDocuments(): Promise<void> {
    if (pendingFiles.length === 0 || isIndexing) return;

    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();

    setIsIndexing(true);

    const processingDocs: IndexedDocument[] = pendingFiles.map((f) => ({
      filename: f.name,
      chunkCount: 0,
      status: "processing" as const,
    }));
    setIndexedDocuments([...indexedDocuments, ...processingDocs]);

    try {
      const formData = new FormData();
      pendingFiles.forEach((file) => {
        formData.append("files", file);
      });
      if (collectionId) {
        formData.append("collection_id", collectionId);
      }

      const response = await fetch("/api/rag/index", {
        method: "POST",
        body: formData,
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        throw new Error(errorData?.detail || "Failed to index documents");
      }

      const data = await response.json();

      setCollectionId(data.collection_id);

      const updatedDocs = [
        ...indexedDocuments.filter((d) => d.status === "indexed"),
      ];
      for (const doc of data.documents) {
        updatedDocs.push({
          filename: doc.filename,
          chunkCount: doc.chunk_count,
          status: doc.status,
        });
      }
      setIndexedDocuments(updatedDocs);
      setPendingFiles([]);
      setUploadDialogOpen(false);

      if (data.status === "success") {
        toast.success(
          `Indexed ${data.document_count} document(s) with ${data.chunk_count} chunks`,
        );
      } else {
        toast.error("Some documents failed to index");
      }
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") return;
      toast.error(
        error instanceof Error ? error.message : "Failed to index documents",
      );

      setIndexedDocuments(
        indexedDocuments.map((d) =>
          d.status === "processing" ? { ...d, status: "error" as const } : d,
        ),
      );
    } finally {
      setIsIndexing(false);
    }
  }

  async function handleQuery(question: string): Promise<void> {
    if (!question.trim() || !collectionId || isQuerying) return;

    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();

    // Add user message
    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: question,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMessage]);

    setIsQuerying(true);
    setStreamingAnswer([]);
    setStreamingSources([]);
    setQuerySteps([
      { step: 1, name: "Searching documents", status: "in_progress" },
      { step: 2, name: "Generating answer", status: "pending" },
    ]);

    try {
      const formData = new FormData();
      formData.append("question", question);
      formData.append("collection_id", collectionId);
      formData.append("top_k", String(topK));
      formData.append("search_type", searchType);

      const response = await fetch("/api/rag/query/stream", {
        method: "POST",
        body: formData,
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        throw new Error(errorData?.detail || "Failed to query");
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error("No response body");

      const decoder = new TextDecoder();
      let buffer = "";
      let sources: Source[] = [];

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const events = parseSSEEvents(buffer);

        for (const event of events) {
          if (event.type === "steps") {
            setQuerySteps(event.data.steps as unknown as SSEStep[]);
          } else if (event.type === "step_update") {
            const update = event.data as unknown as SSEStep;
            setQuerySteps((prev) =>
              prev.map((s) => (s.step === update.step ? update : s)),
            );
          } else if (event.type === "sources") {
            sources = (
              event.data.sources as unknown as Array<{
                document_name: string;
                page_number: string | number | null;
                relevance_score?: number | null;
              }>
            ).map((s) => ({
              documentName: s.document_name,
              pageNumber: s.page_number,
              relevanceScore: s.relevance_score,
            }));
            setStreamingSources(sources);
          } else if (event.type === "answer_chunk") {
            const chunk = event.data.chunk as string;
            setStreamingAnswer((prev) => [...prev, chunk]);
          } else if (event.type === "result") {
            const result = event.data as {
              answer: string;
              sources: Array<{
                document_name: string;
                page_number: string | number | null;
                relevance_score?: number | null;
              }>;
            };

            // Add assistant message
            const assistantMessage: ChatMessage = {
              id: `assistant-${Date.now()}`,
              role: "assistant",
              content: result.answer,
              sources: result.sources.map((s) => ({
                documentName: s.document_name,
                pageNumber: s.page_number,
                relevanceScore: s.relevance_score,
              })),
              timestamp: new Date(),
            };
            setMessages((prev) => [...prev, assistantMessage]);
          } else if (event.type === "error") {
            throw new Error((event.data.message as string) || "Query failed");
          }
        }

        const lastEventEnd = buffer.lastIndexOf("\n\n");
        if (lastEventEnd !== -1) {
          buffer = buffer.slice(lastEventEnd + 2);
        }
      }
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") return;
      toast.error(error instanceof Error ? error.message : "Query failed");
      setQuerySteps((prev) =>
        prev.map((s) =>
          s.status === "in_progress"
            ? { ...s, status: "error", message: "Failed" }
            : s,
        ),
      );
    } finally {
      setIsQuerying(false);
      setStreamingAnswer([]);
      setStreamingSources([]);
      setQuerySteps([]);
    }
  }

  async function handleClearCollection(): Promise<void> {
    if (!collectionId) return;

    try {
      await fetch(`/api/rag/clear/${collectionId}`, { method: "DELETE" });
      setCollectionId(null);
      setIndexedDocuments([]);
      setMessages([]);
      toast.success("Collection cleared");
    } catch {
      toast.error("Failed to clear collection");
    }
  }

  function handleRemoveDocument(filename: string): void {
    setIndexedDocuments(
      indexedDocuments.filter((d) => d.filename !== filename),
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="flex h-[calc(100vh-8rem)] flex-col"
    >
      {/* Header */}
      <header className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Library className="text-primary h-7 w-7" />
          <div>
            <h1 className="font-serif text-2xl font-semibold tracking-tight">
              RAG Builder
            </h1>
            <p className="text-muted-foreground text-sm">
              Ask questions about your documents
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Document status badge */}
          {hasDocuments && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="sm" className="gap-2">
                  <FileText className="h-4 w-4" />
                  {indexedCount} doc{indexedCount !== 1 ? "s" : ""} indexed
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-72">
                <div className="p-2">
                  <DocumentList
                    documents={indexedDocuments}
                    onRemove={handleRemoveDocument}
                    className="max-h-48 overflow-auto"
                  />
                </div>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onClick={handleClearCollection}
                  className="text-destructive focus:text-destructive"
                >
                  <Trash2 className="mr-2 h-4 w-4" />
                  Clear all documents
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}

          {/* Upload button */}
          <Dialog open={uploadDialogOpen} onOpenChange={setUploadDialogOpen}>
            <DialogTrigger asChild>
              <Button size="sm" className="gap-2">
                <Plus className="h-4 w-4" />
                Upload PDF
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2">
                  <Upload className="h-5 w-5" />
                  Upload Documents
                </DialogTitle>
              </DialogHeader>
              <div className="space-y-4 pt-4">
                <FileUpload
                  accept=".pdf"
                  maxSize={50}
                  file={pendingFiles[0] || null}
                  onFileSelect={handleFileSelect}
                  onFileRemove={handleFileRemove}
                  disabled={isIndexing}
                />

                {pendingFiles.length > 0 && (
                  <Button
                    onClick={handleIndexDocuments}
                    disabled={isIndexing}
                    className="w-full"
                  >
                    <Sparkles className="mr-2 h-4 w-4" />
                    {isIndexing ? "Indexing..." : "Index Document"}
                  </Button>
                )}
              </div>
            </DialogContent>
          </Dialog>

          {/* Settings */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon">
                <Settings2 className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
              <div className="space-y-4 p-3">
                <div className="space-y-2">
                  <Label htmlFor="topK" className="text-xs">
                    Results (Top K)
                  </Label>
                  <Select
                    value={String(topK)}
                    onValueChange={(v) => setTopK(Number(v))}
                  >
                    <SelectTrigger id="topK" className="h-8">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="3">3 chunks</SelectItem>
                      <SelectItem value="5">5 chunks</SelectItem>
                      <SelectItem value="10">10 chunks</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="searchType" className="text-xs">
                    Search Type
                  </Label>
                  <Select
                    value={searchType}
                    onValueChange={(v) =>
                      setSearchType(v as "semantic" | "hybrid")
                    }
                  >
                    <SelectTrigger id="searchType" className="h-8">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="semantic">Semantic</SelectItem>
                      <SelectItem value="hybrid">Hybrid</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <p className="text-muted-foreground text-xs">
                  {searchType === "semantic"
                    ? "Uses vector similarity"
                    : "Combines vectors + keywords"}
                </p>
              </div>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </header>

      {/* Chat area */}
      <div
        ref={chatContainerRef}
        className="bg-muted/20 flex-1 overflow-auto rounded-xl border p-4"
      >
        {/* Empty state */}
        {messages.length === 0 && !isQuerying && (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <div className="bg-muted mb-4 rounded-full p-4">
              <MessageSquare className="text-muted-foreground h-8 w-8" />
            </div>
            <h3 className="text-lg font-medium">Start a conversation</h3>
            <p className="text-muted-foreground mt-1 max-w-sm text-sm">
              {hasDocuments
                ? "Ask questions about your indexed documents and get AI-powered answers with citations."
                : "Upload PDF documents first, then ask questions to get AI-powered answers."}
            </p>
            {!hasDocuments && (
              <Button
                onClick={() => setUploadDialogOpen(true)}
                className="mt-4 gap-2"
              >
                <Upload className="h-4 w-4" />
                Upload your first document
              </Button>
            )}
          </div>
        )}

        {/* Messages */}
        <div className="space-y-4">
          {messages.map((message) => (
            <ChatMessageBubble
              key={message.id}
              role={message.role}
              content={message.content}
              sources={message.sources}
            />
          ))}

          {/* Streaming message */}
          {isQuerying && streamingAnswer.length > 0 && (
            <StreamingMessage
              chunks={streamingAnswer}
              sources={streamingSources}
            />
          )}

          {/* Loading indicator */}
          {isQuerying && streamingAnswer.length === 0 && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex gap-3"
            >
              <div className="bg-muted text-muted-foreground flex h-8 w-8 shrink-0 items-center justify-center rounded-full">
                <Loader2 className="h-4 w-4 animate-spin" />
              </div>
              <div className="bg-muted rounded-2xl px-4 py-3">
                <div className="space-y-2">
                  {querySteps.map((step) => (
                    <div
                      key={step.step}
                      className={cn(
                        "flex items-center gap-2 text-sm",
                        step.status === "completed" && "text-green-600",
                        step.status === "in_progress" && "text-primary",
                        step.status === "error" && "text-destructive",
                      )}
                    >
                      {step.status === "in_progress" && (
                        <Loader2 className="h-3 w-3 animate-spin" />
                      )}
                      <span>{step.name}</span>
                      {step.message && (
                        <span className="text-muted-foreground text-xs">
                          ({step.message})
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </motion.div>
          )}
        </div>
      </div>

      {/* Input area */}
      <div className="mt-4">
        <ChatInput
          onSubmit={handleQuery}
          disabled={!hasDocuments}
          isLoading={isQuerying}
          placeholder={
            hasDocuments
              ? "Ask a question about your documents..."
              : "Upload documents first to start asking questions"
          }
        />
      </div>
    </motion.div>
  );
}
