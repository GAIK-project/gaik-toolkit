/**
 * Shared types used across the demo application
 */

/**
 * Demo types available in the application
 */
export type DemoType =
  | "classifier"
  | "construction-diary"
  | "extractor"
  | "vision-extractor"
  | "parser"
  | "transcriber"
  | "incident-report"
  | "rag"
  | "audio-structured"
  | "dental-transcription"
  | "document-structured"
  | "video-search"
  | "luvata-order"
  | "text-to-speech"
  | "postgres-agent"
  | "report-writer";

/**
 * User feedback stored in the database
 */
export interface Feedback {
  id: string;
  user_id: string;
  demo_type: DemoType;
  rating: number;
  comment: string | null;
  created_at: string;
  updated_at: string;
}

/**
 * Form data for submitting feedback
 */
export interface FeedbackFormData {
  rating: number;
  comment?: string;
}

/**
 * Represents a source citation from document retrieval
 */
export interface Source {
  documentName: string;
  pageNumber: string | number | null;
  relevanceScore?: number | null;
}
