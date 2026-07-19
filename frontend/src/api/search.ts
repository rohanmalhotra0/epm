// Project-wide search used by the command palette.

import { api } from "./client";

export type SearchResultType = "conversation" | "message" | "artifact";

export interface SearchResult {
  type: SearchResultType;
  id: string;
  conversationId?: string;
  title: string;
  snippet?: string;
  updatedAt?: string;
}

export function searchProject(projectId: string, q: string, limit = 20): Promise<{ results: SearchResult[] }> {
  return api<{ results: SearchResult[] }>(
    `/api/projects/${projectId}/search?q=${encodeURIComponent(q)}&limit=${limit}`,
  );
}
