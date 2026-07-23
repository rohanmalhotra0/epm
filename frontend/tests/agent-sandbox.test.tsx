import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AgentSandbox } from "../src/components/AgentSandbox";

describe("AgentSandbox", () => {
  afterEach(cleanup);

  it("requires a task before launching the preview", async () => {
    const user = userEvent.setup();
    render(<AgentSandbox />);

    await user.click(screen.getByRole("button", { name: "Launch preview team" }));

    expect(screen.getByText("Enter the task this team should work on.")).toBeVisible();
    expect(screen.getByLabelText("Task for the team")).toHaveAttribute("aria-invalid", "true");
  });

  it("configures and launches a local preview team", async () => {
    const user = userEvent.setup();
    render(<AgentSandbox />);

    await user.selectOptions(screen.getByLabelText("Team size"), "4");
    await user.type(screen.getByLabelText("Task for the team"), "Validate the Workforce forecast.");
    await user.click(screen.getByRole("button", { name: "Launch preview team" }));

    expect(screen.getAllByText("4 agents")[0]).toBeVisible();
    expect(screen.getAllByRole("article")).toHaveLength(4);
    expect(screen.getByText("Preview step", { exact: false })).toHaveTextContent("1 of 4");
    expect(screen.getByRole("button", { name: "Pause" })).toBeEnabled();
    expect(screen.getByLabelText("Team size")).toBeDisabled();
  });

  it("opens a transparent, switchable simulated live view", async () => {
    const user = userEvent.setup();
    render(<AgentSandbox />);

    await user.type(screen.getByLabelText("Task for the team"), "Review a planning rule.");
    await user.click(screen.getByRole("button", { name: "Launch preview team" }));
    await user.click(screen.getAllByRole("button", { name: "Watch live" })[0]);

    const dialog = screen.getByRole("dialog", { name: "Watch live · Coordinator" });
    expect(within(dialog).getByText("Simulated live view")).toBeVisible();
    expect(within(dialog).getByText(/not a screen recording/i)).toBeVisible();
    expect(within(dialog).getByLabelText("Simulated browser context")).toBeVisible();

    await user.click(within(dialog).getByRole("button", { name: /Metadata analyst/ }));
    expect(screen.getByRole("dialog", { name: "Watch live · Metadata analyst" })).toBeVisible();
    expect(within(dialog).getAllByText("Oracle EPM · Dimensions")).toHaveLength(2);
  });
});
