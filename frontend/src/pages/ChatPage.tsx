import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { streamMessage } from "../api/client";
import { useMessages } from "../api/hooks";
import { MessageView, type ChatMessage } from "../components/Message";
import { Composer } from "../components/Composer";
import type { ChatBlockT } from "../blocks";
import { ArtifactsPanel } from "../artifacts/ArtifactsPanel";
import { useArtifacts } from "../artifacts/store";
import { useUi } from "../store/ui";
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
    setLive(null);
    abortRef.current?.();
  }, [id]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages, live, pendingUser]);

  const send = (text: string) => {
    if (!id || live) return;
    setPendingUser(text);
    setLive({ content: "", blocks: [], processSteps: [] });
    finalTextRef.current = "";
    abortRef.current = streamMessage(id, text, {
      onEvent: (type, data) => {
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
      onError: (e) =>
        setLive((prev) => (prev ? { ...prev, content: prev.content + `\n\n_Error: ${e.message}_` } : prev)),
      onDone: () => {
        qc.invalidateQueries({ queryKey: ["messages", id] });
        qc.invalidateQueries({ queryKey: ["conversations"] });
        qc.invalidateQueries({ queryKey: ["deployments"] });
        qc.invalidateQueries({ queryKey: ["artifacts"] });
        if (useTts.getState().autoSpeak && finalTextRef.current.trim()) speak(finalTextRef.current);
        setPendingUser(null);
        setLive(null);
      },
    });
  };

  const stop = () => {
    abortRef.current?.();
    setLive(null);
    setPendingUser(null);
  };

  const empty = messages.length === 0 && !pendingUser && !live;

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
              {(messages as ChatMessage[]).map((m) => (
                <MessageView key={m.id} message={m} onAction={send} />
              ))}
              {pendingUser && <MessageView message={{ id: "pending", role: "user", content: pendingUser }} onAction={send} />}
              {live && (
                <MessageView
                  message={{ id: "live", role: "assistant", content: live.content, blocks: live.blocks, processSteps: live.processSteps }}
                  onAction={send}
                />
              )}
            </>
          )}
        </div>
      </div>
      <Composer onSend={send} streaming={!!live} onStop={stop} />
    </div>
      <ArtifactsPanel />
    </div>
  );
}
