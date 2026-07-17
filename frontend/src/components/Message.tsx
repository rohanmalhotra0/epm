import { BlockRenderer, ProcessSteps, type ChatBlockT } from "../blocks";
import { Markdown } from "../blocks/Markdown";
import { SpeakButton } from "../tts/components";

export interface ChatMessage {
  id: string;
  role: string;
  content: string;
  blocks?: ChatBlockT[];
  processSteps?: Array<{ key: string; label: string; state: string }>;
}

export function MessageView({ message, onAction }: { message: ChatMessage; onAction: (v: string) => void }) {
  const isUser = message.role === "user";
  return (
    <div className={`msg ${isUser ? "user" : "assistant"}`}>
      <div className="avatar">{isUser ? "You" : "EW"}</div>
      <div className="body">
        <div className="role">
          {isUser ? "You" : "EPM Wizard"}
          {!isUser && message.content ? <SpeakButton text={message.content} /> : null}
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
