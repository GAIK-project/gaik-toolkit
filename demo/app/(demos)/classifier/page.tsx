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
  title: "Classifier",
};

const exampleCode = `from gaik.doc_classifier import DocumentClassifier

classifier = DocumentClassifier(config)
results = classifier.classify(
    file_or_dir="documents/",
    classes=["invoice", "receipt", "contract", "report"]
)

# Returns: {"doc.pdf": {"class": "invoice", "confidence": 0.95}}`;

export default function ClassifierPage() {
  return (
    <>
      <header className="mb-8">
        <h1 className="text-3xl font-bold">Document Classifier</h1>
        <p className="mt-2 text-muted-foreground">
          Classify documents into predefined categories using LLM analysis
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle>Coming Soon</CardTitle>
          <CardDescription>
            Interactive demo for the Classifier component
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            The Classifier analyzes the first page of documents and categorizes
            them based on your defined classes, returning confidence scores and
            reasoning.
          </p>
          <CodeBlock language="python" filename="classifier.py" code={exampleCode} />
          <Button asChild>
            <a
              href="https://github.com/GAIK-project/gaik-toolkit/tree/main/packages/python/gaik/src/gaik/doc_classifier"
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
