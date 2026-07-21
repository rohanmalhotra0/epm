import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { streamMessage } from "../api/client";
import type { AttachmentOut } from "../api/attachments";
import { useMessages } from "../api/hooks";
import { MessageView, messageTokens, type ChatMessage } from "../components/Message";
import { Composer } from "../components/Composer";
import type { ChatBlockT } from "../blocks";
import { ArtifactsPanel } from "../artifacts/ArtifactsPanel";
import { useArtifacts } from "../artifacts/store";
import { useUi } from "../store/ui";
import { toast } from "../store/toast";
import { speak, useTts } from "../tts/tts";

interface Live {
  content: string;
  blocks: ChatBlockT[];
  processSteps: Array<{ key: string; label: string; state: string }>;
}

const SUGGESTIONS = [
  { t: "Create an Actuals form", d: "Level-zero descendants of Total Payroll in rows" },
  { t: "Inspect this EPM application", d: "What cubes and dimensions exist?" },
  { t: "Visualize a cube", d: "Show the architecture of OEP_DCSH" },
  { t: "Run a business rule", d: "Run the IR rule" },
  { t: "Create a new-hire workflow", d: "Add New Hire with runtime prompts" },
  { t: "Build context", d: "Learn this EPM environment" },
];

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

export function ChatPage() {
  const { id } = useParams();
  const qc = useQueryClient();
  const { data: messages = [] } = useMessages(id);
  const [pendingUser, setPendingUser] = useState<string | null>(null);
  // Chips on the pending user bubble only — persisted history does not carry
  // attachment metadata, so they disappear once the exchange is reloaded.
  const [pendingAttachments, setPendingAttachments] = useState<AttachmentOut[]>([]);
  const [live, setLive] = useState<Live | null>(null);
  const abortRef = useRef<null | (() => void)>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const finalTextRef = useRef("");
  const projectId = useUi((s) => s.currentProjectId);
  const setArtifactProject = useArtifacts((s) => s.setProjectId);

  // Keep the artifacts panel scoped to the active project.
  useEffect(() => {
    setArtifactProject(projectId ?? undefined);
  }, [projectId, setArtifactProject]);

  useEffect(() => {
    setPendingUser(null);
    setPendingAttachments([]);
    setLive(null);
    abortRef.current?.();
  }, [id]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages, live, pendingUser]);

  const send = (text: string, attachments: AttachmentOut[] = []) => {
    if (!id || live) return;
    setPendingUser(text);
    setPendingAttachments(attachments);
    setLive({ content: "", blocks: [], processSteps: [] });
    finalTextRef.current = "";
    abortRef.current = streamMessage(id, text, {
      onEvent: (type, data) => {
        // The backend emits a terminal `error` event on a mid-stream failure. It was
        // previously ignored, so the user saw a silently truncated reply. Surface it.
        if (type === "error") {
          toast.error("The assistant hit an error", data?.message);
          return;
        }
        if (type === "token") finalTextRef.current += data.text || "";
        setLive((prev) => {
          if (!prev) return prev;
          if (type === "token") return { ...prev, content: prev.content + (data.text || "") };
          if (type === "process") return { ...prev, processSteps: data.steps || prev.processSteps };
          if (type === "block") {
            const blocks = [...prev.blocks];
            const idx = blocks.findIndex((b) => b.id === data.id);
            if (idx >= 0) blocks[idx] = data;
            else blocks.push(data);
            return { ...prev, blocks };
          }
          return prev;
        });
      },
      // A transport failure (network drop, non-2xx) must not freeze the composer:
      // clear the streaming state, surface the error, and reload any persisted state.
      onError: (e) => {
        toast.error("Message failed", e.message);
        setLive(null);
        setPendingUser(null);
        setPendingAttachments([]);
        qc.invalidateQueries({ queryKey: ["messages", id] });
      },
      onDone: () => {
        qc.invalidateQueries({ queryKey: ["messages", id] });
        qc.invalidateQueries({ queryKey: ["conversations"] });
        qc.invalidateQueries({ queryKey: ["deployments"] });
        qc.invalidateQueries({ queryKey: ["artifacts"] });
        if (useTts.getState().autoSpeak && finalTextRef.current.trim()) speak(finalTextRef.current);
        setPendingUser(null);
        setPendingAttachments([]);
        setLive(null);
      },
    }, undefined, attachments.map((a) => a.id));
  };

  const stop = () => {
    abortRef.current?.();
    setLive(null);
    setPendingUser(null);
    setPendingAttachments([]);
  };

  const empty = messages.length === 0 && !pendingUser && !live;

  // "Regenerate" on the last assistant message: re-send the user message that
  // preceded it through the normal send path (no separate streaming logic).
  const msgs = messages as ChatMessage[];
  let lastAssistantIdx = -1;
  for (let i = msgs.length - 1; i >= 0; i--) {
    if (msgs[i].role === "assistant") {
      lastAssistantIdx = i;
      break;
    }
  }
  const precedingUser = (() => {
    for (let i = lastAssistantIdx - 1; i >= 0; i--) {
      if (msgs[i].role === "user") return msgs[i].content;
    }
    return null;
  })();
  const canRegenerate = lastAssistantIdx >= 0 && precedingUser !== null && !live && !pendingUser;

  // Per-conversation token total (sum of per-message usage). Tokens only — no cost.
  const convoTokens = msgs.reduce(
    (acc, m) => {
      const { input, output } = messageTokens(m.usage);
      acc.input += input ?? 0;
      acc.output += output ?? 0;
      return acc;
    },
    { input: 0, output: 0 },
  );
  const convoTotal = convoTokens.input + convoTokens.output;

  return (
    <div className="chat-split">
    <div className="main-col">
      <div className="chat-scroll" ref={scrollRef}>
        <div className="chat-inner">
          {empty ? (
            <div className="welcome">
              <h1>{greeting()}. What would you like to build in EPM?</h1>
              <p className="sub">EPM Wizard runs entirely on your machine. Try one of these, or type a request below.</p>
              <div className="suggestions">
                {SUGGESTIONS.map((s) => (
                  <div key={s.t} className="suggestion" onClick={() => send(s.d)}>
                    <div className="t">{s.t}</div>
                    <div className="d">{s.d}</div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <>
              {msgs.map((m, i) => (
                <MessageView
                  key={m.id}
                  message={m}
                  onAction={send}
                  onRegenerate={canRegenerate && i === lastAssistantIdx ? () => send(precedingUser!) : undefined}
                />
              ))}
              {pendingUser && (
                <MessageView
                  message={{
                    id: "pending",
                    role: "user",
                    content: pendingUser,
                    attachments: pendingAttachments.length
                      ? pendingAttachments.map((a) => ({ filename: a.filename, sizeBytes: a.sizeBytes, kindGuess: a.kindGuess }))
                      : undefined,
                  }}
                  onAction={send}
                />
              )}
              {live && (
                <MessageView
                  streaming
                  message={{ id: "live", role: "assistant", content: live.content, blocks: live.blocks, processSteps: live.processSteps }}
                  onAction={send}
                />
              )}
            </>
          )}
        </div>
      </div>
      {convoTotal > 0 && (
        <div
          className="convo-usage"
          style={{
            fontSize: 11,
            color: "var(--cds-text-secondary, #8d8d8d)",
            padding: "2px 16px",
            textAlign: "right",
          }}
        >
          Conversation tokens: {convoTokens.input.toLocaleString()} in · {convoTokens.output.toLocaleString()} out · {convoTotal.toLocaleString()} total
        </div>
      )}
      <Composer onSend={send} streaming={!!live} onStop={stop} conversationId={id} />
    </div>
      <ArtifactsPanel />
    </div>
  );
}
