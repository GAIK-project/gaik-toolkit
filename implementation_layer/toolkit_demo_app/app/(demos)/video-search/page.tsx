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
import { Separator } from "@/components/ui/separator";
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
  ExternalLink,
  Film,
  Loader2,
  Play,
  Search,
  Sparkles,
  Type,
  Video,
  Zap,
} from "lucide-react";
import { motion, AnimatePresence } from "motion/react";
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

function formatScore(score: number): string {
  if (score >= 0.1) return `${(score * 100).toFixed(0)}%`;
  if (score >= 0.01) return `${(score * 100).toFixed(1)}%`;
  return `${(score * 1000).toFixed(1)}‰`;
}

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
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
  const [playerOpen, setPlayerOpen] = useState(false);
  const [playingVideo, setPlayingVideo] = useState<{
    url: string;
    title: string;
    timestamp: string;
    startSeconds: number;
  } | null>(null);
  const [loadingVideoId, setLoadingVideoId] = useState<string | null>(null);

  const searchInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetchStatus();
    fetchVideos();
  }, []);

  async function fetchStatus() {
    try {
      const res = await apiFetch("/api/video-search/status");
      if (res.ok) setStatus(await res.json());
    } catch {
      /* status indicator will show disconnected */
    }
  }

  async function fetchVideos() {
    try {
      const res = await apiFetch("/api/video-search/videos");
      if (res.ok) setVideos(await res.json());
    } catch {
      /* silently fail */
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
        const err = await res
          .json()
          .catch(() => ({ detail: "Search failed" }));
        throw new Error(err.detail || "Search failed");
      }

      const data = await res.json();
      setResults(data.results || []);

      if (data.results?.length === 0) {
        toast("No results found. Try a different query.", { icon: "🔍" });
      }
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Search failed",
      );
      setResults([]);
    } finally {
      setIsSearching(false);
    }
  }, [query, searchType, videoFilter, isSearching]);

  async function handleResultClick(result: SearchResult) {
    const key = `${result.video_id}-${result.start_seconds}`;
    setLoadingVideoId(key);
    try {
      const res = await apiFetch(
        `/api/video-search/videos/${result.video_id}/play`,
      );
      if (!res.ok) throw new Error("Failed to get playback URL");
      const data = await res.json();
      setPlayingVideo({
        url: data.url,
        title: result.video_title,
        timestamp: result.timestamp,
        startSeconds: result.start_seconds,
      });
      setPlayerOpen(true);
    } catch {
      toast.error("Video not available yet. Videos are being uploaded.");
    } finally {
      setLoadingVideoId(null);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter") handleSearch();
  }

  const searchTypeInfo: Record<string, { icon: typeof Zap; desc: string }> = {
    hybrid: {
      icon: Zap,
      desc: "Combines meaning + keywords for best results",
    },
    semantic: {
      icon: Sparkles,
      desc: "Finds conceptually similar content",
    },
    keyword: { icon: Type, desc: "Exact word matching" },
  };

  return (
    <TooltipProvider>
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="mx-auto max-w-4xl"
      >
        {/* Header */}
        <header className="mb-8 pl-1">
          <h1 className="flex items-center gap-3 font-serif text-3xl font-semibold tracking-tight">
            <Video className="h-8 w-8 text-violet-500" />
            Semantic Dental Video Search
          </h1>
          <p className="text-muted-foreground mt-2 text-lg">
            Search indexed education videos by meaning. Find exact moments in
            lecture recordings using hybrid semantic + keyword search.
          </p>
        </header>

        {/* Status bar */}
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

        {/* Database warning */}
        {status && !status.database_connected && (
          <Card className="mb-6 border-amber-200 bg-amber-50 dark:border-amber-900 dark:bg-amber-950/20">
            <CardContent className="flex items-start gap-3 pt-6">
              <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-amber-500" />
              <div>
                <p className="font-medium text-amber-800 dark:text-amber-200">
                  Database not configured
                </p>
                <p className="text-sm text-amber-700 dark:text-amber-300">
                  Set DATABASE_URL to connect to PostgreSQL with pgvector.
                </p>
              </div>
            </CardContent>
          </Card>
        )}

        <div className="space-y-6">
          {/* Search Card */}
          <Card className="shadow-md">
            <CardContent className="pt-6">
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <Search className="text-muted-foreground pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2" />
                  <Input
                    ref={searchInputRef}
                    placeholder="Search for topics, procedures, concepts..."
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    onKeyDown={handleKeyDown}
                    className="h-11 pl-10 text-base"
                    disabled={!status?.database_connected}
                  />
                </div>
                <Button
                  size="lg"
                  onClick={handleSearch}
                  disabled={
                    isSearching ||
                    !query.trim() ||
                    !status?.database_connected
                  }
                  className="h-11 px-6"
                >
                  {isSearching ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Search className="h-4 w-4" />
                  )}
                </Button>
              </div>

              {/* Search options row */}
              <div className="mt-4 flex flex-wrap items-end gap-4">
                <div className="space-y-1.5">
                  <Label className="text-muted-foreground text-xs font-normal">
                    Search Type
                  </Label>
                  <ToggleGroup
                    type="single"
                    value={searchType}
                    onValueChange={(v) => v && setSearchType(v)}
                    size="sm"
                    className="gap-1"
                  >
                    {Object.entries(searchTypeInfo).map(
                      ([key, { icon: Icon, desc }]) => (
                        <Tooltip key={key}>
                          <TooltipTrigger asChild>
                            <ToggleGroupItem
                              value={key}
                              className="gap-1.5 px-3"
                            >
                              <Icon className="h-3.5 w-3.5" />
                              {key.charAt(0).toUpperCase() + key.slice(1)}
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
                      Filter by Video
                    </Label>
                    <Select
                      value={videoFilter}
                      onValueChange={setVideoFilter}
                    >
                      <SelectTrigger className="h-9 w-55">
                        <SelectValue placeholder="All videos" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">All videos</SelectItem>
                        {videos.map((v) => (
                          <SelectItem key={v.video_id} value={v.video_id}>
                            {v.video_title.length > 35
                              ? v.video_title.slice(0, 35) + "…"
                              : v.video_title}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Loading spinner */}
          {isSearching && (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="text-muted-foreground h-8 w-8 animate-spin" />
            </div>
          )}

          {/* Search Results */}
          {!isSearching && results.length > 0 && (
            <div className="space-y-3">
              <p className="text-muted-foreground pl-1 text-sm font-medium">
                {results.length} result{results.length !== 1 ? "s" : ""} found
              </p>
              {results.map((r, i) => {
                const key = `${r.video_id}-${r.start_seconds}`;
                const isLoading = loadingVideoId === key;
                return (
                  <motion.div
                    key={`${key}-${i}`}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.04 }}
                  >
                    <Card
                      className={cn(
                        "group cursor-pointer border transition-all hover:shadow-md",
                        "hover:border-primary/40",
                        isLoading && "border-primary/30 opacity-80",
                      )}
                      onClick={() => handleResultClick(r)}
                    >
                      <CardContent className="flex items-start gap-4 py-4">
                        {/* Play indicator */}
                        <div
                          className={cn(
                            "bg-muted group-hover:bg-primary/10 flex h-10 w-10 shrink-0 items-center justify-center rounded-full transition-colors",
                            isLoading && "bg-primary/10",
                          )}
                        >
                          {isLoading ? (
                            <Loader2 className="text-primary h-4 w-4 animate-spin" />
                          ) : (
                            <Play className="text-muted-foreground group-hover:text-primary h-4 w-4 transition-colors" />
                          )}
                        </div>

                        {/* Content */}
                        <div className="min-w-0 flex-1">
                          <div className="mb-1.5 flex flex-wrap items-center gap-2">
                            <span className="truncate text-sm font-semibold">
                              {r.video_title}
                            </span>
                            <Badge
                              variant="secondary"
                              className="shrink-0 gap-1 font-mono text-xs"
                            >
                              <Clock className="h-3 w-3" />
                              {r.timestamp}
                            </Badge>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Badge
                                  variant="outline"
                                  className="shrink-0 font-mono text-xs"
                                >
                                  {formatScore(r.score)}
                                </Badge>
                              </TooltipTrigger>
                              <TooltipContent>
                                <p className="text-xs">
                                  Relevance score (raw: {r.score.toFixed(4)})
                                </p>
                              </TooltipContent>
                            </Tooltip>
                          </div>
                          <p className="text-muted-foreground line-clamp-2 text-sm leading-relaxed">
                            {r.text}
                          </p>
                        </div>
                      </CardContent>
                    </Card>
                  </motion.div>
                );
              })}
            </div>
          )}

          {/* Empty states */}
          {!isSearching && hasSearched && results.length === 0 && (
            <EmptyStateCard message="No results found. Try a different search query or search type. Hybrid search combines semantic meaning with keyword matching." />
          )}

          {/* Initial state — show indexed videos */}
          {!hasSearched && !isSearching && status?.database_connected && (
            <div className="space-y-4">
              <EmptyStateCard message="Enter a query above to find relevant moments in indexed lecture recordings. Try searching for topics like 'tekoäly oppiminen', 'johtaminen', or 'koulutus'." />

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
                      These lecture recordings have been transcribed, chunked,
                      and embedded for semantic search.
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="grid gap-2">
                      {videos.map((v) => (
                        <button
                          key={v.video_id}
                          className="hover:bg-muted/50 flex items-center justify-between rounded-lg px-3 py-2.5 text-left transition-colors"
                          onClick={() => {
                            setVideoFilter(v.video_id);
                            setQuery("");
                            searchInputRef.current?.focus();
                          }}
                        >
                          <div className="flex items-center gap-3 min-w-0">
                            <div className="bg-muted flex h-8 w-8 shrink-0 items-center justify-center rounded-md">
                              <Video className="text-muted-foreground h-4 w-4" />
                            </div>
                            <span className="truncate text-sm font-medium">
                              {v.video_title}
                            </span>
                          </div>
                          <Badge
                            variant="outline"
                            className="ml-2 shrink-0 text-xs"
                          >
                            {v.segment_count} segments
                          </Badge>
                        </button>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>
          )}

          <FeedbackButton demoType="video-search" />
        </div>

        {/* Video Player Dialog */}
        <Dialog open={playerOpen} onOpenChange={setPlayerOpen}>
          <DialogContent className="max-w-3xl p-0 overflow-hidden">
            <DialogHeader className="px-6 pt-6 pb-0">
              <DialogTitle className="pr-8 text-base leading-snug">
                {playingVideo?.title}
              </DialogTitle>
              {playingVideo?.timestamp && (
                <p className="text-muted-foreground text-sm">
                  Playing from {playingVideo.timestamp}
                </p>
              )}
            </DialogHeader>
            <div className="px-6 pb-6 pt-4">
              {playingVideo && (
                <video
                  key={playingVideo.url}
                  controls
                  autoPlay
                  className="aspect-video w-full rounded-lg bg-black"
                >
                  <source
                    src={`${playingVideo.url}#t=${Math.floor(playingVideo.startSeconds)}`}
                    type="video/mp4"
                  />
                  Your browser does not support video playback.
                </video>
              )}
            </div>
          </DialogContent>
        </Dialog>
      </motion.div>
    </TooltipProvider>
  );
}
