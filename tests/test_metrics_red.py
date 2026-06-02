"""P1-12 completion: real RED metrics + LLM metrics + degraded mode.

* ``/metrics`` exposes the labelled request counter after a request is served.
* the LLM token counter increments when ``llm_chat`` records actual usage.
* the endpoint still responds (in a degraded plain-text mode) when
  ``prometheus_client`` is unavailable.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from axiom.schema.models import Base
from axiom.vault.crypto import ENV_VAR


def test_prometheus_client_imports_cleanly() -> None:
    """P1-12.1: the declared dependency must import in this venv."""
    import prometheus_client  # noqa: F401
    from prometheus_client import Counter, Gauge, Histogram  # noqa: F401


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv(ENV_VAR, Fernet.generate_key().decode("utf-8"))
    db_url = f"sqlite:///{tmp_path / 'metrics-red.db'}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    engine.dispose()

    from axiom.studio.server import create_app

    app = create_app(db_url=db_url, enable_organizer=False)
    with TestClient(app) as test_client:
        yield test_client


def test_metrics_exposes_request_counter_with_labels(client: TestClient) -> None:
    # Serve a request whose route has a path template.
    resp = client.get("/api/health")
    assert resp.status_code == 200

    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    text = metrics.text
    # The RED request counter is present and carries the method/path/status labels
    # using the route *template* (not the raw path), bounding cardinality.
    assert "axiom_http_requests_total" in text
    assert 'method="GET"' in text
    assert 'path="/api/health"' in text
    assert 'status="200"' in text
    # The latency histogram is also exposed.
    assert "axiom_http_request_duration_seconds" in text


def test_metrics_path_label_uses_route_template_not_raw_path(client: TestClient) -> None:
    # Hit a parameterised route so the raw path (with an id) differs from the
    # template. The metric must use the template to avoid label cardinality blowup.
    client.get("/api/entities/does-not-exist-123/edges")
    metrics = client.get("/metrics").text
    assert "/api/entities/{entity_id}/edges" in metrics
    assert "does-not-exist-123" not in metrics


def test_llm_token_counter_increments_on_record(client: TestClient) -> None:
    from axiom.studio.rate_limit import record_llm_tokens

    before = client.get("/metrics").text
    record_llm_tokens(40, 9)
    after = client.get("/metrics").text

    # The per-direction token counter and the call counter both appear/increment.
    assert "axiom_llm_tokens_total" in after
    assert 'direction="input"' in after
    assert 'direction="output"' in after
    assert "axiom_llm_calls_total" in after
    # The 'after' scrape must reflect a strictly higher total than 'before'.
    assert _llm_token_total(after) > _llm_token_total(before)


def _llm_token_total(metrics_text: str) -> float:
    total = 0.0
    for line in metrics_text.splitlines():
        if line.startswith("axiom_llm_tokens_total{"):
            total += float(line.rsplit(" ", 1)[1])
    return total


def test_metrics_degraded_mode_without_prometheus(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P1-12: /metrics must still respond when prometheus_client is absent."""
    monkeypatch.setenv(ENV_VAR, Fernet.generate_key().decode("utf-8"))
    db_url = f"sqlite:///{tmp_path / 'metrics-degraded.db'}"
    engine = create_engine(db_url, future=True)
    Base.metadata.create_all(engine)
    engine.dispose()

    import axiom.studio.server as server

    # Simulate the optional dependency being unavailable.
    monkeypatch.setattr(server, "_PROMETHEUS_AVAILABLE", False)

    app = server.create_app(db_url=db_url, enable_organizer=False)
    with TestClient(app) as test_client:
        # The app still serves requests with the metrics middleware as a no-op.
        assert test_client.get("/api/health").status_code == 200
        metrics = test_client.get("/metrics")
    assert metrics.status_code == 200
    assert "prometheus-client is not installed" in metrics.text


def test_record_llm_tokens_safe_without_prometheus(monkeypatch: pytest.MonkeyPatch) -> None:
    """The token hook must never raise even when no counters exist."""
    import axiom.studio.server as server

    monkeypatch.setattr(server, "LLM_CALLS_TOTAL", None)
    monkeypatch.setattr(server, "LLM_TOKENS_TOTAL", None)
    # Must not raise.
    server._observe_llm_tokens(10, 5)
