// Typed API client + SSE streaming for the local backend.

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function api<T = unknown>(path: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    headers: { "content-type": "application/json", ...(opts.headers || {}) },
    ...opts,
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
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export interface StreamHandlers {
  onEvent: (type: string, data: any) => void;
  onError?: (err: Error) => void;
  onDone?: () => void;
}

/** POST a chat message and consume the SSE stream. Returns an abort function. */
export function streamMessage(
  conversationId: string,
  content: string,
  handlers: StreamHandlers,
  path?: string,
): () => void {
  const controller = new AbortController();
  const url = path || `/api/conversations/${conversationId}/messages`;
  (async () => {
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ content }),
        signal: controller.signal,
      });
      if (!res.ok || !res.body) {
        throw new ApiError(res.status, `stream failed (${res.status})`);
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split("\n\n");
        buffer = chunks.pop() || "";
        for (const chunk of chunks) {
          const evMatch = chunk.match(/^event: (.+)$/m);
          const dataMatch = chunk.match(/^data: (.+)$/m);
          if (!evMatch) continue;
          const type = evMatch[1].trim();
          let data: any = {};
          if (dataMatch) {
            try {
              data = JSON.parse(dataMatch[1]);
            } catch {
              /* keep {} */
            }
          }
          handlers.onEvent(type, data);
        }
      }
      handlers.onDone?.();
    } catch (err) {
      if ((err as Error).name === "AbortError") {
        handlers.onDone?.();
        return;
      }
      handlers.onError?.(err as Error);
    }
  })();
  return () => controller.abort();
}
