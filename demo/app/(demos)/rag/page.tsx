"use client";

import { FileUpload } from "@/components/demo/file-upload";
import {
  DocumentList,
  type IndexedDocument,
} from "@/components/demo/document-list";
import { CitationCard, type Source } from "@/components/demo/citation-card";
import {
  EmptyStateCard,
  ResultCard,
} from "@/components/demo/result-card";
import { StepIndicator } from "@/components/demo/step-indicator";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import {
  BookOpen,
  ChevronDown,
  ChevronUp,
  Library,
  Loader2,
  Search,
  Settings2,
  Sparkles,
  Trash2,
  Upload,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";

interface SSEStep {
  step: number;
  name: string;
  status: "pending" | "in_progress" | "completed" | "error";
  message?: string;
}

interface SSEEvent {
  type: string;
  data: Record<string, unknown>;
}

function parseSSEEvents(text: string): SSEEvent[] {
  const events: SSEEvent[] = [];
  const lines = text.split("\n");
  let currentEvent: { type?: string; data?: string } = {};

  for (const line of lines) {
    if (line.startsWith("event: ")) {
      currentEvent.type = line.slice(7);
    } else if (line.startsWith("data: ")) {
      currentEvent.data = line.slice(6);
    } else if (line === "" && currentEvent.type && currentEvent.data) {
      try {
        events.push({
          type: currentEvent.type,
          data: JSON.parse(currentEvent.data),
        });
      } catch {
        // Skip invalid JSON
      }
      currentEvent = {};
    }
  }
  return events;
}

interface QueryResult {
  answer: string;
  sources: Source[];
}

export default function RAGPage() {
  // Collection state
  const [collectionId, setCollectionId] = useState<string | null>(null);
  const [indexedDocuments, setIndexedDocuments] = useState<IndexedDocument[]>([]);

  // Upload state
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [isIndexing, setIsIndexing] = useState(false);

  // Query state
  const [question, setQuestion] = useState("");
  const [isQuerying, setIsQuerying] = useState(false);
  const [queryResult, setQueryResult] = useState<QueryResult | null>(null);
  const [streamingAnswer, setStreamingAnswer] = useState<string[]>([]);
  const [querySteps, setQuerySteps] = useState<SSEStep[]>([]);

  // Settings state
  const [showSettings, setShowSettings] = useState(false);
  const [topK, setTopK] = useState(5);
  const [searchType, setSearchType] = useState<"semantic" | "hybrid">("semantic");

  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  const hasDocuments = indexedDocuments.filter((d) => d.status === "indexed").length > 0;

  function handleFileSelect(file: File): void {
    // Add to pending files if not already there
    if (!pendingFiles.some((f) => f.name === file.name)) {
      setPendingFiles([...pendingFiles, file]);
    }
  }

  function handleFileRemove(): void {
    // Clear the most recent pending file
    setPendingFiles([]);
  }

  async function handleIndexDocuments(): Promise<void> {
    if (pendingFiles.length === 0 || isIndexing) return;

    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();

    setIsIndexing(true);

    // Mark files as processing
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

      // Update collection ID
      setCollectionId(data.collection_id);

      // Update documents with results
      const updatedDocs = [...indexedDocuments.filter((d) => d.status === "indexed")];
      for (const doc of data.documents) {
        updatedDocs.push({
          filename: doc.filename,
          chunkCount: doc.chunk_count,
          status: doc.status,
        });
      }
      setIndexedDocuments(updatedDocs);

      // Clear pending files
      setPendingFiles([]);

      if (data.status === "success") {
        toast.success(`Indexed ${data.document_count} document(s) with ${data.chunk_count} chunks`);
      } else {
        toast.error("Some documents failed to index");
      }
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") return;
      toast.error(error instanceof Error ? error.message : "Failed to index documents");

      // Mark processing files as error
      setIndexedDocuments(
        indexedDocuments.map((d) =>
          d.status === "processing" ? { ...d, status: "error" as const } : d
        )
      );
    } finally {
      setIsIndexing(false);
    }
  }

  async function handleQuery(): Promise<void> {
    if (!question.trim() || !collectionId || isQuerying) return;

    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();

    setIsQuerying(true);
    setQueryResult(null);
    setStreamingAnswer([]);
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
              prev.map((s) => (s.step === update.step ? update : s))
            );
          } else if (event.type === "sources") {
            sources = (event.data.sources as unknown as Array<{
              document_name: string;
              page_number: string | number | null;
              relevance_score?: number | null;
            }>).map((s) => ({
              documentName: s.document_name,
              pageNumber: s.page_number,
              relevanceScore: s.relevance_score,
            }));
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
            setQueryResult({
              answer: result.answer,
              sources: result.sources.map((s) => ({
                documentName: s.document_name,
                pageNumber: s.page_number,
                relevanceScore: s.relevance_score,
              })),
            });
            toast.success("Answer generated!");
          } else if (event.type === "error") {
            throw new Error((event.data.message as string) || "Query failed");
          }
        }

        // Clear processed events from buffer
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
            : s
        )
      );
    } finally {
      setIsQuerying(false);
    }
  }

  async function handleClearCollection(): Promise<void> {
    if (!collectionId) return;

    try {
      await fetch(`/api/rag/clear/${collectionId}`, { method: "DELETE" });
      setCollectionId(null);
      setIndexedDocuments([]);
      setQueryResult(null);
      setStreamingAnswer([]);
      toast.success("Collection cleared");
    } catch (error) {
      toast.error("Failed to clear collection");
    }
  }

  function handleRemoveDocument(filename: string): void {
    setIndexedDocuments(indexedDocuments.filter((d) => d.filename !== filename));
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
    >
      <header className="mb-8 pl-1">
        <h1 className="flex items-center gap-3 font-serif text-3xl font-semibold tracking-tight">
          <Library className="text-primary h-8 w-8" />
          RAG Builder
        </h1>
        <p className="text-muted-foreground mt-2 text-lg">
          Index PDF documents and ask questions with AI-powered answers and citations.
        </p>
      </header>

      <div className="grid gap-8 lg:grid-cols-2">
        {/* Left Column: Controls */}
        <div className="space-y-6">
          {/* Document Upload Card */}
          <Card className="shadow-md">
            <CardHeader className="pb-4">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="flex items-center gap-2">
                    <Upload className="h-5 w-5" />
                    Document Upload
                  </CardTitle>
                  <CardDescription>
                    Upload PDF files to index for RAG queries
                  </CardDescription>
                </div>
                {hasDocuments && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={handleClearCollection}
                    className="text-destructive hover:text-destructive"
                  >
                    <Trash2 className="mr-2 h-4 w-4" />
                    Clear All
                  </Button>
                )}
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
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
                  {isIndexing ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Indexing...
                    </>
                  ) : (
                    <>
                      <Sparkles className="mr-2 h-4 w-4" />
                      Index Document{pendingFiles.length > 1 ? "s" : ""}
                    </>
                  )}
                </Button>
              )}

              {indexedDocuments.length > 0 && (
                <DocumentList
                  documents={indexedDocuments}
                  onRemove={handleRemoveDocument}
                  className="pt-2"
                />
              )}
            </CardContent>
          </Card>

          {/* Question Card */}
          <Card className="shadow-md">
            <CardHeader className="pb-4">
              <CardTitle className="flex items-center gap-2">
                <BookOpen className="h-5 w-5" />
                Ask a Question
              </CardTitle>
              <CardDescription>
                Query your indexed documents with natural language
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="question">Your Question</Label>
                <div className="relative">
                  <Input
                    id="question"
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                    placeholder="What would you like to know about your documents?"
                    disabled={!hasDocuments || isQuerying}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        handleQuery();
                      }
                    }}
                    className="pr-10"
                  />
                  <Search className="text-muted-foreground absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2" />
                </div>
              </div>

              {/* Settings Toggle */}
              <div className="border-muted rounded-lg border">
                <button
                  onClick={() => setShowSettings(!showSettings)}
                  className="hover:bg-muted/50 flex w-full items-center justify-between p-3 text-sm font-medium transition-colors"
                  type="button"
                >
                  <div className="flex items-center gap-2">
                    <Settings2 className="text-muted-foreground h-4 w-4" />
                    <span>Search Settings</span>
                  </div>
                  {showSettings ? (
                    <ChevronUp className="text-muted-foreground h-4 w-4" />
                  ) : (
                    <ChevronDown className="text-muted-foreground h-4 w-4" />
                  )}
                </button>
                <AnimatePresence>
                  {showSettings && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      className="overflow-hidden"
                    >
                      <div className="space-y-4 border-t p-4">
                        <div className="grid grid-cols-2 gap-4">
                          <div className="space-y-2">
                            <Label htmlFor="topK">Results (Top K)</Label>
                            <Select
                              value={String(topK)}
                              onValueChange={(v) => setTopK(Number(v))}
                            >
                              <SelectTrigger id="topK">
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
                            <Label htmlFor="searchType">Search Type</Label>
                            <Select
                              value={searchType}
                              onValueChange={(v) =>
                                setSearchType(v as "semantic" | "hybrid")
                              }
                            >
                              <SelectTrigger id="searchType">
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="semantic">Semantic</SelectItem>
                                <SelectItem value="hybrid">Hybrid</SelectItem>
                              </SelectContent>
                            </Select>
                          </div>
                        </div>
                        <p className="text-muted-foreground text-xs">
                          {searchType === "semantic"
                            ? "Uses vector similarity to find relevant content"
                            : "Combines vector search with keyword matching (BM25)"}
                        </p>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>

              <Button
                onClick={handleQuery}
                disabled={!hasDocuments || !question.trim() || isQuerying}
                className="w-full"
                size="lg"
              >
                {isQuerying ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Searching...
                  </>
                ) : (
                  <>
                    <Sparkles className="mr-2 h-4 w-4" />
                    Get Answer
                  </>
                )}
              </Button>

              {!hasDocuments && (
                <p className="text-muted-foreground text-center text-sm">
                  Upload and index documents first to ask questions
                </p>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Right Column: Results */}
        <div className="space-y-4">
          {isQuerying && (
            <Card className="border-primary/20 overflow-hidden shadow-lg">
              <CardContent className="pt-6">
                <div className="flex flex-col gap-6">
                  <div className="flex items-center gap-4">
                    <div className="bg-primary/10 flex h-12 w-12 items-center justify-center rounded-full">
                      <Loader2 className="text-primary h-6 w-6 animate-spin" />
                    </div>
                    <div>
                      <h3 className="text-lg font-semibold">Searching...</h3>
                      <p className="text-muted-foreground text-sm">
                        Finding relevant information in your documents
                      </p>
                    </div>
                  </div>

                  {querySteps.length > 0 && (
                    <div className="bg-muted/30 rounded-lg border p-4">
                      <StepIndicator
                        steps={querySteps.map((s) => ({
                          id: String(s.step),
                          name: s.name,
                          status: s.status,
                          message: s.message,
                        }))}
                        orientation="vertical"
                      />
                    </div>
                  )}

                  {streamingAnswer.length > 0 && (
                    <div className="bg-muted/30 rounded-lg border p-4">
                      <p className="text-muted-foreground mb-2 text-xs font-medium uppercase">
                        Generating answer...
                      </p>
                      <div className="whitespace-pre-wrap text-sm">
                        {streamingAnswer.join("")}
                        <motion.span
                          animate={{ opacity: [1, 0] }}
                          transition={{ duration: 0.5, repeat: Infinity }}
                          className="bg-primary ml-0.5 inline-block h-4 w-2"
                        />
                      </div>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          )}

          {queryResult && !isQuerying && (
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.3 }}
            >
              <CitationCard
                answer={queryResult.answer}
                sources={queryResult.sources}
              />
            </motion.div>
          )}

          {!queryResult && !isQuerying && (
            <EmptyStateCard
              message={
                hasDocuments
                  ? "Ask a question to see AI-generated answers with citations"
                  : "Upload and index PDF documents to get started"
              }
            />
          )}
        </div>
      </div>
    </motion.div>
  );
}
