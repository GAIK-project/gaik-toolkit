"use client";

import { apiFetch, RateLimitError } from "@/lib/api-client";
import { ExamplePreviewDialog } from "@/components/demo/example-preview-dialog";
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
  ArrowLeft,
  Bot,
  FileText,
  MessageSquare,
  Plus,
  Settings2,
  Sparkles,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { FeedbackButton } from "@/components/feedback";
import { Shimmer } from "@/components/ai-elements/shimmer";
import { motion } from "motion/react";
import { useRouter } from "next/navigation";
import posthog from "posthog-js";
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
  // Match any bracketed citation containing document name and page references
  // Handles: [doc, page 1], [doc, page 5-6], [doc, page 3; page 5], [doc, pages 1-3]
  return text.replace(/\s*\[[^\]]+,\s*[Pp]ages?\s*[^\]]+\]/g, "").trim();
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

  const page = source.pageNumber ? `, page ${source.pageNumber}` : "";
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
  onFilesSelect: (files: File[]) => void;
  onFileRemove: (filename: string) => void;
  onIndex: () => void;
}

function UploadDialogContent({
  pendingFiles,
  isIndexing,
  onFilesSelect,
  onFileRemove,
  onIndex,
}: UploadDialogContentProps) {
  function handleInputChange(event: React.ChangeEvent<HTMLInputElement>): void {
    const selected = Array.from(event.target.files || []).filter(
      (file) => file.name.toLowerCase().endsWith(".pdf"),
    );
    if (selected.length > 0) {
      onFilesSelect(selected);
    }
    event.target.value = "";
  }

  return (
    <DialogContent>
      <DialogHeader>
        <DialogTitle className="flex items-center gap-2">
          <Upload className="h-5 w-5" />
          Upload Documents
        </DialogTitle>
      </DialogHeader>
      <div className="space-y-4 pt-4">
        <label className="flex min-h-[176px] cursor-pointer flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed border-muted-foreground/25 p-8 transition-all hover:border-primary/50 hover:bg-muted/50">
          <Upload className="text-muted-foreground h-10 w-10" />
          <div className="text-center">
            <p className="font-medium">Click to upload PDFs</p>
            <p className="text-muted-foreground mt-1 text-sm">Supports multiple PDF files (max 20MB each)</p>
          </div>
          <input
            type="file"
            accept=".pdf"
            multiple
            onChange={handleInputChange}
            disabled={isIndexing}
            className="sr-only"
          />
        </label>
        {pendingFiles.length > 0 && (
          <div className="space-y-2 rounded-lg border p-3">
            <p className="text-sm font-medium">Pending files</p>
            <div className="space-y-2">
              {pendingFiles.map((file) => (
                <div key={`${file.name}-${file.size}`} className="flex items-center justify-between gap-3 rounded-md bg-muted/50 px-3 py-2 text-sm">
                  <span className="truncate">{file.name}</span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7"
                    onClick={() => onFileRemove(file.name)}
                    disabled={isIndexing}
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              ))}
            </div>
          </div>
        )}
        {pendingFiles.length > 0 && (
          <Button onClick={onIndex} disabled={isIndexing} className="w-full">
            <Sparkles className="mr-2 h-4 w-4" />
            {isIndexing ? (
              <Shimmer className="text-inherit">{`Indexing ${pendingFiles.length} document(s)...`}</Shimmer>
            ) : (
              `Index ${pendingFiles.length} Document${pendingFiles.length !== 1 ? "s" : ""}`
            )}
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
  const router = useRouter();
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
  const [howItWorksOpen, setHowItWorksOpen] = useState(false);

  // Settings state
  const [topK, setTopK] = useState(5);
  const [searchType, setSearchType] = useState<"semantic" | "hybrid">(
    "semantic",
  );
  const parserChoice = "docling_rag";

  const abortControllerRef = useRef<AbortController | null>(null);

  // Load from localStorage on mount and verify collection exists
  useEffect(() => {
    const savedCollectionId = localStorage.getItem(STORAGE_KEYS.collectionId);
    const savedDocs = localStorage.getItem(STORAGE_KEYS.indexedDocuments);

    if (savedCollectionId) {
      // Verify collection still exists on backend
      fetch(`/api/rag/status/${savedCollectionId}`)
        .then(async (res) => {
          if (res.ok) {
            const status = await res.json();
            if (status.is_ready) {
              setCollectionId(savedCollectionId);
              if (savedDocs) {
                try {
                  setIndexedDocuments(JSON.parse(savedDocs));
                } catch {
                  // Invalid JSON, ignore
                }
              }
            } else {
              // Collection no longer in backend memory (server restarted)
              localStorage.removeItem(STORAGE_KEYS.collectionId);
              localStorage.removeItem(STORAGE_KEYS.indexedDocuments);
              toast("Previous session expired. Please upload documents again.");
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

  function handleFilesSelect(files: File[]): void {
    setPendingFiles((current) => {
      const existing = new Set(current.map((file) => `${file.name}-${file.size}`));
      const additions = files.filter((file) => !existing.has(`${file.name}-${file.size}`));
      return [...current, ...additions];
    });
  }

  function handleFileRemove(filename: string): void {
    setPendingFiles((current) => current.filter((file) => file.name !== filename));
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
      formData.append("parser_choice", parserChoice);

      const response = await apiFetch("/api/rag/index", {
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
      if (error instanceof RateLimitError) return; // Toast already shown
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
      const formData = new FormData();
      formData.append("parser_choice", parserChoice);

      const response = await apiFetch("/api/rag/load-example", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        throw new Error(errorData?.detail || "Failed to load example");
      }

      const data = await response.json();
      setCollectionId(data.collection_id);
      setIndexedDocuments(
        data.documents.map(
          (doc: { filename: string; chunk_count: number; status: string }) => ({
            filename: doc.filename,
            chunkCount: doc.chunk_count,
            status: doc.status,
          }),
        ),
      );
      toast.success("Example document loaded! Try asking a question.");
    } catch (error) {
      if (error instanceof RateLimitError) return; // Toast already shown
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

    posthog.capture("rag_query_sent", {
      query_length: question.length,
      has_documents: hasDocuments,
      document_count: indexedCount,
      search_type: searchType,
      top_k: topK,
    });

    setIsQuerying(true);
    setStreamingAnswer([]);
    setStreamingSources([]);

    try {
      const formData = new FormData();
      formData.append("question", question);
      formData.append("collection_id", collectionId);
      formData.append("top_k", String(topK));
      formData.append("search_type", searchType);

      const response = await apiFetch("/api/rag/query/stream", {
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
        const { events, remaining } = parseSSEEvents(buffer);
        buffer = remaining;

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
      }
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") return;
      if (error instanceof RateLimitError) return; // Toast already shown
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
    const remaining = indexedDocuments.filter((d) => d.filename !== filename);
    setIndexedDocuments(remaining);

    // Clear messages if no documents remain (conversation context is gone)
    const remainingIndexed = remaining.filter((d) => d.status === "indexed");
    if (remainingIndexed.length === 0) {
      setMessages([]);
      setCollectionId(null);
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="flex h-[calc(100vh-10rem)] flex-col sm:h-[calc(100vh-12rem)]"
    >
      {/* Header */}
      <header className="mb-4">
        <Button
          variant="ghost"
          className="mb-4 -ml-3 gap-2"
          onClick={() => router.push("/")}
        >
          <ArrowLeft className="h-4 w-4" />
          Back
        </Button>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <Bot className="text-primary h-6 w-6 sm:h-7 sm:w-7" />
            <div>
              <h1 className="font-serif text-xl font-semibold tracking-tight sm:text-2xl">
                RAG Builder
              </h1>
              <p className="text-muted-foreground hidden text-sm sm:block">
                Ask questions about your documents
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
          {/* Document status badge - only show when documents exist */}
          {hasDocuments && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="sm" className="gap-2">
                  <FileText className="h-4 w-4" />
                  {indexedCount} doc{indexedCount !== 1 ? "s" : ""} indexed
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-64 sm:w-72">
                <div className="overflow-x-hidden p-2">
                  <DocumentList
                    documents={indexedDocuments}
                    onRemove={handleRemoveDocument}
                    className="max-h-48 overflow-y-auto"
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
                onFilesSelect={handleFilesSelect}
                onFileRemove={handleFileRemove}
                onIndex={handleIndexDocuments}
              />
            </Dialog>
          )}

          {/* Feedback - show when documents exist */}
          {hasDocuments && <FeedbackButton demoType="rag" />}

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
        </div>
      </header>

      <div className="mb-4 rounded-xl border bg-white">
        <button
          type="button"
          className="flex w-full items-center justify-between px-5 py-4 text-left"
          onClick={() => setHowItWorksOpen((current) => !current)}
        >
          <div>
            <h2 className="text-base font-semibold">How It Works</h2>
            <p className="text-muted-foreground mt-1 text-sm">
              Index documents into an in-memory vector store and query them with retrieval-augmented generation.
            </p>
          </div>
          <div className="text-muted-foreground flex items-center gap-2 text-sm font-medium">
            {howItWorksOpen ? "Hide" : "Show"}
            <Upload className={`h-4 w-4 transition-transform ${howItWorksOpen ? "rotate-180" : "-rotate-90"}`} />
          </div>
        </button>
        {howItWorksOpen && (
          <div className="space-y-4 border-t px-5 py-4 text-sm leading-6">
            <p>
              This demo indexes one or more PDF documents into an in-memory vector store and then lets you ask questions over the indexed content. The parser determines how the PDF is converted into RAG chunks before embeddings are created and stored.
            </p>
            <div className="space-y-2">
              <p><strong>1. Choose a parser:</strong></p>
              <p>
                <strong>Vision+ Parser:</strong> Used for high-quality parsing. It can interpret images and place their interpretation in the right location in the document flow. It is intended to extract everything from a document and produce vision-enhanced RAG chunks with metadata. In this demo, Vision+ is limited to 10 pages. Read more at <a href="https://medium.com/@umairali.khan/how-i-enhanced-doclings-image-interpretation-capabilities-641ce017bce5" target="_blank" rel="noreferrer" className="text-primary underline underline-offset-2">this article</a>.
              </p>
              <p>
                <strong>Docling RAG Parser:</strong> Uses the Docling parser running at Haaga-Helia as a service. It provides high-quality parsing with metadata and returns ready-made RAG chunks through the remote parsing endpoint.
              </p>
              <p>
                <strong>PyMuPDF:</strong> Fast local fallback parser that extracts page text directly. It is lighter than the other two options and is useful when you need robust local parsing without the richer image-aware or Docling-based processing.
              </p>
            </div>
            <p>
              <strong>2. Upload PDFs:</strong> You can upload one or more PDF files in the same indexing run. The selected parser is applied to each file, and the resulting chunks are embedded and stored in the same in-memory collection.
            </p>
            <p>
              <strong>3. Build the vector store:</strong> Parsed chunks are embedded and added to the current in-memory vector store. This collection persists only for the running demo session.
            </p>
            <p>
              <strong>4. Ask questions:</strong> After indexing, the retriever searches the stored chunks, and the answer generator produces a response with source references.
            </p>
          </div>
        )}
      </div>

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
                    <h2 className="mb-2 text-xl font-semibold">Get started</h2>
                    <p className="text-muted-foreground mb-6 max-w-md text-center">
                      Try our example document to see RAG in action, or upload
                      your own PDFs to ask questions and get AI-powered answers
                      with citations.
                    </p>
                    <div className="flex gap-3">
                      <ExamplePreviewDialog
                        exampleUrl="/GAIK_Test_Document_Demo.pdf"
                        exampleName="GAIK_Test_Document_Demo.pdf"
                        onUseExampleDirect={handleLoadExample}
                        disabled={isIndexing}
                        buttonVariant="default"
                        buttonSize="lg"
                      />
                      <DialogTrigger asChild>
                        <Button size="lg" variant="outline" className="gap-2">
                          <Plus className="h-5 w-5" />
                          Upload PDF
                        </Button>
                      </DialogTrigger>
                    </div>
                  </div>
                  <UploadDialogContent
                    pendingFiles={pendingFiles}
                    isIndexing={isIndexing}
                    onFilesSelect={handleFilesSelect}
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
                <Shimmer
                  color="var(--color-primary)"
                  shimmerColor="var(--color-primary-foreground)"
                  spread={4}
                  className="text-sm"
                >
                  Searching documents...
                </Shimmer>
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
