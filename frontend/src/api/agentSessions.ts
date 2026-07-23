import { api } from "./client";

export type AgentSessionStatus =
  | "queued"
  | "running"
  | "paused"
  | "completed"
  | "cancelled"
  | "failed";

export type AgentWorkerStatus =
  | "queued"
  | "running"
  | "paused"
  | "completed"
  | "cancelled"
  | "failed";

export interface AgentWorker {
  id: string;
  role: string;
  assignment: string;
  status: AgentWorkerStatus;
  progress: number;
  activity: string;
  output: string | null;
  error?: string | null;
  context?: string | null;
}

export interface AgentSession {
  id: string;
  goal: string;
  projectId?: string | null;
  status: AgentSessionStatus;
  agentCount?: number;
  progress?: number;
  agents: AgentWorker[];
  createdAt: string;
  updatedAt: string;
  completedAt?: string | null;
}

export interface CreateAgentSessionInput {
  goal: string;
  projectId?: string;
  agentCount: number;
}

export function createAgentSession(input: CreateAgentSessionInput) {
  return api<AgentSession>("/api/agent/sessions", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function getAgentSession(sessionId: string) {
  return api<AgentSession>(`/api/agent/sessions/${encodeURIComponent(sessionId)}`);
}

export function pauseAgentSession(sessionId: string) {
  return updateAgentSession(sessionId, "pause");
}

export function resumeAgentSession(sessionId: string) {
  return updateAgentSession(sessionId, "resume");
}

export function cancelAgentSession(sessionId: string) {
  return updateAgentSession(sessionId, "cancel");
}

function updateAgentSession(
  sessionId: string,
  action: "pause" | "resume" | "cancel",
) {
  return api<AgentSession>(
    `/api/agent/sessions/${encodeURIComponent(sessionId)}/${action}`,
    { method: "POST" },
  );
}
