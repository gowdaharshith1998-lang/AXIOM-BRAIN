from __future__ import annotations

import sqlite3
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Literal

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from axiom.api.search import _score_title
from axiom.schema.dto import EntityDTO
from axiom.schema.models import Edge, Entity
from axiom.storage import crud
from axiom.storage.db import init_engine
from axiom.studio.sources import synthetic_sources_snapshot

Direction = Literal["outgoing", "incoming", "both"]
TITLE_KEYS = ("title", "name", "subject", "label")


@dataclass(frozen=True, slots=True)
class _EntityLite:
    id: str
    type: str
    source_id: str | None
    cluster_id: str | None
    composite_importance: float
    data: dict[str, Any]


class _GraphCache:
    def __init__(self) -> None:
        self.entities: dict[str, _EntityLite] = {}
        self.outgoing: dict[str, list[tuple[str, str, str]]] = {}
        self.incoming: dict[str, list[tuple[str, str, str]]] = {}


def _title_from_data(entity_id: str, data: dict[str, Any]) -> str:
    for key in TITLE_KEYS:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return entity_id


def _safe_fts_query(text: str) -> str:
    words = [w for w in text.strip().split() if w]
    if not words:
        return ""
    escaped = [f'"{w.replace("\"", "\"\"")}"*' for w in words[:6]]
    return " AND ".join(escaped)


class NavigationEventForwarder:
    def __init__(self, api_base_url: str = "http://127.0.0.1:8000") -> None:
        self._url = f"{api_base_url.rstrip('/')}/api/internal/agent-navigation"

    def emit_steps(
        self,
        steps: list[tuple[str, str, str | None]],
        *,
        agent_name: str = "external_mcp_client",
    ) -> None:
        if not steps:
            return
        sampled = steps[:50]
        payload = {
            "agent_name": agent_name,
            "steps": [
                {"from_id": from_id, "to_id": to_id, "edge_id": edge_id}
                for from_id, to_id, edge_id in sampled
            ],
        }
        try:
            with httpx.Client(timeout=0.5) as client:
                client.post(self._url, json=payload)
        except Exception:
            return


class AxiomMCPService:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        event_forwarder: NavigationEventForwarder | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._events = event_forwarder
        self._cache = _GraphCache()
        self._cache_lock = threading.Lock()
        self._cache_loaded_at = 0.0
        self._cache_ttl_sec = 10.0
        self._fts_conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._fts_conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts USING fts5(entity_id UNINDEXED, searchable)"
        )

    def _refresh_cache_if_needed(self, session: Session) -> None:
        now = time.monotonic()
        if now - self._cache_loaded_at < self._cache_ttl_sec:
            return
        with self._cache_lock:
            now = time.monotonic()
            if now - self._cache_loaded_at < self._cache_ttl_sec:
                return

            entities = session.execute(select(Entity)).scalars().all()
            edges = session.execute(select(Edge)).scalars().all()

            new_cache = _GraphCache()
            for row in entities:
                lite = _EntityLite(
                    id=row.id,
                    type=row.type,
                    source_id=row.source_id,
                    cluster_id=row.cluster_id,
                    composite_importance=float(row.composite_importance or 0.0),
                    data=row.data,
                )
                new_cache.entities[row.id] = lite
                new_cache.outgoing[row.id] = []
                new_cache.incoming[row.id] = []

            for edge in edges:
                if edge.source_id in new_cache.outgoing:
                    new_cache.outgoing[edge.source_id].append(
                        (edge.target_id, edge.id, edge.relationship)
                    )
                if edge.target_id in new_cache.incoming:
                    new_cache.incoming[edge.target_id].append(
                        (edge.source_id, edge.id, edge.relationship)
                    )

            cur = self._fts_conn.cursor()
            cur.execute("DELETE FROM entities_fts")
            rows = []
            for ent in new_cache.entities.values():
                title = _title_from_data(ent.id, ent.data)
                name = str(ent.data.get("name", ""))
                subject = str(ent.data.get("subject", ""))
                label = str(ent.data.get("label", ""))
                rows.append((ent.id, f"{title} {name} {subject} {label}".strip()))
            cur.executemany(
                "INSERT INTO entities_fts(entity_id, searchable) VALUES (?, ?)",
                rows,
            )
            self._fts_conn.commit()

            self._cache = new_cache
            self._cache_loaded_at = now

    def query_brain(
        self,
        query: str,
        max_results: int,
        entity_types: list[str] | None = None,
        cluster_id: str | None = None,
    ) -> dict[str, Any]:
        q = query.strip()
        if not q:
            return {"results": [], "count": 0}

        safe_limit = min(max(max_results, 1), 50)
        with self._session_factory() as session:
            self._refresh_cache_if_needed(session)

        fts_query = _safe_fts_query(q)
        seed_ids: list[str] = []
        if fts_query:
            try:
                cur = self._fts_conn.cursor()
                cur.execute(
                    "SELECT entity_id FROM entities_fts WHERE entities_fts MATCH ? LIMIT ?",
                    (fts_query, 600),
                )
                seed_ids = [str(row[0]) for row in cur.fetchall()]
            except Exception:
                seed_ids = []

        if not seed_ids:
            seed_ids = list(self._cache.entities.keys())[:600]

        seeds: list[tuple[_EntityLite, float]] = []
        for entity_id in seed_ids:
            entity = self._cache.entities.get(entity_id)
            if entity is None:
                continue
            if entity_types and entity.type not in entity_types:
                continue
            if cluster_id is not None and entity.cluster_id != cluster_id:
                continue
            score = _score_title(q, _title_from_data(entity.id, entity.data))
            if score > 0:
                seeds.append((entity, score))

        seeds.sort(key=lambda item: (-item[1], -item[0].composite_importance, item[0].id))
        seeds = seeds[:safe_limit]

        candidate_map: dict[str, dict[str, Any]] = {}
        nav_steps: list[tuple[str, str, str | None]] = []

        for entity, match_score in seeds:
            candidate_map[entity.id] = self._entity_result(entity, "query_match", match_score)

            neighbors = self._cache.outgoing.get(entity.id, []) + self._cache.incoming.get(entity.id, [])
            for neighbor_id, edge_id, _rel in neighbors:
                neighbor = self._cache.entities.get(neighbor_id)
                if neighbor is None:
                    continue
                if entity_types and neighbor.type not in entity_types:
                    continue
                if cluster_id is not None and neighbor.cluster_id != cluster_id:
                    continue
                nav_steps.append((entity.id, neighbor.id, edge_id))
                if neighbor.id in candidate_map:
                    continue
                neighbor_score = max(0.0, match_score - 0.2)
                candidate_map[neighbor.id] = {
                    "id": neighbor.id,
                    "type": neighbor.type,
                    "data": neighbor.data,
                    "source_id": neighbor.source_id,
                    "cluster_id": neighbor.cluster_id,
                    "composite_importance": neighbor.composite_importance,
                    "title": _title_from_data(neighbor.id, neighbor.data),
                    "score": round(neighbor.composite_importance, 6),
                    "match_score": round(float(neighbor_score), 6),
                    "matched_on": f"neighbor_of:{entity.id}",
                }

        if self._events is not None:
            self._events.emit_steps(nav_steps)

        ranked = sorted(
            candidate_map.values(),
            key=lambda item: (
                -float(item.get("score", 0.0)),
                -float(item.get("match_score", 0.0)),
                str(item["id"]),
            ),
        )
        return {"results": ranked[:safe_limit], "count": len(ranked[:safe_limit])}

    def get_entity(
        self,
        entity_id: str,
        include_neighbors: bool = False,
        hops: int = 1,
    ) -> dict[str, Any]:
        with self._session_factory() as session:
            entity = session.get(Entity, entity_id)
            if entity is None:
                raise LookupError(f"unknown entity id: {entity_id}")

            result: dict[str, Any] = {
                "entity": {
                    **EntityDTO.model_validate(entity).model_dump(mode="json"),
                    "title": _title_from_data(entity.id, entity.data),
                }
            }
            if include_neighbors:
                safe_hops = min(max(hops, 1), 2)
                neighbors = crud.list_neighbors(session, entity_id, depth=safe_hops, direction="both")
                result["neighbors"] = [
                    {**neighbor.model_dump(mode="json"), "title": _title_from_data(neighbor.id, neighbor.data)}
                    for neighbor in neighbors
                ]
                if self._events is not None:
                    self._events.emit_steps([(entity_id, n.id, None) for n in neighbors])
            return result

    def traverse(
        self,
        from_id: str,
        edge_types: list[str] | None = None,
        max_depth: int = 2,
        direction: Direction = "both",
    ) -> dict[str, Any]:
        safe_depth = min(max(max_depth, 1), 6)
        cap = 200

        with self._session_factory() as session:
            self._refresh_cache_if_needed(session)

        if from_id not in self._cache.entities:
            raise LookupError(f"unknown entity id: {from_id}")

        visited: set[str] = {from_id}
        q: deque[tuple[str, int]] = deque([(from_id, 0)])
        nodes: list[dict[str, Any]] = []
        edges_out: list[dict[str, Any]] = []
        nav_steps: list[tuple[str, str, str | None]] = []

        while q and len(visited) < cap:
            current_id, depth = q.popleft()
            nodes.append({"id": current_id, "depth": depth})
            if depth >= safe_depth:
                continue

            rels: list[tuple[str, str, str]] = []
            if direction in ("outgoing", "both"):
                rels.extend(self._cache.outgoing.get(current_id, []))
            if direction in ("incoming", "both"):
                rels.extend(self._cache.incoming.get(current_id, []))

            for next_id, edge_id, relationship in rels:
                if edge_types and relationship not in edge_types:
                    continue
                edges_out.append(
                    {
                        "edge_id": edge_id,
                        "from_id": current_id,
                        "to_id": next_id,
                        "relationship": relationship,
                        "depth": depth + 1,
                    }
                )
                nav_steps.append((current_id, next_id, edge_id))
                if next_id in visited:
                    continue
                visited.add(next_id)
                if len(visited) >= cap:
                    break
                q.append((next_id, depth + 1))

        if self._events is not None:
            self._events.emit_steps(nav_steps)

        return {
            "root_id": from_id,
            "direction": direction,
            "max_depth": safe_depth,
            "node_cap": cap,
            "nodes": nodes,
            "edges": edges_out,
            "truncated": len(visited) >= cap,
        }

    def list_sources(self) -> dict[str, Any]:
        with self._session_factory() as session:
            rows = synthetic_sources_snapshot(session)
        out = [{**row, "is_demo": True} for row in rows]
        return {"sources": out, "count": len(out)}

    @staticmethod
    def _entity_result(entity: _EntityLite, matched_on: str, match_score: float) -> dict[str, Any]:
        return {
            "id": entity.id,
            "type": entity.type,
            "title": _title_from_data(entity.id, entity.data),
            "source_id": entity.source_id,
            "cluster_id": entity.cluster_id,
            "score": round(entity.composite_importance, 6),
            "match_score": round(float(match_score), 6),
            "matched_on": matched_on,
        }


def build_mcp_server(
    *,
    db_url: str = "sqlite:///./axiom.db",
    api_base_url: str = "http://127.0.0.1:8000",
) -> FastMCP:
    engine = init_engine(db_url)
    session_local = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    service = AxiomMCPService(
        session_factory=session_local,
        event_forwarder=NavigationEventForwarder(api_base_url=api_base_url),
    )

    mcp = FastMCP(name="AXIOM MCP")

    @mcp.tool(name="axiom_query_brain", description="Smart search over entities with 1-hop expansion")
    def axiom_query_brain(
        query: str,
        max_results: int = 8,
        entity_types: list[str] | None = None,
        cluster_id: str | None = None,
    ) -> dict[str, Any]:
        return service.query_brain(query, max_results, entity_types, cluster_id)

    @mcp.tool(name="axiom_get_entity", description="Fetch one entity and optional neighbors")
    def axiom_get_entity(
        entity_id: str,
        include_neighbors: bool = False,
        hops: int = 1,
    ) -> dict[str, Any]:
        try:
            return service.get_entity(entity_id, include_neighbors, hops)
        except LookupError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool(name="axiom_traverse", description="BFS graph traversal with cycle detection")
    def axiom_traverse(
        from_id: str,
        edge_types: list[str] | None = None,
        max_depth: int = 2,
        direction: Direction = "both",
    ) -> dict[str, Any]:
        try:
            return service.traverse(from_id, edge_types, max_depth, direction)
        except LookupError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool(name="axiom_list_sources", description="List connected sources")
    def axiom_list_sources() -> dict[str, Any]:
        return service.list_sources()

    return mcp


def serve_stdio(*, db_url: str = "sqlite:///./axiom.db", api_base_url: str = "http://127.0.0.1:8000") -> None:
    mcp = build_mcp_server(db_url=db_url, api_base_url=api_base_url)
    mcp.run(transport="stdio")
