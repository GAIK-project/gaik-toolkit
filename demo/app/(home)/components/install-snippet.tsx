"use client";

import { CodeBlock } from "@/components/code-block";
import { GitHubIcon } from "@/components/github-icon";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ArrowUpRight, BookOpen, Package, Terminal } from "lucide-react";
import { motion } from "motion/react";

export function InstallSnippet() {
  return (
    <section>
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-100px" }}
        transition={{ duration: 0.5, ease: "easeOut" }}
      >
        <Card className="bg-card overflow-hidden border shadow-sm">
          <CardHeader>
            <div className="flex items-center gap-3">
              <span className="bg-primary/10 text-primary flex h-10 w-10 items-center justify-center rounded-full">
                <Terminal className="h-5 w-5" />
              </span>
              <CardTitle className="text-xl font-semibold">
                Quick start
              </CardTitle>
            </div>
          </CardHeader>
          <CardContent className="grid gap-4 md:grid-cols-[1.2fr_0.8fr]">
            <CodeBlock
              language="bash"
              filename="terminal"
              code="pip install gaik[all]"
            />
            <div className="flex h-full flex-col gap-3">
              <a
                href="https://pypi.org/project/gaik/"
                target="_blank"
                rel="noopener noreferrer"
                className="bg-background hover:bg-accent hover:text-accent-foreground dark:bg-input/30 dark:border-input dark:hover:bg-input/50 inline-flex h-auto flex-1 items-center justify-center gap-2 rounded-md border px-4 py-2 text-sm font-medium shadow-xs transition-all"
              >
                <Package className="h-4 w-4" />
                PyPI Package
                <ArrowUpRight className="h-4 w-4" />
              </a>
              <a
                href="https://gaik-project.github.io/gaik-toolkit/"
                target="_blank"
                rel="noopener noreferrer"
                className="bg-background hover:bg-accent hover:text-accent-foreground dark:bg-input/30 dark:border-input dark:hover:bg-input/50 inline-flex h-auto flex-1 items-center justify-center gap-2 rounded-md border px-4 py-2 text-sm font-medium shadow-xs transition-all"
              >
                <BookOpen className="h-4 w-4" />
                Documentation
                <ArrowUpRight className="h-4 w-4" />
              </a>
              <a
                href="https://github.com/GAIK-project/gaik-toolkit/tree/main/examples"
                target="_blank"
                rel="noopener noreferrer"
                className="bg-primary text-primary-foreground hover:bg-primary/90 inline-flex h-auto flex-1 items-center justify-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-all"
              >
                <GitHubIcon className="h-4 w-4" />
                View Examples
                <ArrowUpRight className="h-4 w-4" />
              </a>
            </div>
          </CardContent>
        </Card>
      </motion.div>
    </section>
  );
}
