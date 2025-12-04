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
  title: "Parser",
};

const parserTabs = [
  {
    name: "Vision",
    code: `from gaik.parsers import VisionParser

# Vision-based parsing with GPT-4V
parser = VisionParser(config)
pages = parser.convert_pdf("document.pdf")`,
  },
  {
    name: "PyMuPDF",
    code: `from gaik.parsers import PyMuPDFParser

# Fast local PDF parsing
parser = PyMuPDFParser()
result = parser.parse_document("document.pdf")`,
  },
  {
    name: "DOCX",
    code: `from gaik.parsers import DocxParser

# Word document parsing
parser = DocxParser()
result = parser.parse_document("document.docx")`,
  },
];

export default function ParserPage() {
  return (
    <>
      <header className="mb-8">
        <h1 className="text-3xl font-bold">Document Parser</h1>
        <p className="mt-2 text-muted-foreground">
          Parse PDFs and Word documents with vision models, PyMuPDF, or Docling
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle>Coming Soon</CardTitle>
          <CardDescription>
            Interactive demo for the Parser component
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            The Parser component supports multiple backends: VisionParser
            (GPT-4V), PyMuPDFParser (fast local), DocxParser (Word documents),
            and DoclingParser (advanced OCR).
          </p>
          <CodeBlock language="python" tabs={parserTabs} />
          <Button asChild>
            <a
              href="https://github.com/GAIK-project/gaik-toolkit/tree/main/packages/python/gaik/src/gaik/parsers"
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
