import { useMemo, useState } from "react";
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
  Launch,
  Pause,
  Play,
  Restart,
  Screen,
  Task,
  UserMultiple,
} from "@carbon/icons-react";
import "../styles/agent-sandbox.css";

type SessionState = "draft" | "running" | "paused" | "complete";

interface AgentProfile {
  role: string;
  assignment: string;
  context: string;
  activity: string;
  output: string;
}

const AGENT_PROFILES: AgentProfile[] = [
  {
    role: "Coordinator",
    assignment: "Breaks the task into workstreams and combines results.",
    context: "EPM Wizard · project overview",
    activity: "Mapping dependencies and assigning validation checkpoints.",
    output: "Created a four-step execution plan with review gates.",
  },
  {
    role: "Metadata analyst",
    assignment: "Checks dimensions, members, forms, and project context.",
    context: "Oracle EPM · Dimensions",
    activity: "Reviewing Scenario and Version member relationships.",
    output: "Found 12 relevant members and flagged 2 assumptions.",
  },
  {
    role: "Rule builder",
    assignment: "Drafts calculations and implementation changes.",
    context: "Oracle EPM · Calculation Manager",
    activity: "Drafting the scoped calculation and checking substitutions.",
    output: "Prepared a draft rule without deploying any changes.",
  },
  {
    role: "Validation lead",
    assignment: "Tests outputs and looks for data or logic regressions.",
    context: "Oracle EPM · Smart View validation",
    activity: "Comparing expected totals across Scenario and Period.",
    output: "Queued six checks covering totals, signs, and missing data.",
  },
  {
    role: "Release reviewer",
    assignment: "Reviews safety, approvals, and deployment readiness.",
    context: "EPM Wizard · deployment review",
    activity: "Checking environment class and required approvals.",
    output: "Production writes remain blocked pending explicit approval.",
  },
  {
    role: "Documentation",
    assignment: "Captures decisions, assumptions, and handoff notes.",
    context: "EPM Wizard · task notes",
    activity: "Summarizing decisions and unresolved questions.",
    output: "Drafted a concise implementation and validation handoff.",
  },
];

const PROGRESS_BY_STEP = [
  [0, 0, 0, 0, 0, 0],
  [18, 12, 8, 5, 4, 2],
  [48, 39, 32, 26, 21, 16],
  [76, 68, 61, 54, 47, 41],
  [100, 100, 100, 100, 100, 100],
];

const ACTIVITY_TIMES = ["00:04", "00:11", "00:18"];

function statusFor(progress: number, state: SessionState) {
  if (progress === 100) return "Complete";
  if (state === "paused") return "Paused";
  if (progress === 0) return "Ready";
  return "Working";
}

export function AgentSandbox() {
  const [task, setTask] = useState("");
  const [agentCount, setAgentCount] = useState(3);
  const [sessionState, setSessionState] = useState<SessionState>("draft");
  const [previewStep, setPreviewStep] = useState(0);
  const [taskError, setTaskError] = useState<string | null>(null);
  const [watchingIndex, setWatchingIndex] = useState<number | null>(null);

  const agents = useMemo(() => AGENT_PROFILES.slice(0, agentCount), [agentCount]);
  const progress = PROGRESS_BY_STEP[previewStep];
  const watchingAgent = watchingIndex === null ? null : agents[watchingIndex];

  const launchPreview = () => {
    if (!task.trim()) {
      setTaskError("Enter the task this team should work on.");
      return;
    }
    setTaskError(null);
    setPreviewStep(1);
    setSessionState("running");
  };

  const advancePreview = () => {
    const nextStep = Math.min(previewStep + 1, PROGRESS_BY_STEP.length - 1);
    setPreviewStep(nextStep);
    setSessionState(nextStep === PROGRESS_BY_STEP.length - 1 ? "complete" : "running");
  };

  const resetPreview = () => {
    setPreviewStep(0);
    setSessionState("draft");
    setWatchingIndex(null);
  };

  const openLiveView = (index: number) => {
    setWatchingIndex(index);
  };

  return (
    <section className="agent-sandbox" aria-labelledby="agent-sandbox-title">
      <div className="agent-sandbox-heading">
        <div>
          <div className="agent-sandbox-title-row">
            <UserMultiple size={20} aria-hidden="true" />
            <h3 id="agent-sandbox-title">Agent sandbox</h3>
            <Tag type="cool-gray" size="sm">Local preview</Tag>
          </div>
          <p>
            Split one EPM task across a focused team, then inspect each workstream from one place.
          </p>
        </div>
        <div className="agent-sandbox-summary" aria-live="polite">
          <span>{agentCount} agents</span>
          <span aria-hidden="true">·</span>
          <strong>{sessionState === "draft" ? "Not started" : statusFor(progress[0], sessionState)}</strong>
        </div>
      </div>

      <InlineNotification
        kind="info"
        lowContrast
        hideCloseButton
        title="Preview only"
        subtitle="This interface simulates team activity locally. It does not start backend agents, capture a screen, or make EPM changes yet."
      />

      <div className="agent-sandbox-launcher">
        <TextArea
          id="sandbox-task"
          labelText="Task for the team"
          placeholder="For example: Review the Workforce forecast rule, validate totals, and prepare a safe deployment plan"
          rows={3}
          value={task}
          invalid={taskError !== null}
          invalidText={taskError ?? undefined}
          disabled={sessionState !== "draft"}
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
            disabled={sessionState !== "draft"}
            onChange={(event) => setAgentCount(Number(event.target.value))}
          >
            {AGENT_PROFILES.map((_, index) => {
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
          {sessionState === "draft" ? (
            <Button renderIcon={Launch} onClick={launchPreview}>
              Launch preview team
            </Button>
          ) : (
            <div className="agent-sandbox-session-controls">
              {sessionState !== "complete" && (
                <Button
                  kind="secondary"
                  renderIcon={sessionState === "paused" ? Play : Pause}
                  onClick={() =>
                    setSessionState(sessionState === "paused" ? "running" : "paused")
                  }
                >
                  {sessionState === "paused" ? "Resume" : "Pause"}
                </Button>
              )}
              {sessionState !== "complete" && (
                <Button
                  renderIcon={Play}
                  disabled={sessionState === "paused"}
                  onClick={advancePreview}
                >
                  Advance preview
                </Button>
              )}
              <Button kind="ghost" renderIcon={Restart} onClick={resetPreview}>
                Reset
              </Button>
            </div>
          )}
        </div>
      </div>

      <div className="agent-sandbox-team-head">
        <div>
          <h4>Team activity</h4>
          <p>
            Each agent has a narrow role so work can happen in parallel and be reviewed clearly.
          </p>
        </div>
        {sessionState !== "draft" && (
          <span className="agent-sandbox-step">
            Preview step <strong>{previewStep}</strong> of <strong>4</strong>
          </span>
        )}
      </div>

      <div className="agent-sandbox-grid">
        {agents.map((agent, index) => {
          const agentProgress = progress[index];
          const agentStatus = statusFor(agentProgress, sessionState);
          return (
            <article className="agent-sandbox-card" key={agent.role}>
              <div className="agent-sandbox-card-head">
                <span className="agent-sandbox-avatar" aria-hidden="true">
                  <Bot size={18} />
                </span>
                <div>
                  <h5>{agent.role}</h5>
                  <span>Agent {String(index + 1).padStart(2, "0")}</span>
                </div>
                <span
                  className={`agent-sandbox-status agent-sandbox-status-${agentStatus.toLowerCase()}`}
                >
                  {agentStatus}
                </span>
              </div>
              <p>{agent.assignment}</p>
              <ProgressBar
                label={`${agent.role} progress`}
                value={agentProgress}
                status={agentProgress === 100 ? "finished" : "active"}
              />
              <div className="agent-sandbox-card-foot">
                <span>{agentProgress}%</span>
                <Button
                  kind="ghost"
                  size="sm"
                  renderIcon={Screen}
                  disabled={sessionState === "draft"}
                  onClick={() => openLiveView(index)}
                >
                  Watch live
                </Button>
              </div>
            </article>
          );
        })}
      </div>

      <Modal
        open={watchingAgent !== null}
        passiveModal
        size="lg"
        modalHeading={watchingAgent ? `Watch live · ${watchingAgent.role}` : "Watch live"}
        onRequestClose={() => setWatchingIndex(null)}
      >
        {watchingAgent && watchingIndex !== null && (
          <div className="agent-live" data-testid="agent-live-view">
            <InlineNotification
              kind="info"
              lowContrast
              hideCloseButton
              title="Simulated live view"
              subtitle="This is a UI preview of agent observability, not a screen recording or active browser session."
            />
            <div className="agent-live-layout">
              <nav className="agent-live-agents" aria-label="Agents in this preview team">
                {agents.map((agent, index) => (
                  <Button
                    key={agent.role}
                    kind={watchingIndex === index ? "secondary" : "ghost"}
                    size="sm"
                    onClick={() => setWatchingIndex(index)}
                  >
                    <span>
                      <strong>{agent.role}</strong>
                      <small>{statusFor(progress[index], sessionState)} · {progress[index]}%</small>
                    </span>
                  </Button>
                ))}
              </nav>

              <div className="agent-live-workspace">
                <div className="agent-live-browser" aria-label="Simulated browser context">
                  <div className="agent-live-browser-bar">
                    <span aria-hidden="true">EPM</span>
                    <code>{watchingAgent.context}</code>
                    <Tag type="gray" size="sm">Preview feed</Tag>
                  </div>
                  <div className="agent-live-browser-body">
                    <aside>
                      <span>Overview</span>
                      <strong>Applications</strong>
                      <span>Rules</span>
                      <span>Data</span>
                      <span>Reports</span>
                    </aside>
                    <div className="agent-live-canvas">
                      <div className="agent-live-canvas-head">
                        <Task size={16} aria-hidden="true" />
                        <strong>Current browser context</strong>
                      </div>
                      <dl>
                        <div>
                          <dt>Area</dt>
                          <dd>{watchingAgent.context}</dd>
                        </div>
                        <div>
                          <dt>Access</dt>
                          <dd>Read-only preview</dd>
                        </div>
                        <div>
                          <dt>Task</dt>
                          <dd>{task}</dd>
                        </div>
                      </dl>
                    </div>
                  </div>
                </div>

                <div className="agent-live-panels">
                  <section>
                    <h4>Activity</h4>
                    <ol>
                      <li>
                        <time>{ACTIVITY_TIMES[0]}</time>
                        <span>Received the shared task and scoped the assignment.</span>
                      </li>
                      <li>
                        <time>{ACTIVITY_TIMES[1]}</time>
                        <span>{watchingAgent.activity}</span>
                      </li>
                      <li>
                        <time>{ACTIVITY_TIMES[2]}</time>
                        <span>Shared an update with the coordinator.</span>
                      </li>
                    </ol>
                  </section>
                  <section>
                    <h4>Latest output</h4>
                    <div className="agent-live-output">
                      <CheckmarkFilled size={16} aria-hidden="true" />
                      <p>{watchingAgent.output}</p>
                    </div>
                  </section>
                </div>
              </div>
            </div>
          </div>
        )}
      </Modal>
    </section>
  );
}
