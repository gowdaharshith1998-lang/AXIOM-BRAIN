from __future__ import annotations

import hashlib
import json
import math
import os
import struct
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

import httpx
from sqlalchemy import Engine, inspect, select
from sqlalchemy.orm import Session

from axiom.govern.llm_keys import (
    LLMProviderKeyNotFound,
    get_provider_key_plaintext_with_session,
)
from axiom.schema.models import Entity, EntityEmbedding
from axiom.storage.db import create_schema_table, schema_table_indexes
from axiom.vault.errors import VaultCorrupt, VaultLocked

DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DETERMINISTIC_EMBEDDING_MODEL = "axiom-hash-embedding-v1"
EMBEDDING_DIMENSIONS = 64


class EmbeddingProvider(Protocol):
    @property
    def model(self) -> str: ...

    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...


@dataclass(frozen=True, slots=True)
class DeterministicEmbeddingProvider:
    model: str = DETERMINISTIC_EMBEDDING_MODEL
    dimensions: int = EMBEDDING_DIMENSIONS

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [_hash_vector(text, dimensions=self.dimensions) for text in texts]


@dataclass(frozen=True, slots=True)
class OpenAIEmbeddingProvider:
    api_key: str
    model: str = DEFAULT_EMBEDDING_MODEL
    dimensions: int = EMBEDDING_DIMENSIONS
    timeout: float = 10.0

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        response = httpx.post(
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "input": texts,
                "dimensions": self.dimensions,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        rows = sorted(payload["data"], key=lambda item: int(item["index"]))
        return [[float(value) for value in row["embedding"]] for row in rows]


def ensure_entity_embeddings_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    if not inspector.has_table("entity_embeddings"):
        create_schema_table(EntityEmbedding.__table__, engine)
        return
    indexes = {idx["name"] for idx in inspector.get_indexes("entity_embeddings")}
    if "ix_entity_embeddings_content_hash" not in indexes:
        for index in schema_table_indexes(EntityEmbedding.__table__):
            if index.name == "ix_entity_embeddings_content_hash":
                index.create(bind=engine, checkfirst=True)


def canonical_entity_text(entity: Entity) -> str:
    data = entity.data or {}
    title = _first_text(data, ("title", "name", "subject", "label"))
    fragments: list[str] = [entity.type, title]
    for key in sorted(data):
        value = data[key]
        if isinstance(value, str):
            fragments.append(value)
        elif isinstance(value, (int, float, bool)):
            fragments.append(str(value))
        elif isinstance(value, list):
            fragments.extend(str(item) for item in value if isinstance(item, (str, int, float)))
    if entity.cluster_id:
        fragments.append(entity.cluster_id)
    return " ".join(fragment.strip() for fragment in fragments if fragment and fragment.strip())


def canonical_content_hash(entity: Entity) -> str:
    payload = {
        "type": entity.type,
        "data": entity.data or {},
        "cluster_id": entity.cluster_id,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def get_embedding_provider(session: Session | None = None) -> EmbeddingProvider:
    if os.environ.get("AXIOM_TEST_REAL_EMBEDDINGS") != "1" and os.environ.get(
        "PYTEST_CURRENT_TEST"
    ):
        return DeterministicEmbeddingProvider()

    api_key: str | None = None
    if session is not None:
        try:
            api_key = get_provider_key_plaintext_with_session(session, "openai")
        except (LLMProviderKeyNotFound, VaultCorrupt, VaultLocked):
            api_key = None

    api_key = api_key or os.environ.get("OPENAI_API_KEY")
    if api_key:
        return OpenAIEmbeddingProvider(
            api_key=api_key,
            model=os.environ.get("AXIOM_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL),
        )
    return DeterministicEmbeddingProvider()


def embed_entity(
    session: Session,
    entity: Entity,
    provider: EmbeddingProvider | None = None,
) -> EntityEmbedding:
    return embed_entities_batch(session, [entity], provider=provider)[0]


def embed_entities_batch(
    session: Session,
    entities: list[Entity],
    provider: EmbeddingProvider | None = None,
) -> list[EntityEmbedding]:
    if not entities:
        return []

    resolved_provider = provider or get_embedding_provider(session)
    pending: list[tuple[Entity, str, str]] = []
    unchanged: list[EntityEmbedding] = []
    for entity in entities:
        content_hash = canonical_content_hash(entity)
        existing = session.get(EntityEmbedding, entity.id)
        if (
            existing is not None
            and existing.content_hash == content_hash
            and existing.model == resolved_provider.model
        ):
            unchanged.append(existing)
            continue
        pending.append((entity, content_hash, canonical_entity_text(entity)))

    written: list[EntityEmbedding] = []
    if pending:
        vectors = resolved_provider.embed_texts([item[2] for item in pending])
        now = datetime.utcnow()
        for (entity, content_hash, _text), vector in zip(pending, vectors, strict=True):
            row = session.get(EntityEmbedding, entity.id)
            if row is None:
                row = EntityEmbedding(
                    entity_id=entity.id,
                    embedding=_pack_vector(vector),
                    content_hash=content_hash,
                    model=resolved_provider.model,
                    created_at=now,
                    updated_at=now,
                )
            else:
                row.embedding = _pack_vector(vector)
                row.content_hash = content_hash
                row.model = resolved_provider.model
                row.updated_at = now
            session.add(row)
            written.append(row)
        session.commit()
        for row in written:
            session.refresh(row)

    return unchanged + written


def bootstrap_embeddings(session: Session, provider: EmbeddingProvider | None = None) -> int:
    embedding_count = int(session.query(EntityEmbedding).count())
    if embedding_count:
        return 0
    entities = list(session.execute(select(Entity)).scalars().all())
    if not entities:
        return 0
    return len(embed_entities_batch(session, entities, provider=provider))


def vector_from_blob(blob: bytes) -> list[float]:
    if not blob:
        return []
    return list(struct.unpack(f"{len(blob) // 4}f", blob))


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


def _pack_vector(vector: list[float]) -> bytes:
    return struct.pack(f"{len(vector)}f", *[float(value) for value in vector])


def _hash_vector(text: str, *, dimensions: int) -> list[float]:
    values: list[float] = []
    seed = text.encode("utf-8")
    counter = 0
    while len(values) < dimensions:
        digest = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
        for index in range(0, len(digest), 4):
            chunk = digest[index : index + 4]
            raw = int.from_bytes(chunk, "big")
            values.append((raw / 0xFFFFFFFF) * 2.0 - 1.0)
            if len(values) == dimensions:
                break
        counter += 1
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [value / norm for value in values]


def _first_text(data: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""
