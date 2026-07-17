// Artifacts-panel API client.
//
// Thin typed wrappers over the backend report/edit endpoints (see
// backend/app/api/routes_reports.py). No app-shell dependencies — safe to import
// from anywhere. Base URL comes from VITE_API_BASE (default "" so a Vite dev
// proxy on /api works).

import type {
  FormPreview,
  PromptEditRequest,
  PromptEditResult,
  ReportPreview,
} from "../schemas/types";

const BASE = (import.meta as { env?: { VITE_API_BASE?: string } }).env?.VITE_API_BASE ?? "";

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status} ${detail}`);
  }
  return res.json() as Promise<T>;
}

/** Apply a natural-language edit to a form or report (artifact/table/cell scope). */
export function promptEdit(req: PromptEditRequest, projectId?: string): Promise<PromptEditResult> {
  const q = projectId ? `?projectId=${encodeURIComponent(projectId)}` : "";
  return post<PromptEditResult>(`/api/artifact/edit${q}`, req);
}

export function reportPreview(spec: Record<string, unknown>, projectId?: string): Promise<ReportPreview> {
  const q = projectId ? `?projectId=${encodeURIComponent(projectId)}` : "";
  return post<ReportPreview>(`/api/reports/preview${q}`, { spec });
}

export function formPreview(spec: Record<string, unknown>, projectId?: string): Promise<FormPreview> {
  const q = projectId ? `?projectId=${encodeURIComponent(projectId)}` : "";
  return post<FormPreview>(`/api/forms/preview${q}`, { spec });
}

export function reportRender(
  spec: Record<string, unknown>,
  projectId?: string,
): Promise<{ html: string; csv: string }> {
  const q = projectId ? `?projectId=${encodeURIComponent(projectId)}` : "";
  return post<{ html: string; csv: string }>(`/api/reports/render${q}`, { spec });
}

export interface DownloadResult {
  artifactId: string;
  filename: string;
  checksum: string;
  sizeBytes: number;
  downloadUrl: string;
}

export function reportDownload(spec: Record<string, unknown>, projectId?: string): Promise<DownloadResult> {
  const q = projectId ? `?projectId=${encodeURIComponent(projectId)}` : "";
  return post<DownloadResult>(`/api/reports/download${q}`, { spec });
}

/** Trigger a browser download for an artifact by id (the ZIP package). */
export function downloadArtifact(url: string): void {
  const a = document.createElement("a");
  a.href = `${BASE}${url}`;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
}
