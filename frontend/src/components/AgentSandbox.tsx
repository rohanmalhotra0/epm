import { useEffect, useMemo, useRef, useState } from "react";
import {
  Button,
  InlineNotification,
  Modal,
  ProgressBar,
  Select,
  SelectItem,
  Tag,
  TextArea,
} from "@carbon/react";
import {
  Bot,
  CheckmarkFilled,
  Copy,
  Launch,
  Pause,
  Play,
  Restart,
  Screen,
  StopFilled,
  Task,
  UserMultiple,
} from "@carbon/icons-react";
import {
  cancelAgentSession,
  createAgentSession,
  getAgentSession,
  pauseAgentSession,
  resumeAgentSession,
  type AgentSession,
  type AgentSessionStatus,
  type AgentWorker,
} from "../api/agentSessions";
import { ApiError } from "../api/client";
import { useInertAppBackground } from "../hooks/useInertAppBackground";
import { useUi } from "../store/ui";
import "../styles/agent-sandbox.css";

type PendingAction = "launch" | "pause" | "resume" | "cancel" | "reset" | null;
type ConfirmationAction = "cancel" | "reset" | null;
type CopyState = "idle" | "copied" | "error";

const MAX_TASK_LENGTH = 4_000;

const ACTIVE_SESSION_STATUSES = new Set<AgentSessionStatus>([
  "queued",
  "running",
  "paused",
]);

function displayStatus(status: string) {
  return status.charAt(0).toUpperCase() + status.slice(1);
}

function statusClass(status: string) {
  return status.toLowerCase().replace(/[^a-z0-9-]/g, "");
}

function normalizedProgress(progress: number) {
  return Math.max(0, Math.min(100, Math.round(progress)));
}

function progressStatus(agent: AgentWorker): "active" | "finished" | "error" {
  if (agent.status === "failed") return "error";
  if (agent.status === "completed" || normalizedProgress(agent.progress) === 100) {
    return "finished";
  }
  return "active";
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Something went wrong. Try again.";
}

function agentResult(agent: AgentWorker) {
  if (agent.status === "failed" && agent.error) return agent.error;
  return agent.output || agent.error || agent.activity || "No result reported.";
}

export function AgentSandbox() {
  const projectId = useUi((state) => state.currentProjectId);
  const [task, setTask] = useState("");
  const [agentCount, setAgentCount] = useState(3);
  const [session, setSession] = useState<AgentSession | null>(null);
  const [taskError, setTaskError] = useState<string | null>(null);
  const [controlError, setControlError] = useState<string | null>(null);
  const [pendingAction, setPendingAction] = useState<PendingAction>(null);
  const [watchingAgentId, setWatchingAgentId] = useState<string | null>(null);
  const [confirmationAction, setConfirmationAction] =
    useState<ConfirmationAction>(null);
  const [copyState, setCopyState] = useState<CopyState>("idle");
  const taskRef = useRef<HTMLTextAreaElement>(null);
  const observeModalRef = useRef<HTMLDivElement>(null);
  const confirmationModalRef = useRef<HTMLDivElement>(null);

  const agents = session?.agents ?? [];
  const watchingAgent =
    agents.find((agent) => agent.id === watchingAgentId) ?? null;
  const sessionIsActive = session
    ? ACTIVE_SESSION_STATUSES.has(session.status)
    : false;
  const displayedAgentCount = session
    ? session.agentCount ?? agents.length
    : agentCount;
  const sessionProgress = normalizedProgress(session?.progress ?? 0);
  const handoff = useMemo(
    () =>
      session
        ? [
            "READ-ONLY AGENT SANDBOX HANDOFF",
            `Task: ${session.goal}`,
            `Session: ${session.id}`,
            `Status: ${displayStatus(session.status)}`,
            `Team: ${displayedAgentCount} ${
              displayedAgentCount === 1 ? "agent" : "agents"
            }`,
            "Safety: Analysis only; no browser, EPM connector, deployment, or write access.",
            "",
            ...agents.map(
              (agent) =>
                `${agent.role} [${displayStatus(agent.status)}]: ${agentResult(agent)}`,
            ),
          ].join("\n")
        : "",
    [agents, displayedAgentCount, session],
  );

  useInertAppBackground(observeModalRef, watchingAgent !== null);
  useInertAppBackground(confirmationModalRef, confirmationAction !== null);

  useEffect(() => {
    if (!session || !ACTIVE_SESSION_STATUSES.has(session.status) || pendingAction) {
      return;
    }

    let disposed = false;
    let timeoutId: number | undefined;
    const refresh = async () => {
      let shouldPollAgain = true;
      try {
        const refreshedSession = await getAgentSession(session.id);
        if (!disposed) {
          setSession(refreshedSession);
          setControlError(null);
        }
      } catch (error) {
        if (!disposed) {
          if (error instanceof ApiError && error.status === 404) {
            shouldPollAgain = false;
            setSession(null);
            setWatchingAgentId(null);
            setControlError(
              "This agent session is no longer available. You can launch a new team.",
            );
          } else {
            setControlError(
              `Could not refresh this session: ${errorMessage(error)}`,
            );
          }
        }
      } finally {
        if (!disposed && shouldPollAgain) {
          timeoutId = window.setTimeout(refresh, 1000);
        }
      }
    };
    timeoutId = window.setTimeout(refresh, 1000);

    return () => {
      disposed = true;
      if (timeoutId !== undefined) {
        window.clearTimeout(timeoutId);
      }
    };
  }, [pendingAction, session?.id, session?.status]);

  const launchSession = async () => {
    const goal = task.trim();
    if (!goal) {
      setTaskError("Enter the task this team should work on.");
      taskRef.current?.focus();
      return;
    }
    if (goal.length > MAX_TASK_LENGTH) {
      setTaskError("Keep the task to 4,000 characters or fewer.");
      taskRef.current?.focus();
      return;
    }

    setTaskError(null);
    setControlError(null);
    setPendingAction("launch");
    try {
      const createdSession = await createAgentSession({
        goal,
        ...(projectId ? { projectId } : {}),
        agentCount,
      });
      setSession(createdSession);
      setWatchingAgentId(null);
      setCopyState("idle");
    } catch (error) {
      setControlError(`Could not launch the agent team: ${errorMessage(error)}`);
    } finally {
      setPendingAction(null);
    }
  };

  const updateSession = async (action: "pause" | "resume") => {
    if (!session) return;

    setControlError(null);
    setPendingAction(action);
    try {
      const updatedSession =
        action === "pause"
          ? await pauseAgentSession(session.id)
          : await resumeAgentSession(session.id);
      setSession(updatedSession);
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        setSession(null);
        setWatchingAgentId(null);
        setControlError(
          "This agent session is no longer available. You can launch a new team.",
        );
      } else {
        setControlError(
          `Could not ${action} this session: ${errorMessage(error)}`,
        );
      }
    } finally {
      setPendingAction(null);
    }
  };

  const clearSession = () => {
    setSession(null);
    setWatchingAgentId(null);
    setControlError(null);
    setCopyState("idle");
    window.requestAnimationFrame(() => taskRef.current?.focus());
  };

  const requestReset = () => {
    if (sessionIsActive) {
      setConfirmationAction("reset");
      return;
    }
    clearSession();
  };

  const confirmCancellation = async () => {
    if (!session || !confirmationAction) return;

    const action = confirmationAction;
    setControlError(null);
    setPendingAction(action);
    try {
      const cancelledSession = await cancelAgentSession(session.id);
      setConfirmationAction(null);
      if (action === "reset") {
        clearSession();
      } else {
        setSession(cancelledSession);
      }
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        setConfirmationAction(null);
        clearSession();
      } else {
        setControlError(`Could not cancel this session: ${errorMessage(error)}`);
      }
    } finally {
      setPendingAction(null);
    }
  };

  const copyHandoff = async () => {
    try {
      if (!navigator.clipboard?.writeText) {
        throw new Error("Clipboard access is unavailable");
      }
      await navigator.clipboard.writeText(handoff);
      setCopyState("copied");
    } catch {
      setCopyState("error");
    }
  };

  return (
    <section className="agent-sandbox" aria-labelledby="agent-sandbox-title">
      <div className="agent-sandbox-heading">
        <div>
          <div className="agent-sandbox-title-row">
            <UserMultiple size={20} aria-hidden="true" />
            <h3 id="agent-sandbox-title">Agent sandbox</h3>
            <Tag type="cool-gray" size="sm">Backend session</Tag>
          </div>
          <p>
            Split one EPM task across a focused team and follow each workstream.
          </p>
        </div>
        <div
          className="agent-sandbox-summary"
          aria-label="Session summary"
          aria-live="polite"
        >
          <span>
            {displayedAgentCount} {displayedAgentCount === 1 ? "agent" : "agents"}
          </span>
          <span aria-hidden="true">·</span>
          <strong>
            {pendingAction === "launch"
              ? "Launching"
              : session
                ? displayStatus(session.status)
                : "Not started"}
          </strong>
        </div>
      </div>

      <InlineNotification
        kind="info"
        lowContrast
        hideCloseButton
        title="Before you launch"
        subtitle="Launching makes one AI provider call per agent. These workers analyze text only and have no browser control, Oracle EPM connection, deployment, or write access."
      />

      <div className="agent-sandbox-launcher">
        <TextArea
          ref={taskRef}
          id="sandbox-task"
          labelText="Task for the team"
          placeholder="For example: Review the Workforce forecast rule, validate totals, and prepare a safe deployment plan"
          rows={3}
          enableCounter
          maxCount={MAX_TASK_LENGTH}
          value={task}
          invalid={taskError !== null}
          invalidText={taskError ?? undefined}
          disabled={session !== null || pendingAction === "launch"}
          onChange={(event) => {
            setTask(event.target.value);
            if (taskError) setTaskError(null);
          }}
        />
        <div className="agent-sandbox-launch-controls">
          <Select
            id="sandbox-agent-count"
            labelText="Team size"
            size="sm"
            value={String(agentCount)}
            disabled={session !== null || pendingAction === "launch"}
            onChange={(event) => setAgentCount(Number(event.target.value))}
          >
            {Array.from({ length: 12 }, (_, index) => {
              const count = index + 1;
              return (
                <SelectItem
                  key={count}
                  value={String(count)}
                  text={`${count} ${count === 1 ? "agent" : "agents"}`}
                />
              );
            })}
          </Select>

          {!session ? (
            <Button
              renderIcon={Launch}
              disabled={pendingAction === "launch"}
              onClick={launchSession}
            >
              {pendingAction === "launch" ? "Launching team…" : "Launch agent team"}
            </Button>
          ) : (
            <div className="agent-sandbox-session-controls">
              {sessionIsActive && session.status !== "queued" && (
                <Button
                  kind="secondary"
                  renderIcon={session.status === "paused" ? Play : Pause}
                  disabled={pendingAction !== null}
                  onClick={() =>
                    updateSession(session.status === "paused" ? "resume" : "pause")
                  }
                >
                  {session.status === "paused" ? "Resume updates" : "Pause updates"}
                </Button>
              )}
              {sessionIsActive && (
                <Button
                  kind="danger--tertiary"
                  renderIcon={StopFilled}
                  disabled={pendingAction !== null}
                  onClick={() => setConfirmationAction("cancel")}
                >
                  Cancel
                </Button>
              )}
              <Button
                kind="ghost"
                renderIcon={Restart}
                disabled={pendingAction !== null}
                onClick={requestReset}
              >
                Reset
              </Button>
            </div>
          )}

          {sessionIsActive && (
            <p className="agent-sandbox-control-note">
              Pausing holds new results here; provider calls already in progress
              may continue.
            </p>
          )}

          {controlError && !confirmationAction && (
            <p className="agent-sandbox-control-error" role="alert">
              {controlError}
            </p>
          )}
        </div>
      </div>

      <div className="agent-sandbox-team-head">
        <div>
          <h4>Team activity</h4>
          <p>
            Status, progress, and output update from the running backend session.
          </p>
        </div>
        {session && (
          <span className="agent-sandbox-step">
            Session <strong>{session.id.slice(0, 8)}</strong>
          </span>
        )}
      </div>

      {agents.length > 0 ? (
        <div className="agent-sandbox-grid">
          {agents.map((agent, index) => {
            const progress = normalizedProgress(agent.progress);
            return (
              <article className="agent-sandbox-card" key={agent.id}>
                <div className="agent-sandbox-card-head">
                  <span className="agent-sandbox-avatar" aria-hidden="true">
                    <Bot size={18} />
                  </span>
                  <div>
                    <h5>{agent.role}</h5>
                    <span>Agent {String(index + 1).padStart(2, "0")}</span>
                  </div>
                  <span
                    className={`agent-sandbox-status agent-sandbox-status-${statusClass(agent.status)}`}
                  >
                    {displayStatus(agent.status)}
                  </span>
                </div>
                <p>{agent.assignment}</p>
                <ProgressBar
                  label={`${agent.role} progress`}
                  value={progress}
                  status={progressStatus(agent)}
                />
                <div className="agent-sandbox-card-foot">
                  <span>{progress}%</span>
                  <Button
                    kind="ghost"
                    size="sm"
                    renderIcon={Screen}
                    aria-label={`Observe ${agent.role}`}
                    onClick={() => setWatchingAgentId(agent.id)}
                  >
                    Observe
                  </Button>
                </div>
              </article>
            );
          })}
        </div>
      ) : (
        <div className="agent-sandbox-empty">
          <Bot size={20} aria-hidden="true" />
          <p>Enter a task and launch a team to see live agent activity here.</p>
        </div>
      )}

      {session && (session.status === "completed" || session.status === "failed") && (
        <section
          className={`agent-sandbox-handoff${
            session.status === "failed" ? " agent-sandbox-handoff-failed" : ""
          }`}
          aria-labelledby="agent-sandbox-handoff-title"
        >
          <div className="agent-sandbox-handoff-heading">
            <div>
              <div className="agent-sandbox-handoff-title">
                {session.status === "completed" ? (
                  <CheckmarkFilled size={18} aria-hidden="true" />
                ) : (
                  <StopFilled size={18} aria-hidden="true" />
                )}
                <h4 id="agent-sandbox-handoff-title">
                  {session.status === "completed"
                    ? "Completed team handoff"
                    : "Failed session handoff"}
                </h4>
              </div>
              <p>
                Review the results below or copy the full read-only handoff.
              </p>
            </div>
            <Button
              kind="secondary"
              size="sm"
              renderIcon={Copy}
              aria-label="Copy handoff"
              onClick={copyHandoff}
            >
              {copyState === "copied" ? "Copied" : "Copy handoff"}
            </Button>
          </div>

          <dl className="agent-sandbox-handoff-meta">
            <div>
              <dt>Task</dt>
              <dd>{session.goal}</dd>
            </div>
            <div>
              <dt>Status</dt>
              <dd>
                {displayStatus(session.status)} · {sessionProgress}%
              </dd>
            </div>
            <div>
              <dt>Access</dt>
              <dd>No browser, Oracle EPM, deployment, or write access</dd>
            </div>
          </dl>

          <ul className="agent-sandbox-handoff-results">
            {agents.map((agent) => (
              <li key={agent.id}>
                <strong>
                  {agent.role} · {displayStatus(agent.status)}
                </strong>
                <span>{agentResult(agent)}</span>
              </li>
            ))}
          </ul>

          <span className="agent-sandbox-copy-status" aria-live="polite">
            {copyState === "copied" ? "Handoff copied to clipboard." : ""}
          </span>
          {copyState === "error" && (
            <InlineNotification
              kind="error"
              lowContrast
              hideCloseButton
              title="Could not copy the handoff"
              subtitle="Clipboard access is unavailable in this browser."
            />
          )}
        </section>
      )}

      <Modal
        ref={observeModalRef}
        open={watchingAgent !== null}
        passiveModal
        size="lg"
        modalHeading={
          watchingAgent ? `Observe agent · ${watchingAgent.role}` : "Observe agent"
        }
        onRequestClose={() => setWatchingAgentId(null)}
      >
        {watchingAgent && (
          <div className="agent-live" data-testid="agent-live-view">
            <InlineNotification
              kind="info"
              lowContrast
              hideCloseButton
              title="Live worker telemetry"
              subtitle="These sandbox workers have no browser or Oracle EPM access. This view shows backend-reported state, activity, and output only."
            />
            <div className="agent-live-layout">
              <nav className="agent-live-agents" aria-label="Agents in this session">
                {agents.map((agent) => (
                  <Button
                    key={agent.id}
                    kind={watchingAgentId === agent.id ? "secondary" : "ghost"}
                    size="sm"
                    aria-pressed={watchingAgentId === agent.id}
                    onClick={() => setWatchingAgentId(agent.id)}
                  >
                    <span>
                      <strong>{agent.role}</strong>
                      <small>
                        {displayStatus(agent.status)} ·{" "}
                        {normalizedProgress(agent.progress)}%
                      </small>
                    </span>
                  </Button>
                ))}
              </nav>

              <div className="agent-live-workspace">
                <section
                  className="agent-live-worker"
                  aria-label="Agent workspace state"
                >
                  <div className="agent-live-worker-bar">
                    <Task size={16} aria-hidden="true" />
                    <strong>Worker state</strong>
                    <Tag type="gray" size="sm">
                      {displayStatus(watchingAgent.status)}
                    </Tag>
                  </div>
                  <dl>
                    <div>
                      <dt>Role</dt>
                      <dd>{watchingAgent.role}</dd>
                    </div>
                    <div>
                      <dt>Assignment</dt>
                      <dd>{watchingAgent.assignment}</dd>
                    </div>
                    <div>
                      <dt>Context</dt>
                      <dd>{watchingAgent.context || "Backend worker"}</dd>
                    </div>
                    <div>
                      <dt>Session goal</dt>
                      <dd>{session?.goal}</dd>
                    </div>
                  </dl>
                </section>

                <div className="agent-live-panels">
                  <section>
                    <h4>Current activity</h4>
                    <p className="agent-live-activity">
                      {watchingAgent.activity || "Waiting for the next worker update…"}
                    </p>
                    {watchingAgent.error && (
                      <p className="agent-live-error" role="alert">
                        {watchingAgent.error}
                      </p>
                    )}
                  </section>
                  <section>
                    <h4>Latest output</h4>
                    <div className="agent-live-output">
                      {watchingAgent.output && (
                        <CheckmarkFilled size={16} aria-hidden="true" />
                      )}
                      <p>{watchingAgent.output || "No output yet."}</p>
                    </div>
                  </section>
                </div>
              </div>
            </div>
          </div>
        )}
      </Modal>

      {confirmationAction && (
        <Modal
          ref={confirmationModalRef}
          open
          danger
          size="xs"
          modalHeading={
            confirmationAction === "reset"
              ? "Reset and cancel this session?"
              : "Cancel this session?"
          }
          primaryButtonText={
            pendingAction === "cancel" || pendingAction === "reset"
              ? "Cancelling…"
              : confirmationAction === "reset"
                ? "Cancel and reset"
                : "Cancel session"
          }
          secondaryButtonText="Keep running"
          primaryButtonDisabled={pendingAction !== null}
          onRequestSubmit={confirmCancellation}
          onRequestClose={() => {
            if (!pendingAction) setConfirmationAction(null);
          }}
        >
          <p className="agent-sandbox-confirm-copy">
            Running work will stop and cannot be resumed.
          </p>
          {controlError && (
            <p className="agent-sandbox-control-error" role="alert">
              {controlError}
            </p>
          )}
        </Modal>
      )}
    </section>
  );
}
