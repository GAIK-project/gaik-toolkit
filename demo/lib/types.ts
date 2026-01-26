/**
 * Shared types used across the demo application
 */

/**
 * Represents a source citation from document retrieval
 */
export interface Source {
  documentName: string;
  pageNumber: string | number | null;
  relevanceScore?: number | null;
}
