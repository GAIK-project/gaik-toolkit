"use client";

import { apiFetch } from "@/lib/api-client";
import { EmptyStateCard } from "@/components/demo/result-card";
import { FeedbackButton } from "@/components/feedback";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import {
  AlertCircle,
  Clock,
  Database,
  Film,
  Loader2,
  Play,
  Search,
  Sparkles,
  Type,
  Video,
  Volume2,
  Zap,
} from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";

interface SearchResult {
  text: string;
  video_title: string;
  video_id: string;
  start_seconds: number;
  end_seconds: number;
  timestamp: string;
  score: number;
}

interface VideoInfo {
  video_id: string;
  video_title: string;
  segment_count: number;
}

interface StatusInfo {
  database_connected: boolean;
  total_segments: number;
  total_videos: number;
  embedding_model: string;
}

function formatMatchScore(score: number, topScore: number): string {
  if (score <= 0 || topScore <= 0) return "0%";
  return `${Math.max(1, Math.round((score / topScore) * 100))}%`;
}

export default function VideoSearchPage() {
  const [query, setQuery] = useState("");
  const [searchType, setSearchType] = useState("hybrid");
  const [videoFilter, setVideoFilter] = useState<string>("all");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);

  const [videos, setVideos] = useState<VideoInfo[]>([]);
  const [status, setStatus] = useState<StatusInfo | null>(null);
  const [backendError, setBackendError] = useState<string | null>(null);
  const [playerOpen, setPlayerOpen] = useState(false);
  const [playingVideo, setPlayingVideo] = useState<{
    url: string;
    title: string;
    timestamp: string;
    startSeconds: number;
  } | null>(null);
  const [loadingVideoId, setLoadingVideoId] = useState<string | null>(null);
  const [videoLoading, setVideoLoading] = useState(true);
  const [thumbnails, setThumbnails] = useState<Record<string, string>>({});
  const [thumbnailFailures, setThumbnailFailures] = useState<
    Record<string, true>
  >({});

  const searchInputRef = useRef<HTMLInputElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const prefersReducedMotion = useReducedMotion();

  useEffect(() => {
    fetchStatus();
    fetchVideos();
  }, []);

  useEffect(() => {
    if (hasSearched && query.trim()) {
      handleSearch();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchType, videoFilter]);

  useEffect(() => {
    const videoIds = [...new Set(results.map((result) => result.video_id))];
    const pendingIds = videoIds.filter(
      (videoId) => !thumbnails[videoId] && !thumbnailFailures[videoId],
    );

    if (pendingIds.length === 0) return;

    let cancelled = false;

    for (const videoId of pendingIds) {
      apiFetch(`/api/video-search/videos/${videoId}/thumbnail`)
        .then(async (response) => {
          if (!response.ok) {
            if (!cancelled && response.status === 404) {
              setThumbnailFailures((prev) => ({ ...prev, [videoId]: true }));
              return;
            }
            throw new Error("Thumbnail request failed");
          }

          const data = await response.json();
          if (!cancelled && data?.url) {
            setThumbnails((prev) => ({ ...prev, [videoId]: data.url }));
          }
        })
        .catch(() => {
          if (!cancelled) {
            setThumbnailFailures((prev) => ({ ...prev, [videoId]: true }));
          }
        });
    }

    return () => {
      cancelled = true;
    };
  }, [results, thumbnailFailures, thumbnails]);

  async function fetchStatus() {
    try {
      const res = await apiFetch("/api/video-search/status");
      if (!res.ok) throw new Error("Backend unreachable");
      setStatus(await res.json());
      setBackendError(null);
    } catch {
      setStatus(null);
      setBackendError("Backend unreachable");
    }
  }

  async function fetchVideos() {
    try {
      const res = await apiFetch("/api/video-search/videos");
      if (res.ok) {
        setVideos(await res.json());
      } else {
        setVideos([]);
      }
    } catch {
      setVideos([]);
    }
  }

  const handleSearch = useCallback(async () => {
    if (!query.trim() || isSearching) return;

    setIsSearching(true);
    setHasSearched(true);

    try {
      const formData = new FormData();
      formData.append("query", query);
      formData.append("top_k", "10");
      formData.append("search_type", searchType);
      if (videoFilter && videoFilter !== "all") {
        formData.append("video_id", videoFilter);
      }

      const res = await apiFetch("/api/video-search/search", {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Search failed" }));
        throw new Error(err.detail || "Search failed");
      }

      const data = await res.json();
      setResults(data.results || []);

      if (data.results?.length === 0) {
        toast("No results found. Try a different query.", { icon: "🔍" });
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Search failed");
      setResults([]);
    } finally {
      setIsSearching(false);
    }
  }, [isSearching, query, searchType, videoFilter]);

  async function handleResultClick(result: SearchResult) {
    const key = `${result.video_id}-${result.start_seconds}`;
    setLoadingVideoId(key);

    try {
      const res = await apiFetch(
        `/api/video-search/videos/${result.video_id}/play`,
      );
      if (!res.ok) {
        const detail = await res
          .json()
          .catch(() => ({ detail: "Playback failed" }));
        throw new Error(
          res.status === 404
            ? "This video's media is missing from storage."
            : detail.detail || "Failed to get playback URL",
        );
      }

      const data = await res.json();
      setVideoLoading(true);
      setPlayingVideo({
        url: data.url,
        title: result.video_title,
        timestamp: result.timestamp,
        startSeconds: result.start_seconds,
      });
      setPlayerOpen(true);
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Video playback failed",
      );
    } finally {
      setLoadingVideoId(null);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter") handleSearch();
  }

  const searchTypeInfo: Record<
    string,
    { icon: typeof Zap; label: string; helper: string; desc: string }
  > = {
    hybrid: {
      icon: Zap,
      label: "Balanced",
      helper: "Best default",
      desc: "Looks at both the topic and the exact words that were said.",
    },
    semantic: {
      icon: Sparkles,
      label: "By meaning",
      helper: "Idea match",
      desc: "Useful when you remember the idea but not the exact wording.",
    },
    keyword: {
      icon: Type,
      label: "Exact words",
      helper: "Literal match",
      desc: "Useful when you know the exact term, phrase, or quote.",
    },
  };

  const topScore = results.reduce(
    (maxScore, result) => Math.max(maxScore, result.score),
    0,
  );
  const activeSearchType = searchTypeInfo[searchType];
  const ActiveSearchIcon = activeSearchType.icon;

  return (
    <TooltipProvider>
      <motion.div
        initial={prefersReducedMotion ? false : { opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: prefersReducedMotion ? 0 : 0.4 }}
        className="mx-auto max-w-4xl"
      >
        <header className="mb-8 grid gap-5 lg:grid-cols-[1.2fr_0.8fr] lg:items-start">
          <div className="space-y-4 pl-1">
            <Badge
              variant="outline"
              className="border-primary/25 bg-primary/5 text-primary"
            >
              AI Video Search
            </Badge>
            <h1 className="flex items-center gap-3 font-serif text-3xl font-semibold tracking-tight">
              <Video className="text-primary h-8 w-8" />
              Semantic Video Search
            </h1>
            <p className="text-muted-foreground max-w-2xl text-lg leading-relaxed">
              Search your indexed videos with normal language and jump straight
              to the relevant moment. The system checks both what is being
              discussed and the exact wording in the subtitles.
            </p>
            <div className="grid gap-2 sm:grid-cols-3">
              <div className="bg-card border-border/70 rounded-xl border px-3 py-3 shadow-xs">
                <p className="text-sm font-medium">Ask naturally</p>
                <p className="text-muted-foreground mt-1 text-xs">
                  Describe the idea you want to find.
                </p>
              </div>
              <div className="bg-card border-border/70 rounded-xl border px-3 py-3 shadow-xs">
                <p className="text-sm font-medium">See the best moments</p>
                <p className="text-muted-foreground mt-1 text-xs">
                  Open the exact timestamp directly from the result list.
                </p>
              </div>
              <div className="bg-card border-border/70 rounded-xl border px-3 py-3 shadow-xs">
                <p className="text-sm font-medium">Works with subtitles</p>
                <p className="text-muted-foreground mt-1 text-xs">
                  Generated transcripts can power this search workflow.
                </p>
              </div>
            </div>
          </div>

          <Card className="border-primary/20 bg-card/95 shadow-md">
            <CardContent className="space-y-4 p-5">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold">What happens here</p>
                  <p className="text-muted-foreground mt-1 text-sm">
                    A simple three-step flow from question to playback.
                  </p>
                </div>
                <Badge variant="secondary" className="shrink-0">
                  Subtitle-powered
                </Badge>
              </div>

              <div className="space-y-2.5">
                {[
                  "Describe the topic, phrase, or question you want to find.",
                  "The search compares meaning and exact wording in the subtitle index.",
                  "Open the best hit and start playback from the matching timestamp.",
                ].map((step, index) => (
                  <div
                    key={step}
                    className="bg-muted/35 border-border/60 flex items-start gap-3 rounded-xl border px-3 py-3"
                  >
                    <div className="bg-primary/10 text-primary flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold">
                      {index + 1}
                    </div>
                    <p className="text-sm leading-relaxed">{step}</p>
                  </div>
                ))}
              </div>

              <Link
                href="/dental-transcription"
                className="text-primary inline-flex text-sm font-medium hover:underline"
              >
                See the transcription and subtitle example
              </Link>
            </CardContent>
          </Card>
        </header>

        {status && (
          <div className="mb-6 flex items-center gap-2 text-sm">
            <Database className="text-muted-foreground h-4 w-4" />
            <span
              className={cn(
                "inline-block h-2 w-2 rounded-full",
                status.database_connected ? "bg-green-500" : "bg-red-500",
              )}
            />
            <span className="text-muted-foreground">
              {status.database_connected
                ? `${status.total_videos} videos, ${status.total_segments} segments indexed`
                : "Database not connected"}
            </span>
          </div>
        )}

        {backendError && (
          <Card className="border-destructive/20 bg-destructive/5 mb-6">
            <CardContent className="flex items-start gap-3 pt-6">
              <AlertCircle className="text-destructive mt-0.5 h-5 w-5 shrink-0" />
              <div>
                <p className="text-destructive font-medium">
                  Backend unreachable
                </p>
                <p className="text-muted-foreground text-sm">
                  Start the FastAPI backend or verify the local proxy target in
                  `BACKEND_URL` before using video search.
                </p>
              </div>
            </CardContent>
          </Card>
        )}

        {status && !status.database_connected && (
          <Card className="mb-6 border-amber-200 bg-amber-50 dark:border-amber-900 dark:bg-amber-950/20">
            <CardContent className="flex items-start gap-3 pt-6">
              <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-amber-500" />
              <div>
                <p className="font-medium text-amber-800 dark:text-amber-200">
                  Database not configured
                </p>
                <p className="text-sm text-amber-700 dark:text-amber-300">
                  Set `DATABASE_URL` to connect to PostgreSQL with pgvector.
                </p>
              </div>
            </CardContent>
          </Card>
        )}

        <div className="space-y-6">
          <Card className="shadow-md">
            <CardContent className="pt-6">
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <Label htmlFor="video-search-query" className="sr-only">
                    Search query
                  </Label>
                  <Search className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2" />
                  <Input
                    id="video-search-query"
                    name="query"
                    ref={searchInputRef}
                    placeholder="Search your videos with normal words"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    onKeyDown={handleKeyDown}
                    className="border-border/85 bg-card h-12 pl-10 text-base shadow-sm"
                    autoComplete="off"
                    disabled={!status?.database_connected}
                  />
                </div>
                <Button
                  size="lg"
                  aria-label="Run video search"
                  onClick={handleSearch}
                  disabled={
                    isSearching || !query.trim() || !status?.database_connected
                  }
                  className="h-12 gap-2 px-5"
                >
                  {isSearching ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Searching
                    </>
                  ) : (
                    <>
                      <Search className="h-4 w-4" />
                      Search
                    </>
                  )}
                </Button>
              </div>

              <div className="mt-4 flex flex-wrap items-end gap-4">
                <div className="space-y-1.5">
                  <Label className="text-muted-foreground text-xs font-normal">
                    Search style
                  </Label>
                  <ToggleGroup
                    type="single"
                    aria-label="Search Type"
                    value={searchType}
                    onValueChange={(value) => value && setSearchType(value)}
                    size="sm"
                    className="bg-muted/70 border-border grid w-full max-w-[28rem] grid-cols-3 rounded-2xl border p-1 shadow-sm"
                  >
                    {Object.entries(searchTypeInfo).map(
                      ([key, { icon: Icon, label, helper, desc }]) => (
                        <Tooltip key={key}>
                          <TooltipTrigger asChild>
                            <ToggleGroupItem
                              value={key}
                              className="text-muted-foreground hover:bg-background/80 hover:text-foreground data-[state=on]:!bg-primary data-[state=on]:!text-primary-foreground data-[state=on]:!border-primary min-h-14 min-w-0 flex-1 flex-col items-start gap-0.5 rounded-xl border border-transparent px-3 py-2 text-left whitespace-normal shadow-none data-[state=on]:shadow-md"
                            >
                              <span className="flex items-center gap-1.5 text-sm font-medium">
                                <Icon className="h-3.5 w-3.5" />
                                {label}
                              </span>
                              <span className="text-[11px] opacity-80">
                                {helper}
                              </span>
                            </ToggleGroupItem>
                          </TooltipTrigger>
                          <TooltipContent side="bottom">
                            <p className="text-xs">{desc}</p>
                          </TooltipContent>
                        </Tooltip>
                      ),
                    )}
                  </ToggleGroup>
                </div>

                {videos.length > 0 && (
                  <div className="space-y-1.5">
                    <Label className="text-muted-foreground text-xs font-normal">
                      Video scope
                    </Label>
                    <Select value={videoFilter} onValueChange={setVideoFilter}>
                      <SelectTrigger
                        aria-label="Filter by Video"
                        className={cn(
                          "border-border/85 bg-card h-10 w-55 shadow-sm",
                          videoFilter !== "all" &&
                            "border-primary/40 bg-primary/5 text-foreground",
                        )}
                      >
                        <SelectValue placeholder="All videos" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">All videos</SelectItem>
                        {videos.map((video) => (
                          <SelectItem
                            key={video.video_id}
                            value={video.video_id}
                          >
                            {video.video_title.length > 35
                              ? `${video.video_title.slice(0, 35)}…`
                              : video.video_title}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                )}
              </div>

              <div className="bg-muted/35 border-border/70 mt-4 rounded-2xl border px-4 py-3">
                <div className="flex items-center gap-2">
                  <div className="bg-primary/10 text-primary flex h-8 w-8 items-center justify-center rounded-full">
                    <ActiveSearchIcon className="h-4 w-4" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold">
                      {activeSearchType.label}
                    </p>
                    <p className="text-muted-foreground text-xs">
                      {activeSearchType.helper}
                    </p>
                  </div>
                </div>
                <p className="text-muted-foreground mt-1 text-sm">
                  {activeSearchType.desc}
                </p>
              </div>
            </CardContent>
          </Card>

          {isSearching && (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="text-muted-foreground h-8 w-8 animate-spin" />
            </div>
          )}

          {!isSearching && results.length > 0 && (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-3 pl-1">
                <p className="text-muted-foreground text-sm font-medium">
                  {results.length} result{results.length !== 1 ? "s" : ""} found
                </p>
                <span className="text-muted-foreground/70 flex items-center gap-1 text-xs">
                  <ActiveSearchIcon className="h-3 w-3" />
                  {activeSearchType.label}:{" "}
                  {activeSearchType.helper.toLowerCase()}
                </span>
              </div>

              {results.map((result, index) => {
                const key = `${result.video_id}-${result.start_seconds}`;
                const isLoading = loadingVideoId === key;
                const thumbnailUrl = thumbnails[result.video_id];

                return (
                  <motion.div
                    key={`${key}-${index}`}
                    initial={
                      prefersReducedMotion ? false : { opacity: 0, y: 10 }
                    }
                    animate={{ opacity: 1, y: 0 }}
                    transition={{
                      delay: prefersReducedMotion ? 0 : index * 0.04,
                    }}
                  >
                    <button
                      type="button"
                      className={cn(
                        "group bg-card hover:border-primary/40 focus-visible:ring-ring/50 w-full cursor-pointer rounded-lg border text-left transition-all hover:shadow-md focus-visible:ring-[3px] focus-visible:outline-none",
                        isLoading && "border-primary/30 opacity-80",
                      )}
                      onClick={() => handleResultClick(result)}
                    >
                      <CardContent className="flex items-start gap-4 py-4">
                        <div
                          className={cn(
                            "bg-muted relative h-16 w-24 shrink-0 overflow-hidden rounded-md",
                            isLoading && "opacity-80",
                          )}
                        >
                          {thumbnailUrl ? (
                            <img
                              src={thumbnailUrl}
                              alt={`Thumbnail for ${result.video_title}`}
                              width={96}
                              height={64}
                              loading="lazy"
                              className="h-full w-full object-cover"
                              onError={() => {
                                setThumbnailFailures((prev) => ({
                                  ...prev,
                                  [result.video_id]: true,
                                }));
                                setThumbnails((prev) => {
                                  const next = { ...prev };
                                  delete next[result.video_id];
                                  return next;
                                });
                              }}
                            />
                          ) : (
                            <div className="from-muted to-muted/70 flex h-full w-full flex-col items-center justify-center gap-1 bg-gradient-to-br px-2 text-center">
                              <Video className="text-muted-foreground h-5 w-5" />
                              <span className="text-muted-foreground/80 line-clamp-2 text-[10px] font-medium">
                                No preview
                              </span>
                            </div>
                          )}

                          <div className="absolute inset-0 flex items-center justify-center bg-black/20 opacity-0 transition-opacity group-hover:opacity-100">
                            {isLoading ? (
                              <Loader2 className="h-5 w-5 animate-spin text-white" />
                            ) : (
                              <Play className="h-5 w-5 text-white drop-shadow" />
                            )}
                          </div>
                        </div>

                        <div className="min-w-0 flex-1">
                          <div className="mb-1.5 flex flex-wrap items-center gap-2">
                            <span className="truncate text-sm font-semibold">
                              {result.video_title}
                            </span>
                            <Badge
                              variant="secondary"
                              className="shrink-0 gap-1 font-mono text-xs"
                            >
                              <Clock className="h-3 w-3" />
                              {result.timestamp}
                            </Badge>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Badge
                                  variant="outline"
                                  className="border-primary/20 bg-primary/5 text-primary shrink-0 font-mono text-xs"
                                >
                                  {formatMatchScore(result.score, topScore)}
                                </Badge>
                              </TooltipTrigger>
                              <TooltipContent>
                                <p className="text-xs">
                                  Relative match{" "}
                                  {formatMatchScore(result.score, topScore)}
                                  {" · "}raw {result.score.toFixed(4)}
                                </p>
                              </TooltipContent>
                            </Tooltip>
                          </div>
                          <p className="text-muted-foreground line-clamp-2 text-sm leading-relaxed">
                            {result.text}
                          </p>
                        </div>
                      </CardContent>
                    </button>
                  </motion.div>
                );
              })}
            </div>
          )}

          {!isSearching && hasSearched && results.length === 0 && (
            <EmptyStateCard message="No results found. Try a different wording, another search style, or narrow the search to one video." />
          )}

          {!hasSearched && !isSearching && status?.database_connected && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.2 }}
              className="space-y-4"
            >
              <Card className="border-primary/20 border-dashed">
                <CardContent className="flex flex-col items-center justify-center py-12 text-center">
                  <Search className="text-muted-foreground/40 mb-3 h-10 w-10" />
                  <p className="text-muted-foreground">
                    Search the indexed videos above to find the most relevant
                    moment.
                  </p>
                  <p className="text-muted-foreground/60 mt-1 text-sm">
                    Try searches like &ldquo;tekoäly työelämässä&rdquo;,
                    &ldquo;kielitaito&rdquo;, or &ldquo;johtaminen&rdquo;
                  </p>
                </CardContent>
              </Card>

              {videos.length > 0 && (
                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="flex items-center gap-2 text-base">
                      <Film className="h-4 w-4" />
                      Indexed Videos
                      <Badge variant="secondary" className="ml-1">
                        {videos.length}
                      </Badge>
                    </CardTitle>
                    <CardDescription>
                      These videos already have subtitles and can be searched by
                      topic or wording.
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="grid gap-2">
                      {videos.map((video) => (
                        <button
                          key={video.video_id}
                          className="hover:bg-muted/50 flex items-center justify-between rounded-lg px-3 py-2.5 text-left transition-colors"
                          onClick={() => {
                            setVideoFilter(video.video_id);
                            setQuery("");
                            searchInputRef.current?.focus();
                          }}
                        >
                          <div className="flex min-w-0 items-center gap-3">
                            <div className="bg-muted flex h-8 w-8 shrink-0 items-center justify-center rounded-md">
                              <Video className="text-muted-foreground h-4 w-4" />
                            </div>
                            <span className="truncate text-sm font-medium">
                              {video.video_title}
                            </span>
                          </div>
                          <Badge
                            variant="outline"
                            className="ml-2 shrink-0 text-xs"
                          >
                            {video.segment_count} segments
                          </Badge>
                        </button>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}
            </motion.div>
          )}

          <FeedbackButton demoType="video-search" />
        </div>

        <Dialog
          open={playerOpen}
          onOpenChange={(open) => {
            setPlayerOpen(open);
            if (!open) {
              setVideoLoading(true);
              setPlayingVideo(null);
            }
          }}
        >
          <DialogContent className="max-h-[90vh] overflow-hidden p-0 sm:max-w-4xl lg:max-w-5xl">
            <DialogHeader className="px-6 pt-6 pb-0">
              <DialogTitle className="pr-8 text-base leading-snug">
                {playingVideo?.title}
              </DialogTitle>
              <DialogDescription asChild>
                {playingVideo?.timestamp ? (
                  <p className="text-muted-foreground text-sm">
                    Playing from {playingVideo.timestamp}
                  </p>
                ) : (
                  <p className="sr-only">Video player</p>
                )}
              </DialogDescription>
            </DialogHeader>
            <div className="px-6 pt-4 pb-6">
              {playingVideo && (
                <div className="relative overflow-hidden rounded-lg bg-black">
                  {videoLoading && (
                    <div className="absolute inset-0 z-10 flex items-center justify-center bg-black/80">
                      <Loader2 className="h-8 w-8 animate-spin text-white/60" />
                    </div>
                  )}
                  <video
                    ref={videoRef}
                    key={playingVideo.url}
                    controls
                    autoPlay
                    muted
                    src={playingVideo.url}
                    className="aspect-video w-full"
                    onLoadedMetadata={() => {
                      setVideoLoading(false);
                      const video = videoRef.current;
                      if (video && playingVideo.startSeconds > 0) {
                        video.currentTime = playingVideo.startSeconds;
                        video.play().catch(() => {});
                      }
                    }}
                    onError={() => {
                      setVideoLoading(false);
                      toast.error(
                        "Playback failed. Media could not be loaded.",
                      );
                    }}
                  />
                </div>
              )}
              <p className="text-muted-foreground/50 mt-2 flex items-center gap-1 text-xs">
                <Volume2 className="h-3 w-3" />
                Video starts muted for autoplay. Click the speaker icon to
                unmute.
              </p>
            </div>
          </DialogContent>
        </Dialog>
      </motion.div>
    </TooltipProvider>
  );
}
