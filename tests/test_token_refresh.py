from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
import responses
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from axiom.connectors.sync_runner import (
    ConnectorReauthRequiredError,
    connector_token_state,
)
from axiom.schema.models import Base, ConnectorConfigRow, ConnectorStateRow
from axiom.vault.store import (
    get_secret_with_session,
    store_secret_with_session,
)


def _session_factory(tmp_path: Path) -> sessionmaker[Session]:
    engine = create_engine(f"sqlite:///{tmp_path / 'refresh.db'}", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def _seed_connector(
    session: Session,
    vendor: str,
    *,
    access_plaintext: str,
    refresh_plaintext: str | None,
    expires_at: datetime | None,
    client_secret: str = "client_secret",
) -> ConnectorStateRow:
    """Persist a connected connector with vault-backed tokens (mirrors the server)."""
    state_id = f"{vendor}_state_1"
    config = ConnectorConfigRow(
        id=vendor,
        vendor=vendor,
        oauth_client_id="client_id",
        oauth_client_secret=None,
        redirect_uri=f"https://axiom.local/{vendor}/callback",
        scopes=[],
        install_state="connected",
    )
    if client_secret:
        store_secret_with_session(
            session, f"connector:{vendor}", "oauth_client_secret", client_secret
        )
        config.oauth_client_secret = f"vault:connector:{vendor}:oauth_client_secret"
    session.add(config)

    store_secret_with_session(
        session, f"connector:{vendor}", f"state:{state_id}:access_token", access_plaintext
    )
    refresh_ref = None
    if refresh_plaintext is not None:
        store_secret_with_session(
            session, f"connector:{vendor}", f"state:{state_id}:refresh_token", refresh_plaintext
        )
        refresh_ref = f"vault:connector:{vendor}:state:{state_id}:refresh_token"

    row = ConnectorStateRow(
        id=state_id,
        connector_id=vendor,
        vendor=vendor,
        access_token=f"vault:connector:{vendor}:state:{state_id}:access_token",
        refresh_token=refresh_ref,
        token_expires_at=expires_at,
        account_label=f"{vendor} workspace",
        status="connected",
    )
    session.add(row)
    session.commit()
    return row


@responses.activate
def test_near_expiry_triggers_refresh_and_persists_new_token(tmp_path: Path) -> None:
    responses.post(
        "https://api.linear.app/oauth/token",
        json={"access_token": "lin_rotated", "refresh_token": "lin_refresh_2", "expires_in": 3600},
    )

    sf = _session_factory(tmp_path)
    with sf() as session:
        row = _seed_connector(
            session,
            "linear",
            access_plaintext="lin_old",
            refresh_plaintext="lin_refresh_1",
            expires_at=datetime.utcnow() + timedelta(minutes=2),  # inside the 5-min buffer
        )

        token_state = connector_token_state(session, row)

        # The rotated access token is returned and used for the sync.
        assert token_state.access_token == "lin_rotated"
        assert token_state.refresh_token == "lin_refresh_2"

    # The refresh exchanged the stored refresh token via grant_type=refresh_token.
    assert responses.calls[0].request.url == "https://api.linear.app/oauth/token"
    sent_body = responses.calls[0].request.body
    body_text = sent_body.decode() if isinstance(sent_body, bytes) else str(sent_body)
    assert "grant_type=refresh_token" in body_text
    assert "refresh_token=lin_refresh_1" in body_text

    # The rotated tokens are persisted to the vault and the expiry is advanced.
    with sf() as session:
        refreshed = session.execute(
            select(ConnectorStateRow).where(ConnectorStateRow.vendor == "linear")
        ).scalar_one()
        assert refreshed.status == "connected"
        assert refreshed.token_expires_at is not None
        assert refreshed.token_expires_at > datetime.utcnow() + timedelta(minutes=30)
        stored_access = get_secret_with_session(
            session, "connector:linear", "state:linear_state_1:access_token"
        )
        stored_refresh = get_secret_with_session(
            session, "connector:linear", "state:linear_state_1:refresh_token"
        )
        assert stored_access == "lin_rotated"
        assert stored_refresh == "lin_refresh_2"


@responses.activate
def test_slack_near_expiry_rotates_via_oauth_v2_access(tmp_path: Path) -> None:
    responses.post(
        "https://slack.com/api/oauth.v2.access",
        json={
            "ok": True,
            "access_token": "xoxb-rotated",
            "refresh_token": "xoxe-2",
            "expires_in": 43200,
        },
    )

    sf = _session_factory(tmp_path)
    with sf() as session:
        row = _seed_connector(
            session,
            "slack",
            access_plaintext="xoxb-old",
            refresh_plaintext="xoxe-1",
            expires_at=datetime.utcnow() - timedelta(seconds=1),  # already expired
        )
        token_state = connector_token_state(session, row)
        assert token_state.access_token == "xoxb-rotated"
        assert token_state.refresh_token == "xoxe-2"

    with sf() as session:
        stored_access = get_secret_with_session(
            session, "connector:slack", "state:slack_state_1:access_token"
        )
        assert stored_access == "xoxb-rotated"


@responses.activate
def test_refresh_failure_sets_reauth_required(tmp_path: Path) -> None:
    responses.post(
        "https://api.linear.app/oauth/token", status=400, json={"error": "invalid_grant"}
    )

    sf = _session_factory(tmp_path)
    with sf() as session:
        row = _seed_connector(
            session,
            "linear",
            access_plaintext="lin_old",
            refresh_plaintext="lin_refresh_1",
            expires_at=datetime.utcnow() - timedelta(minutes=1),
        )
        with pytest.raises(ConnectorReauthRequiredError, match="linear"):
            connector_token_state(session, row)

    with sf() as session:
        refreshed = session.execute(
            select(ConnectorStateRow).where(ConnectorStateRow.vendor == "linear")
        ).scalar_one()
        assert refreshed.status == "reauth_required"


def test_missing_refresh_token_sets_reauth_required(tmp_path: Path) -> None:
    sf = _session_factory(tmp_path)
    with sf() as session:
        row = _seed_connector(
            session,
            "linear",
            access_plaintext="lin_old",
            refresh_plaintext=None,  # nothing to refresh with
            expires_at=datetime.utcnow() - timedelta(minutes=1),
        )
        with pytest.raises(ConnectorReauthRequiredError, match="no refresh token"):
            connector_token_state(session, row)

    with sf() as session:
        refreshed = session.execute(
            select(ConnectorStateRow).where(ConnectorStateRow.vendor == "linear")
        ).scalar_one()
        assert refreshed.status == "reauth_required"


@responses.activate
def test_non_expiring_vendor_is_noop(tmp_path: Path) -> None:
    # GitHub/Notion tokens never expire and refresh() is a documented no-op.
    sf = _session_factory(tmp_path)
    with sf() as session:
        row = _seed_connector(
            session,
            "github",
            access_plaintext="gho_token",
            refresh_plaintext=None,
            expires_at=None,  # non-expiring
        )
        token_state = connector_token_state(session, row)
        assert token_state.access_token == "gho_token"

    # No outbound refresh calls were made for a non-expiring vendor.
    assert len(responses.calls) == 0
    with sf() as session:
        refreshed = session.execute(
            select(ConnectorStateRow).where(ConnectorStateRow.vendor == "github")
        ).scalar_one()
        assert refreshed.status == "connected"


def test_token_not_near_expiry_skips_refresh(tmp_path: Path) -> None:
    sf = _session_factory(tmp_path)
    with sf() as session:
        row = _seed_connector(
            session,
            "linear",
            access_plaintext="lin_fresh",
            refresh_plaintext="lin_refresh_1",
            expires_at=datetime.utcnow() + timedelta(hours=2),  # well outside the buffer
        )
        token_state = connector_token_state(session, row)
        # Returns the existing access token unchanged with no HTTP refresh.
        assert token_state.access_token == "lin_fresh"
