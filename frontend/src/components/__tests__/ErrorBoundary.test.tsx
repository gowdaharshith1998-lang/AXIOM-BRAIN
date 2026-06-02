import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";

import { ErrorBoundary } from "@/components/ErrorBoundary";

function Boom(): never {
  throw new Error("boom");
}

describe("ErrorBoundary", () => {
  beforeEach(() => {
    // componentDidCatch logs via console.error; silence the expected error so it
    // does not pollute test output.
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders children when there is no error", () => {
    render(
      <ErrorBoundary>
        <span>healthy child</span>
      </ErrorBoundary>,
    );
    expect(screen.getByText("healthy child")).toBeInTheDocument();
  });

  it("renders the default fallback when a child throws", () => {
    render(
      <ErrorBoundary label="the widget">
        <Boom />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText(/Something went wrong in the widget/)).toBeInTheDocument();
  });

  it("renders a custom fallback when provided", () => {
    render(
      <ErrorBoundary fallback={<div>custom fallback</div>}>
        <Boom />
      </ErrorBoundary>,
    );
    expect(screen.getByText("custom fallback")).toBeInTheDocument();
  });
});
