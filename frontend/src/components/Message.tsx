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
      </div>
    </div>
  );
}
