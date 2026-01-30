"use client";

import { FileUpload } from "@/components/demo/file-upload";
import {
  DocumentList,
  type IndexedDocument,
} from "@/components/demo/document-list";
import { type Source } from "@/lib/types";
import {
  Conversation,
  ConversationContent,
  ConversationEmptyState,
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
  PromptInputTextarea,
  PromptInputFooter,
  PromptInputSubmit,
} from "@/components/ai-elements/prompt-input";
import {
  Sources,
  SourcesTrigger,
  SourcesContent,
  Source as SourceItem,
} from "@/components/ai-elements/sources";
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
import { parseSSEEvents } from "@/lib/sse";
import {
  Bot,
  FileText,
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

/** Remove inline citations like [document_name, page 1] - sources are shown in Sources component */
function removeCitations(text: string): string {
  // Match patterns like [document_name, page 1] or [document_name, Page 1]
  return text.replace(/\s*\[[^\]]+,\s*[Pp]age\s*\d+\]/g, "").trim();
}

/** Format source title for display - makes document names more readable */
function formatSourceTitle(source: Source): string {
  // Convert kebab-case/snake_case to readable title and truncate if too long
  let name = source.documentName
    .replace(/[-_]/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());

  // Truncate long names
  if (name.length > 40) {
    name = name.slice(0, 37) + "...";
  }

  const page = source.pageNumber ? `, sivu ${source.pageNumber}` : "";
  return `${name}${page}`;
}

/** Deduplicate sources by document name + page number */
function deduplicateSources(sources: Source[]): Source[] {
  const seen = new Set<string>();
  return sources.filter((s) => {
    const key = `${s.documentName}-${s.pageNumber}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

/** Transforms API source format to local Source type */
function transformSources(
  apiSources: Array<{
    document_name: string;
    page_number: string | number | null;
    relevance_score?: number | null;
  }>,
): Source[] {
  return apiSources.map((s) => ({
    documentName: s.document_name,
    pageNumber: s.page_number,
    relevanceScore: s.relevance_score,
  }));
}

const STORAGE_KEYS = {
  collectionId: "rag-collection-id",
  indexedDocuments: "rag-indexed-documents",
} as const;

/** Reusable upload dialog content - used in both header and empty state */
interface UploadDialogContentProps {
  pendingFiles: File[];
  isIndexing: boolean;
  onFileSelect: (file: File) => void;
  onFileRemove: () => void;
  onIndex: () => void;
}

function UploadDialogContent({
  pendingFiles,
  isIndexing,
  onFileSelect,
  onFileRemove,
  onIndex,
}: UploadDialogContentProps) {
  return (
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
          maxSize={20}
          file={pendingFiles[0] || null}
          onFileSelect={onFileSelect}
          onFileRemove={onFileRemove}
          disabled={isIndexing}
        />
        {pendingFiles.length > 0 && (
          <Button onClick={onIndex} disabled={isIndexing} className="w-full">
            <Sparkles className="mr-2 h-4 w-4" />
            {isIndexing ? "Indexing..." : "Index Document"}
          </Button>
        )}
      </div>
    </DialogContent>
  );
}

/** Renders deduplicated sources with consistent formatting */
function SourcesList({ sources }: { sources: Source[] }) {
  const uniqueSources = deduplicateSources(sources);
  if (uniqueSources.length === 0) return null;

  return (
    <Sources>
      <SourcesTrigger count={uniqueSources.length} />
      <SourcesContent>
        {uniqueSources.map((source, i) => (
          <SourceItem key={i} title={formatSourceTitle(source)} />
        ))}
      </SourcesContent>
    </Sources>
  );
}

export default function RAGPage() {
  // Collection state
  const [collectionId, setCollectionId] = useState<string | null>(null);
  const [indexedDocuments, setIndexedDocuments] = useState<IndexedDocument[]>(
    [],
  );
  const [isHydrated, setIsHydrated] = useState(false);

  // Upload state
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [isIndexing, setIsIndexing] = useState(false);
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false);

  // Chat state
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isQuerying, setIsQuerying] = useState(false);
  const [streamingAnswer, setStreamingAnswer] = useState<string[]>([]);
  const [streamingSources, setStreamingSources] = useState<Source[]>([]);

  // Settings state
  const [topK, setTopK] = useState(5);
  const [searchType, setSearchType] = useState<"semantic" | "hybrid">(
    "semantic",
  );

  const abortControllerRef = useRef<AbortController | null>(null);

  // Load from localStorage on mount and verify collection exists
  useEffect(() => {
    const savedCollectionId = localStorage.getItem(STORAGE_KEYS.collectionId);
    const savedDocs = localStorage.getItem(STORAGE_KEYS.indexedDocuments);

    if (savedCollectionId) {
      // Verify collection still exists on backend
      fetch(`/api/rag/status/${savedCollectionId}`)
        .then((res) => {
          if (res.ok) {
            setCollectionId(savedCollectionId);
            if (savedDocs) {
              try {
                setIndexedDocuments(JSON.parse(savedDocs));
              } catch {
                // Invalid JSON, ignore
              }
            }
          } else {
            // Collection no longer exists, clear localStorage
            localStorage.removeItem(STORAGE_KEYS.collectionId);
            localStorage.removeItem(STORAGE_KEYS.indexedDocuments);
            toast("Previous session expired. Please upload documents again.");
          }
        })
        .catch(() => {
          // Backend unreachable, don't restore state
          localStorage.removeItem(STORAGE_KEYS.collectionId);
          localStorage.removeItem(STORAGE_KEYS.indexedDocuments);
        })
        .finally(() => {
          setIsHydrated(true);
        });
    } else {
      setIsHydrated(true);
    }
  }, []);

  // Save to localStorage when state changes
  useEffect(() => {
    if (!isHydrated) return;

    if (collectionId) {
      localStorage.setItem(STORAGE_KEYS.collectionId, collectionId);
    } else {
      localStorage.removeItem(STORAGE_KEYS.collectionId);
    }

    if (indexedDocuments.length > 0) {
      localStorage.setItem(
        STORAGE_KEYS.indexedDocuments,
        JSON.stringify(indexedDocuments),
      );
    } else {
      localStorage.removeItem(STORAGE_KEYS.indexedDocuments);
    }
  }, [collectionId, indexedDocuments, isHydrated]);

  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

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

  async function handleLoadExample(): Promise<void> {
    if (isIndexing) return;

    setIsIndexing(true);
    try {
      const response = await fetch("/api/rag/load-example", { method: "POST" });

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        throw new Error(errorData?.detail || "Failed to load example");
      }

      const data = await response.json();
      setCollectionId(data.collection_id);
      setIndexedDocuments(
        data.documents.map((doc: { filename: string; chunk_count: number; status: string }) => ({
          filename: doc.filename,
          chunkCount: doc.chunk_count,
          status: doc.status,
        })),
      );
      toast.success("Example document loaded! Try asking a question.");
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Failed to load example",
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
          if (event.type === "sources") {
            sources = transformSources(
              event.data.sources as unknown as Array<{
                document_name: string;
                page_number: string | number | null;
                relevance_score?: number | null;
              }>,
            );
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
              sources: transformSources(result.sources),
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
    } finally {
      setIsQuerying(false);
      setStreamingAnswer([]);
      setStreamingSources([]);
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
      className="flex h-[calc(100vh-12rem)] flex-col"
    >
      {/* Header */}
      <header className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Bot className="text-primary h-7 w-7" />
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
          {/* Document status badge - only show when documents exist */}
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

          {/* Upload button - only show when documents exist */}
          {hasDocuments && (
            <Dialog open={uploadDialogOpen} onOpenChange={setUploadDialogOpen}>
              <DialogTrigger asChild>
                <Button size="sm" className="gap-2">
                  <Plus className="h-4 w-4" />
                  Upload PDF
                </Button>
              </DialogTrigger>
              <UploadDialogContent
                pendingFiles={pendingFiles}
                isIndexing={isIndexing}
                onFileSelect={handleFileSelect}
                onFileRemove={handleFileRemove}
                onIndex={handleIndexDocuments}
              />
            </Dialog>
          )}

          {/* Settings */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="sm" className="gap-2">
                <Settings2 className="h-4 w-4" />
                Settings
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
      <Conversation className="flex-1 rounded-xl border bg-white">
        <ConversationContent className="p-4">
          {/* Empty state */}
          {messages.length === 0 && !isQuerying && (
            <>
              {hasDocuments ? (
                <ConversationEmptyState
                  title="Start a conversation"
                  description="Ask questions about your indexed documents and get AI-powered answers with citations."
                  icon={<MessageSquare className="h-8 w-8" />}
                />
              ) : (
                <Dialog
                  open={uploadDialogOpen}
                  onOpenChange={setUploadDialogOpen}
                >
                  <div className="flex h-full flex-col items-center justify-center py-16">
                    <div className="bg-primary/10 mb-6 rounded-full p-6">
                      <Upload className="text-primary h-12 w-12" />
                    </div>
                    <h2 className="mb-2 text-xl font-semibold">
                      Upload your documents
                    </h2>
                    <p className="text-muted-foreground mb-6 max-w-md text-center">
                      Upload PDF documents to get started. You can then ask
                      questions and get AI-powered answers with citations.
                    </p>
                    <div className="flex gap-3">
                      <DialogTrigger asChild>
                        <Button size="lg" className="gap-2">
                          <Plus className="h-5 w-5" />
                          Upload PDF
                        </Button>
                      </DialogTrigger>
                      <Button
                        size="lg"
                        variant="outline"
                        className="gap-2"
                        onClick={handleLoadExample}
                        disabled={isIndexing}
                      >
                        <Sparkles className="h-5 w-5" />
                        {isIndexing ? "Loading..." : "Try Example"}
                      </Button>
                    </div>
                  </div>
                  <UploadDialogContent
                    pendingFiles={pendingFiles}
                    isIndexing={isIndexing}
                    onFileSelect={handleFileSelect}
                    onFileRemove={handleFileRemove}
                    onIndex={handleIndexDocuments}
                  />
                </Dialog>
              )}
            </>
          )}

          {/* Messages */}
          {messages.map((message) => (
            <Message key={message.id} from={message.role}>
              <MessageContent>
                <MessageResponse>
                  {removeCitations(message.content)}
                </MessageResponse>
                {message.sources && <SourcesList sources={message.sources} />}
              </MessageContent>
            </Message>
          ))}

          {/* Streaming message */}
          {isQuerying && streamingAnswer.length > 0 && (
            <Message from="assistant">
              <MessageContent>
                <MessageResponse>
                  {removeCitations(streamingAnswer.join(""))}
                </MessageResponse>
                <SourcesList sources={streamingSources} />
              </MessageContent>
            </Message>
          )}

          {/* Loading indicator */}
          {isQuerying && streamingAnswer.length === 0 && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex gap-3"
            >
              <div className="bg-muted rounded-2xl px-4 py-3">
                <motion.span
                  animate={{ opacity: [0.5, 1, 0.5] }}
                  transition={{ duration: 1.5, repeat: Infinity }}
                  className="text-primary text-sm"
                >
                  Searching documents
                </motion.span>
              </div>
            </motion.div>
          )}
        </ConversationContent>
        <ConversationScrollButton />
      </Conversation>

      {/* Input area */}
      <PromptInput onSubmit={({ text }) => handleQuery(text)} className="mt-4">
        <PromptInputBody>
          <PromptInputTextarea
            placeholder={
              hasDocuments
                ? "Ask a question about your documents..."
                : "Upload documents first to start asking questions"
            }
            disabled={!hasDocuments}
          />
        </PromptInputBody>
        <PromptInputFooter>
          <div />
          <PromptInputSubmit
            status={isQuerying ? "streaming" : "ready"}
            disabled={!hasDocuments}
          />
        </PromptInputFooter>
      </PromptInput>
    </motion.div>
  );
}
