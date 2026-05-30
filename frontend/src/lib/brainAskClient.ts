export type AskCitation = {
  entity_id: string;
  title: string;
  type: string;
  cluster_id: string | null;
  score: number;
  matched_on: string;
  snippet: string;
};

export type AskUsage = {
  input_tokens: number;
  output_tokens: number;
};

export type AskResponse = {
  question: string;
  provider: string;
  model: string;
  answer: string;
  citations: AskCitation[];
  retrieval_mode: "hybrid" | "lexical" | "semantic" | "graph";
  usage: AskUsage;
  duration_ms: number;
  receipt: Record<string, unknown>;
};

export type AskRequest = {
  question: string;
  provider?: "anthropic" | "openai";
  model?: string;
  mode?: "hybrid" | "lexical" | "semantic" | "graph";
  top_k?: number;
  entity_types?: string[];
  cluster_id?: string;
  max_tokens?: number;
};

export type AskError = {
  status: number;
  detail: string;
};

export async function askBrain(
  request: AskRequest,
  init?: { signal?: AbortSignal },
): Promise<AskResponse> {
  const response = await fetch("/api/brain/ask", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    signal: init?.signal,
  });
  if (!response.ok) {
    let detail = "ask the brain failed";
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body?.detail === "string" && body.detail) detail = body.detail;
    } catch {
      // body was not JSON; leave default detail
    }
    const error: AskError = { status: response.status, detail };
    throw error;
  }
  return (await response.json()) as AskResponse;
}
