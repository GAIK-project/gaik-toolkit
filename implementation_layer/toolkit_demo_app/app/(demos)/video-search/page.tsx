"use client";

import { apiFetch } from "@/lib/api-client";
import { EmptyStateCard } from "@/components/demo/result-card";
import { FeedbackButton } from "@/components/feedback";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
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
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { cn } from "@/lib/utils";
import {
  AlertCircle,
  Clock,
  Database,
  Loader2,
  Play,
  Search,
  Video,
  X,
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

export default function VideoSearchPage() {
  const [query, setQuery] = useState("");
  const [searchType, setSearchType] = useState("hybrid");
  const [videoFilter, setVideoFilter] = useState<string>("all");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);

  const [videos, setVideos] = useState<VideoInfo[]>([]);
  const [status, setStatus] = useState<StatusInfo | null>(null);
  const [playingVideo, setPlayingVideo] = useState<{
    url: string;
    title: string;
    startSeconds: number;
  } | null>(null);

  // Fetch status and video list on mount
  useEffect(() => {
    fetchStatus();
    fetchVideos();
  }, []);

  async function fetchStatus() {
    try {
      const res = await apiFetch("/api/video-search/status");
      if (res.ok) {
        setStatus(await res.json());
      }
    } catch {
      // Silently fail - status indicator will show disconnected
    }
  }

  async function fetchVideos() {
    try {
      const res = await apiFetch("/api/video-search/videos");
      if (res.ok) {
        setVideos(await res.json());
      }
    } catch {
      // Silently fail
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
        toast("No results found. Try a different search query.", {
          icon: "🔍",
        });
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

  async function playVideo(videoId: string, title: string, startSeconds: number) {
    try {
      const res = await apiFetch(`/api/video-search/videos/${videoId}/play`);
      if (!res.ok) throw new Error("Failed to get playback URL");
      const data = await res.json();
      setPlayingVideo({ url: data.url, title, startSeconds });
    } catch (error) {
      toast.error("Failed to load video");
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter") {
      handleSearch();
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
    >
      <header className="mb-8 pl-1">
        <h1 className="flex items-center gap-3 font-serif text-3xl font-semibold tracking-tight">
          <Video className="h-8 w-8 text-violet-500" />
          Semantic Dental Video Search
        </h1>
        <p className="text-muted-foreground mt-2 text-lg">
          Search dental education videos by meaning. Find exact moments in
          lecture recordings.
        </p>
      </header>

      {/* Status bar */}
      {status && (
        <div className="mb-6 flex items-center gap-4 text-sm">
          <div className="flex items-center gap-1.5">
            <Database className="h-4 w-4" />
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
        </div>
      )}

      {/* Database not configured warning */}
      {status && !status.database_connected && (
        <Card className="mb-6 border-amber-200 bg-amber-50 dark:border-amber-900 dark:bg-amber-950/20">
          <CardContent className="flex items-start gap-3 pt-6">
            <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-amber-500" />
            <div>
              <p className="font-medium text-amber-800 dark:text-amber-200">
                Database not configured
              </p>
              <p className="text-sm text-amber-700 dark:text-amber-300">
                Set the DATABASE_URL environment variable to connect to a
                PostgreSQL database with pgvector. Video search requires indexed
                content.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="space-y-6">
        {/* Search controls */}
        <Card className="shadow-md">
          <CardHeader className="pb-4">
            <CardTitle>Search Videos</CardTitle>
            <CardDescription>
              Enter a natural language query to find relevant moments in dental
              education videos.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex gap-3">
              <div className="relative flex-1">
                <Search className="text-muted-foreground absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2" />
                <Input
                  placeholder="e.g. root canal procedure steps, fluoride treatment..."
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={handleKeyDown}
                  className="pl-10"
                  disabled={!status?.database_connected}
                />
              </div>
              <Button
                onClick={handleSearch}
                disabled={
                  isSearching || !query.trim() || !status?.database_connected
                }
              >
                {isSearching ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Search className="h-4 w-4" />
                )}
              </Button>
            </div>

            <div className="flex flex-wrap items-center gap-4">
              <div className="space-y-1">
                <Label className="text-xs">Search Type</Label>
                <ToggleGroup
                  type="single"
                  value={searchType}
                  onValueChange={(v) => v && setSearchType(v)}
                  size="sm"
                >
                  <ToggleGroupItem value="hybrid">Hybrid</ToggleGroupItem>
                  <ToggleGroupItem value="semantic">Semantic</ToggleGroupItem>
                  <ToggleGroupItem value="keyword">Keyword</ToggleGroupItem>
                </ToggleGroup>
              </div>

              {videos.length > 0 && (
                <div className="space-y-1">
                  <Label className="text-xs">Filter by Video</Label>
                  <Select value={videoFilter} onValueChange={setVideoFilter}>
                    <SelectTrigger className="w-[200px]">
                      <SelectValue placeholder="All videos" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All videos</SelectItem>
                      {videos.map((v) => (
                        <SelectItem key={v.video_id} value={v.video_id}>
                          {v.video_title.length > 30
                            ? v.video_title.slice(0, 30) + "..."
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

        {/* Video Player */}
        <AnimatePresence>
          {playingVideo && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
            >
              <Card className="overflow-hidden shadow-md">
                <CardHeader className="flex flex-row items-center justify-between pb-2">
                  <CardTitle className="text-lg">
                    {playingVideo.title}
                  </CardTitle>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setPlayingVideo(null)}
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </CardHeader>
                <CardContent>
                  <video
                    src={`${playingVideo.url}#t=${playingVideo.startSeconds}`}
                    controls
                    autoPlay
                    className="w-full rounded-lg"
                    style={{ maxHeight: "400px" }}
                  />
                </CardContent>
              </Card>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Search Results */}
        {isSearching && (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="text-muted-foreground h-8 w-8 animate-spin" />
          </div>
        )}

        {!isSearching && results.length > 0 && (
          <div className="space-y-3">
            <p className="text-muted-foreground text-sm">
              {results.length} result{results.length !== 1 ? "s" : ""} found
            </p>
            {results.map((r, i) => (
              <motion.div
                key={`${r.video_id}-${r.start_seconds}-${i}`}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.05 }}
              >
                <Card className="hover:border-primary/30 cursor-pointer transition-colors shadow-sm">
                  <CardContent className="flex items-start gap-4 pt-5">
                    <Button
                      variant="outline"
                      size="icon"
                      className="mt-1 shrink-0"
                      onClick={() =>
                        playVideo(r.video_id, r.video_title, r.start_seconds)
                      }
                    >
                      <Play className="h-4 w-4" />
                    </Button>
                    <div className="min-w-0 flex-1">
                      <div className="mb-1 flex items-center gap-2">
                        <span className="truncate font-medium">
                          {r.video_title}
                        </span>
                        <Badge variant="secondary" className="shrink-0">
                          <Clock className="mr-1 h-3 w-3" />
                          {r.timestamp}
                        </Badge>
                        <Badge
                          variant="outline"
                          className="shrink-0 font-mono text-xs"
                        >
                          {(r.score * 100).toFixed(0)}%
                        </Badge>
                      </div>
                      <p className="text-muted-foreground line-clamp-3 text-sm">
                        {r.text}
                      </p>
                    </div>
                  </CardContent>
                </Card>
              </motion.div>
            ))}
          </div>
        )}

        {!isSearching && hasSearched && results.length === 0 && (
          <EmptyStateCard message="No results found. Try a different search query or search type. Hybrid search combines semantic meaning with keyword matching." />
        )}

        {!hasSearched && !isSearching && status?.database_connected && (
          <EmptyStateCard message="Enter a query above to find relevant moments in indexed dental lecture recordings. Try searching for procedures, treatments, or specific topics." />
        )}

        <FeedbackButton demoType="video-search" />
      </div>
    </motion.div>
  );
}
