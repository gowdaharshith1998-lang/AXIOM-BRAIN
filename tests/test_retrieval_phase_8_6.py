from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from axiom.govern.llm_keys import ensure_llm_provider_keys_schema, set_provider_key_with_session
from axiom.organize.agent import OrganizerAgent
from axiom.retrieval.embeddings import (
    DeterministicEmbeddingProvider,
    OpenAIEmbeddingProvider,
    bootstrap_embeddings,
    canonical_content_hash,
    embed_entities_batch,
    get_embedding_provider,
)
from axiom.retrieval.search import graph_search, hybrid_search, lexical_search, semantic_search
from axiom.schema.models import Base, Edge, Entity, EntityEmbedding
from axiom.studio.server import create_app
from axiom.vault.crypto import generate_master_key


class _Provider:
    model = "test-embeddings"

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        out: list[list[float]] = []
        for text in texts:
            lowered = text.lower()
            if "refund" in lowered:
                out.append([1.0, 0.0, 0.0])
            elif "billing" in lowered:
                out.append([0.0, 1.0, 0.0])
            else:
                out.append([0.0, 0.0, 1.0])
        return out


@pytest.fixture()
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = create_engine(f"sqlite:///{tmp_path / 'retrieval.db'}", future=True)
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    try:
        yield sf
    finally:
        engine.dispose()


def _seed(sf: sessionmaker[Session]) -> None:
    with sf() as session:
        session.add_all(
            [
                Entity(
                    id="e1",
                    type="decision",
                    data={"title": "Refund Policy"},
                    cluster_id="growth_product",
                ),
                Entity(
                    id="e2",
                    type="doc",
                    data={"title": "Billing Playbook"},
                    cluster_id="billing_payments",
                ),
                Entity(
                    id="e3",
                    type="ticket",
                    data={"title": "Support Escalation"},
                    cluster_id="growth_product",
                ),
            ]
        )
        session.add_all(
            [
                Edge(
                    id="edge1", source_id="e1", target_id="e3", relationship="references", data={}
                ),
                Edge(id="edge2", source_id="e2", target_id="e3", relationship="mentions", data={}),
            ]
        )
        session.commit()


def test_canonical_hash_changes_with_content(session_factory: sessionmaker[Session]) -> None:
    _seed(session_factory)
    with session_factory() as session:
        entity = session.get(Entity, "e1")
        assert entity is not None
        before = canonical_content_hash(entity)
        entity.data = {"title": "Refund Policy v2"}
        assert canonical_content_hash(entity) != before


def test_embed_entity_writes_blob_and_metadata(session_factory: sessionmaker[Session]) -> None:
    _seed(session_factory)
    provider = _Provider()
    with session_factory() as session:
        entity = session.get(Entity, "e1")
        assert entity is not None
        [row] = embed_entities_batch(session, [entity], provider=provider)
        assert row.entity_id == "e1"
        assert row.model == "test-embeddings"
        assert len(row.embedding) == 12


def test_embed_skip_when_hash_unchanged(session_factory: sessionmaker[Session]) -> None:
    _seed(session_factory)
    provider = _Provider()
    with session_factory() as session:
        entity = session.get(Entity, "e1")
        assert entity is not None
        embed_entities_batch(session, [entity], provider=provider)
        embed_entities_batch(session, [entity], provider=provider)
    assert len(provider.calls) == 1


def test_embed_rewrites_when_hash_changes(session_factory: sessionmaker[Session]) -> None:
    _seed(session_factory)
    provider = _Provider()
    with session_factory() as session:
        entity = session.get(Entity, "e1")
        assert entity is not None
        embed_entities_batch(session, [entity], provider=provider)
        entity.data = {"title": "Billing Policy"}
        session.commit()
        embed_entities_batch(session, [entity], provider=provider)
        row = session.get(EntityEmbedding, "e1")
        assert row is not None
        assert row.content_hash == canonical_content_hash(entity)
    assert len(provider.calls) == 2


class _ModelProvider:
    """Embedding provider whose model name is configurable (Phase 2 EMB-003)."""

    def __init__(self, model: str) -> None:
        self.model = model
        self.calls: list[list[str]] = []

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        return [[0.0, 0.0, 1.0] for _ in texts]


def test_embed_recomputes_on_model_change(session_factory: sessionmaker[Session]) -> None:
    # Phase 2 (EMB-003): switching the embedding model must invalidate the
    # cached vector even when the content hash is unchanged, so stale
    # hash-provider vectors are re-embedded with the upgraded model.
    _seed(session_factory)
    hash_provider = _ModelProvider("axiom-hash-embedding-v1")
    upgraded = _ModelProvider("text-embedding-3-small")
    with session_factory() as session:
        entity = session.get(Entity, "e1")
        assert entity is not None
        embed_entities_batch(session, [entity], provider=hash_provider)
        first = session.get(EntityEmbedding, "e1")
        assert first is not None
        assert first.model == "axiom-hash-embedding-v1"

        # Same entity/content, different model => must NOT skip; must recompute.
        embed_entities_batch(session, [entity], provider=upgraded)
        row = session.get(EntityEmbedding, "e1")
        assert row is not None
        assert row.model == "text-embedding-3-small"
    assert len(upgraded.calls) == 1


def test_bootstrap_embeds_all_when_empty(session_factory: sessionmaker[Session]) -> None:
    _seed(session_factory)
    with session_factory() as session:
        assert bootstrap_embeddings(session, provider=_Provider()) == 3
        assert bootstrap_embeddings(session, provider=_Provider()) == 0


def test_lexical_search_ranks_title_match(session_factory: sessionmaker[Session]) -> None:
    _seed(session_factory)
    with session_factory() as session:
        rows = lexical_search(session, "refund", top_k=2)
    assert rows[0]["id"] == "e1"
    assert rows[0]["breakdown"]["lexical"]["score"] > 0


def test_semantic_search_uses_embeddings(session_factory: sessionmaker[Session]) -> None:
    _seed(session_factory)
    provider = _Provider()
    with session_factory() as session:
        embed_entities_batch(
            session, session.execute(select(Entity)).scalars().all(), provider=provider
        )
        rows = semantic_search(session, "billing", top_k=1, provider=provider)
    assert rows[0]["id"] == "e2"


def test_graph_search_expands_from_lexical_seed(session_factory: sessionmaker[Session]) -> None:
    _seed(session_factory)
    with session_factory() as session:
        rows = graph_search(session, "refund", top_k=3)
    assert "e3" in {row["id"] for row in rows}
    assert next(row for row in rows if row["id"] == "e3")["matched_on"] == "neighbor_of:e1"


def test_hybrid_search_rrf_returns_breakdown(session_factory: sessionmaker[Session]) -> None:
    _seed(session_factory)
    provider = _Provider()
    with session_factory() as session:
        embed_entities_batch(
            session, session.execute(select(Entity)).scalars().all(), provider=provider
        )
        out = hybrid_search(session, "refund", top_k=3, provider=provider)
    assert out["mode"] == "hybrid"
    assert out["results"][0]["id"] == "e1"
    assert "lexical" in out["results"][0]["breakdown"]
    assert "semantic" in out["breakdown"]


def test_hybrid_search_accepts_weights(session_factory: sessionmaker[Session]) -> None:
    _seed(session_factory)
    provider = _Provider()
    with session_factory() as session:
        embed_entities_batch(
            session, session.execute(select(Entity)).scalars().all(), provider=provider
        )
        out = hybrid_search(
            session,
            "refund",
            top_k=3,
            weights={"semantic": 2.0, "lexical": 0.5},
            provider=provider,
        )
    assert out["results"][0]["score"] > 0
    assert set(out["results"][0]["methods"]) >= {"lexical", "semantic"}


def test_hybrid_search_semantic_mode_only(session_factory: sessionmaker[Session]) -> None:
    _seed(session_factory)
    provider = _Provider()
    with session_factory() as session:
        embed_entities_batch(
            session, session.execute(select(Entity)).scalars().all(), provider=provider
        )
        out = hybrid_search(session, "billing", mode="semantic", top_k=2, provider=provider)
    assert out["results"][0]["id"] == "e2"
    assert out["results"][0]["methods"] == ["semantic"]


def test_hybrid_search_filters_by_cluster(session_factory: sessionmaker[Session]) -> None:
    _seed(session_factory)
    with session_factory() as session:
        out = hybrid_search(session, "refund", mode="lexical", top_k=5, cluster_id="growth_product")
    assert out["results"]
    assert {row["cluster_id"] for row in out["results"]} == {"growth_product"}


def test_internal_search_rejects_bad_mode(tmp_path: Path) -> None:
    db_url = f"sqlite:///{tmp_path / 'bad_mode.db'}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    engine.dispose()
    with TestClient(create_app(db_url=db_url)) as client:
        response = client.post("/api/internal/search", json={"query": "refund", "mode": "bad"})
    assert response.status_code == 422


def test_internal_search_endpoint_modes(tmp_path: Path) -> None:
    db_url = f"sqlite:///{tmp_path / 'search_api.db'}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    _seed(sf)
    engine.dispose()

    with TestClient(create_app(db_url=db_url)) as client:
        response = client.post(
            "/api/internal/search", json={"query": "refund", "mode": "lexical", "top_k": 2}
        )
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "lexical"
    assert data["results"][0]["methods"] == ["lexical"]


@pytest.mark.asyncio
async def test_organizer_embeds_changed_entities(session_factory: sessionmaker[Session]) -> None:
    _seed(session_factory)
    agent = OrganizerAgent(session_factory=session_factory)
    count = await agent.embed_changed_entities()
    assert count == 3
    with session_factory() as session:
        assert session.query(EntityEmbedding).count() == 3


@pytest.mark.asyncio
async def test_organizer_embedding_skip_unchanged(session_factory: sessionmaker[Session]) -> None:
    _seed(session_factory)
    agent = OrganizerAgent(session_factory=session_factory)
    assert await agent.embed_changed_entities() == 3
    assert await agent.embed_changed_entities() == 0


def test_provider_prefers_vault_key(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    monkeypatch.setenv("AXIOM_TEST_REAL_EMBEDDINGS", "1")
    monkeypatch.setenv("AXIOM_VAULT_KEY", generate_master_key())
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    with session_factory() as session:
        ensure_llm_provider_keys_schema(session.get_bind())
        set_provider_key_with_session(session, "openai", "sk-vault")
        provider = get_embedding_provider(session)
    assert isinstance(provider, OpenAIEmbeddingProvider)
    assert provider.api_key == "sk-vault"


def test_provider_env_fallback_and_test_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AXIOM_TEST_REAL_EMBEDDINGS", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    provider = get_embedding_provider(None)
    assert isinstance(provider, OpenAIEmbeddingProvider)
    assert provider.api_key == "sk-env"
    monkeypatch.delenv("AXIOM_TEST_REAL_EMBEDDINGS")
    assert isinstance(get_embedding_provider(None), DeterministicEmbeddingProvider)
