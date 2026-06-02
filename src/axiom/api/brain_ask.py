"""Ask the Brain — grounded RAG service.

The Ask service is the YC-demo headline feature: a natural-language question
gets answered by an LLM that has been grounded in the actual ingested graph.
Every answer ships with explicit entity citations the UI can click through to,
so the answer never drifts away from sourced facts.

Pipeline:
    question -> hybrid_search (lexical + semantic + graph) -> top-k entities
             -> build a deterministic context bundle (id, title, type, snippet)
             -> chat_complete(provider, system + grounded user prompt)
             -> structured response with answer text + citation list
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from axiom.providers.llm_chat import (
    DEFAULT_MODELS,
    SUPPORTED_PROVIDERS,
    ChatCompletion,
    ChatCompletionError,
    ChatMessage,
    LLMProviderKeyNotFound,
    UnknownLLMProvider,
    VaultCorrupt,
    VaultLocked,
    chat_complete,
)
from axiom.retrieval.search import SearchMode, hybrid_search

log = logging.getLogger("axiom.api.brain_ask")

MAX_QUESTION_LENGTH = 4000
MIN_QUESTION_LENGTH = 3
DEFAULT_TOP_K = 8
MAX_TOP_K = 25
SNIPPET_MAX_CHARS = 480
CONTEXT_MAX_CHARS = 12_000


@dataclass(frozen=True, slots=True)
class Citation:
    entity_id: str
    title: str
    type: str
    cluster_id: str | None
    score: float
    matched_on: str
    snippet: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "title": self.title,
            "type": self.type,
            "cluster_id": self.cluster_id,
            "score": round(float(self.score), 6),
            "matched_on": self.matched_on,
            "snippet": self.snippet,
        }


@dataclass(frozen=True, slots=True)
class AskResult:
    question: str
    provider: str
    model: str
    answer: str
    citations: list[Citation]
    retrieval_mode: SearchMode
    usage: dict[str, int]
    duration_ms: int
    receipt: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "provider": self.provider,
            "model": self.model,
            "answer": self.answer,
            "citations": [c.to_dict() for c in self.citations],
            "retrieval_mode": self.retrieval_mode,
            "usage": dict(self.usage),
            "duration_ms": self.duration_ms,
            "receipt": dict(self.receipt),
        }


def _normalize_question(question: str) -> str:
    cleaned = (question or "").strip()
    if len(cleaned) < MIN_QUESTION_LENGTH:
        raise ValueError("question must be at least 3 characters")
    if len(cleaned) > MAX_QUESTION_LENGTH:
        raise ValueError(f"question must be {MAX_QUESTION_LENGTH} characters or fewer")
    return cleaned


def _summarize_entity_data(data: dict[str, Any]) -> str:
    """Return a short, deterministic snippet of an entity's data JSON.

    Picks human-readable scalar fields first, falls back to a compact JSON
    rendering if no text fields are present.
    """

    if not data:
        return ""
    preferred_keys = (
        "summary",
        "description",
        "body",
        "text",
        "note",
        "details",
        "subject",
        "title",
        "name",
    )
    parts: list[str] = []
    for key in preferred_keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
        if sum(len(part) for part in parts) >= SNIPPET_MAX_CHARS:
            break
    if not parts:
        try:
            parts.append(
                json.dumps(
                    {k: v for k, v in data.items() if not isinstance(v, (dict, list))},
                    default=str,
                    sort_keys=True,
                )
            )
        except (TypeError, ValueError):
            parts.append(str(data))
    text = " — ".join(parts)
    if len(text) > SNIPPET_MAX_CHARS:
        return text[: SNIPPET_MAX_CHARS - 1].rstrip() + "…"
    return text


def _citations_from_results(results: list[dict[str, Any]]) -> list[Citation]:
    citations: list[Citation] = []
    for row in results:
        snippet = _summarize_entity_data(dict(row.get("data") or {}))
        citations.append(
            Citation(
                entity_id=str(row.get("id") or ""),
                title=str(row.get("title") or "Untitled"),
                type=str(row.get("type") or "entity"),
                cluster_id=row.get("cluster_id"),
                score=float(row.get("score") or 0.0),
                matched_on=str(row.get("matched_on") or row.get("methods", ["hybrid"])[0]),
                snippet=snippet,
            )
        )
    return citations


def _build_context(citations: list[Citation]) -> str:
    blocks: list[str] = []
    total = 0
    for index, citation in enumerate(citations, start=1):
        header = (
            f"[{index}] id={citation.entity_id} type={citation.type} "
            f"cluster={citation.cluster_id or '-'} title={citation.title!r}"
        )
        body = citation.snippet or "(no inline text; see entity record)"
        block = f"{header}\n{body}"
        if total + len(block) > CONTEXT_MAX_CHARS and blocks:
            break
        blocks.append(block)
        total += len(block)
    return "\n\n".join(blocks)


SYSTEM_PROMPT = (
    "You are AXIOM, a company brain. Answer questions strictly from the "
    "labeled context below. Cite each fact by its bracketed number like [1] "
    "the first time you use it. If the context does not contain the answer, "
    "say so plainly and recommend which entities or sources to inspect next. "
    "Do not invent entity IDs, policies, or numbers. Keep answers concise — "
    "one or two short paragraphs unless the user asks for detail."
)


def _build_messages(question: str, citations: list[Citation]) -> list[ChatMessage]:
    if not citations:
        user_content = (
            f"Question: {question}\n\nContext: (no matching entities found in the brain.)"
        )
    else:
        context_block = _build_context(citations)
        user_content = f"Question: {question}\n\nContext (numbered entities):\n{context_block}"
    return [
        ChatMessage(role="system", content=SYSTEM_PROMPT),
        ChatMessage(role="user", content=user_content),
    ]


def _default_provider(session: Session) -> str | None:
    """Pick a default provider by inspecting the LLM key store, preferring
    Anthropic when present, then OpenAI."""

    from axiom.govern.llm_keys import list_provider_key_metadata_with_session

    rows = list_provider_key_metadata_with_session(session)
    providers = {row.provider for row in rows}
    for candidate in ("anthropic", "openai"):
        if candidate in providers:
            return candidate
    return None


def ask_brain(
    session: Session,
    *,
    question: str,
    provider: str | None = None,
    model: str | None = None,
    mode: SearchMode = "hybrid",
    top_k: int = DEFAULT_TOP_K,
    entity_types: list[str] | None = None,
    cluster_id: str | None = None,
    max_tokens: int = 1024,
    completer: Any | None = None,
) -> AskResult:
    """Run a grounded RAG query against the brain.

    ``completer`` is an optional callable matching the signature of
    ``chat_complete`` — injected for tests so they can avoid hitting an LLM.
    """

    cleaned = _normalize_question(question)
    safe_top_k = max(1, min(int(top_k or DEFAULT_TOP_K), MAX_TOP_K))

    started_at = time.monotonic()
    retrieval = hybrid_search(
        session,
        cleaned,
        mode=mode,
        top_k=safe_top_k,
        entity_types=entity_types,
        cluster_id=cluster_id,
    )
    citations = _citations_from_results(retrieval.get("results", []))

    resolved_provider = (provider or _default_provider(session) or "").strip().lower()
    if not resolved_provider:
        raise LLMProviderKeyNotFound(
            "no LLM provider key registered — add one via /api/internal/llm-keys"
        )
    if resolved_provider not in SUPPORTED_PROVIDERS:
        raise UnknownLLMProvider(
            f"unsupported chat provider: {resolved_provider!r}; "
            f"supported: {sorted(SUPPORTED_PROVIDERS)}"
        )
    resolved_model = (model or DEFAULT_MODELS[resolved_provider]).strip()

    messages = _build_messages(cleaned, citations)
    call = completer or chat_complete
    completion: ChatCompletion = call(
        session,
        provider=resolved_provider,
        messages=messages,
        model=resolved_model,
        max_tokens=max_tokens,
    )
    duration_ms = int((time.monotonic() - started_at) * 1000)

    receipt = {
        "type": "brain.ask",
        "retrieval_mode": mode,
        "top_k": safe_top_k,
        "matched_entities": [c.entity_id for c in citations],
        "provider": completion.provider,
        "model": completion.model,
        "input_chars": sum(len(msg.content) for msg in messages),
        "output_chars": len(completion.content),
        "duration_ms": duration_ms,
    }

    return AskResult(
        question=cleaned,
        provider=completion.provider,
        model=completion.model,
        answer=completion.content,
        citations=citations,
        retrieval_mode=mode,
        usage=dict(completion.usage),
        duration_ms=duration_ms,
        receipt=receipt,
    )


__all__ = [
    "AskResult",
    "Citation",
    "ChatCompletionError",
    "DEFAULT_TOP_K",
    "LLMProviderKeyNotFound",
    "MAX_QUESTION_LENGTH",
    "MAX_TOP_K",
    "MIN_QUESTION_LENGTH",
    "UnknownLLMProvider",
    "VaultCorrupt",
    "VaultLocked",
    "ask_brain",
]
