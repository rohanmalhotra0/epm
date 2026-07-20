// Chat file-attachment upload. Like project import (see data.ts), this cannot go
// through `api()` because that helper always sets a JSON content-type; multipart
// uploads need the browser to set the boundary itself.

import { ApiError } from "./client";

export type AttachmentKind = "chartOfAccounts" | "layout" | "dataTable" | "unknown";

export interface AttachmentOut {
  id: string;
  conversationId: string;
  projectId: string;
  filename: string;
  mediaType: string;
  sizeBytes: number;
  checksum: string;
  sheetNames: string[];
  kindGuess: AttachmentKind;
}

export const ACCEPTED_EXTENSIONS = [".xlsx", ".xlsm", ".csv", ".txt"];
export const MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024;

const KIND_LABELS: Record<string, string> = {
  chartOfAccounts: "chart of accounts",
  layout: "layout",
  dataTable: "data table",
  unknown: "file",
};

/** Human-readable label for a `kindGuess` (tolerant of unknown/missing values). */
export function attachmentKindLabel(kind: string | undefined | null): string {
  return (kind && KIND_LABELS[kind]) || kind || "file";
}

/** Client-side pre-flight check. Returns a human-readable rejection reason, or null if OK. */
export function validateAttachmentFile(file: File): string | null {
  const name = file.name.toLowerCase();
  if (!ACCEPTED_EXTENSIONS.some((ext) => name.endsWith(ext))) {
    return `Only ${ACCEPTED_EXTENSIONS.join(", ")} files are supported.`;
  }
  if (file.size > MAX_ATTACHMENT_BYTES) {
    return "Files must be 10 MB or smaller.";
  }
  return null;
}

/** POST a spreadsheet/CSV as multipart form data. Returns the stored attachment. */
export async function uploadAttachment(conversationId: string, file: File): Promise<AttachmentOut> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`/api/conversations/${conversationId}/attachments`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as AttachmentOut;
}
