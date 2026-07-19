import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { CommandPalette } from "../src/components/CommandPalette";
import { useUi } from "../src/store/ui";
import { searchProject } from "../src/api/search";

vi.mock("../src/api/search", () => ({
  searchProject: vi.fn().mockResolvedValue({
    results: [
      { type: "conversation", id: "c1", title: "Budget review", snippet: "…", updatedAt: "2026-01-01" },
      { type: "artifact", id: "a1", title: "Actuals form", snippet: "form artifact", updatedAt: "2026-01-02" },
    ],
  }),
}));

function renderPalette(props: Partial<React.ComponentProps<typeof CommandPalette>> = {}) {
  return render(
    <MemoryRouter>
      <CommandPalette open onClose={() => {}} onNewChat={() => {}} {...props} />
    </MemoryRouter>,
  );
}

describe("CommandPalette", () => {
  beforeEach(() => {
    act(() => useUi.setState({ currentProjectId: "p1" }));
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it("renders nothing when closed", () => {
    const { container } = render(
      <MemoryRouter>
        <CommandPalette open={false} onClose={() => {}} onNewChat={() => {}} />
      </MemoryRouter>,
    );
    expect(container.querySelector(".cmdk")).toBeNull();
  });

  it("shows quick actions when the query is empty", () => {
    renderPalette();
    expect(screen.getByText("Quick actions")).toBeInTheDocument();
    for (const label of ["New chat", "Contexts", "Artifacts", "Deployments", "Skills", "Explorer", "Data", "Settings"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(screen.getByText(/Toggle theme/)).toBeInTheDocument();
  });

  it("runs the selected quick action on Enter", () => {
    const onNewChat = vi.fn();
    renderPalette({ onNewChat });
    const input = screen.getByLabelText("Command palette search");
    fireEvent.keyDown(input, { key: "Enter" }); // first item = New chat
    expect(onNewChat).toHaveBeenCalled();
  });

  it("moves the selection with arrow keys", () => {
    renderPalette();
    const input = screen.getByLabelText("Command palette search");
    fireEvent.keyDown(input, { key: "ArrowDown" });
    expect(screen.getByText("Contexts").closest(".cmdk-item")).toHaveClass("active");
    fireEvent.keyDown(input, { key: "ArrowUp" });
    expect(screen.getByText("New chat").closest(".cmdk-item")).toHaveClass("active");
  });

  it("closes on Escape", () => {
    const onClose = vi.fn();
    renderPalette({ onClose });
    fireEvent.keyDown(screen.getByLabelText("Command palette search"), { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });

  it("debounces and renders grouped search results", async () => {
    vi.useFakeTimers();
    renderPalette();
    const input = screen.getByLabelText("Command palette search");
    fireEvent.change(input, { target: { value: "budget" } });
    expect(searchProject).not.toHaveBeenCalled();
    await act(async () => {
      vi.advanceTimersByTime(250);
    });
    vi.useRealTimers();
    expect(searchProject).toHaveBeenCalledWith("p1", "budget", 20);
    expect(await screen.findByText("Budget review")).toBeInTheDocument();
    expect(screen.getByText("Conversations")).toBeInTheDocument();
    expect(screen.getByText("Artifacts")).toBeInTheDocument();
    expect(screen.getByText("Actuals form")).toBeInTheDocument();
  });

  it("toggles the theme from a quick action", () => {
    act(() => useUi.setState({ theme: "g100" }));
    renderPalette();
    fireEvent.click(screen.getByText(/Toggle theme/));
    expect(useUi.getState().theme).toBe("white");
  });
});
