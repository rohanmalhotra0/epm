import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AgentPage } from "../src/pages/AgentPage";

vi.mock("../src/agent/extensionBridge", () => ({
  detectExtension: vi.fn(async () => ({ installed: false })),
  launchAgent: vi.fn(),
}));

const token = {
  id: "token-1",
  name: "My laptop",
  prefix: "epmw_abcd",
  createdAt: "2026-07-23T12:00:00Z",
  lastUsedAt: null,
};

function jsonResponse(data: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status >= 400 ? "Request failed" : "OK",
    json: async () => data,
  } as Response;
}

describe("AgentPage API token safety", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse([token])));
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("requires a named danger confirmation before revoking and restores focus on cancel", async () => {
    const user = userEvent.setup();
    render(<AgentPage />);

    const revokeButton = await screen.findByRole("button", { name: "Revoke My laptop" });
    await user.click(revokeButton);

    expect(fetch).toHaveBeenCalledTimes(1);
    const dialog = screen.getByRole("alertdialog", { name: "Revoke “My laptop”?" });
    expect(dialog).toHaveTextContent("epmw_abcd");
    expect(dialog).toHaveTextContent("This action cannot be undone.");
    expect(within(dialog).getByRole("button", { name: "Cancel" })).toHaveFocus();

    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));

    expect(
      screen.queryByRole("alertdialog", { name: "Revoke “My laptop”?" }),
    ).not.toBeInTheDocument();
    await waitFor(() => expect(revokeButton).toHaveFocus());
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("revokes only after confirmation", async () => {
    let revoked = false;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: RequestInfo | URL, options?: RequestInit) => {
        if (options?.method === "DELETE") {
          revoked = true;
          return jsonResponse(undefined, 204);
        }
        return jsonResponse(revoked ? [] : [token]);
      }),
    );
    const user = userEvent.setup();
    render(<AgentPage />);

    await user.click(await screen.findByRole("button", { name: "Revoke My laptop" }));
    const dialog = screen.getByRole("alertdialog", { name: "Revoke “My laptop”?" });
    await user.click(within(dialog).getByRole("button", { name: /Revoke token$/ }));

    await waitFor(() =>
      expect(
        screen.queryByRole("alertdialog", { name: "Revoke “My laptop”?" }),
      ).not.toBeInTheDocument(),
    );
    expect(screen.queryByRole("button", { name: "Revoke My laptop" })).not.toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith("/api/ext-tokens/token-1", expect.objectContaining({
      method: "DELETE",
    }));
  });

  it("keeps revoke failures next to the destructive action and announced", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: RequestInfo | URL, options?: RequestInit) => {
        if (options?.method === "DELETE") {
          return jsonResponse({ detail: "Token is already in use." }, 409);
        }
        return jsonResponse([token]);
      }),
    );
    const user = userEvent.setup();
    render(<AgentPage />);

    await user.click(await screen.findByRole("button", { name: "Revoke My laptop" }));
    const dialog = screen.getByRole("alertdialog", { name: "Revoke “My laptop”?" });
    await user.click(within(dialog).getByRole("button", { name: /Revoke token$/ }));

    const error = await within(dialog).findByRole("alert");
    expect(error).toHaveTextContent("Couldn't revoke token");
    expect(error).toHaveTextContent("Token is already in use.");
    expect(dialog).toBeVisible();
  });

  it("announces the one-time token reveal and preserves copy", async () => {
    const writeText = vi.fn(async () => undefined);
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: RequestInfo | URL, options?: RequestInit) => {
        if (options?.method === "POST") {
          return jsonResponse({ ...token, token: "epmw_secret-once" }, 201);
        }
        return jsonResponse([token]);
      }),
    );
    const user = userEvent.setup();
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    render(<AgentPage />);

    await user.type(screen.getByLabelText("Token name (optional)"), "My laptop");
    await user.click(screen.getByRole("button", { name: "Generate token" }));

    const reveal = await screen.findByRole("status", {
      name: /Copy your token now/,
    });
    expect(reveal).toHaveAttribute("aria-live", "polite");
    expect(reveal).toHaveTextContent("it won't be shown again");
    expect(within(reveal).getByLabelText("New API token: epmw_secret-once")).toBeInTheDocument();

    await user.click(within(reveal).getByRole("button", { name: "Copy" }));
    expect(writeText).toHaveBeenCalledWith("epmw_secret-once");
  });
});
