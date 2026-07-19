import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SkillsPage } from "../src/pages/SkillsPage";
import { useToasts } from "../src/store/toast";

const CATALOG = {
  skills: [
    {
      name: "forms",
      title: "Design data entry forms",
      description: "Create and validate Planning forms from a description.",
      examples: ["Create an Actuals payroll form", "Add a variance column"],
    },
    {
      name: "context",
      title: "Learn your application",
      description: "Build a local metadata context.",
      examples: [],
    },
  ],
};

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SkillsPage />
    </QueryClientProvider>,
  );
}

describe("SkillsPage", () => {
  let writeText: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    useToasts.setState({ toasts: [] });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => CATALOG,
    }));
    writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the fetched skill cards with titles and descriptions", async () => {
    renderPage();
    expect(await screen.findByText("Design data entry forms")).toBeInTheDocument();
    expect(screen.getByText("Learn your application")).toBeInTheDocument();
    expect(screen.getByText(/Create and validate Planning forms/)).toBeInTheDocument();
    expect(vi.mocked(fetch)).toHaveBeenCalledWith("/api/meta/skills", expect.anything());
  });

  it("copies an example to the clipboard and raises a toast", async () => {
    renderPage();
    fireEvent.click(await screen.findByText("Create an Actuals payroll form"));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("Create an Actuals payroll form"));
    await waitFor(() => {
      const toasts = useToasts.getState().toasts;
      expect(toasts.some((t) => t.title === "Copied — paste it in the chat")).toBe(true);
    });
  });

  it("shows an error message when the catalog cannot be loaded", async () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
      json: async () => ({ detail: "boom" }),
    } as unknown as Response);
    renderPage();
    expect(await screen.findByText(/Could not load the skill catalog/)).toBeInTheDocument();
  });
});
