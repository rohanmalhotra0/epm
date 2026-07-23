import { afterEach, describe, expect, it, vi } from "vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type {
  AgentSession,
  AgentWorker,
} from "../src/api/agentSessions";
import { AgentSandbox } from "../src/components/AgentSandbox";
import { useUi } from "../src/store/ui";

function worker(
  id: string,
  role: string,
  overrides: Partial<AgentWorker> = {},
): AgentWorker {
  return {
    id,
    role,
    assignment: `${role} assignment`,
    status: "running",
    progress: 20,
    activity: `${role} is checking the task.`,
    output: `${role} shared an update.`,
    ...overrides,
  };
}

function session(overrides: Partial<AgentSession> = {}): AgentSession {
  return {
    id: "session-12345678",
    goal: "Validate the Workforce forecast.",
    projectId: "project-7",
    status: "running",
    agentCount: 3,
    progress: 20,
    agents: [
      worker("agent-1", "Coordinator"),
      worker("agent-2", "Metadata analyst", {
        progress: 35,
        activity: "Reviewing the Scenario dimension.",
        output: "Found two assumptions to validate.",
      }),
      worker("agent-3", "Validation lead"),
    ],
    createdAt: "2026-07-23T12:00:00Z",
    updatedAt: "2026-07-23T12:00:01Z",
    ...overrides,
  };
}

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { "content-type": "application/json" },
    }),
  );
}

function renderWithAppBackground() {
  return render(
    <div className="app-shell">
      <main>
        <AgentSandbox />
      </main>
      <aside data-testid="app-background">
        <button type="button">Background action</button>
      </aside>
    </div>,
  );
}

describe("AgentSandbox", () => {
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    useUi.setState({ currentProjectId: null });
  });

  it("requires a task before launching a backend session", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderWithAppBackground();

    await user.click(screen.getByRole("button", { name: "Launch agent team" }));

    expect(screen.getByText("Enter the task this team should work on.")).toBeVisible();
    expect(screen.getByLabelText("Task for the team")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
    expect(screen.getByLabelText("Task for the team")).toHaveFocus();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("enforces the backend task limit and focuses invalid input", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<AgentSandbox />);
    const taskInput = screen.getByLabelText("Task for the team");

    expect(taskInput).toHaveAttribute("maxlength", "4000");
    fireEvent.change(taskInput, { target: { value: "x".repeat(4_001) } });
    await user.click(screen.getByRole("button", { name: "Launch agent team" }));

    expect(
      screen.getByText("Keep the task to 4,000 characters or fewer."),
    ).toBeVisible();
    expect(taskInput).toHaveFocus();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("creates 1-12 agents using the current project", async () => {
    useUi.setState({ currentProjectId: "project-7" });
    const created = session({
      agentCount: 12,
      agents: Array.from({ length: 12 }, (_, index) =>
        worker(`agent-${index + 1}`, `Worker ${index + 1}`),
      ),
    });
    const fetchMock = vi.fn().mockImplementation(() => jsonResponse(created));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<AgentSandbox />);

    expect(screen.getByText("Before you launch")).toBeVisible();
    expect(screen.getByText(/one AI provider call per agent/i)).toBeVisible();
    expect(
      screen.getByText(/no browser control, Oracle EPM connection, deployment, or write access/i),
    ).toBeVisible();
    expect(screen.getByLabelText("Team size")).toHaveDisplayValue("3 agents");
    expect(within(screen.getByLabelText("Team size")).getAllByRole("option")).toHaveLength(
      12,
    );
    await user.selectOptions(screen.getByLabelText("Team size"), "12");
    await user.type(
      screen.getByLabelText("Task for the team"),
      "Validate the Workforce forecast.",
    );
    await user.click(screen.getByRole("button", { name: "Launch agent team" }));

    await waitFor(() => expect(screen.getAllByRole("article")).toHaveLength(12));
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/agent/sessions",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          goal: "Validate the Workforce forecast.",
          projectId: "project-7",
          agentCount: 12,
        }),
      }),
    );
    expect(
      within(screen.getByLabelText("Session summary")).getByText("Running"),
    ).toBeVisible();
    expect(screen.getByLabelText("Team size")).toBeDisabled();
    expect(screen.queryByText(/preview/i)).not.toBeInTheDocument();
  });

  it("polls active sessions and renders backend progress", async () => {
    vi.useFakeTimers();
    const refreshed = session({
      status: "completed",
      progress: 100,
      agents: [
        worker("agent-1", "Coordinator", {
          status: "completed",
          progress: 100,
          activity: "Coordination is complete.",
          output: "Final plan ready.",
        }),
      ],
      agentCount: 1,
    });
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(() => jsonResponse(session()))
      .mockImplementationOnce(() => jsonResponse(refreshed));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentSandbox />);

    fireEvent.change(screen.getByLabelText("Task for the team"), {
      target: { value: "Validate the forecast." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Launch agent team" }));
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(
      within(screen.getByLabelText("Session summary")).getByText("Running"),
    ).toBeVisible();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });

    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/agent/sessions/session-12345678",
      expect.objectContaining({ headers: expect.any(Object) }),
    );
    expect(
      within(screen.getByLabelText("Session summary")).getByText("Completed"),
    ).toBeVisible();
    expect(screen.getByText("100%")).toBeVisible();
  });

  it("forgets a session that the backend no longer has", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(() => jsonResponse(session()))
      .mockImplementationOnce(() =>
        jsonResponse({ detail: "agent session not found" }, 404),
      );
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentSandbox />);

    fireEvent.change(screen.getByLabelText("Task for the team"), {
      target: { value: "Validate the forecast." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Launch agent team" }));
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(
      within(screen.getByLabelText("Session summary")).getByText("Running"),
    ).toBeVisible();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });

    expect(
      screen.getByText(
        "This agent session is no longer available. You can launch a new team.",
      ),
    ).toHaveAttribute("role", "alert");
    expect(screen.getByRole("button", { name: "Launch agent team" })).toBeEnabled();
    expect(screen.getByLabelText("Task for the team")).toBeEnabled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("pauses and resumes the real session lifecycle", async () => {
    const paused = session({
      status: "paused",
      agents: session().agents.map((agent) => ({ ...agent, status: "paused" })),
    });
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(() => jsonResponse(session()))
      .mockImplementationOnce(() => jsonResponse(paused))
      .mockImplementationOnce(() => jsonResponse(session()));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderWithAppBackground();

    await user.type(screen.getByLabelText("Task for the team"), "Review a rule.");
    await user.click(screen.getByRole("button", { name: "Launch agent team" }));
    expect(
      await screen.findByText(/provider calls already in progress may continue/i),
    ).toBeVisible();
    await user.click(
      await screen.findByRole("button", { name: "Pause updates" }),
    );

    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/agent/sessions/session-12345678/pause",
      expect.objectContaining({ method: "POST" }),
    );
    await user.click(
      await screen.findByRole("button", { name: "Resume updates" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "/api/agent/sessions/session-12345678/resume",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("cancels active work before resetting the form", async () => {
    const cancelled = session({
      status: "cancelled",
      agents: session().agents.map((agent) => ({ ...agent, status: "cancelled" })),
    });
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(() => jsonResponse(session()))
      .mockImplementationOnce(() => jsonResponse(cancelled));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderWithAppBackground();

    await user.type(screen.getByLabelText("Task for the team"), "Review a rule.");
    await user.click(screen.getByRole("button", { name: "Launch agent team" }));
    await user.click(await screen.findByRole("button", { name: "Reset" }));

    const dialog = screen.getByRole("dialog", {
      name: "Reset and cancel this session?",
    });
    expect(screen.getByTestId("app-background")).toHaveAttribute("inert");
    expect(screen.getByTestId("app-background")).toHaveAttribute(
      "aria-hidden",
      "true",
    );
    await user.click(
      within(dialog).getByRole("button", { name: /Cancel and reset$/ }),
    );

    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/agent/sessions/session-12345678/cancel",
      expect.objectContaining({ method: "POST" }),
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Launch agent team" })).toBeEnabled(),
    );
    expect(screen.getByLabelText("Task for the team")).toBeEnabled();
    expect(screen.getByTestId("app-background")).not.toHaveAttribute("inert");
    expect(screen.getByTestId("app-background")).not.toHaveAttribute("aria-hidden");
  });

  it("resets cleanly when an active session already expired", async () => {
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(() => jsonResponse(session()))
      .mockImplementationOnce(() =>
        jsonResponse({ detail: "agent session not found" }, 404),
      );
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderWithAppBackground();

    await user.type(screen.getByLabelText("Task for the team"), "Review a rule.");
    await user.click(screen.getByRole("button", { name: "Launch agent team" }));
    await user.click(await screen.findByRole("button", { name: "Reset" }));
    await user.click(
      within(
        screen.getByRole("dialog", {
          name: "Reset and cancel this session?",
        }),
      ).getByRole("button", { name: /Cancel and reset$/ }),
    );

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Launch agent team" })).toBeEnabled(),
    );
    expect(
      screen.queryByRole("dialog", {
        name: "Reset and cancel this session?",
      }),
    ).not.toBeInTheDocument();
  });

  it("observes and switches between real worker telemetry", async () => {
    const fetchMock = vi.fn().mockImplementation(() => jsonResponse(session()));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderWithAppBackground();

    await user.type(screen.getByLabelText("Task for the team"), "Review a planning rule.");
    await user.click(screen.getByRole("button", { name: "Launch agent team" }));
    await user.click(
      await screen.findByRole("button", { name: "Observe Coordinator" }),
    );

    const dialog = screen.getByRole("dialog", {
      name: "Observe agent · Coordinator",
    });
    expect(
      screen.getByRole("button", { name: "Observe Metadata analyst", hidden: true }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("app-background")).toHaveAttribute("inert");
    expect(screen.getByTestId("app-background")).toHaveAttribute(
      "aria-hidden",
      "true",
    );
    expect(within(dialog).getByText("Live worker telemetry")).toBeVisible();
    expect(
      within(dialog).getByText(/no browser or Oracle EPM access/i),
    ).toBeVisible();
    expect(within(dialog).queryByText(/browser pixels/i)).not.toBeInTheDocument();
    expect(within(dialog).getByLabelText("Agent workspace state")).toBeVisible();
    expect(within(dialog).getByRole("button", { name: /Coordinator/ })).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    await user.click(
      within(dialog).getByRole("button", { name: /Metadata analyst/ }),
    );
    expect(
      screen.getByRole("dialog", { name: "Observe agent · Metadata analyst" }),
    ).toBeVisible();
    expect(within(dialog).getByText("Reviewing the Scenario dimension.")).toBeVisible();
    expect(within(dialog).getByText("Found two assumptions to validate.")).toBeVisible();
    expect(
      within(dialog).getByRole("button", { name: /Metadata analyst/ }),
    ).toHaveAttribute("aria-pressed", "true");

    await user.click(within(dialog).getByRole("button", { name: "Close" }));
    expect(screen.getByTestId("app-background")).not.toHaveAttribute("inert");
    expect(screen.getByTestId("app-background")).not.toHaveAttribute("aria-hidden");
  });

  it.each([
    {
      sessionStatus: "completed" as const,
      agentStatus: "completed" as const,
      heading: "Completed team handoff",
      result: "Final plan ready.",
      error: null,
    },
    {
      sessionStatus: "failed" as const,
      agentStatus: "failed" as const,
      heading: "Failed session handoff",
      result: "",
      error: "The provider rejected the request.",
    },
  ])(
    "shows and copies a $sessionStatus handoff built from real results",
    async ({ sessionStatus, agentStatus, heading, result, error }) => {
      const finished = session({
        status: sessionStatus,
        progress: sessionStatus === "completed" ? 100 : 40,
        agentCount: 1,
        agents: [
          worker("agent-1", "Coordinator", {
            status: agentStatus,
            progress: sessionStatus === "completed" ? 100 : 40,
            output: result,
            error,
          }),
        ],
      });
      const fetchMock = vi.fn().mockImplementation(() => jsonResponse(finished));
      const writeText = vi.fn().mockResolvedValue(undefined);
      vi.stubGlobal("fetch", fetchMock);
      vi.spyOn(globalThis.navigator, "clipboard", "get").mockReturnValue({
        writeText,
      } as unknown as Clipboard);
      render(<AgentSandbox />);

      fireEvent.change(screen.getByLabelText("Task for the team"), {
        target: { value: "Prepare a handoff." },
      });
      fireEvent.click(screen.getByRole("button", { name: "Launch agent team" }));

      expect(
        await screen.findByRole("heading", { name: heading }),
      ).toBeVisible();
      expect(
        screen.getByText(result || "The provider rejected the request."),
      ).toBeVisible();
      fireEvent.click(screen.getByRole("button", { name: "Copy handoff" }));

      await waitFor(() => expect(writeText).toHaveBeenCalledOnce());
      expect(writeText.mock.calls[0][0]).toContain("READ-ONLY AGENT SANDBOX HANDOFF");
      expect(writeText.mock.calls[0][0]).toContain(
        result || "The provider rejected the request.",
      );
      expect(screen.getByText("Handoff copied to clipboard.")).toBeVisible();
    },
  );

  it("announces a cancel failure only inside the confirmation modal", async () => {
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(() => jsonResponse(session()))
      .mockImplementationOnce(() =>
        jsonResponse({ detail: "Cancellation timed out." }, 503),
      );
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderWithAppBackground();

    await user.type(screen.getByLabelText("Task for the team"), "Review a rule.");
    await user.click(screen.getByRole("button", { name: "Launch agent team" }));
    await user.click(await screen.findByRole("button", { name: /Cancel/ }));

    const dialog = screen.getByRole("dialog", { name: "Cancel this session?" });
    await user.click(
      within(dialog).getByRole("button", { name: /Cancel session$/ }),
    );

    const alerts = await within(dialog).findAllByRole("alert");
    expect(alerts).toHaveLength(1);
    expect(alerts[0]).toHaveTextContent(
      "Could not cancel this session: Cancellation timed out.",
    );
    expect(screen.getAllByText(/Could not cancel this session/)).toHaveLength(1);
  });

  it("shows backend errors beside the launch controls", async () => {
    const fetchMock = vi
      .fn()
      .mockImplementation(() =>
        jsonResponse({ detail: "Agent service is unavailable." }, 503),
      );
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<AgentSandbox />);

    await user.type(screen.getByLabelText("Task for the team"), "Review a rule.");
    await user.click(screen.getByRole("button", { name: "Launch agent team" }));

    expect(
      await screen.findByText(
        "Could not launch the agent team: Agent service is unavailable.",
      ),
    ).toHaveAttribute("role", "alert");
  });
});
