import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AskPanel } from "@/components/AskPanel";

type FetchMock = ReturnType<typeof vi.fn>;

const okResponse = {
  question: "What is the refund policy?",
  provider: "anthropic",
  model: "claude-haiku-4-5-20251001",
  answer: "Refunds beyond 30 days require VP approval [1].",
  citations: [
    {
      entity_id: "ent_refund_decision",
      title: "Refund Policy 2026 (v3)",
      type: "decision",
      cluster_id: "policy",
      score: 0.9123,
      matched_on: "lexical",
      snippet: "Refunds beyond 30 days require VP approval.",
    },
  ],
  retrieval_mode: "hybrid",
  usage: { input_tokens: 12, output_tokens: 9 },
  duration_ms: 142,
  receipt: { type: "brain.ask" },
};

describe("AskPanel", () => {
  let originalFetch: typeof globalThis.fetch;
  let fetchMock: FetchMock;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
    fetchMock = vi.fn(async () => new Response(JSON.stringify(okResponse), { status: 200 }));
    globalThis.fetch = fetchMock as unknown as typeof globalThis.fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("submits the question to /api/brain/ask and renders the cited answer", async () => {
    render(<AskPanel initialQuestion="" />);
    const input = screen.getByLabelText("Ask the Brain");
    fireEvent.change(input, { target: { value: "What is the refund policy?" } });
    fireEvent.click(screen.getByRole("button", { name: /ask/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [calledUrl, calledInit] = fetchMock.mock.calls[0] ?? [];
    expect(calledUrl).toBe("/api/brain/ask");
    expect((calledInit as RequestInit).method).toBe("POST");

    await waitFor(() => screen.getByTestId("ask-answer"));
    expect(screen.getByTestId("ask-answer").textContent).toContain("Refunds beyond 30 days");
    expect(screen.getByTestId("ask-citation-ent_refund_decision")).toBeInTheDocument();
  });

  it("renders an error with the 409 guidance when no provider key is registered", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "no LLM provider key registered" }), {
        status: 409,
      }),
    );
    render(<AskPanel initialQuestion="What is the refund policy?" />);
    fireEvent.click(screen.getByRole("button", { name: /ask/i }));
    const errorBox = await screen.findByTestId("ask-error");
    expect(errorBox.textContent).toContain("no LLM provider key registered");
    expect(errorBox.textContent).toContain("Settings → LLM Keys");
  });

  it("dispatches axiom:focus-entity when a citation is clicked", async () => {
    const events: CustomEvent[] = [];
    const handler = (event: Event) => {
      events.push(event as CustomEvent);
    };
    window.addEventListener("axiom:focus-entity", handler);

    render(<AskPanel initialQuestion="" />);
    fireEvent.change(screen.getByLabelText("Ask the Brain"), {
      target: { value: "What is the refund policy?" },
    });
    fireEvent.click(screen.getByRole("button", { name: /ask/i }));
    await screen.findByTestId("ask-answer");
    fireEvent.click(screen.getByTestId("ask-citation-ent_refund_decision"));
    window.removeEventListener("axiom:focus-entity", handler);

    expect(events.length).toBeGreaterThanOrEqual(1);
    expect(events[events.length - 1].detail).toEqual({ entityId: "ent_refund_decision" });
  });
});
