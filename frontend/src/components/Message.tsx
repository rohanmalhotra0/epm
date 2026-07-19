import { Copy, Renew } from "@carbon/icons-react";
import { BlockRenderer, ProcessSteps, type ChatBlockT } from "../blocks";
import { Markdown } from "../blocks/Markdown";
import { SpeakButton } from "../tts/components";
import { toast } from "../store/toast";

export interface ChatMessage {
  id: string;
  role: string;
  content: string;
  blocks?: ChatBlockT[];
  processSteps?: Array<{ key: string; label: string; state: string }>;
}

function copyMessage(content: string) {
  navigator.clipboard
    .writeText(content)
    .then(() => toast.success("Copied to clipboard"))
    .catch(() => toast.error("Copy failed"));
}

export function MessageView({
  message,
  onAction,
  onRegenerate,
}: {
  message: ChatMessage;
  onAction: (v: string) => void;
  /** Present only on the last assistant message: re-send the preceding user message. */
  onRegenerate?: () => void;
}) {
  const isUser = message.role === "user";
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
        {message.content && (
          <div className="content">{isUser ? <div style={{ whiteSpace: "pre-wrap" }}>{message.content}</div> : <Markdown text={message.content} />}</div>
        )}
        {(message.blocks || []).map((b) => (
          <BlockRenderer key={b.id} block={b} onAction={onAction} />
        ))}
      </div>
    </div>
  );
}
