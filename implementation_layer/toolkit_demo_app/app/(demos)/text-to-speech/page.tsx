"use client";

import { apiFetch, RateLimitError } from "@/lib/api-client";
import { FeedbackButton } from "@/components/feedback";
import {
  EmptyStateCard,
  LoadingCard,
  ResultCard,
} from "@/components/demo/result-card";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ArrowLeft, ChevronDown, Download, RotateCcw, Volume2 } from "lucide-react";
import { motion } from "motion/react";
import { useRouter } from "next/navigation";
import posthog from "posthog-js";
import { useEffect, useMemo, useState } from "react";
import toast from "react-hot-toast";

const MAX_CHARACTERS = 1000;
const VOICES = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"] as const;
const LANGUAGES = ["fi", "en"] as const;

const EXAMPLE_TEXT = `Päivämäärä 10.04.2025.
Kohde: 4120-01 Revontulentie 3, 02100 Espoo, Toimistotalo Revontuli, osittainen purku.
Työviikko 4.
Sää: +6 astetta, puolipilvistä, tuuli noin 4 m/s.
Resurssit: työnjohtajia 1 henkilö, omia työntekijöitä 3 henkilöä, asbestipurku-urakoitsijan työntekijöitä 4 henkilöä, muita alihankkijoita 2 henkilöä. Yhteensä 10 henkilöä.
Päivän työt: asbestipurku jatkui kellarikerroksen teknisissä tiloissa suunnitelman mukaisesti. Sisäpurkua tehtiin kolmannessa kerroksessa; käytävätilojen väliseinät, lasiseinät ja vanhat toimistokalusteet purettiin. Lajittelua tehtiin sisäpihalla, ja romun ajoa suoritettiin kahdella kuormalla kaatopaikalle. Metallijae ja puu eroteltiin erikseen.
Päivän tapahtumat: kolmannen kerroksen keittiötilasta löytyi avauksen yhteydessä asbestia sisältävä vanha putkieriste, jota ei ollut alkuperäisessä kartoituksessa. Alue eristettiin välittömästi ja työ siellä keskeytettiin.`;

type Voice = (typeof VOICES)[number];
type Language = (typeof LANGUAGES)[number];

interface TextToSpeechResult {
  filename: string;
  job_id: string;
  model: string;
  voice: string;
  language: string;
  response_format: string;
  content_type: string;
  character_count: number;
  audio_base64: string;
}

export default function TextToSpeechPage() {
  const router = useRouter();
  const [text, setText] = useState("");
  const [voice, setVoice] = useState<Voice>("alloy");
  const [language, setLanguage] = useState<Language>("fi");
  const [isLoading, setIsLoading] = useState(false);
  const [howItWorksOpen, setHowItWorksOpen] = useState(false);
  const [result, setResult] = useState<TextToSpeechResult | null>(null);

  function loadExample(): void {
    setText(EXAMPLE_TEXT.slice(0, MAX_CHARACTERS));
    setLanguage("fi");
    setResult(null);
  }

  function resetDemo(): void {
    setText("");
    setVoice("alloy");
    setLanguage("fi");
    setResult(null);
  }

  const audioUrl = useMemo(() => {
    if (!result) return null;
    const binary = atob(result.audio_base64);
    const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
    const blob = new Blob([bytes], { type: result.content_type });
    return URL.createObjectURL(blob);
  }, [result]);

  useEffect(() => {
    return () => {
      if (audioUrl) {
        URL.revokeObjectURL(audioUrl);
      }
    };
  }, [audioUrl]);

  async function handleSubmit(): Promise<void> {
    if (isLoading) return;
    const normalizedText = text.trim();
    if (!normalizedText) {
      toast.error("Please enter text first");
      return;
    }
    if (normalizedText.length > MAX_CHARACTERS) {
      toast.error(`Text cannot exceed ${MAX_CHARACTERS} characters`);
      return;
    }

    setIsLoading(true);
    setResult(null);

    try {
      const formData = new FormData();
      formData.append("text", normalizedText);
      formData.append("voice", voice);
      formData.append("language", language);

      const response = await apiFetch("/api/text-to-speech", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const error = await response.json().catch(() => null);
        throw new Error(error?.detail ?? "Failed to generate audio");
      }

      const data = (await response.json()) as TextToSpeechResult;
      setResult(data);
      posthog.capture("tts_generated", {
        language: data.language,
        voice: data.voice,
        characters: data.character_count,
        model: data.model,
      });
      toast.success("Audio generated successfully");
    } catch (error) {
      if (error instanceof RateLimitError) return;
      toast.error(error instanceof Error ? error.message : "An error occurred");
    } finally {
      setIsLoading(false);
    }
  }

  function handleDownload(): void {
    if (!audioUrl || !result) return;
    const link = document.createElement("a");
    link.href = audioUrl;
    link.download = result.filename;
    link.click();
  }

  const characterCount = text.length;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
    >
      <header className="mb-8">
        <Button
          variant="ghost"
          className="mb-4 -ml-3 gap-2"
          onClick={() => router.push("/")}
        >
          <ArrowLeft className="h-4 w-4" />
          Back
        </Button>
        <h1 className="flex items-center gap-3 font-serif text-3xl font-semibold tracking-tight">
          <Volume2 className="h-8 w-8" />
          Text-to-Speech
        </h1>
        <p className="text-muted-foreground mt-2">
          Convert text into downloadable speech audio using OpenAI or Azure OpenAI.
        </p>
      </header>

      <div className="grid gap-6 md:gap-8 lg:grid-cols-2">
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <CardTitle>Input Text</CardTitle>
                  <CardDescription>
                    Enter up to {MAX_CHARACTERS} characters and generate spoken audio.
                  </CardDescription>
                </div>
                <div className="flex gap-2">
                  <Button type="button" variant="outline" size="sm" onClick={loadExample} disabled={isLoading}>
                    Load Example
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={resetDemo}
                    disabled={isLoading || (!text && !result && voice === "alloy" && language === "fi")}
                    className="gap-2"
                  >
                    <RotateCcw className="h-4 w-4" />
                    Reset
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="space-y-2">
                <Label htmlFor="tts-text">Text</Label>
                <Textarea
                  id="tts-text"
                  value={text}
                  onChange={(event) => setText(event.target.value.slice(0, MAX_CHARACTERS))}
                  placeholder="Write the text you want to convert into speech..."
                  rows={10}
                  disabled={isLoading}
                />
                <div className="text-muted-foreground flex justify-end text-xs">
                  {characterCount}/{MAX_CHARACTERS}
                </div>
              </div>

              <Accordion type="single" collapsible defaultValue="settings" className="w-full">
                <AccordionItem value="settings" className="border-none">
                  <AccordionTrigger className="text-muted-foreground hover:text-foreground py-2 text-sm font-medium">
                    Speech Settings
                  </AccordionTrigger>
                  <AccordionContent className="space-y-4 pt-4">
                    <div className="space-y-2">
                      <div className="space-y-1">
                        <Label htmlFor="tts-language">Language</Label>
                        <p className="text-muted-foreground text-xs">The model can also infer the text language automatically.</p>
                      </div>
                      <Select value={language} onValueChange={(value: Language) => setLanguage(value)} disabled={isLoading}>
                        <SelectTrigger id="tts-language">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="fi">fi</SelectItem>
                          <SelectItem value="en">en</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="tts-voice">Voice</Label>
                      <Select value={voice} onValueChange={(value: Voice) => setVoice(value)} disabled={isLoading}>
                        <SelectTrigger id="tts-voice">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {VOICES.map((option) => (
                            <SelectItem key={option} value={option}>
                              {option}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>

                  </AccordionContent>
                </AccordionItem>
              </Accordion>

              <Button
                onClick={handleSubmit}
                disabled={isLoading || !text.trim()}
                className="w-full"
                size="lg"
              >
                {isLoading ? "Generating audio..." : "Generate Speech"}
              </Button>
            </CardContent>
          </Card>

          <Card>
            <button
              type="button"
              className="flex w-full items-center justify-between px-6 py-5 text-left"
              onClick={() => setHowItWorksOpen((current) => !current)}
            >
              <div>
                <CardTitle>How It Works</CardTitle>
                <CardDescription className="mt-1">
                  Convert text into speech and download the generated audio.
                </CardDescription>
              </div>
              <div className="text-muted-foreground flex items-center gap-2 text-sm font-medium">
                {howItWorksOpen ? "Hide" : "Show"}
                <ChevronDown className={`h-4 w-4 transition-transform ${howItWorksOpen ? "rotate-180" : ""}`} />
              </div>
            </button>
            {howItWorksOpen ? (
              <CardContent className="text-muted-foreground space-y-3 text-sm leading-6">
                <p>
                  <strong>1. Enter text:</strong> Add the text you want the model to speak. The demo accepts up to 1000 characters.
                </p>
                <p>
                  <strong>2. Choose voice and language:</strong> Select one of the supported voices and choose whether the speech should be generated in Finnish or English.
                </p>
                <p>
                  <strong>3. Generate audio:</strong> The backend uses the `gpt-4o-mini-tts` text-to-speech model through the standalone GAIK `TextToSpeech` software component.
                </p>
                <p>
                  <strong>4. Review and download:</strong> After generation, you can play the audio in the browser and download the generated file.
                </p>
              </CardContent>
            ) : null}
          </Card>
        </div>

        <div>
          {isLoading ? (
            <LoadingCard
              title="Generating Audio"
              description="The text is being converted into speech."
              feedbackSlot={<FeedbackButton demoType="text-to-speech" />}
              delay={0}
            />
          ) : result && audioUrl ? (
            <ResultCard
              title="Generated Audio"
              description={`Voice: ${result.voice} - Language: ${result.language}`}
              feedbackSlot={<FeedbackButton demoType="text-to-speech" />}
              delay={0}
            >
              <div className="space-y-6">
                <div className="grid gap-4 sm:grid-cols-2">
                  <Card className="bg-muted/40">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-base">Generation Details</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-1 text-sm">
                      <p><strong>Model:</strong> {result.model}</p>
                      <p><strong>Voice:</strong> {result.voice}</p>
                      <p><strong>Language:</strong> {result.language}</p>
                      <p><strong>Characters:</strong> {result.character_count}</p>
                    </CardContent>
                  </Card>
                  <Card className="bg-muted/40">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-base">Audio File</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3 text-sm">
                      <p><strong>Filename:</strong> {result.filename}</p>
                      <p><strong>Format:</strong> {result.response_format}</p>
                      <Button onClick={handleDownload} className="w-full gap-2">
                        <Download className="h-4 w-4" />
                        Download Audio
                      </Button>
                    </CardContent>
                  </Card>
                </div>

                <audio controls className="w-full" src={audioUrl} />
              </div>
            </ResultCard>
          ) : (
            <EmptyStateCard
              icon={Volume2}
              title="No audio generated yet"
              description="Enter text, choose a voice and language, then generate speech."
              variant="bordered"
              feedbackSlot={<FeedbackButton demoType="text-to-speech" />}
              delay={0}
            />
          )}
        </div>
      </div>
    </motion.div>
  );
}
