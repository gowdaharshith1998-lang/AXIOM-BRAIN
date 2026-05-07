import { fireEvent, render, screen } from "@testing-library/react";
import { cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BottomToolbar, fpsColor } from "@/components/BottomToolbar";
import { useBrainStore } from "@/state/brain.store";

describe("BottomToolbar", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("renders all toolbar items", () => {
    useBrainStore.setState({ fps: 60, entities: new Map(), edges: new Map() });
    render(<BottomToolbar />);
    expect(screen.getByText("AXIOM v0.1")).toBeInTheDocument();
    expect(screen.getByText("⛶ Fullscreen")).toBeInTheDocument();
    expect(screen.getByText("● Live")).toBeInTheDocument();
    expect(screen.getByText("⏱ Timeline")).toBeInTheDocument();
    expect(screen.getByText("⬇ Export JSON")).toBeInTheDocument();
    expect(screen.getByText("60 FPS")).toBeInTheDocument();
  });

  it("opens the command palette from the search bar", () => {
    const dispatch = vi.spyOn(window, "dispatchEvent");
    render(<BottomToolbar />);
    fireEvent.click(screen.getByText(/Find symbol/));
    expect(dispatch).toHaveBeenCalledWith(expect.objectContaining({ type: "axiom:open-palette" }));
  });

  it("color-codes fps", () => {
    expect(fpsColor(60)).toBe("#22c55e");
    expect(fpsColor(40)).toBe("#eab308");
    expect(fpsColor(20)).toBe("#ef4444");
  });

  it("shows zero fps before the first renderer sample", () => {
    useBrainStore.setState({ fps: 0, entities: new Map(), edges: new Map() });
    render(<BottomToolbar />);
    expect(screen.getByText("0 FPS")).toBeInTheDocument();
  });

  it("exports visible JSON", () => {
    Object.defineProperty(URL, "createObjectURL", { value: vi.fn(), configurable: true });
    Object.defineProperty(URL, "revokeObjectURL", { value: vi.fn(), configurable: true });
    const create = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:axiom");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    render(<BottomToolbar />);
    fireEvent.click(screen.getByText("⬇ Export JSON"));
    expect(create).toHaveBeenCalledOnce();
    expect(click).toHaveBeenCalledOnce();
  });
});
