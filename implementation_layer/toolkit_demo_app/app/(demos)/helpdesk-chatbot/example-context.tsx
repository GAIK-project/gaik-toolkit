"use client";

import type { HelpdeskExample } from "@/lib/helpdesk-chatbot/examples";
import { createContext, useContext } from "react";

// The helpdesk being played. The cards in the chat read its team names and
// category labels from here, so the same cards serve every example.
const ExampleContext = createContext<HelpdeskExample | null>(null);

export const ExampleProvider = ExampleContext.Provider;

export function useHelpdeskExample(): HelpdeskExample {
  const example = useContext(ExampleContext);
  if (!example) throw new Error("ExampleProvider is missing");
  return example;
}
