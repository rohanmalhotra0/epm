import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type {
  ArtifactOut,
  ContextVersionOut,
  ConversationOut,
  DeploymentOut,
  DiagnosticsReport,
  EnvironmentOut,
  MessageOut,
  ProjectOut,
  ProviderOut,
  RuleExecutionOut,
} from "../schemas/types";

// --- projects ---
export const useProjects = () =>
  useQuery({ queryKey: ["projects"], queryFn: () => api<ProjectOut[]>("/api/projects") });

export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; description?: string }) =>
      api<ProjectOut>("/api/projects", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
  });
}

// --- conversations ---
export const useConversations = (projectId: string | undefined, search = "") =>
  useQuery({
    queryKey: ["conversations", projectId, search],
    enabled: !!projectId,
    queryFn: () =>
      api<ConversationOut[]>(
        `/api/projects/${projectId}/conversations${search ? `?search=${encodeURIComponent(search)}` : ""}`,
      ),
  });

export function useCreateConversation(projectId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      api<ConversationOut>(`/api/projects/${projectId}/conversations`, {
        method: "POST",
        body: JSON.stringify({}),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["conversations", projectId] }),
  });
}

export function useUpdateConversation(projectId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string } & Partial<ConversationOut>) =>
      api<ConversationOut>(`/api/conversations/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["conversations", projectId] }),
  });
}

export function useDeleteConversation(projectId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api(`/api/conversations/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["conversations", projectId] }),
  });
}

export const useMessages = (conversationId: string | undefined) =>
  useQuery({
    queryKey: ["messages", conversationId],
    enabled: !!conversationId,
    queryFn: () => api<MessageOut[]>(`/api/conversations/${conversationId}/messages`),
  });

// --- environments ---
export const useEnvironments = (projectId: string | undefined) =>
  useQuery({
    queryKey: ["environments", projectId],
    enabled: !!projectId,
    queryFn: () => api<EnvironmentOut[]>(`/api/projects/${projectId}/environments`),
  });

export function useConnectEnvironment(projectId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, password, remember }: { id: string; password?: string; remember?: boolean }) =>
      api(`/api/environments/${id}/connect`, {
        method: "POST",
        body: JSON.stringify({ password, remember }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["environments", projectId] }),
  });
}

export function useCreateEnvironment(projectId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api<EnvironmentOut>(`/api/projects/${projectId}/environments`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["environments", projectId] }),
  });
}

// --- providers ---
export const useProviders = () =>
  useQuery({ queryKey: ["providers"], queryFn: () => api<ProviderOut[]>("/api/providers") });

export function useCreateProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api<ProviderOut>("/api/providers", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["providers"] }),
  });
}

export function useUpdateProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string } & Record<string, unknown>) =>
      api<ProviderOut>(`/api/providers/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["providers"] }),
  });
}

// --- context / artifacts / deployments ---
export const useContexts = (projectId: string | undefined) =>
  useQuery({
    queryKey: ["contexts", projectId],
    enabled: !!projectId,
    queryFn: () => api<ContextVersionOut[]>(`/api/projects/${projectId}/contexts`),
  });

export function useBuildContext(projectId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (mode: "quick" | "deep") =>
      api<ContextVersionOut>(`/api/projects/${projectId}/contexts/build?mode=${mode}`, { method: "POST" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["contexts", projectId] });
      qc.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}

export const useArtifacts = (projectId: string | undefined, kind?: string) =>
  useQuery({
    queryKey: ["artifacts", projectId, kind],
    enabled: !!projectId,
    queryFn: () =>
      api<ArtifactOut[]>(`/api/projects/${projectId}/artifacts${kind ? `?kind=${kind}` : ""}`),
  });

export const useDeployments = (projectId: string | undefined) =>
  useQuery({
    queryKey: ["deployments", projectId],
    enabled: !!projectId,
    queryFn: () => api<DeploymentOut[]>(`/api/projects/${projectId}/deployments`),
  });

export const useRuleExecutions = (projectId: string | undefined) =>
  useQuery({
    queryKey: ["ruleExecutions", projectId],
    enabled: !!projectId,
    queryFn: () => api<RuleExecutionOut[]>(`/api/projects/${projectId}/rule-executions`),
  });

export const useDiagnostics = () =>
  useQuery({ queryKey: ["diagnostics"], queryFn: () => api<DiagnosticsReport>("/api/diagnostics") });

// --- settings ---
export interface AppSettings {
  demoEnabled: boolean;
}

export const useSettings = () =>
  useQuery({ queryKey: ["settings"], queryFn: () => api<AppSettings>("/api/settings") });

export function useUpdateSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<AppSettings>) =>
      api<AppSettings>("/api/settings", { method: "PATCH", body: JSON.stringify(body) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["settings"] });
      qc.invalidateQueries({ queryKey: ["environments"] });
    },
  });
}
