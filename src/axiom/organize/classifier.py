"""Hybrid (keyword + LLM) cluster classifier.

Tier 1: keyword scoring. Fast, free, deterministic. ~60% of entities have
a strong unambiguous keyword winner.

Tier 2: LLM fallback (Anthropic Haiku). Only invoked when keyword tier
returns nothing or is ambiguous (top two scores within 1 point). Result
is cached on a short hash of the entity title to avoid repeated calls
for the same canonical phrase.

The classifier is fully offline-safe: if no API key is resolved (vault
``default`` entry for Anthropic—see :mod:`axiom.providers.router`—then
standard ``ANTHROPIC_API_KEY`` env—or the SDK is missing, or the LLM call
fails), it falls back to the highest keyword score, then to the canonical
DEFAULT_CLUSTER_ID.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Mapping
from typing import cast

from axiom.organize.clusters import (
    CLUSTER_IDS,
    DEFAULT_CLUSTER_ID,
    SEMANTIC_CLUSTERS,
    is_valid_cluster_id,
)
from axiom.providers.router import get_active_llm_key_anthropic
from axiom.schema.models import Entity

logger = logging.getLogger("axiom.organize.classifier")


class HybridClassifier:
    """Two-tier semantic classifier (keyword + optional LLM fallback)."""

    LLM_MODEL = "claude-haiku-4-5-20251001"
    LLM_MAX_TOKENS = 20
    STRONG_MATCH_THRESHOLD = 3  # keyword hits required to skip the LLM
    AMBIGUITY_BAND = 1  # top-two delta that triggers the LLM

    def __init__(
        self,
        *,
        anthropic_client: object | None = None,
        cache: dict[str, str] | None = None,
        api_key: str | None = None,
    ) -> None:
        self._cache: dict[str, str] = {} if cache is None else cache
        # Lazy SDK client unless injected. Default path resolves ANTHROPIC_API_KEY via
        # vault-first router (phase 5.13.4). Explicit ``api_key=""`` disables the LLM tier.
        self._anthropic_client: object | None = anthropic_client
        if anthropic_client is not None:
            self._api_key: str | None = api_key.strip() if api_key and api_key.strip() else None
        elif api_key is not None:
            trimmed = api_key.strip() if api_key and api_key.strip() else None
            self._api_key = trimmed
        else:
            resolution = get_active_llm_key_anthropic()
            self._api_key = resolution.key
            logger.info("anthropic key loaded from %s", resolution.source)

    @property
    def cache(self) -> Mapping[str, str]:
        return self._cache

    def classify(self, entity: Entity) -> str | None:
        scores = self._keyword_score(entity)
        top_score = max(scores.values()) if scores else 0

        if top_score >= self.STRONG_MATCH_THRESHOLD:
            return self._argmax(scores)

        if top_score == 0:
            llm_choice = self._llm_classify(entity)
            return llm_choice or DEFAULT_CLUSTER_ID

        if self._is_ambiguous(scores):
            llm_choice = self._llm_classify(entity)
            return llm_choice or self._argmax(scores)

        return self._argmax(scores)

    def _keyword_score(self, entity: Entity) -> dict[str, int]:
        text = self._entity_text(entity).lower()
        return {
            cluster_id: sum(1 for kw in spec["keywords"] if kw in text)
            for cluster_id, spec in SEMANTIC_CLUSTERS.items()
        }

    def _is_ambiguous(self, scores: dict[str, int]) -> bool:
        ordered = sorted(scores.values(), reverse=True)
        if len(ordered) < 2:
            return False
        return ordered[0] - ordered[1] <= self.AMBIGUITY_BAND

    def _argmax(self, scores: dict[str, int]) -> str:
        # Tie-break: stable order by CLUSTER_IDS so re-runs are deterministic.
        winner = max(
            CLUSTER_IDS,
            key=lambda cid: (scores.get(cid, 0), -CLUSTER_IDS.index(cid)),
        )
        return winner

    def _llm_classify(self, entity: Entity) -> str | None:
        title = self._title_or_fallback(entity)
        cache_key = hashlib.sha256(title.encode("utf-8")).hexdigest()[:16]
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        client = self._resolve_client()
        if client is None:
            return None

        prompt = self._build_prompt(entity, title)

        try:
            response = self._call_client(client, prompt)
            cluster_id = self._extract_cluster_id(response)
        except Exception:  # noqa: BLE001 — LLM failure is best-effort
            logger.exception("LLM cluster classification failed")
            return None

        if is_valid_cluster_id(cluster_id):
            assert cluster_id is not None
            self._cache[cache_key] = cluster_id
            return cluster_id

        return None

    def _resolve_client(self) -> object | None:
        if self._anthropic_client is not None:
            return self._anthropic_client
        if not self._api_key:
            return None
        try:  # pragma: no cover — exercised only when SDK + key are present
            import anthropic
        except ImportError:
            return None
        try:  # pragma: no cover
            client = anthropic.Anthropic(api_key=self._api_key)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to instantiate Anthropic client")
            return None
        self._anthropic_client = client
        return client

    @classmethod
    def _build_prompt(cls, entity: Entity, title: str) -> str:
        bullet_list = "\n".join(
            f"- {cid}: {spec['label']}" for cid, spec in SEMANTIC_CLUSTERS.items()
        )
        snippet = str(entity.data)[:500]
        return (
            "Classify this entity into ONE of these clusters:\n"
            f"{bullet_list}\n\n"
            f"Entity title: {title}\n"
            f"Entity type: {entity.type}\n"
            f"Entity data: {snippet}\n\n"
            'Reply with ONLY the cluster_id (e.g. "billing_payments"). '
            'If unclear, reply "decisions_policy".'
        )

    def _call_client(self, client: object, prompt: str) -> object:
        # Anthropic SDK shape (client.messages.create) is the canonical path.
        # Tests can inject a duck-typed object exposing the same method.
        messages_attr = getattr(client, "messages", None)
        if messages_attr is None:
            raise RuntimeError("anthropic client missing 'messages' attribute")
        create = getattr(messages_attr, "create", None)
        if not callable(create):
            raise RuntimeError("anthropic client.messages missing 'create' method")
        return cast(
            object,
            create(
                model=self.LLM_MODEL,
                max_tokens=self.LLM_MAX_TOKENS,
                messages=[{"role": "user", "content": prompt}],
            ),
        )

    @staticmethod
    def _extract_cluster_id(response: object) -> str | None:
        content = getattr(response, "content", None)
        if not content:
            return None
        first = content[0]
        if isinstance(first, dict):
            text = first.get("text")
        else:
            text = getattr(first, "text", None)
        if not isinstance(text, str):
            return None
        return text.strip().lower()

    @staticmethod
    def _title_or_fallback(entity: Entity) -> str:
        data = entity.data if isinstance(entity.data, dict) else {}
        for key in ("title", "name", "subject", "label"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return entity.id or ""

    @staticmethod
    def _entity_text(entity: Entity) -> str:
        data = entity.data if isinstance(entity.data, dict) else {}
        title = ""
        for key in ("title", "name", "subject", "label"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                title = value.strip()
                break
        return f"{title} {entity.type} {data}"
