import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { CodeBlock } from "@/components/code-block";

export const metadata = {
  title: "Transcriber",
};

const exampleCode = `from gaik.transcriber import Transcriber

transcriber = Transcriber(
    api_config=config,
    enhanced_transcript=True
)
result = transcriber.transcribe("meeting.mp4")

print(result.raw_transcript)
print(result.enhanced_transcript)`;

export default function TranscriberPage() {
  return (
    <>
      <header className="mb-8">
        <h1 className="text-3xl font-bold">Audio/Video Transcriber</h1>
        <p className="mt-2 text-muted-foreground">
          Transcribe audio and video with Whisper and optional GPT enhancement
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle>Coming Soon</CardTitle>
          <CardDescription>
            Interactive demo for the Transcriber component
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            The Transcriber handles large audio/video files by chunking,
            compressing, and optionally enhancing transcripts with LLM
            post-processing for better readability.
          </p>
          <CodeBlock language="python" filename="transcriber.py" code={exampleCode} />
          <Button asChild>
            <a
              href="https://github.com/GAIK-project/gaik-toolkit/tree/main/packages/python/gaik/src/gaik/transcriber"
              target="_blank"
              rel="noopener noreferrer"
            >
              View Documentation
            </a>
          </Button>
        </CardContent>
      </Card>
    </>
  );
}
