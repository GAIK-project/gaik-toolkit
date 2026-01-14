"use client";

import { useState, useRef, useEffect } from "react";
import { motion } from "motion/react";
import { Mic, Loader2, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { FileUpload } from "@/components/demo/file-upload";
import { DemoStepper } from "@/components/demo/demo-stepper";
import {
  ResultCard,
  ResultText,
  LoadingCard,
  EmptyStateCard,
} from "@/components/demo/result-card";
import { Step } from "@/components/demo/step-indicator";
import toast from "react-hot-toast";

interface TranscribeResult {
  filename: string;
  raw_transcript: string;
  enhanced_transcript: string | null;
  job_id: string;
}

export default function TranscriberPage() {
  const [file, setFile] = useState<File | null>(null);
  const [customContext, setCustomContext] = useState("");
  const [enhanced, setEnhanced] = useState(true);
  const [compressAudio, setCompressAudio] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<TranscribeResult | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  const flowSteps: Step[] = [
    {
      id: "upload",
      name: "Upload",
      status: file ? "completed" : "pending",
    },
    {
      id: "transcribe",
      name: "Transcribe",
      status: result ? "completed" : "pending",
    },
    {
      id: "review",
      name: "Review",
      status: result ? "completed" : "pending",
    },
  ];

  async function handleSubmit(): Promise<void> {
    if (isLoading) return; // Prevent double-click

    if (!file) {
      toast.error("Please select an audio/video file first");
      return;
    }

    // Abort previous request if any
    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();

    setIsLoading(true);
    setResult(null);

    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("custom_context", customContext);
      formData.append("enhanced", String(enhanced));
      formData.append("compress_audio", String(compressAudio));

      const response = await fetch("/api/transcribe", {
        method: "POST",
        body: formData,
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok) {
        let errorMessage = "Failed to transcribe";
        try {
          const error = await response.json();
          errorMessage = error.detail || errorMessage;
        } catch {
          // JSON parsing failed, use default message
        }
        throw new Error(errorMessage);
      }

      const data = await response.json();
      setResult(data);
      toast.success("Transcription complete!");
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") {
        return; // Request was aborted, don't show error
      }
      toast.error(error instanceof Error ? error.message : "An error occurred");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
    >
      <header className="mb-8">
        <h1 className="flex items-center gap-3 font-serif text-3xl font-semibold tracking-tight">
          <Mic className="h-8 w-8" />
          Audio/Video Transcriber
        </h1>
        <p className="text-muted-foreground mt-2">
          Transcribe audio and video with Whisper and optional GPT enhancement
        </p>
      </header>

      <DemoStepper steps={flowSteps} className="mb-8" />

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Input Section */}
        <Card>
          <CardHeader>
            <CardTitle>Upload Media</CardTitle>
            <CardDescription>
              Select an audio or video file to transcribe
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <FileUpload
              accept=".mp3,.wav,.m4a,.mp4,.webm,.ogg,.flac"
              maxSize={50}
              onFileSelect={setFile}
              onFileRemove={() => {
                setFile(null);
                setResult(null);
              }}
              disabled={isLoading}
            />

            <div className="space-y-2">
              <Label htmlFor="context">Custom Context (Optional)</Label>
              <Textarea
                id="context"
                value={customContext}
                onChange={(e) => setCustomContext(e.target.value)}
                placeholder="Add context to help with transcription accuracy (e.g., speaker names, technical terms, topic)..."
                disabled={isLoading}
                rows={3}
              />
            </div>

            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label htmlFor="enhanced">Enhanced Transcript</Label>
                  <p className="text-muted-foreground text-xs">
                    Use LLM to improve readability
                  </p>
                </div>
                <Switch
                  id="enhanced"
                  checked={enhanced}
                  onCheckedChange={setEnhanced}
                  disabled={isLoading}
                />
              </div>

              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label htmlFor="compress">Compress Audio</Label>
                  <p className="text-muted-foreground text-xs">
                    Compress before sending (faster upload)
                  </p>
                </div>
                <Switch
                  id="compress"
                  checked={compressAudio}
                  onCheckedChange={setCompressAudio}
                  disabled={isLoading}
                />
              </div>
            </div>

            <Button
              onClick={handleSubmit}
              disabled={!file || isLoading}
              className="w-full"
              size="lg"
            >
              {isLoading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Transcribing...
                </>
              ) : (
                <>
                  <Sparkles className="mr-2 h-4 w-4" />
                  Transcribe
                </>
              )}
            </Button>
          </CardContent>
        </Card>

        {/* Results Section */}
        <div className="space-y-4">
          {isLoading && (
            <LoadingCard
              message="Transcribing audio..."
              subMessage="This may take a while for longer files"
            />
          )}

          {result && !isLoading && (
            <ResultCard
              title="Transcription Result"
              description={`File: ${result.filename}`}
              delay={0}
            >
              {result.enhanced_transcript ? (
                <Tabs defaultValue="enhanced" className="w-full">
                  <TabsList className="grid w-full grid-cols-2">
                    <TabsTrigger value="enhanced">Enhanced</TabsTrigger>
                    <TabsTrigger value="raw">Raw</TabsTrigger>
                  </TabsList>
                  <TabsContent value="enhanced" className="mt-4">
                    <ResultText
                      content={result.enhanced_transcript}
                      maxHeight="400px"
                    />
                  </TabsContent>
                  <TabsContent value="raw" className="mt-4">
                    <ResultText
                      content={result.raw_transcript}
                      maxHeight="400px"
                    />
                  </TabsContent>
                </Tabs>
              ) : (
                <ResultText
                  content={result.raw_transcript || "No transcript generated"}
                  maxHeight="400px"
                />
              )}
            </ResultCard>
          )}

          {!result && !isLoading && (
            <EmptyStateCard message="Upload an audio/video file to see transcription here" />
          )}
        </div>
      </div>
    </motion.div>
  );
}
