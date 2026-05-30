from __future__ import annotations

import base64
import stat
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session, sessionmaker

from axiom.govern.llm_keys import set_provider_key_with_session
from axiom.govern.receipts import ReceiptInsert, canonical_payload, chain_insert_receipt
from axiom.govern.verify import verify_receipt_chain, verify_receipt_signature
from axiom.schema.models import Base, Entity, Receipt
from axiom.sign import ed25519_signer
from axiom.skills.registry import activate_skill_with_session, register_skill_with_session
from axiom.skills.runner import run_skill
from axiom.studio.server import create_app
from axiom.vault.crypto import ENV_VAR


@pytest.fixture(autouse=True)
def isolated_signing_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    ed25519_signer.clear_keypair_cache()


@pytest.fixture()
def receipt_sf(tmp_path: Path) -> sessionmaker[Session]:
    engine = create_engine(f"sqlite:///{tmp_path / 'signing_receipts.db'}", future=True)
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with sf() as session:
        session.add(
            Entity(
                id="ent_1",
                type="document",
                source_id="synthetic-default",
                cluster_id="engineering_code",
                composite_importance=0.2,
                data={"title": "Entity One"},
            )
        )
        session.commit()
    return sf


def _receipt_payload(index: int = 1) -> ReceiptInsert:
    return ReceiptInsert(
        id=f"receipt_{index}",
        action_id=f"act_{index}",
        agent_name="agent_a",
        intent="read",
        target_entity_id="ent_1",
        cluster_id="engineering_code",
        decision="allow",
        reason="allowed",
        policy_id="policy.test",
        guidance=None,
        suggested_alternative=None,
        signing_scheme="ed25519",
        signature="fake-signature",
    )


def test_keypair_creation_writes_correct_modes() -> None:
    keypair = ed25519_signer.generate_keypair()
    private_path = Path.home() / ".axiom" / "signing_key.pem"
    public_path = Path.home() / ".axiom" / "signing_key.pem.pub"

    assert keypair.public_key_bytes
    assert private_path.exists()
    assert public_path.exists()
    assert stat.S_IMODE(private_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(public_path.stat().st_mode) == 0o644


def test_load_existing_keypair_returns_same_keys() -> None:
    created = ed25519_signer.generate_keypair()
    ed25519_signer.clear_keypair_cache()

    loaded = ed25519_signer.load_or_create_keypair()

    assert loaded.public_key_bytes == created.public_key_bytes


def test_sign_verify_roundtrip() -> None:
    payload = b'{"action":"read"}'
    signature = ed25519_signer.sign(payload)
    keypair = ed25519_signer.load_or_create_keypair()

    assert len(signature) == 64
    assert ed25519_signer.verify(payload, signature, keypair.public_key_bytes)


def test_sign_verify_wrong_pubkey_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = b'{"action":"read"}'
    signature = ed25519_signer.sign(payload)
    monkeypatch.setenv("HOME", str(tmp_path / "other-home"))
    ed25519_signer.clear_keypair_cache()
    wrong = ed25519_signer.generate_keypair()

    assert not ed25519_signer.verify(payload, signature, wrong.public_key_bytes)


def test_modify_payload_invalidates_signature() -> None:
    signature = ed25519_signer.sign(b'{"action":"read"}')
    keypair = ed25519_signer.load_or_create_keypair()

    assert not ed25519_signer.verify(b'{"action":"write"}', signature, keypair.public_key_bytes)


def test_canonical_payload_deterministic_across_runs() -> None:
    first = SimpleNamespace(
        id="receipt_1",
        action_id="act_1",
        agent_name="agent",
        intent="read",
        target_entity_id="ent_1",
        cluster_id="engineering_code",
        decision="allow",
        reason="allowed",
        policy_id="policy.test",
        passport_id=None,
        guidance=None,
        suggested_alternative=None,
        signing_scheme="ed25519",
        signature="sig-a",
        prev_hash="prev-a",
        this_hash="hash-a",
        reserved_state=None,
        demo_flag=True,
        created_at=SimpleNamespace(isoformat=lambda: "2026-05-11T00:00:00"),
    )
    second = SimpleNamespace(**{**first.__dict__, "signature": "sig-b", "prev_hash": "prev-b"})

    assert canonical_payload(first) == canonical_payload(second)
    assert b"signature" not in canonical_payload(first)
    assert b"prev_hash" not in canonical_payload(first)
    assert b"this_hash" not in canonical_payload(first)


def test_chain_insert_uses_real_ed25519(receipt_sf: sessionmaker[Session]) -> None:
    receipt, inserted = chain_insert_receipt(receipt_sf, _receipt_payload())

    assert inserted is True
    assert receipt.signing_scheme == "ed25519"
    assert len(base64.b64decode(receipt.signature)) == 64
    assert verify_receipt_signature(
        receipt, ed25519_signer.load_or_create_keypair().public_key_bytes
    )["verified"]


def test_verify_receipt_chain_returns_signature_verified_true_after_fix(
    receipt_sf: sessionmaker[Session],
) -> None:
    receipt, _ = chain_insert_receipt(receipt_sf, _receipt_payload())

    with receipt_sf() as session:
        result = verify_receipt_chain(session, receipt.id)

    assert result["chain_verified"] is True
    assert result["signature_verified"] is True


def test_tamper_signature_column_fails_verification(receipt_sf: sessionmaker[Session]) -> None:
    receipt, _ = chain_insert_receipt(receipt_sf, _receipt_payload())
    with receipt_sf() as session:
        session.execute(
            update(Receipt).where(Receipt.id == receipt.id).values(signature="tampered")
        )
        session.commit()

    with receipt_sf() as session:
        result = verify_receipt_chain(session, receipt.id)

    assert result["chain_verified"] is False
    assert result["signature_verified"] is False


def test_pubkey_endpoint_returns_valid_base64(tmp_path: Path) -> None:
    db_url = f"sqlite:///{tmp_path / 'pubkey.db'}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    engine.dispose()

    app = create_app(db_url=db_url, enable_organizer=False)
    with TestClient(app) as client:
        body = client.get("/api/internal/signing-pubkey").json()

    assert (
        base64.b64decode(body["public_key"])
        == ed25519_signer.load_or_create_keypair().public_key_bytes
    )


@pytest.mark.asyncio
async def test_watchdog_receipt_uses_real_signer(receipt_sf: sessionmaker[Session]) -> None:
    from axiom.govern.watchdog import WatchdogAgent

    class Broadcaster:
        current_seq = 0

        async def publish(self, envelope: dict[str, Any]) -> int:
            self.current_seq += 1
            return self.current_seq

        async def subscribe(self, *, since: int = 0):  # type: ignore[no-untyped-def]
            if False:
                yield since

    agent: WatchdogAgent

    async def sleeper(_delay: float) -> None:
        agent._stop = True  # type: ignore[attr-defined]

    agent = WatchdogAgent(
        session_factory=receipt_sf,
        broadcaster=Broadcaster(),
        debounce_sec=0.0,
        sleeper=sleeper,
    )
    with receipt_sf() as session:
        entity = session.get(Entity, "ent_1")
        assert entity is not None
        entity.cluster_id = "billing_payments"
        session.add(entity)
        session.commit()
    await agent.handle_entity_event("ent_1")
    await agent._debounce_loop()  # type: ignore[attr-defined]

    with receipt_sf() as session:
        receipt = session.execute(select(Receipt)).scalar_one()
        assert receipt.signing_scheme == "ed25519"
        assert verify_receipt_signature(
            receipt, ed25519_signer.load_or_create_keypair().public_key_bytes
        )["verified"]


def test_skill_run_receipt_uses_real_signer(
    receipt_sf: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ENV_VAR, Fernet.generate_key().decode("utf-8"))

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"content": [{"type": "text", "text": '{"priority":"high"}'}]}

    monkeypatch.setattr("axiom.skills.runner.httpx.post", lambda *a, **kw: Response())
    with receipt_sf() as session:
        skill = register_skill_with_session(
            session,
            name="classify_ticket_priority",
            description="Classify support ticket priority",
            intent="classify",
            prompt_template="Classify: {ticket}",
            llm_provider="anthropic",
            llm_model="claude-3-haiku",
            output_schema={
                "type": "object",
                "required": ["priority"],
                "properties": {"priority": {"type": "string"}},
            },
        )
        activate_skill_with_session(session, skill.id)
        set_provider_key_with_session(session, "anthropic", "sk-ant-test-1234")
        skill_id = skill.id

    result = run_skill(
        skill_id,
        {"ticket": "Production checkout is down"},
        "agent_runner",
        session_factory=receipt_sf,
    )

    with receipt_sf() as session:
        receipt = session.get(Receipt, result["run"]["receipt_id"])
        assert receipt is not None
        assert receipt.signing_scheme == "ed25519"
        assert verify_receipt_signature(
            receipt, ed25519_signer.load_or_create_keypair().public_key_bytes
        )["verified"]
