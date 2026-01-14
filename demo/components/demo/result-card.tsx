"use client";

import { motion } from "motion/react";
import { Copy, Check, Loader2 } from "lucide-react";
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
import toast from "react-hot-toast";

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
    try {
      await navigator.clipboard.writeText(copyContent);
      setCopied(true);
      toast.success("Copied to clipboard");
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error("Failed to copy to clipboard");
    }
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

export function ResultText({
  content,
  maxHeight = "300px",
  className,
}: ResultTextProps) {
  return (
    <div
      className={cn(
        "bg-muted overflow-auto rounded-md p-4 font-mono text-sm whitespace-pre-wrap",
        className,
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

export function ResultJson({
  data,
  maxHeight = "300px",
  className,
}: ResultJsonProps) {
  const formatted = JSON.stringify(data, null, 2);

  return (
    <div
      className={cn(
        "bg-muted overflow-auto rounded-md p-4 font-mono text-sm",
        className,
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

  function getColor(): string {
    if (percentage >= 80) return "bg-green-500";
    if (percentage >= 60) return "bg-yellow-500";
    return "bg-red-500";
  }

  return (
    <div className={cn("space-y-2", className)}>
      {label && (
        <div className="flex justify-between text-sm">
          <span>{label}</span>
          <span className="font-medium">{percentage}%</span>
        </div>
      )}
      <div className="bg-muted h-2 w-full overflow-hidden rounded-full">
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

interface LoadingCardProps {
  message: string;
  subMessage?: string;
}

export function LoadingCard({ message, subMessage }: LoadingCardProps) {
  return (
    <Card>
      <CardContent className="flex items-center justify-center py-12">
        <div className="text-center">
          <Loader2 className="text-primary mx-auto h-8 w-8 animate-spin" />
          <p className="text-muted-foreground mt-2">{message}</p>
          {subMessage && (
            <p className="text-muted-foreground mt-1 text-xs">{subMessage}</p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

interface EmptyStateCardProps {
  message: string;
}

export function EmptyStateCard({ message }: EmptyStateCardProps) {
  return (
    <Card className="border-dashed">
      <CardContent className="flex items-center justify-center py-12">
        <p className="text-muted-foreground text-center">{message}</p>
      </CardContent>
    </Card>
  );
}
