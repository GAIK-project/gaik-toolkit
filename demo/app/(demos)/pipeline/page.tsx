"use client";

import { useState } from "react";
import { motion } from "motion/react";
import {
  Workflow,
  Loader2,
  Sparkles,
  FileAudio,
  FileText,
  Download,
} from "lucide-react";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { FileUpload } from "@/components/demo/file-upload";
import { DemoStepper } from "@/components/demo/demo-stepper";
import {
  ResultCard,
  ResultText,
  ResultJson,
} from "@/components/demo/result-card";
import { StepIndicator, Step } from "@/components/demo/step-indicator";
import { toast } from "sonner";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface PipelineStep {
  step: number;
  name: string;
  status: "pending" | "in_progress" | "completed" | "error";
  message?: string | null;
}

interface AudioPipelineResult {
  job_id: string;
  steps: PipelineStep[];
  raw_transcript: string | null;
  enhanced_transcript: string | null;
  extracted_data: Record<string, unknown>[] | null;
  pdf_available: boolean;
  error?: string | null;
}

interface DocumentPipelineResult {
  job_id: string;
  steps: PipelineStep[];
  parsed_content: string | null;
  extracted_data: Record<string, unknown>[] | null;
  pdf_available: boolean;
  error?: string | null;
}

function mapSteps(steps: PipelineStep[]): Step[] {
  return steps.map((s) => ({
    id: `step-${s.step}`,
    name: s.name,
    status: s.status,
    message: s.message,
  }));
}

export default function PipelinePage() {
  const [pipelineType, setPipelineType] = useState<"audio" | "document">(
    "audio"
  );

  // Audio pipeline state
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [audioRequirements, setAudioRequirements] = useState("");
  const [enhanced, setEnhanced] = useState(true);
  const [compressAudio, setCompressAudio] = useState(true);
  const [generateAudioPdf, setGenerateAudioPdf] = useState(false);
  const [audioResult, setAudioResult] = useState<AudioPipelineResult | null>(
    null
  );

  // Document pipeline state
  const [docFile, setDocFile] = useState<File | null>(null);
  const [docRequirements, setDocRequirements] = useState("");
  const [parserType, setParserType] = useState("auto");
  const [generateDocPdf, setGenerateDocPdf] = useState(false);
  const [docResult, setDocResult] = useState<DocumentPipelineResult | null>(
    null
  );

  // Shared state
  const [isLoading, setIsLoading] = useState(false);
  const [steps, setSteps] = useState<Step[]>([]);

  const activeFile = pipelineType === "audio" ? audioFile : docFile;
  const activeRequirements =
    pipelineType === "audio" ? audioRequirements : docRequirements;
  const hasResult = pipelineType === "audio" ? audioResult : docResult;

  const flowSteps: Step[] = [
    {
      id: "upload",
      name: "Upload",
      status: activeFile ? "completed" : "pending",
    },
    {
      id: "configure",
      name: "Configure",
      status:
        activeFile && activeRequirements.trim() ? "completed" : "pending",
    },
    {
      id: "review",
      name: "Results",
      status: hasResult ? "completed" : "pending",
    },
  ];

  const handleAudioPipeline = async () => {
    if (!audioFile) {
      toast.error("Please select an audio/video file first");
      return;
    }

    if (!audioRequirements.trim()) {
      toast.error("Please describe what data you want to extract");
      return;
    }

    setIsLoading(true);
    setAudioResult(null);

    // Initialize steps
    const initialSteps: Step[] = [
      { id: "upload", name: "Upload", status: "completed" },
      { id: "transcribe", name: "Transcribe", status: "in_progress" },
      { id: "extract", name: "Extract", status: "pending" },
    ];
    if (generateAudioPdf) {
      initialSteps.push({ id: "pdf", name: "Generate PDF", status: "pending" });
    }
    setSteps(initialSteps);

    try {
      const formData = new FormData();
      formData.append("file", audioFile);
      formData.append("user_requirements", audioRequirements);
      formData.append("generate_pdf", String(generateAudioPdf));
      formData.append("enhanced", String(enhanced));
      formData.append("compress_audio", String(compressAudio));

      const response = await fetch(`${API_URL}/pipeline/audio`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Pipeline failed");
      }

      const data: AudioPipelineResult = await response.json();
      setAudioResult(data);
      setSteps(mapSteps(data.steps));

      if (data.error) {
        toast.error(data.error);
      } else {
        toast.success("Pipeline complete!");
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "An error occurred");
      setSteps((prev) =>
        prev.map((s) =>
          s.status === "in_progress" ? { ...s, status: "error" } : s
        )
      );
    } finally {
      setIsLoading(false);
    }
  };

  const handleDocumentPipeline = async () => {
    if (!docFile) {
      toast.error("Please select a document file first");
      return;
    }

    if (!docRequirements.trim()) {
      toast.error("Please describe what data you want to extract");
      return;
    }

    setIsLoading(true);
    setDocResult(null);

    // Initialize steps
    const initialSteps: Step[] = [
      { id: "upload", name: "Upload", status: "completed" },
      { id: "parse", name: "Parse", status: "in_progress" },
      { id: "extract", name: "Extract", status: "pending" },
    ];
    if (generateDocPdf) {
      initialSteps.push({ id: "pdf", name: "Generate PDF", status: "pending" });
    }
    setSteps(initialSteps);

    try {
      const formData = new FormData();
      formData.append("file", docFile);
      formData.append("user_requirements", docRequirements);
      formData.append("parser_type", parserType);
      formData.append("generate_pdf", String(generateDocPdf));

      const response = await fetch(`${API_URL}/pipeline/document`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Pipeline failed");
      }

      const data: DocumentPipelineResult = await response.json();
      setDocResult(data);
      setSteps(mapSteps(data.steps));

      if (data.error) {
        toast.error(data.error);
      } else {
        toast.success("Pipeline complete!");
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "An error occurred");
      setSteps((prev) =>
        prev.map((s) =>
          s.status === "in_progress" ? { ...s, status: "error" } : s
        )
      );
    } finally {
      setIsLoading(false);
    }
  };

  const downloadPdf = (jobId: string) => {
    window.open(`${API_URL}/pipeline/pdf/${jobId}`, "_blank");
  };

  const resetPipeline = () => {
    setSteps([]);
    setAudioResult(null);
    setDocResult(null);
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
    >
      <header className="mb-8">
        <h1 className="text-3xl font-semibold tracking-tight font-serif flex items-center gap-3">
          <Workflow className="h-8 w-8" />
          Pipeline Demo
        </h1>
        <p className="mt-2 text-muted-foreground">
          End-to-end workflows: Audio/Document to Structured Data with optional
          PDF export
        </p>
      </header>

      <DemoStepper steps={flowSteps} className="mb-8" />

      {/* Pipeline Type Selector */}
      <Tabs
        value={pipelineType}
        onValueChange={(v) => {
          setPipelineType(v as "audio" | "document");
          resetPipeline();
        }}
        className="mb-6"
      >
        <TabsList className="grid w-full max-w-md grid-cols-2">
          <TabsTrigger value="audio" className="gap-2">
            <FileAudio className="h-4 w-4" />
            Audio Pipeline
          </TabsTrigger>
          <TabsTrigger value="document" className="gap-2">
            <FileText className="h-4 w-4" />
            Document Pipeline
          </TabsTrigger>
        </TabsList>

        {/* Audio Pipeline Tab */}
        <TabsContent value="audio" className="mt-6">
          <div className="grid gap-6 lg:grid-cols-2">
            {/* Input Section */}
            <Card>
              <CardHeader>
                <CardTitle>Audio Pipeline</CardTitle>
                <CardDescription>
                  Upload audio → Transcribe → Extract structured data
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <FileUpload
                  accept=".mp3,.wav,.m4a,.mp4,.webm,.ogg,.flac"
                  maxSize={50}
                  onFileSelect={setAudioFile}
                  onFileRemove={() => {
                    setAudioFile(null);
                    resetPipeline();
                  }}
                  disabled={isLoading}
                />

                <div className="space-y-2">
                  <Label htmlFor="audio-requirements">
                    What data do you want to extract?
                  </Label>
                  <Textarea
                    id="audio-requirements"
                    value={audioRequirements}
                    onChange={(e) => setAudioRequirements(e.target.value)}
                    placeholder="E.g., Extract meeting date, attendees, action items, and decisions made..."
                    disabled={isLoading}
                    rows={3}
                  />
                </div>

                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <div className="space-y-0.5">
                      <Label htmlFor="enhanced">Enhanced Transcript</Label>
                      <p className="text-xs text-muted-foreground">
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
                      <p className="text-xs text-muted-foreground">
                        Compress before sending
                      </p>
                    </div>
                    <Switch
                      id="compress"
                      checked={compressAudio}
                      onCheckedChange={setCompressAudio}
                      disabled={isLoading}
                    />
                  </div>

                  <div className="flex items-center justify-between">
                    <div className="space-y-0.5">
                      <Label htmlFor="pdf-audio">Generate PDF Report</Label>
                      <p className="text-xs text-muted-foreground">
                        Create downloadable PDF
                      </p>
                    </div>
                    <Switch
                      id="pdf-audio"
                      checked={generateAudioPdf}
                      onCheckedChange={setGenerateAudioPdf}
                      disabled={isLoading}
                    />
                  </div>
                </div>

                <Button
                  onClick={handleAudioPipeline}
                  disabled={!audioFile || !audioRequirements.trim() || isLoading}
                  className="w-full"
                  size="lg"
                >
                  {isLoading ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Processing...
                    </>
                  ) : (
                    <>
                      <Sparkles className="mr-2 h-4 w-4" />
                      Run Pipeline
                    </>
                  )}
                </Button>
              </CardContent>
            </Card>

            {/* Results Section */}
            <div className="space-y-4">
              {/* Step Indicator */}
              {steps.length > 0 && (
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm">Pipeline Progress</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <StepIndicator steps={steps} orientation="horizontal" />
                  </CardContent>
                </Card>
              )}

              {/* Loading state */}
              {isLoading && (
                <Card>
                  <CardContent className="flex items-center justify-center py-12">
                    <div className="text-center">
                      <Loader2 className="h-8 w-8 animate-spin mx-auto text-primary" />
                      <p className="mt-2 text-muted-foreground">
                        Running pipeline...
                      </p>
                      <p className="text-xs text-muted-foreground mt-1">
                        This may take a while
                      </p>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Results */}
              {audioResult && !isLoading && (
                <>
                  {/* Transcript */}
                  {(audioResult.raw_transcript ||
                    audioResult.enhanced_transcript) && (
                    <ResultCard
                      title="Transcript"
                      copyContent={
                        audioResult.enhanced_transcript ||
                        audioResult.raw_transcript ||
                        ""
                      }
                    >
                      {audioResult.enhanced_transcript ? (
                        <Tabs defaultValue="enhanced" className="w-full">
                          <TabsList className="grid w-full grid-cols-2">
                            <TabsTrigger value="enhanced">Enhanced</TabsTrigger>
                            <TabsTrigger value="raw">Raw</TabsTrigger>
                          </TabsList>
                          <TabsContent value="enhanced" className="mt-4">
                            <ResultText
                              content={audioResult.enhanced_transcript}
                              maxHeight="200px"
                            />
                          </TabsContent>
                          <TabsContent value="raw" className="mt-4">
                            <ResultText
                              content={audioResult.raw_transcript || ""}
                              maxHeight="200px"
                            />
                          </TabsContent>
                        </Tabs>
                      ) : (
                        <ResultText
                          content={audioResult.raw_transcript || ""}
                          maxHeight="200px"
                        />
                      )}
                    </ResultCard>
                  )}

                  {/* Extracted Data */}
                  {audioResult.extracted_data &&
                    audioResult.extracted_data.length > 0 && (
                      <ResultCard
                        title="Extracted Data"
                        copyContent={JSON.stringify(
                          audioResult.extracted_data,
                          null,
                          2
                        )}
                        delay={0.1}
                      >
                        <ResultJson
                          data={audioResult.extracted_data}
                          maxHeight="250px"
                        />
                      </ResultCard>
                    )}

                  {/* PDF Download */}
                  {audioResult.pdf_available && (
                    <Card>
                      <CardContent className="pt-6">
                        <Button
                          onClick={() => downloadPdf(audioResult.job_id)}
                          className="w-full"
                          variant="outline"
                        >
                          <Download className="mr-2 h-4 w-4" />
                          Download PDF Report
                        </Button>
                      </CardContent>
                    </Card>
                  )}
                </>
              )}

              {/* Empty state */}
              {!audioResult && !isLoading && steps.length === 0 && (
                <Card className="border-dashed">
                  <CardContent className="flex items-center justify-center py-12">
                    <p className="text-muted-foreground text-center">
                      Upload an audio file and describe the data you want to
                      extract
                    </p>
                  </CardContent>
                </Card>
              )}
            </div>
          </div>
        </TabsContent>

        {/* Document Pipeline Tab */}
        <TabsContent value="document" className="mt-6">
          <div className="grid gap-6 lg:grid-cols-2">
            {/* Input Section */}
            <Card>
              <CardHeader>
                <CardTitle>Document Pipeline</CardTitle>
                <CardDescription>
                  Upload document → Parse → Extract structured data
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <FileUpload
                  accept=".pdf,.docx"
                  maxSize={20}
                  onFileSelect={setDocFile}
                  onFileRemove={() => {
                    setDocFile(null);
                    resetPipeline();
                  }}
                  disabled={isLoading}
                />

                <div className="space-y-2">
                  <Label htmlFor="parser">Parser Type</Label>
                  <Select
                    value={parserType}
                    onValueChange={setParserType}
                    disabled={isLoading}
                  >
                    <SelectTrigger id="parser">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="auto">Auto-detect</SelectItem>
                      <SelectItem value="pymupdf">PyMuPDF (fast)</SelectItem>
                      <SelectItem value="docx">DOCX Parser</SelectItem>
                      <SelectItem value="vision">Vision (GPT-4V)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="doc-requirements">
                    What data do you want to extract?
                  </Label>
                  <Textarea
                    id="doc-requirements"
                    value={docRequirements}
                    onChange={(e) => setDocRequirements(e.target.value)}
                    placeholder="E.g., Extract invoice number, date, total amount, and line items..."
                    disabled={isLoading}
                    rows={3}
                  />
                </div>

                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <Label htmlFor="pdf-doc">Generate PDF Report</Label>
                    <p className="text-xs text-muted-foreground">
                      Create downloadable PDF
                    </p>
                  </div>
                  <Switch
                    id="pdf-doc"
                    checked={generateDocPdf}
                    onCheckedChange={setGenerateDocPdf}
                    disabled={isLoading}
                  />
                </div>

                <Button
                  onClick={handleDocumentPipeline}
                  disabled={!docFile || !docRequirements.trim() || isLoading}
                  className="w-full"
                  size="lg"
                >
                  {isLoading ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Processing...
                    </>
                  ) : (
                    <>
                      <Sparkles className="mr-2 h-4 w-4" />
                      Run Pipeline
                    </>
                  )}
                </Button>
              </CardContent>
            </Card>

            {/* Results Section */}
            <div className="space-y-4">
              {/* Step Indicator */}
              {steps.length > 0 && (
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm">Pipeline Progress</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <StepIndicator steps={steps} orientation="horizontal" />
                  </CardContent>
                </Card>
              )}

              {/* Loading state */}
              {isLoading && (
                <Card>
                  <CardContent className="flex items-center justify-center py-12">
                    <div className="text-center">
                      <Loader2 className="h-8 w-8 animate-spin mx-auto text-primary" />
                      <p className="mt-2 text-muted-foreground">
                        Running pipeline...
                      </p>
                      <p className="text-xs text-muted-foreground mt-1">
                        This may take a while
                      </p>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Results */}
              {docResult && !isLoading && (
                <>
                  {/* Parsed Content */}
                  {docResult.parsed_content && (
                    <ResultCard
                      title="Parsed Content"
                      copyContent={docResult.parsed_content}
                    >
                      <ResultText
                        content={docResult.parsed_content}
                        maxHeight="200px"
                      />
                    </ResultCard>
                  )}

                  {/* Extracted Data */}
                  {docResult.extracted_data &&
                    docResult.extracted_data.length > 0 && (
                      <ResultCard
                        title="Extracted Data"
                        copyContent={JSON.stringify(
                          docResult.extracted_data,
                          null,
                          2
                        )}
                        delay={0.1}
                      >
                        <ResultJson
                          data={docResult.extracted_data}
                          maxHeight="250px"
                        />
                      </ResultCard>
                    )}

                  {/* PDF Download */}
                  {docResult.pdf_available && (
                    <Card>
                      <CardContent className="pt-6">
                        <Button
                          onClick={() => downloadPdf(docResult.job_id)}
                          className="w-full"
                          variant="outline"
                        >
                          <Download className="mr-2 h-4 w-4" />
                          Download PDF Report
                        </Button>
                      </CardContent>
                    </Card>
                  )}
                </>
              )}

              {/* Empty state */}
              {!docResult && !isLoading && steps.length === 0 && (
                <Card className="border-dashed">
                  <CardContent className="flex items-center justify-center py-12">
                    <p className="text-muted-foreground text-center">
                      Upload a document and describe the data you want to
                      extract
                    </p>
                  </CardContent>
                </Card>
              )}
            </div>
          </div>
        </TabsContent>
      </Tabs>
    </motion.div>
  );
}
