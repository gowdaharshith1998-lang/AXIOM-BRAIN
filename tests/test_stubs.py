from __future__ import annotations

import asyncio
from pathlib import Path

import pytest


def test_ingest_interfaces_shape():
    from axiom.ingest.interfaces import IngestEvent, IngestPipeline

    assert hasattr(IngestEvent, "event_id")
    assert hasattr(IngestPipeline, "run")


def test_ingest_pipeline_stub_raises():
    from axiom.ingest.interfaces import IngestPipeline

    class Impl(IngestPipeline):
        async def run(self, *, since=None):  # type: ignore[override,no-untyped-def]
            return await super().run(since=since)

    with pytest.raises(NotImplementedError, match="lands in Phase 3"):
        asyncio.run(Impl().run())


def test_mcp_interfaces_shape():
    from axiom.mcp.interfaces import MCPServer, ToolCall, ToolResult

    assert hasattr(ToolCall, "tool")
    assert hasattr(ToolResult, "ok")
    assert hasattr(MCPServer, "handle")


def test_mcp_server_stub_raises():
    from axiom.mcp.interfaces import MCPServer, ToolCall

    class Impl(MCPServer):
        def register_tools(self) -> None:  # type: ignore[override]
            return super().register_tools()

        async def handle(self, call: ToolCall):  # type: ignore[override,no-untyped-def]
            return await super().handle(call)

    with pytest.raises(NotImplementedError, match="lands in Phase 6"):
        asyncio.run(Impl().handle(ToolCall(tool="axiom_query_brain", params={})))


def test_studio_interfaces_shape():
    from axiom.studio.interfaces import StudioEventStream, WebSocketEvent

    assert hasattr(WebSocketEvent, "type")
    assert hasattr(StudioEventStream, "publish")


def test_studio_publish_stub_raises():
    from axiom.studio.interfaces import StudioEventStream, WebSocketEvent

    class Impl(StudioEventStream):
        async def subscribe(self, *, since_seq=None):  # type: ignore[override,no-untyped-def]
            return await super().subscribe(since_seq=since_seq)

        def publish(self, event: WebSocketEvent) -> None:  # type: ignore[override]
            return super().publish(event)

    with pytest.raises(NotImplementedError, match="lands in Phase 4"):
        Impl().publish(WebSocketEvent(type="stats", timestamp_ms=0, payload={}))


def test_skills_interfaces_shape():
    from axiom.skills.interfaces import SkillDescriptor, SkillsEmitter

    assert hasattr(SkillDescriptor, "skill_id")
    assert hasattr(SkillsEmitter, "emit_one")


def test_skills_emitter_stub_raises():
    from axiom.skills.interfaces import SkillsEmitter

    class Impl(SkillsEmitter):
        def emit_all(self):  # type: ignore[override,no-untyped-def]
            return super().emit_all()

        def emit_one(self, process_entity_id: str):  # type: ignore[override]
            return super().emit_one(process_entity_id)

    with pytest.raises(NotImplementedError, match="lands in Phase 8"):
        Impl().emit_one("ent_x")


def test_policy_engine_stub_raises():
    from axiom.policy.interfaces import PolicyEngine

    class Impl(PolicyEngine):
        def evaluate(self, *, agent_id: str, tool: str, params: dict):  # type: ignore[override]
            return super().evaluate(agent_id=agent_id, tool=tool, params=params)

    with pytest.raises(NotImplementedError, match="lands in Phase 9"):
        Impl().evaluate(agent_id="agent_1", tool="axiom_record_action", params={})


def test_sign_interfaces_shape():
    from axiom.sign.interfaces import SignedPayload, Signer

    assert hasattr(SignedPayload, "signature_ed25519_b64")
    assert hasattr(Signer, "sign")


def test_signer_stub_raises():
    from axiom.sign.interfaces import Signer

    class Impl(Signer):
        def sign(self, payload, *, scheme="ed25519+ml-dsa-65"):  # type: ignore[override,no-untyped-def]
            return super().sign(payload, scheme=scheme)

        def verify(self, signed):  # type: ignore[override,no-untyped-def]
            return super().verify(signed)

    with pytest.raises(NotImplementedError, match="lands in Phase 10"):
        Impl().sign({"x": 1})


def test_sources_interfaces_shape():
    from axiom.sources.interfaces import IngestEvent, Source, SourceMetadata

    assert hasattr(IngestEvent, "event_type")
    assert hasattr(SourceMetadata, "source_id")
    assert hasattr(Source, "discover")


def test_source_stub_raises():
    from axiom.sources.interfaces import Source

    class Impl(Source):
        source_id = "src_x"
        source_type = "synthetic"  # type: ignore[assignment]

        async def discover(self):  # type: ignore[override,no-untyped-def]
            return await super().discover()

        async def ingest(self, since=None):  # type: ignore[override,no-untyped-def]
            return await super().ingest(since=since)

        async def watch(self, on_event):  # type: ignore[override,no-untyped-def]
            return await super().watch(on_event)

        async def disconnect(self) -> None:  # type: ignore[override]
            return await super().disconnect()

        def metadata(self):  # type: ignore[override,no-untyped-def]
            return super().metadata()

    with pytest.raises(NotImplementedError, match=r"lands in Phase 12\+"):
        asyncio.run(Impl().discover())


def test_no_calibra_imports_in_phase_1():
    """Calibra is Phase 7. Phase 1 must not import or reference calibra."""
    src_root = Path(__file__).parent.parent / "src"
    hits: list[str] = []
    for path in src_root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in {".py", ".toml", ".txt", ".md"}:
            continue
        content = path.read_text(encoding="utf-8", errors="ignore").lower()
        if "calibra" in content:
            hits.append(str(path))

    assert hits == [], f"Found calibra references in src/: {hits}"

