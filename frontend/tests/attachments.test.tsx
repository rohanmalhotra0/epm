import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Composer } from "../src/components/Composer";
import { ChatPage } from "../src/pages/ChatPage";
import { useToasts } from "../src/store/toast";

const attachment = {
  id: "a1",
  conversationId: "c1",
  projectId: "p1",
  filename: "coa.xlsx",
  mediaType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  sizeBytes: 3,
  checksum: "abc123",
  sheetNames: ["Accounts"],
  kindGuess: "chartOfAccounts",
};

function jsonResponse(data: unknown, status = 200) {
  return { ok: true, status, json: async () => data } as Response;
}

/** SSE response whose reader never resolves — keeps the stream (and pending state) open. */
function hangingStreamResponse() {
  return {
    ok: true,
    status: 200,
    body: { getReader: () => ({ read: () => new Promise(() => {}) }) },
  } as unknown as Response;
}

function stubFetch() {
  const mock = vi.fn(async (url: RequestInfo | URL, opts?: RequestInit) => {
    const u = String(url);
    if (u.includes("/attachments")) return jsonResponse(attachment, 201);
    if (u.includes("/messages") && opts?.method === "POST") return hangingStreamResponse();
    return jsonResponse([]);
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

function pickFile(file: File) {
  const input = screen.getByLabelText("Attach spreadsheet files");
  fireEvent.change(input, { target: { files: [file] } });
}

afterEach(() => {
  vi.unstubAllGlobals();
  act(() => useToasts.setState({ toasts: [] }));
});

describe("Composer attachments", () => {
  beforeEach(() => stubFetch());

  it("shows the paperclip button when a conversation is active", () => {
    render(<Composer onSend={vi.fn()} streaming={false} onStop={() => {}} conversationId="c1" />);
    expect(screen.getByLabelText("Attach files")).toBeInTheDocument();
  });

  it("uploads a picked file and renders a chip with size and kind tag", async () => {
    render(<Composer onSend={vi.fn()} streaming={false} onStop={() => {}} conversationId="c1" />);
    pickFile(new File(["a,b"], "coa.xlsx"));
    expect(await screen.findByText("coa.xlsx")).toBeInTheDocument();
    expect(screen.getByText("chart of accounts")).toBeInTheDocument();
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    const call = fetchMock.mock.calls.find((c) => String(c[0]) === "/api/conversations/c1/attachments");
    expect(call).toBeTruthy();
    expect((call![1] as RequestInit).method).toBe("POST");
    expect((call![1] as RequestInit).body).toBeInstanceOf(FormData);
  });

  it("removes a chip via its ✕ button", async () => {
    render(<Composer onSend={vi.fn()} streaming={false} onStop={() => {}} conversationId="c1" />);
    pickFile(new File(["a,b"], "coa.xlsx"));
    await screen.findByText("coa.xlsx");
    fireEvent.click(screen.getByLabelText("Remove coa.xlsx"));
    expect(screen.queryByText("coa.xlsx")).toBeNull();
  });

  it("passes uploaded attachments to onSend and clears the chips", async () => {
    const onSend = vi.fn();
    render(<Composer onSend={onSend} streaming={false} onStop={() => {}} conversationId="c1" />);
    pickFile(new File(["a,b"], "coa.xlsx"));
    await screen.findByText("chart of accounts");
    const ta = screen.getByLabelText("Message EPM Wizard");
    fireEvent.change(ta, { target: { value: "map these accounts" } });
    fireEvent.keyDown(ta, { key: "Enter" });
    expect(onSend).toHaveBeenCalledWith("map these accounts", [expect.objectContaining({ id: "a1" })]);
    expect(screen.queryByText("coa.xlsx")).toBeNull();
  });

  it("sends a default content when text is empty but attachments are present", async () => {
    const onSend = vi.fn();
    render(<Composer onSend={onSend} streaming={false} onStop={() => {}} conversationId="c1" />);
    pickFile(new File(["a,b"], "coa.xlsx"));
    await screen.findByText("chart of accounts");
    fireEvent.keyDown(screen.getByLabelText("Message EPM Wizard"), { key: "Enter" });
    expect(onSend).toHaveBeenCalledWith("Analyze the attached file.", [expect.objectContaining({ id: "a1" })]);
  });

  it("rejects unsupported extensions with a toast and no upload", () => {
    render(<Composer onSend={vi.fn()} streaming={false} onStop={() => {}} conversationId="c1" />);
    pickFile(new File(["x"], "notes.txt"));
    expect(useToasts.getState().toasts.some((t) => t.kind === "error" && t.title.includes("notes.txt"))).toBe(true);
    expect(fetch).not.toHaveBeenCalled();
    expect(screen.queryByText("notes.txt")).toBeNull();
  });

  it("rejects files over 10 MB with a toast and no upload", () => {
    render(<Composer onSend={vi.fn()} streaming={false} onStop={() => {}} conversationId="c1" />);
    const big = new File(["x"], "big.xlsx");
    Object.defineProperty(big, "size", { value: 11 * 1024 * 1024 });
    pickFile(big);
    expect(useToasts.getState().toasts.some((t) => t.kind === "error" && t.subtitle?.includes("10 MB"))).toBe(true);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("accepts a dropped file and highlights the drop target while dragging", async () => {
    render(<Composer onSend={vi.fn()} streaming={false} onStop={() => {}} conversationId="c1" />);
    fireEvent.dragEnter(document.body, { dataTransfer: { types: ["Files"], files: [] } });
    expect(screen.getByText(/Drop .*to attach/)).toBeInTheDocument();
    fireEvent.drop(document.body, { dataTransfer: { types: ["Files"], files: [new File(["a,b"], "coa.xlsx")] } });
    expect(screen.queryByText(/Drop .*to attach/)).toBeNull();
    expect(await screen.findByText("coa.xlsx")).toBeInTheDocument();
  });
});

describe("ChatPage send with attachments", () => {
  // jsdom does not implement Element.scrollTo (used by the chat auto-scroll).
  beforeEach(() => {
    Element.prototype.scrollTo = Element.prototype.scrollTo || (() => {});
  });

  it("includes attachment ids in the message POST body and shows chips on the pending bubble", async () => {
    const fetchMock = stubFetch();
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/c/c1"]}>
          <Routes>
            <Route path="/c/:id" element={<ChatPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    pickFile(new File(["a,b"], "coa.xlsx"));
    await screen.findByText("chart of accounts");
    const ta = screen.getByLabelText("Message EPM Wizard");
    fireEvent.change(ta, { target: { value: "map these accounts" } });
    fireEvent.keyDown(ta, { key: "Enter" });

    await vi.waitFor(() => {
      const call = fetchMock.mock.calls.find(
        (c) => String(c[0]).includes("/messages") && (c[1] as RequestInit)?.method === "POST",
      );
      expect(call).toBeTruthy();
      expect(JSON.parse((call![1] as RequestInit).body as string)).toEqual({
        content: "map these accounts",
        attachments: ["a1"],
      });
    });
    // The just-sent attachment shows as a chip on the pending user bubble.
    expect(await screen.findByText("coa.xlsx")).toBeInTheDocument();
    expect(screen.getByText("map these accounts")).toBeInTheDocument();
  });
});
