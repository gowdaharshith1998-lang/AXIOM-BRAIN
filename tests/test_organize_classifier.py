"""Phase 5.7.A — hybrid classifier behaviour."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from axiom.organize.classifier import HybridClassifier
from axiom.organize.clusters import (
    CLUSTER_IDS,
    DEFAULT_CLUSTER_ID,
    SEMANTIC_CLUSTERS,
)
from axiom.schema.models import Entity


def _ent(*, type_: str = "decision", data: dict[str, Any] | None = None) -> Entity:
    return Entity(id="ent" + "0" * 29, type=type_, data=data or {})


@dataclass
class _Block:
    text: str


@dataclass
class _FakeResponse:
    content: list[Any]


@dataclass
class _FakeMessages:
    """Captures invocations + returns programmable responses."""

    queue: list[Any] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)

    def create(self, *, model: str, max_tokens: int, messages: list[dict[str, str]]) -> Any:
        self.calls.append({"model": model, "max_tokens": max_tokens, "messages": messages})
        if not self.queue:
            raise AssertionError("Unexpected LLM call (queue empty)")
        item = self.queue.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


@dataclass
class _FakeClient:
    messages: _FakeMessages = field(default_factory=_FakeMessages)


def _client_returning(*texts: str) -> _FakeClient:
    client = _FakeClient()
    for text in texts:
        client.messages.queue.append(_FakeResponse(content=[_Block(text=text)]))
    return client


# ─── 1. keyword tier ──────────────────────────────────────────────────────


def test_keyword_strong_match() -> None:
    classifier = HybridClassifier(api_key="")
    entity = _ent(
        type_="document",
        data={"title": "Refund policy: stripe checkout invoice handling"},
    )
    assert classifier.classify(entity) == "billing_payments"
    # No LLM client was needed.
    assert classifier.cache == {}


def test_keyword_no_match_falls_back_to_llm() -> None:
    client = _client_returning("growth_product")
    classifier = HybridClassifier(anthropic_client=client)
    entity = _ent(
        type_="document",
        data={"title": "Quarterly objectives memo"},
    )
    assert classifier.classify(entity) == "growth_product"
    assert len(client.messages.calls) == 1


def test_ambiguous_match_falls_back_to_llm() -> None:
    client = _client_returning("incidents_ops")
    classifier = HybridClassifier(anthropic_client=client)
    # one billing keyword (invoice) + one incidents keyword (incident).
    entity = _ent(
        type_="document",
        data={"title": "Invoice incident postmortem"},
    )
    assert classifier.classify(entity) == "incidents_ops"
    assert len(client.messages.calls) == 1


# ─── 2. fallback robustness ───────────────────────────────────────────────


def test_llm_failure_falls_back_to_keyword_winner() -> None:
    client = _FakeClient()
    client.messages.queue.append(RuntimeError("anthropic boom"))
    classifier = HybridClassifier(anthropic_client=client)

    # one billing kw + one incidents kw → ambiguous → LLM call → fails
    entity = _ent(
        type_="document",
        data={"title": "Invoice incident debrief"},
    )
    cluster = classifier.classify(entity)
    assert cluster in {"billing_payments", "incidents_ops"}
    assert len(client.messages.calls) == 1


def test_invalid_llm_response_falls_back() -> None:
    classifier = HybridClassifier(anthropic_client=_client_returning("not_a_real_cluster"))
    entity = _ent(
        type_="document",
        data={"title": "Quarterly objectives memo"},
    )
    # No keywords matched and the LLM gave garbage → DEFAULT_CLUSTER_ID.
    assert classifier.classify(entity) == DEFAULT_CLUSTER_ID


# ─── 3. caching ───────────────────────────────────────────────────────────


def test_cache_hit() -> None:
    client = _client_returning("growth_product")
    cache: dict[str, str] = {}
    classifier = HybridClassifier(anthropic_client=client, cache=cache)
    entity = _ent(
        type_="document",
        data={"title": "Quarterly objectives memo"},
    )
    assert classifier.classify(entity) == "growth_product"
    # Second call must reuse the cache.
    assert classifier.classify(entity) == "growth_product"
    assert len(client.messages.calls) == 1
    assert "growth_product" in cache.values()


# ─── 4. type-shape coverage (drawn from real generators) ─────────────────


@pytest.mark.parametrize(
    ("type_", "data", "expected"),
    [
        (
            "decision",
            {"title": "Approved RFC: design_doc for proposal"},
            "decisions_policy",
        ),
        (
            "ticket",
            {"title": "Stripe webhook retries duplicate invoice receipts"},
            "billing_payments",
        ),
        (
            "thread",
            {"title": "Customer support ticket complaint escalation"},
            "customer_support",
        ),
        (
            "code",
            {"file_path": "src/axiom/ingest/pipeline.py", "kind": "merge", "branch": "main"},
            "engineering_code",
        ),
    ],
)
def test_classify_known_shapes(type_: str, data: dict[str, Any], expected: str) -> None:
    classifier = HybridClassifier(api_key="")
    entity = _ent(type_=type_, data=data)
    assert classifier.classify(entity) == expected


# ─── 5. structural invariants ────────────────────────────────────────────


def test_default_cluster_is_known() -> None:
    assert DEFAULT_CLUSTER_ID in SEMANTIC_CLUSTERS
    assert set(CLUSTER_IDS) == set(SEMANTIC_CLUSTERS)


def test_offline_no_keys_no_keywords_returns_default() -> None:
    classifier = HybridClassifier(api_key="")
    entity = _ent(type_="document", data={"title": "Generic memo"})
    cluster = classifier.classify(entity)
    assert cluster == DEFAULT_CLUSTER_ID
