"use client";

import { motion } from "motion/react";
import { Copy, Check } from "lucide-react";
import { useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface ResultCardProps {
  title: string;
  description?: string;
  children: React.ReactNode;
  copyContent?: string;
  className?: string;
  delay?: number;
}

export function ResultCard({
  title,
  description,
  children,
  copyContent,
  className,
  delay = 0,
}: ResultCardProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    if (!copyContent) return;
    await navigator.clipboard.writeText(copyContent);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay }}
    >
      <Card className={cn("overflow-hidden", className)}>
        <CardHeader className="flex flex-row items-start justify-between space-y-0 pb-2">
          <div>
            <CardTitle className="text-lg">{title}</CardTitle>
            {description && (
              <CardDescription className="mt-1">{description}</CardDescription>
            )}
          </div>
          {copyContent && (
            <Button
              variant="ghost"
              size="icon"
              onClick={handleCopy}
              className="h-8 w-8"
            >
              {copied ? (
                <Check className="h-4 w-4 text-green-600" />
              ) : (
                <Copy className="h-4 w-4" />
              )}
            </Button>
          )}
        </CardHeader>
        <CardContent>{children}</CardContent>
      </Card>
    </motion.div>
  );
}

interface ResultTextProps {
  content: string;
  maxHeight?: string;
  className?: string;
}

export function ResultText({ content, maxHeight = "300px", className }: ResultTextProps) {
  return (
    <div
      className={cn(
        "rounded-md bg-muted p-4 font-mono text-sm overflow-auto whitespace-pre-wrap",
        className
      )}
      style={{ maxHeight }}
    >
      {content}
    </div>
  );
}

interface ResultJsonProps {
  data: unknown;
  maxHeight?: string;
  className?: string;
}

export function ResultJson({ data, maxHeight = "300px", className }: ResultJsonProps) {
  const formatted = JSON.stringify(data, null, 2);

  return (
    <div
      className={cn(
        "rounded-md bg-muted p-4 font-mono text-sm overflow-auto",
        className
      )}
      style={{ maxHeight }}
    >
      <pre>{formatted}</pre>
    </div>
  );
}

interface ConfidenceBarProps {
  value: number;
  label?: string;
  className?: string;
}

export function ConfidenceBar({ value, label, className }: ConfidenceBarProps) {
  const percentage = Math.round(value * 100);
  const getColor = () => {
    if (percentage >= 80) return "bg-green-500";
    if (percentage >= 60) return "bg-yellow-500";
    return "bg-red-500";
  };

  return (
    <div className={cn("space-y-2", className)}>
      {label && (
        <div className="flex justify-between text-sm">
          <span>{label}</span>
          <span className="font-medium">{percentage}%</span>
        </div>
      )}
      <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
        <motion.div
          className={cn("h-full rounded-full", getColor())}
          initial={{ width: 0 }}
          animate={{ width: `${percentage}%` }}
          transition={{ duration: 0.8, ease: "easeOut" }}
        />
      </div>
    </div>
  );
}
