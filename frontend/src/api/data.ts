// Local-data management helpers: project export download + multipart import.
// Import cannot go through `api()` because that helper always sets a JSON
// content-type; multipart uploads need the browser to set the boundary itself.

import { ApiError } from "./client";
import type { ProjectOut } from "../schemas/types";

/** Trigger a browser download of the project export zip via a temporary anchor. */
export function downloadProjectExport(projectId: string): void {
  const a = document.createElement("a");
  a.href = `/api/projects/${projectId}/export`;
  a.download = "";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

/** POST an exported project zip as multipart form data. Returns the created project. */
export async function uploadProjectImport(file: File): Promise<ProjectOut> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch("/api/projects/import", { method: "POST", body: form });
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
  return (await res.json()) as ProjectOut;
}
