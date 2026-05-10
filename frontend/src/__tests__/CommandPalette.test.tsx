import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CommandPalette } from "@/components/CommandPalette";
import { useBrainStore } from "@/state/brain.store";

describe("CommandPalette", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.useRealTimers();
    window.localStorage.clear();
    useBrainStore.setState({ entities: new Map(), edges: new Map(), selectedId: null });
  });

  it("opens with Ctrl-K and Escape closes it", () => {
    render(<CommandPalette />);

    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    expect(screen.getByPlaceholderText("Ask the brain… (e.g. how do refunds work)")).toBeInTheDocument();

    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("opens with slash outside text input", () => {
    render(<CommandPalette />);

    fireEvent.keyDown(window, { key: "/" });

    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("does not open with slash while typing in another input", () => {
    render(
      <>
        <input aria-label="Other input" />
        <CommandPalette />
      </>,
    );

    fireEvent.keyDown(screen.getByLabelText("Other input"), { key: "/" });

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("dismisses the HUD hint", () => {
    render(<CommandPalette />);

    fireEvent.click(screen.getByLabelText("Dismiss search hint"));

    expect(screen.queryByText("Press ⌘K to find anything")).not.toBeInTheDocument();
  });

  it("renders an empty state for no search matches", async () => {
    vi.spyOn(window, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({ results: [] }),
    } as Response);
    render(<CommandPalette />);

    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    fireEvent.change(screen.getByPlaceholderText("Ask the brain… (e.g. how do refunds work)"), {
      target: { value: "missing" },
    });

    await waitFor(() => expect(screen.getByText("No matching entities")).toBeInTheDocument());
  });

  it("searches entities and dispatches fly-to on Enter", async () => {
    const fetchMock = vi.spyOn(window, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        results: [
          {
            id: "entity-1",
            type: "decision",
            title: "Refund Policy 2026 (v3)",
            connection_count: 14,
            methods: ["hybrid"],
            breakdown: { lexical: { rank: 1, score: 0.9 } },
          },
        ],
      }),
    } as Response);
    const dispatchSpy = vi.spyOn(window, "dispatchEvent");
    render(<CommandPalette />);

    fireEvent.keyDown(window, { key: "k", metaKey: true });
    fireEvent.change(screen.getByPlaceholderText("Ask the brain… (e.g. how do refunds work)"), {
      target: { value: "refund" },
    });

    await waitFor(() => expect(screen.getByText("Refund Policy 2026 (v3)")).toBeInTheDocument());
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Enter" });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/internal/search",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ query: "refund", mode: "hybrid", top_k: 8 }),
      }),
    );
    expect(useBrainStore.getState().selectedId).toBe("entity-1");
    expect(dispatchSpy).toHaveBeenCalledWith(expect.objectContaining({ type: "axiom:fly-to-entity" }));
  });

  it("falls back to loaded entities when backend search is unavailable", async () => {
    vi.spyOn(window, "fetch").mockResolvedValue({
      ok: false,
      status: 404,
    } as Response);
    useBrainStore.setState({
      entities: new Map([
        [
          "refund-doc",
          {
            id: "refund-doc",
            type: "document",
            data: { title: "Refund Policy 2026 (v3)" },
            source_id: null,
            created_at: "t",
            updated_at: "t",
          },
        ],
      ]),
      edges: new Map(),
    });
    render(<CommandPalette />);

    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    fireEvent.change(screen.getByPlaceholderText("Ask the brain… (e.g. how do refunds work)"), {
      target: { value: "refund" },
    });

    await waitFor(() => expect(screen.getByText("Refund Policy 2026 (v3)")).toBeInTheDocument());
  });

  it("persists the selected search mode", async () => {
    vi.spyOn(window, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({ results: [] }),
    } as Response);
    render(<CommandPalette />);

    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    fireEvent.click(screen.getByRole("button", { name: "Semantic" }));

    expect(window.localStorage.getItem("axiom.search.mode")).toBe("semantic");
  });

  it("uses the persisted search mode for requests", async () => {
    window.localStorage.setItem("axiom.search.mode", "graph");
    const fetchMock = vi.spyOn(window, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({ results: [] }),
    } as Response);
    render(<CommandPalette />);

    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    fireEvent.change(screen.getByPlaceholderText("Ask the brain… (e.g. how do refunds work)"), {
      target: { value: "refund" },
    });

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/internal/search",
        expect.objectContaining({
          body: JSON.stringify({ query: "refund", mode: "graph", top_k: 8 }),
        }),
      ),
    );
  });

  it("renders method badges with breakdown tooltip", async () => {
    vi.spyOn(window, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        results: [
          {
            id: "entity-1",
            type: "decision",
            title: "Refund Policy 2026 (v3)",
            connection_count: 14,
            methods: ["lexical", "semantic"],
            breakdown: {
              lexical: { rank: 1, score: 0.91 },
              semantic: { rank: 2, score: 0.82 },
            },
          },
        ],
      }),
    } as Response);
    render(<CommandPalette />);

    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    fireEvent.change(screen.getByPlaceholderText("Ask the brain… (e.g. how do refunds work)"), {
      target: { value: "refund" },
    });

    await waitFor(() => expect(screen.getByText("lex")).toBeInTheDocument());
    expect(screen.getByText("sem")).toBeInTheDocument();
    expect(screen.getByTitle((title) => title.includes("lexical: rank 1") && title.includes("semantic: rank 2"))).toBeInTheDocument();
  });
});
