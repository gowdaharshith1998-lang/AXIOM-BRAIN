# AXIOM

**AXIOM Control** builds **AXIOM**: a live **company brain** — an organizational knowledge graph you can explore in 3D, fed by a real ingestion and clustering pipeline today. The long-term vision is connectors, agent skills, governance, and calibrated beliefs; those pieces are **roadmapped**, not shipped yet.

**Repo name:** AXIOM-BRAIN (repository identifier; product-facing name is AXIOM / AXIOM Control.)

---

## What's built today

These paths exist and run end-to-end in this repo:

- **Backend ingestion → SQLite → broadcast:** FastAPI service ingests events, persists entities and edges with SQLAlchemy, and publishes sequenced envelopes over WebSockets with **replay from a sequence number** (`?since=`).
- **Synthetic data sources:** A fixture-backed synthetic org plus a **live synthetic emitter** (Poisson-timed events) so the graph stays animated without external SaaS wiring.
- **Hybrid cluster classifier:** **Keyword scoring** across seven cluster vocabularies with deterministic tie-breaks; **optional Anthropic LLM fallback** only when keyword scores are weak or ambiguous (fully offline-safe when no API key — falls back to keywords / default cluster). Model is configurable in code at `HybridClassifier`.
- **Organizer loops:** Periodic classification, PageRank-style **composite importance**, and **within-cluster edge proposals** (many edges are `same_cluster_related` — structural suggestion, not curated semantics).
- **Cluster health monitoring:** Per-cluster ingest snapshots and health transitions surfaced via API and events.
- **Studio API:** Entity/edge dumps, cluster health, Levenshtein-ranked **entity search** — used by the UI.
- **Frontend "living brain":** React + Three.js **3D graph** (hex nodes, clusters, conduits, camera motion) driven by **live REST bootstrap + WebSocket updates**.
- **⌘K command palette:** Debounced search wired to backend ranking (with sensible client fallback).
- **Schema & migrations:** Alembic migrations and CRUD tests around the storage layer.

**Explicitly not production-grade yet:** There is **no** real multi-mode policy engine, **no** cryptographic signing of agent actions, **no** real Slack/GitHub/Linear/Notion connectors, and **no** MCP server or executable agent skills in this repo today. Some UI and websocket traffic **simulates** agent actions and receipts for demo atmosphere; that is **not** verified governance.

---

## Status & roadmap

**Current focus — Phase 5.12:** Visual **Company Brain** experience — cluster layout, chrome, inspector, live stats — on top of the **real ingest + classifier + WebSocket** stack described above.

**Upcoming (roadmap — not implemented as specified here):**

| Phase | Focus |
| --- | --- |
| **6** | MCP server exposure + skills-shaped interfaces |
| **7** | **Calibra** — Bayesian belief calibration (integration lands here) |
| **8** | Skills with **real** implementations (beyond stubs) |
| **9** | Policy engine — **ALLOW / CORRECT / DENY / PAUSE** (and enforcement hooks) |
| **10** | Cryptographic receipts — **Ed25519** + **ML-DSA-65** (FIPS 204) hybrid signing (and verification path) |
| **11** | Real source connectors — Slack, GitHub, Linear, Notion, etc. |

Earlier phase checklists in older docs are superseded by **Phase 5.12** as the active rebuild track for the visual brain.

---

## Architecture

AXIOM-BRAIN is a **FastAPI** application backed by **SQLite** (configurable via SQLAlchemy **`DATABASE_URL`**) with **Alembic** migrations. Ingestion pulls from **synthetic fixtures and a timed synthetic emitter**, runs a **keyword-first classifier** with an **optional Anthropic** LLM tier for ambiguity, and broadcasts changes through an in-memory **WebSocket hub** with **sequence-based replay**. The **React + Three.js** frontend loads entities and edges from the API, subscribes to the brain socket, and renders an interactive **entity graph** with **⌘K search** backed by server-side string ranking. Nav and some footer controls are **presentational** until later phases wire routing and governance surfaces.

---

## Demo

There is **no reliable hosted demo URL** in-repo today (a previously linked site has been observed unreachable from the public internet). **Run locally:**

Backend (from repo root, after installing the package and dependencies — see project docs / `pyproject.toml`):

```bash
# Example — align with your documented entrypoint
uvicorn axiom.studio.server:app --factory --host 127.0.0.1 --port 8000
```

Frontend:

```bash
cd frontend && npm install && npm run dev
```

Open the Vite URL (typically `http://localhost:5173`). The UI expects the API at **`http://127.0.0.1:8000`** unless you configure otherwise.

---

## Configuration

Copy `.env.example` to `.env` and fill in any keys you need. Notable values:

| Variable | Purpose |
| --- | --- |
| `ANTHROPIC_API_KEY` | Optional. Enables the hybrid classifier's **optional** Anthropic LLM fallback when keyword classification is ambiguous or weak. When unset, classification stays **keyword-only** (and default cluster fallback). |
| `DATABASE_URL` | SQLAlchemy URL. Defaults to `sqlite:///./axiom.db`. |

---

## Calibra

**Calibra** (external Bayesian calibration package) is **not** imported in early phases. Integration is planned for **Phase 7**, per the product roadmap.

---

## License

This project is licensed under the **MIT License** — see [`LICENSE`](LICENSE).
