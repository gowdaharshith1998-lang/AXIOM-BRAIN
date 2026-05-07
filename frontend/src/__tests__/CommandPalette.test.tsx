import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CommandPalette } from "@/components/CommandPalette";
import { useBrainStore } from "@/state/brain.store";

describe("CommandPalette", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.useRealTimers();
    useBrainStore.setState({ selectedId: null });
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
      json: async () => [],
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
      json: async () => [
        {
          id: "entity-1",
          type: "decision",
          title: "Refund Policy 2026 (v3)",
          connection_count: 14,
        },
      ],
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
      "http://127.0.0.1:8000/api/entities/search?q=refund&limit=8",
      expect.any(Object),
    );
    expect(useBrainStore.getState().selectedId).toBe("entity-1");
    expect(dispatchSpy).toHaveBeenCalledWith(expect.objectContaining({ type: "axiom:fly-to-entity" }));
  });
});
