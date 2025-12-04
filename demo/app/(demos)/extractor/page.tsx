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
  title: "Extractor",
};

const exampleCode = `from gaik.extractor import DataExtractor

extractor = DataExtractor(config)
results = extractor.extract(
    extraction_model=InvoiceData,
    user_requirements="Extract invoice details",
    documents=[document_text]
)`;

export default function ExtractorPage() {
  return (
    <>
      <header className="mb-8">
        <h1 className="text-3xl font-bold">Data Extractor</h1>
        <p className="mt-2 text-muted-foreground">
          Extract structured data from documents using natural language
          requirements
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle>Coming Soon</CardTitle>
          <CardDescription>
            Interactive demo for the Extractor component
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            The Extractor component allows you to define a Pydantic model and
            extract structured data from any document using natural language
            instructions.
          </p>
          <CodeBlock language="python" filename="extractor.py" code={exampleCode} />
          <Button asChild>
            <a
              href="https://github.com/GAIK-project/gaik-toolkit/tree/main/packages/python/gaik/src/gaik/extractor"
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
