import { Copy, Document, Renew } from "@carbon/icons-react";
import { BlockRenderer, ProcessSteps, type ChatBlockT } from "../blocks";
import { Markdown } from "../blocks/Markdown";
import { SpeakButton } from "../tts/components";
import { toast } from "../store/toast";
import { attachmentKindLabel } from "../api/attachments";
import { formatBytes } from "../utils/format";

export interface ChatMessage {
  id: string;
  role: string;
  content: string;
  blocks?: ChatBlockT[];
  processSteps?: Array<{ key: string; label: string; state: string }>;
  /** Local-only (pending bubble): persisted history does not carry attachment metadata. */
  attachments?: Array<{ filename: string; sizeBytes?: number; kindGuess?: string }>;
  /** Provenance surfaced from MessageOut — model/provider/token usage of the reply. */
  model?: string | null;
  provider?: string | null;
  usage?: Record<string, unknown> | null;
}

function pickNum(usage: Record<string, unknown> | null | undefined, ...keys: string[]): number | undefined {
  if (!usage) return undefined;
  for (const k of keys) {
    const v = usage[k];
    if (typeof v === "number" && Number.isFinite(v)) return v;
  }
  return undefined;
}

/** Extract input/output/total token counts from a MessageOut.usage bag, tolerating key styles. */
export function messageTokens(usage: Record<string, unknown> | null | undefined): {
  input?: number;
  output?: number;
  total?: number;
} {
  const input = pickNum(usage, "inputTokens", "input_tokens", "promptTokens", "prompt_tokens");
  const output = pickNum(usage, "outputTokens", "output_tokens", "completionTokens", "completion_tokens");
  let total = pickNum(usage, "totalTokens", "total_tokens");
  if (total === undefined && (input !== undefined || output !== undefined)) {
    total = (input ?? 0) + (output ?? 0);
  }
  return { input, output, total };
}

function copyMessage(content: string) {
  navigator.clipboard
    .writeText(content)
    .then(() => toast.success("Copied to clipboard"))
    .catch(() => toast.error("Copy failed"));
}

/** Animated "the assistant is working" indicator, shown before the first token. */
function TypingDots() {
  return (
    <div className="typing-dots" role="status" aria-label="EPM Wizard is thinking">
      <span /><span /><span />
    </div>
  );
}

export function MessageView({
  message,
  onAction,
  onRegenerate,
  streaming = false,
}: {
  message: ChatMessage;
  onAction: (v: string) => void;
  /** Present only on the last assistant message: re-send the preceding user message. */
  onRegenerate?: () => void;
  /** True while this message is still being streamed — drives the typing animation. */
  streaming?: boolean;
}) {
  const isUser = message.role === "user";
  const awaitingFirstToken = streaming && !message.content && !(message.blocks?.length);
  return (
    <div className={`msg ${isUser ? "user" : "assistant"}`}>
      <div className="avatar">{isUser ? "You" : "EW"}</div>
      <div className="body">
        <div className="role">
          {isUser ? "You" : "EPM Wizard"}
          {!isUser && message.content ? <SpeakButton text={message.content} /> : null}
          {message.content ? (
            <button
              className="epmw-speak"
              title="Copy message"
              aria-label="Copy message"
              onClick={() => copyMessage(message.content)}
            >
              <Copy size={14} />
            </button>
          ) : null}
          {onRegenerate ? (
            <button className="epmw-speak" title="Regenerate response" aria-label="Regenerate response" onClick={onRegenerate}>
              <Renew size={14} />
            </button>
          ) : null}
        </div>
        {!isUser && message.processSteps && message.processSteps.length > 0 && (
          <ProcessSteps steps={message.processSteps} />
        )}
        {awaitingFirstToken && <TypingDots />}
        {message.content && (
          <div className="content">
            {isUser ? (
              <div style={{ whiteSpace: "pre-wrap" }}>{message.content}</div>
            ) : (
              <>
                <Markdown text={message.content} />
                {streaming && <span className="stream-caret" aria-hidden="true" />}
              </>
            )}
          </div>
        )}
        {(message.attachments?.length ?? 0) > 0 && (
          <div className="attach-chips msg-attach">
            {message.attachments!.map((a, i) => (
              <span className="attach-chip" key={i}>
                <Document size={14} />
                <span className="name mono">{a.filename}</span>
                {a.sizeBytes != null && <span className="meta">{formatBytes(a.sizeBytes)}</span>}
                <span className="tag-inline">{attachmentKindLabel(a.kindGuess)}</span>
              </span>
            ))}
          </div>
        )}
        {(message.blocks || []).map((b) => (
          <BlockRenderer key={b.id} block={b} onAction={onAction} />
        ))}
        {!isUser && <MessageUsageFooter message={message} />}
      </div>
    </div>
  );
}

/** Small per-message provenance line: token usage + model. Tokens only — no cost. */
function MessageUsageFooter({ message }: { message: ChatMessage }) {
  const { input, output, total } = messageTokens(message.usage);
  const hasTokens = input !== undefined || output !== undefined || total !== undefined;
  if (!hasTokens && !message.model) return null;
  const parts: string[] = [];
  if (input !== undefined) parts.push(`${input.toLocaleString()} in`);
  if (output !== undefined) parts.push(`${output.toLocaleString()} out`);
  if (input === undefined && output === undefined && total !== undefined) {
    parts.push(`${total.toLocaleString()} tokens`);
  }
  if (message.model) parts.push(message.model);
  return (
    <div
      className="msg-usage"
      style={{ fontSize: 11, color: "var(--cds-text-secondary, #8d8d8d)", marginTop: 6 }}
    >
      {parts.join(" · ")}
    </div>
  );
}
