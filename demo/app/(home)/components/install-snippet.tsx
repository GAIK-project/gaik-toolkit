import { ArrowUpRight, Terminal } from "lucide-react";
import { CodeBlock } from "@/components/code-block";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function InstallSnippet() {
  return (
    <section>
      <Card className="bg-card overflow-hidden border shadow-sm">
        <CardHeader>
          <div className="flex items-center gap-3">
            <span className="bg-primary/10 text-primary flex h-10 w-10 items-center justify-center rounded-full">
              <Terminal className="h-5 w-5" />
            </span>
            <CardTitle className="text-xl font-semibold">Quick start</CardTitle>
          </div>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-[1.2fr_0.8fr]">
          <CodeBlock
            language="bash"
            filename="terminal"
            code="pip install gaik[all]"
          />
          <div className="flex flex-col gap-3">
            <Button variant="outline" asChild>
              <a
                href="https://pypi.org/project/gaik/"
                target="_blank"
                rel="noopener noreferrer"
              >
                PyPI Package
                <ArrowUpRight className="h-4 w-4" />
              </a>
            </Button>
            <Button variant="outline" asChild>
              <a
                href="https://gaik-project.github.io/gaik-toolkit/"
                target="_blank"
                rel="noopener noreferrer"
              >
                Documentation
                <ArrowUpRight className="h-4 w-4" />
              </a>
            </Button>
            <Button asChild>
              <a
                href="https://github.com/GAIK-project/gaik-toolkit/tree/main/examples"
                target="_blank"
                rel="noopener noreferrer"
              >
                View Examples
                <ArrowUpRight className="h-4 w-4" />
              </a>
            </Button>
          </div>
        </CardContent>
      </Card>
    </section>
  );
}
