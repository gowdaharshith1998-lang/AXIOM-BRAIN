# DESIGN — AXIOM Phase 0 (Foundational Design)

**Repo:** `gowdaharshith1998-lang/AXIOM-BRAIN`  
**Dispatch:** Phase 0 — design recon (single design doc + stub skeleton; no production code)  

> **Read-first dependency note:** the dispatch references a parent roadmap at `/mnt/user-data/outputs/AXIOM_BUILD_ROADMAP_2026-05-05.md`. That file was not accessible in this environment at the time of writing. This document therefore specifies the required *contracts* for Phases 1–15 as requested, but it also lists explicit roadmap-dependent open questions in §14 that must be ruled on before Phase 1 begins.

---

## 1. Vision and architecture

AXIOM is a multi-source visual company brain: it pulls knowledge out of fragmented sources, structures it, keeps it current, and turns it into executable skills for AI agents. It is explicitly aligned with Tom Blomfield’s “Company Brain” RFS (a living map of how a company works, plus an executable skills file that agents can safely follow) and Diana Hu’s “AI Operating System for Companies” RFS (closing loops by monitoring what’s happening vs what should be happening, and adjusting).

The product is built as four cooperating subsystems with clear contracts: (1) **Brain** (data + 3D visualization) stores the canonical graph in SQLite and exposes read/query traversal interfaces; (2) **Calibra** (external package) provides Bayesian belief calibration and uncertainty states (KNOW/UNCERTAIN/UNKNOWN) used to gate actions and annotate facts; (3) **AXIOM governance** is the runtime policy+signing layer enforcing ALLOW/CORRECT/DENY (plus PAUSE when uncertain) and emitting verifiable receipts for every agent action; (4) **Skills emitter** walks Process entities, emits signed `SKILL.md` skill instructions, and makes those skills discoverable to agents via MCP.

There are two primary interfaces over one substrate. **Agents** interact via MCP tools that query the graph, load skills, check policy, and record signed actions. **Humans** supervise through the 3D visual brain, where graph changes stream via WebSocket events and where approvals and corrections are visible as receipts. This separation matters: agents get a tight, typed tool surface; humans get a “map of the company” that stays legible as sources grow.

AXIOM’s governance stance is three-mode: **ALLOW** (proceed), **CORRECT** (redirect the agent to an allowed alternative with guidance and a bounded retry budget), and **DENY** (block and escalate). CORRECT is the differentiator: instead of binary allow/deny governance, the system can keep work moving safely by steering actions into approved pathways while recording the correction as a signed governance receipt. (The roadmap should cite the April 2026 literature gap; if the roadmap requires a specific citation or framing, see §14.)

AXIOM is hosted production from day 1. The demo target is a URL partners can click (with real-time graph updates and verifiable receipts), not a local-only prototype or a video. This drives non-negotiable choices: WebSocket support, durable storage for SQLite WAL, secrets in platform secret stores, and end-to-end verifiability of agent actions.

---

## 2. Entity schema

AXIOM’s brain stores **7 first-class entity types**. No type is the “default”; code is only one of seven.

### 2.1 Common entity fields (all types)

Required fields:
- `id` (string, globally unique; recommended: `ent_<ulid>`; stable)
- `type` (string; one of: `code`, `person`, `decision`, `thread`, `ticket`, `document`, `process`)
- `source_id` (string; foreign key to Sources table; indicates provenance)
- `created_at` (RFC3339 string or unix ms; stored as ISO8601 text in SQLite)
- `updated_at` (RFC3339 string or unix ms)
- `palette_color` (string; UI/3D hint; e.g. `"#7C3AED"`)
- `metadata` (JSON object; stored as JSON text; see contract below)

Metadata JSON contract (common keys, optional unless specified):
- `axiom_signed` (bool): whether this entity change is covered by a signed ingest receipt
- `signing_scheme` (string): e.g. `"ed25519+ml-dsa-65"`
- `receipt_id` (string): ingest receipt id that attests this entity version
- `merkle_leaf_index` (int): index of leaf in Merkle log anchoring the receipt
- `calibra_state` (`"KNOW"|"UNCERTAIN"|"UNKNOWN"`)
- `calibra_confidence` (float in \[0,1])
- `extensions` (object): type- and connector-specific extension space; must be namespaced by connector, e.g. `{"linear": {...}}`

### 2.2 Type-specific fields

#### 2.2.1 `person`
Required:
- `display_name` (string)
Optional:
- `role` (string)
- `identifiers` (object): `{ "email"?: string, "slack_user_id"?: string, "github_login"?: string, "linear_user_id"?: string }`
- `avatar_url` (string)

Example:
```json
{
  "id": "ent_01J2Z6K8T7Y0P6GJ2R7R8XK3C2",
  "type": "person",
  "source_id": "src_synthetic",
  "created_at": "2026-05-06T07:59:00Z",
  "updated_at": "2026-05-06T07:59:00Z",
  "palette_color": "#10B981",
  "display_name": "Asha Patel",
  "role": "Customer Support",
  "identifiers": {"email": "asha@axiom.example"},
  "metadata": {
    "calibra_state": "KNOW",
    "calibra_confidence": 0.92,
    "extensions": {"synthetic": {"department": "support"}}
  }
}
```

#### 2.2.2 `ticket`
Required:
- `title` (string)
- `status` (string; free-text; connector provides canonical mapping)
Optional:
- `description` (string)
- `assignee_id` (string; entity id referencing a `person`)
- `project_id` (string; connector-specific; extension-friendly)
- `priority` (string)
- `external_url` (string)

Example:
```json
{
  "id": "ent_01J2Z6M0F8S9E7E3Y8X6G3D2QH",
  "type": "ticket",
  "source_id": "src_linear_demo",
  "created_at": "2026-05-06T07:10:00Z",
  "updated_at": "2026-05-06T07:40:00Z",
  "palette_color": "#F59E0B",
  "title": "Refund request for duplicate charge",
  "status": "refund_requested",
  "assignee_id": "ent_01J2Z6K8T7Y0P6GJ2R7R8XK3C2",
  "metadata": {
    "calibra_state": "UNCERTAIN",
    "calibra_confidence": 0.63,
    "extensions": {"linear": {"team_key": "SUP", "issue_id": "LIN-123"}}
  }
}
```

#### 2.2.3 `thread`
Required:
- `title` (string; for Slack/Gmail: subject; for others: synthesized)
Optional:
- `channel` (string)
- `started_by_id` (string; `person`)
- `external_url` (string)
- `message_count` (int)

Example:
```json
{
  "id": "ent_01J2Z6N2GQJ9AQ8AK5V9JYV1WZ",
  "type": "thread",
  "source_id": "src_slack_demo",
  "created_at": "2026-05-06T06:55:00Z",
  "updated_at": "2026-05-06T07:50:00Z",
  "palette_color": "#3B82F6",
  "title": "Support escalation: billing mismatch",
  "channel": "#support-escalations",
  "message_count": 18,
  "metadata": {
    "calibra_state": "KNOW",
    "calibra_confidence": 0.85,
    "extensions": {"slack": {"channel_id": "C123", "thread_ts": "1714978500.000100"}}
  }
}
```

#### 2.2.4 `decision`
Required:
- `title` (string)
- `status` (string; e.g. `proposed|accepted|rejected`; free-text)
Optional:
- `owner_id` (string; `person`)
- `decided_at` (RFC3339 string)
- `summary` (string)
- `rationale` (string)

Example:
```json
{
  "id": "ent_01J2Z6P8Q2R9K8Q5H5B0K9WJ8A",
  "type": "decision",
  "source_id": "src_synthetic",
  "created_at": "2026-05-06T07:00:00Z",
  "updated_at": "2026-05-06T07:45:00Z",
  "palette_color": "#EC4899",
  "title": "Default policy stance is permissive with CORRECT steering",
  "status": "accepted",
  "owner_id": "ent_01J2Z6K8T7Y0P6GJ2R7R8XK3C2",
  "decided_at": "2026-05-06T07:44:30Z",
  "summary": "Agents can proceed unless a clause denies or corrects.",
  "rationale": "Maintains velocity while steering into approved workflows.",
  "metadata": {
    "axiom_signed": true,
    "signing_scheme": "ed25519+ml-dsa-65",
    "receipt_id": "rcpt_ing_01J2Z6P9R0...",
    "merkle_leaf_index": 42,
    "calibra_state": "KNOW",
    "calibra_confidence": 0.9
  }
}
```

#### 2.2.5 `document`
Required:
- `title` (string)
Optional:
- `doc_type` (string; e.g. `policy|spec|memo|runbook`; free-text)
- `external_url` (string)
- `content_hash` (string; sha256 hex; content storage is connector-defined)
- `excerpt` (string)

Example:
```json
{
  "id": "ent_01J2Z6R4R7N8FQZ3VZC9J0H7A2",
  "type": "document",
  "source_id": "src_drive_demo",
  "created_at": "2026-05-06T05:00:00Z",
  "updated_at": "2026-05-06T05:00:00Z",
  "palette_color": "#8B5CF6",
  "title": "Refund policy v1",
  "doc_type": "policy",
  "external_url": "https://drive.example/doc/abc",
  "content_hash": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
  "excerpt": "Refunds under $50 may be auto-approved…",
  "metadata": {"calibra_state": "KNOW", "calibra_confidence": 0.88}
}
```

#### 2.2.6 `process`
Required:
- `name` (string)
Optional:
- `scope` (string; e.g. `ticket|thread|document|decision`; free-text)
- `inputs_schema` (JSON; declarative)
- `outputs_schema` (JSON; declarative)
- `steps_markdown` (string; human-authored process description)

Example:
```json
{
  "id": "ent_01J2Z6S9X5Z7G4A6X2T0D9J3AA",
  "type": "process",
  "source_id": "src_synthetic",
  "created_at": "2026-05-06T06:00:00Z",
  "updated_at": "2026-05-06T06:00:00Z",
  "palette_color": "#22C55E",
  "name": "Refund processing",
  "scope": "ticket",
  "inputs_schema": {"ticket_id": "string", "refund_amount": "number"},
  "outputs_schema": {"refund_status": "enum[approved,denied,pending]"},
  "steps_markdown": "Validate → decide → update ticket → receipt",
  "metadata": {"calibra_state": "KNOW", "calibra_confidence": 0.8}
}
```

#### 2.2.7 `code`
Required:
- `file_path` (string)
Optional:
- `language` (string)
- `kind` (string; e.g. `file|module|class|function`; free-text)
- `repo` (string; future extension, single-tenant at launch)
- `symbol` (string)

Example:
```json
{
  "id": "ent_01J2Z6V2K0F1RZ9Q8M3M8D2Q0P",
  "type": "code",
  "source_id": "src_github_demo",
  "created_at": "2026-05-06T02:00:00Z",
  "updated_at": "2026-05-06T02:00:00Z",
  "palette_color": "#64748B",
  "file_path": "src/axiom/sources/base.py",
  "language": "python",
  "kind": "file",
  "symbol": null,
  "metadata": {
    "calibra_state": "UNKNOWN",
    "calibra_confidence": 0.4,
    "extensions": {"github": {"repo": "gowdaharshith1998-lang/AXIOM-BRAIN", "ref": "main"}}
  }
}
```

---

## 3. Edge schema

Edges are typed relationships between entities, but the `relationship` itself is **free-text** (TEXT column) to avoid migrations for new relationship types.

Required fields:
- `id` (string, e.g. `edg_<ulid>`)
- `from_entity_id` (string; FK entities.id)
- `to_entity_id` (string; FK entities.id)
- `relationship` (string; free-text, e.g. `PERSON_PARTICIPATES_IN_THREAD`)
- `source_id` (string; FK sources.source_id)
- `created_at` (RFC3339 string)
- `metadata` (JSON object; edge-level attributes)

Relationship conventions:
- Relationships are uppercase snake-case for readability, but not enforced by DB.
- Connector-specific relationships may be namespaced in metadata if needed.

Common relationships (illustrative, non-exhaustive):
- `PERSON_PARTICIPATES_IN_THREAD`
- `TICKET_BELONGS_TO_PROJECT`
- `DECISION_REFERENCES_THREAD`
- `DOCUMENT_REFERENCED_BY_DECISION`
- `PROCESS_EMITS_SKILL`
- `SKILL_APPLIES_TO_TICKET`

Examples (5 canonical edges):
```json
{
  "id": "edg_01J2Z7009G3Y1A8T3D8V9W0Q1A",
  "from_entity_id": "ent_01J2Z6K8T7Y0P6GJ2R7R8XK3C2",
  "to_entity_id": "ent_01J2Z6N2GQJ9AQ8AK5V9JYV1WZ",
  "relationship": "PERSON_PARTICIPATES_IN_THREAD",
  "source_id": "src_slack_demo",
  "created_at": "2026-05-06T07:00:00Z",
  "metadata": {"joined_at": "2026-05-06T06:55:10Z", "role": "participant"}
}
```
```json
{
  "id": "edg_01J2Z703FQ0K2VQYJ9Y2V3V4AA",
  "from_entity_id": "ent_01J2Z6P8Q2R9K8Q5H5B0K9WJ8A",
  "to_entity_id": "ent_01J2Z6N2GQJ9AQ8AK5V9JYV1WZ",
  "relationship": "DECISION_REFERENCES_THREAD",
  "source_id": "src_synthetic",
  "created_at": "2026-05-06T07:45:00Z",
  "metadata": {"why": "decision was discussed in this thread"}
}
```
```json
{
  "id": "edg_01J2Z706P0Y7M7H3Q9T0B1C2DD",
  "from_entity_id": "ent_01J2Z6R4R7N8FQZ3VZC9J0H7A2",
  "to_entity_id": "ent_01J2Z6P8Q2R9K8Q5H5B0K9WJ8A",
  "relationship": "DOCUMENT_REFERENCED_BY_DECISION",
  "source_id": "src_synthetic",
  "created_at": "2026-05-06T07:45:05Z",
  "metadata": {"excerpt_ref": "refund threshold clause"}
}
```
```json
{
  "id": "edg_01J2Z708Q7C9B8N1A2S3D4F5GG",
  "from_entity_id": "ent_01J2Z6S9X5Z7G4A6X2T0D9J3AA",
  "to_entity_id": "ent_01J2Z6M0F8S9E7E3Y8X6G3D2QH",
  "relationship": "PROCESS_APPLIES_TO_TICKET",
  "source_id": "src_synthetic",
  "created_at": "2026-05-06T07:46:00Z",
  "metadata": {"scope": "ticket"}
}
```
```json
{
  "id": "edg_01J2Z70A3J1H6K8L9M0N2P3Q4RR",
  "from_entity_id": "ent_01J2Z6V2K0F1RZ9Q8M3M8D2Q0P",
  "to_entity_id": "ent_01J2Z6S9X5Z7G4A6X2T0D9J3AA",
  "relationship": "CODE_IMPLEMENTATION_SUPPORTS_PROCESS",
  "source_id": "src_synthetic",
  "created_at": "2026-05-06T07:48:00Z",
  "metadata": {"note": "placeholder edge type; Phase 2+ clarifies semantics"}
}
```

---

## 4. Receipt schema

Receipts are cryptographically verifiable audit artifacts emitted for actions and governance. They are written to:
- `~/.axiom/receipts/<type>/<receipt_id>.json`
- Detached signature files: `~/.axiom/receipts/<type>/<receipt_id>.json.sig` (Ed25519) and `...json.pqsig` (ML-DSA-65), plus optional Merkle inclusion proof file.

### 4.1 Action receipt (signed agent action)

Fields:
- `receipt_type`: `"action"`
- `action_id`: string
- `agent_id`: string
- `tool`: string (e.g. `"axiom_record_action"`)
- `params`: object (canonicalized JSON; stable ordering; no ephemeral keys)
- `timestamp`: RFC3339 string
- `result_hash`: string (sha256 of canonicalized result payload)
- `before_hash` (optional): string (sha256 of prior relevant entity/graph snapshot)
- `after_hash` (optional): string (sha256 of after snapshot)
- `decision`: `"allow"|"correct"|"deny"`
- `task_id` (optional): string
- `signing_scheme`: `"ed25519+ml-dsa-65"`
- `signature_ed25519`: base64
- `signature_mldsa`: base64
- `merkle_leaf_index`: int

### 4.2 Ingest receipt (entity/edge creation/modification)

Fields:
- `receipt_type`: `"ingest"`
- `receipt_id`: string
- `entity_ids`: array\[string]
- `edge_ids` (optional): array\[string]
- `source_id`: string
- `timestamp`: RFC3339 string
- `signing_scheme`: string
- `signature` (primary signature; plus detached sig files)
- `merkle_leaf_index`: int

### 4.3 Skill-load receipt (agent loads a skill)

Fields:
- `receipt_type`: `"skill_load"`
- `receipt_id`: string
- `agent_id`: string
- `skill_id`: string
- `skill_hash`: string (sha256 of SKILL.md canonical bytes)
- `timestamp`: RFC3339 string
- `calibra_confidence_at_load` (optional): float
- `signing_scheme`: string
- `signature`: base64
- `merkle_leaf_index`: int

### 4.4 Governance receipt (CORRECT or DENY)

Fields:
- `receipt_type`: `"governance"`
- `receipt_id`: string
- `original_action_payload`: object (canonicalized)
- `decision`: `"correct"|"deny"`
- `guidance` (optional): string (required if decision==correct)
- `reason` (optional): string (required if decision==deny)
- `policy_clause_id`: string
- `timestamp`: RFC3339 string
- `signing_scheme`: string
- `signature`: base64
- `merkle_leaf_index`: int

---

## 5. Source ABC

Every connector is a Python `ABC` that produces a stream of normalized ingest events (entity/edge add/modify/remove) with explicit source attribution.

### 5.1 Types

`SourceMetadata` (connector identity + health):
- `source_id`: string
- `source_type`: `"linear"|"slack"|"gmail"|"drive"|"github"|"synthetic"`
- `display_name`: string
- `connected`: bool
- `last_sync_at` (optional): RFC3339 string
- `capabilities`: object (e.g. `{"supports_watch": true, "supports_backfill": true}`)

`IngestEventType` (enum):
- `entity_added`
- `entity_modified`
- `entity_removed`
- `edge_added`
- `edge_removed`

`IngestEvent` (one atom of change):
- `event_id`: string (stable id; connector-generated)
- `event_type`: `IngestEventType`
- `source_id`: string
- `occurred_at`: RFC3339 string
- `entity` (optional): normalized entity payload (per §2)
- `edge` (optional): normalized edge payload (per §3)
- `external_ref` (optional): object (connector-specific pointers; e.g. linear issue id)
- `raw` (optional): object (raw connector payload; stored only if policy allows)

### 5.2 Connector interface

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import Callable, Literal, TypedDict


class SourceMetadata(TypedDict):
    source_id: str
    source_type: str
    display_name: str
    connected: bool
    last_sync_at: str | None
    capabilities: dict


class IngestEvent(TypedDict):
    event_id: str
    event_type: str
    source_id: str
    occurred_at: str
    entity: dict | None
    edge: dict | None
    external_ref: dict | None
    raw: dict | None


class Source(ABC):
    source_id: str
    source_type: Literal["linear", "slack", "gmail", "drive", "github", "synthetic"]

    @abstractmethod
    async def discover(self) -> SourceMetadata: ...

    @abstractmethod
    async def ingest(self, since: datetime | None = None) -> AsyncIterator[IngestEvent]: ...

    @abstractmethod
    async def watch(
        self, on_event: Callable[[IngestEvent], None]
    ) -> AbstractAsyncContextManager[None]: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    def metadata(self) -> dict: ...
```

### 5.3 Skeletons (non-functional; contract-only)

`SyntheticSource` (Phase 3):
- Purpose: emit a small deterministic “company seed” graph (from `fixtures/synthetic_company.json`) for demos and tests.
- Ingest semantics: `ingest()` yields entities then edges; `watch()` optionally replays fixed events on timers (if required by Phase 3).

`LinearSource` (Phase 12):
- Purpose: ingest issues, comments, and project/user metadata as tickets/threads/people/edges.
- Ingest semantics: `discover()` validates token scopes and returns capabilities; `ingest(since)` backfills modified issues since timestamp; `watch()` subscribes to webhooks or polling loop (roadmap-dependent; see §14).

---

## 6. MCP tool surface

All tools are prefixed `axiom_`. Tools are pure interface contracts: request/response shapes, side effects, and Calibra interaction.

### 6.1 Shared models

All tool requests and responses share:
- `request_id`: string (caller-generated)
- `timestamp`: RFC3339 string

Policy decisions share:
- `decision`: `"allow"|"correct"|"deny"|"pause"`
- `policy_clause_id` (optional)
- `guidance` (optional; required when decision==correct)
- `reason` (optional; required when decision==deny)

### 6.2 Tools (required + supporting)

#### Tool: `axiom_query_brain`
- **Description:** Run a structured query over entities/edges (filters + full-text + pagination).
- **Request (Pydantic shape):**
  - `request_id: str`
  - `query: str | None` (full-text; optional)
  - `entity_types: list[str] | None`
  - `source_ids: list[str] | None`
  - `filters: dict | None` (field filters)
  - `limit: int = 50`
  - `cursor: str | None`
- **Response:**
  - `entities: list[dict]`
  - `edges: list[dict]` (optional; present if query requests)
  - `next_cursor: str | None`
- **Side effects:** None (read-only); emits `stats` WebSocket heartbeat optionally.
- **Calibra:** `calibra.query()` may be called to annotate confidence for returned entities (roadmap-dependent).

#### Tool: `axiom_get_entity`
- **Description:** Fetch a single entity by id.
- **Request:** `entity_id: str`
- **Response:** `entity: dict | None`
- **Side effects:** None
- **Calibra:** none (or `calibra.query()` for metadata enrichment).

#### Tool: `axiom_traverse`
- **Description:** Graph traversal from a seed entity with relationship filters and depth.
- **Request:** `seed_entity_id: str`, `depth: int = 2`, `relationships: list[str] | None`, `direction: "out"|"in"|"both" = "both"`, `limit: int = 500`
- **Response:** `entities: list[dict]`, `edges: list[dict]`
- **Side effects:** None
- **Calibra:** none.

#### Tool: `axiom_list_sources`
- **Description:** List configured sources and their status.
- **Request:** none
- **Response:** `sources: list[dict]`
- **Side effects:** None
- **Calibra:** none.

#### Tool: `axiom_get_source_status`
- **Description:** Get a single source status/health.
- **Request:** `source_id: str`
- **Response:** `source: dict | None`
- **Side effects:** None
- **Calibra:** none.

#### Tool: `axiom_list_skills`
- **Description:** List emitted skills available to agents.
- **Request:** `scope: str | None`, `limit: int = 50`, `cursor: str | None`
- **Response:** `skills: list[dict]`, `next_cursor: str | None`
- **Side effects:** None
- **Calibra:** none.

#### Tool: `axiom_load_skill`
- **Description:** Retrieve skill contents by `skill_id`.
- **Request:** `skill_id: str`
- **Response:** `skill_markdown: str`, `skill_hash: str`, `signing: dict`
- **Side effects:** None; emits `skill_emitted` only if loaded triggers caching (roadmap-dependent).
- **Calibra:** may call `calibra.query()` to return `calibra_confidence_at_load`.

#### Tool: `axiom_attest_skill_load`
- **Description:** Agent attests it loaded a specific skill hash.
- **Request:** `agent_id: str`, `skill_id: str`, `skill_hash: str`, `timestamp: str`
- **Response:** `skill_load_receipt_id: str`, `merkle_leaf_index: int`
- **Side effects:** writes `skill-load` receipt; emits `receipt_emitted`.
- **Calibra:** none.

#### Tool: `axiom_get_receipts`
- **Description:** Fetch receipts by type/time range.
- **Request:** `receipt_type: str | None`, `since: str | None`, `until: str | None`, `limit: int = 100`, `cursor: str | None`
- **Response:** `receipts: list[dict]`, `next_cursor: str | None`
- **Side effects:** None
- **Calibra:** none.

#### Tool: `axiom_verify_receipt`
- **Description:** Verify detached signatures + Merkle inclusion proof for a receipt.
- **Request:** `receipt_id: str`, `receipt_type: str`
- **Response:** `verified: bool`, `details: dict`
- **Side effects:** None
- **Calibra:** none.

#### Tool: `axiom_check_policy`
- **Description:** Evaluate policy for a proposed action/tool call.
- **Request:** `agent_id: str`, `tool: str`, `action_type: str | None`, `target_type: str | None`, `params: dict`
- **Response:** `decision: str`, `policy_clause_id: str | None`, `guidance: str | None`, `reason: str | None`, `retry_budget_remaining: int | None`
- **Side effects:** emits `policy_decision_made` WebSocket event; may emit governance receipt for CORRECT/DENY (see §4.4).
- **Calibra:** may call `calibra.query()` on target entity to influence decision or trigger PAUSE.

#### Tool: `axiom_record_action`
- **Description:** Record (and sign) an agent action and its result hash; canonical “audit log append”.
- **Request:** `agent_id: str`, `tool: str`, `params: dict`, `result: dict | None`, `decision: str`, `task_id: str | None`
- **Response:** `action_receipt_id: str`, `merkle_leaf_index: int`, `result_hash: str`
- **Side effects:** writes action receipt; emits `agent_action_signed` and `receipt_emitted`.
- **Calibra:** `calibra.observe()` may be called to update beliefs about system state (“action succeeded”, “entity changed”)—exact mapping is Phase 6+.

#### Tool: `axiom_get_calibra_confidence`
- **Description:** Retrieve Calibra’s confidence for a belief/entity.
- **Request:** `belief_name: str | None`, `entity_id: str | None`
- **Response:** `calibra_state: str`, `calibra_confidence: float`, `details: dict | None`
- **Side effects:** None
- **Calibra:** calls `calibra.query()` or equivalent adapter.

#### Tool: `axiom_pause_for_evidence`
- **Description:** Request additional evidence when confidence is too low; returns an explicit PAUSE token.
- **Request:** `reason: str`, `requested_evidence: list[str]`, `context: dict | None`
- **Response:** `decision: "pause"`, `pause_id: str`, `requested_evidence: list[str]`
- **Side effects:** emits `approval_queue_updated` (or a dedicated pause queue event); writes governance receipt with decision `pause` (roadmap-dependent).
- **Calibra:** none directly.

#### Tool: `axiom_request_human_approval`
- **Description:** Enqueue an approval request for a sensitive action.
- **Request:** `agent_id: str`, `action_summary: str`, `proposed_action: dict`, `risk: str | None`
- **Response:** `approval_id: str`, `status: "queued"|"approved"|"rejected"`
- **Side effects:** emits `approval_queue_updated`; writes governance receipt when approved/rejected.
- **Calibra:** none.

Supporting tools (recommended for ergonomics):
- `axiom_list_entity_types` (returns \[7] types)
- `axiom_get_stats` (graph counts, source sync status)
- `axiom_subscribe_events` (WebSocket handshake variant; Phase 4/5 UI)

---

## 7. Policy YAML schema

Policy is YAML-defined; no ML internals. Evaluation rules must be deterministic and auditable.

### 7.1 Schema

```yaml
version: "1"
metadata:
  policy_name: "intelligent-default"
  description: "Default three-mode policy for AXIOM"

retry_budget:
  max_corrects_per_task: 3
  drift_threshold_cosine: 0.85
  escalate_after_drift: true

evaluation:
  strategy: "first_match_wins"  # ordered clauses
  default_decision: "allow"     # permissive by default (see §14 for stance question)

clauses:
  - id: "clause_001"
    match:
      tool: "axiom_record_action"
      action_type: "modify_entity"
      target_type: "billing"
    decision: "correct"
    guidance: |
      Direct modification of billing entities requires going through
      the billing reconciliation skill. Use that skill instead.
    allowed_alternative_tool: "axiom_load_skill"
    allowed_alternative_params:
      skill_id: "billing_reconcile_v2"

  - id: "clause_002"
    match:
      tool: "axiom_record_action"
      action_type: "modify_entity"
      target_type: "customer"
      field: "ssn"
    decision: "deny"
    reason: "PII fields require explicit human approval"
    escalate_to: "human_approval_queue"

  - id: "clause_003"
    match:
      tool: "axiom_record_action"
    decision: "allow"
```

### 7.2 Evaluation semantics

- **Ordered, first-match-wins**: clauses are evaluated top-to-bottom; the first matching clause decides.
- A clause `match` is a partial object match: absent keys do not constrain.
- `default_decision` applies if no clause matches.
- CORRECT consumes 1 unit of retry budget for the current `task_id`; when budget is exhausted, policy escalates to human approval (or deny), per `retry_budget.escalate_after_drift`.
- Drift detection: compute cosine similarity between successive action payload embeddings within a `task_id`; if below `drift_threshold_cosine`, escalate.

---

## 8. Skills emitter output

Skills are emitted as signed `SKILL.md` markdown files with YAML front-matter. AXIOM does **not** execute skills; agents execute them in their own runtimes and attest loads.

Canonical schema:
```markdown
---
id: refund_processing_v1
version: 1
scope: ticket
inputs:
  - name: ticket_id
    type: string
    required: true
  - name: refund_amount
    type: number
    required: true
outputs:
  - name: refund_status
    type: enum[approved, denied, pending]
side_effects:
  - mutates: Ticket
  - emits: refund_decision_receipt
requires_approval: false
calibra_threshold: 0.7
signing:
  scheme: ed25519+ml-dsa-65
  signature: <base64>
  merkle_leaf_index: 1234
provenance:
  emitted_from: process_entity_id_xyz
  emitted_at: 2026-05-05T12:34:56Z
  emitted_by: axiom_skills_emitter_v1
---

# Refund Processing

## Step 1: Validate ticket
- Load Ticket entity by id
- Confirm status is "refund_requested"
- Check refund_amount against policy threshold

## Step 2: Decision
- If refund_amount > $X, escalate via axiom_request_human_approval
- Else, record decision via axiom_record_action

## Step 3: Update ticket
- Modify Ticket entity status to "refund_approved" or "refund_denied"
- Sign result via axiom_record_action

## Fallbacks
- If Calibra confidence < calibra_threshold, axiom_pause_for_evidence and gather more data
- If policy returns CORRECT, follow the corrective guidance and retry
- If policy returns DENY, surface to human approval queue
```

Emitter rules:
- Emitted skill id is stable and versioned (`_vN`).
- Front-matter is the contract; body is human-readable procedural steps.
- The signature covers the entire file bytes in a canonical newline format.

---

## 9. WebSocket message types

All events use a single envelope:
```json
{
  "type": "<message_type>",
  "timestamp": 1714980000000,
  "payload": {}
}
```

Event payloads:

- `bootstrap_complete`
  - `payload`: `{ "graph_counts": { "entities": 0, "edges": 0 }, "sources": [], "skills": [] }`

- `entity_added` / `entity_modified` / `entity_removed`
  - `payload`: `{ "entity": { ... }, "source_id": "..." }` (for removed: `{ "entity_id": "...", "type": "..." }`)

- `edge_added` / `edge_removed`
  - `payload`: `{ "edge": { ... }, "source_id": "..." }` (for removed: `{ "edge_id": "..." }`)

- `receipt_emitted`
  - `payload`: `{ "receipt_type": "action|ingest|skill_load|governance", "receipt_id": "...", "merkle_leaf_index": 123 }`

- `agent_action_signed`
  - `payload`: `{ "agent_id": "...", "action_receipt_id": "...", "decision": "allow|correct|deny", "result_hash": "..." }`

- `correct_signal_emitted`
  - `payload`: `{ "receipt_id": "...", "policy_clause_id": "...", "guidance": "..." }`

- `deny_signal_emitted`
  - `payload`: `{ "receipt_id": "...", "policy_clause_id": "...", "reason": "..." }`

- `skill_emitted`
  - `payload`: `{ "skill_id": "...", "version": 1, "skill_hash": "...", "process_entity_id": "..." }`

- `source_connected` / `source_disconnected`
  - `payload`: `{ "source_id": "...", "source_type": "...", "display_name": "...", "connected": true|false }`

- `source_sync_started` / `source_sync_completed`
  - `payload`: `{ "source_id": "...", "started_at": "...", "completed_at": "...", "stats": { "entities": 0, "edges": 0 } }`

- `calibra_confidence_changed`
  - `payload`: `{ "entity_id": "...", "calibra_state": "KNOW|UNCERTAIN|UNKNOWN", "calibra_confidence": 0.0 }`

- `policy_decision_made`
  - `payload`: `{ "agent_id": "...", "tool": "...", "decision": "allow|correct|deny|pause", "policy_clause_id": "..." }`

- `approval_queue_updated`
  - `payload`: `{ "approval_id": "...", "status": "queued|approved|rejected", "summary": "..." }`

- `stats`
  - `payload`: `{ "entities": 0, "edges": 0, "sources_connected": 0, "receipts_total": 0 }`

---

## 10. Hosting topology

Phase 0 does not pick the final platforms; it documents topology + tradeoffs.

- **Backend candidate (recommended):** Fly.io
  - Pros: global edge, good WebSocket support, persistent volumes for SQLite WAL, straightforward Python deploy.
  - Cons: operational complexity vs fully-managed platforms; requires careful volume placement.

- **Backend alternative:** Render.com
  - Pros: simpler managed experience; persistent disks; easy deploy.
  - Cons: global latency; confirm WebSocket and long-lived connections behavior under plan constraints.

- **Frontend candidates:** Vercel or Cloudflare Pages
  - Both: excellent static/SPA hosting; good CI integration.
  - Decision in Phase 11 (OD1.5 per dispatch).

- **Custom domain:** placeholder `axiom.example` until OD1 is ruled.
- **Secrets:** platform secret store only (no secrets in git).
- **OAuth callback URLs:** templated patterns:
  - Production: `https://<domain>/api/oauth/callback/<source_type>`
  - Local dev: `http://localhost:3000/api/oauth/callback/<source_type>` (exact ports are Phase 1/11)
- **HTTPS:** Let’s Encrypt via platform.
- **Database:** SQLite WAL mode on persistent volume/disk.
- **WebSocket:** must be explicitly verified on chosen backend platform.
- **CI/CD:** GitHub Actions deploy on push to `main`.

---

## 11. Database schema

Single-tenant SQLite schema. Relationship/type columns are free-text TEXT.

### 11.1 DDL (SQLite)

```sql
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS sources (
  source_id TEXT PRIMARY KEY,
  source_type TEXT NOT NULL,
  display_name TEXT NOT NULL,
  connected INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS entities (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  source_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  palette_color TEXT NOT NULL,
  data_json TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  FOREIGN KEY(source_id) REFERENCES sources(source_id)
);
CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(type);
CREATE INDEX IF NOT EXISTS idx_entities_source_id ON entities(source_id);
CREATE INDEX IF NOT EXISTS idx_entities_updated_at ON entities(updated_at);

CREATE TABLE IF NOT EXISTS edges (
  id TEXT PRIMARY KEY,
  from_entity_id TEXT NOT NULL,
  to_entity_id TEXT NOT NULL,
  relationship TEXT NOT NULL,
  source_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  FOREIGN KEY(from_entity_id) REFERENCES entities(id),
  FOREIGN KEY(to_entity_id) REFERENCES entities(id),
  FOREIGN KEY(source_id) REFERENCES sources(source_id)
);
CREATE INDEX IF NOT EXISTS idx_edges_from ON edges(from_entity_id);
CREATE INDEX IF NOT EXISTS idx_edges_to ON edges(to_entity_id);
CREATE INDEX IF NOT EXISTS idx_edges_relationship ON edges(relationship);

CREATE TABLE IF NOT EXISTS skills (
  skill_id TEXT PRIMARY KEY,
  version INTEGER NOT NULL,
  scope TEXT NOT NULL,
  skill_hash TEXT NOT NULL,
  process_entity_id TEXT NOT NULL,
  emitted_at TEXT NOT NULL,
  signed_metadata_json TEXT NOT NULL DEFAULT '{}',
  markdown TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_skills_scope ON skills(scope);
CREATE INDEX IF NOT EXISTS idx_skills_process ON skills(process_entity_id);

CREATE TABLE IF NOT EXISTS actions (
  action_id TEXT PRIMARY KEY,
  agent_id TEXT NOT NULL,
  tool TEXT NOT NULL,
  params_json TEXT NOT NULL,
  decision TEXT NOT NULL,
  result_hash TEXT NOT NULL,
  task_id TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_actions_agent ON actions(agent_id);
CREATE INDEX IF NOT EXISTS idx_actions_task ON actions(task_id);
CREATE INDEX IF NOT EXISTS idx_actions_tool ON actions(tool);

CREATE TABLE IF NOT EXISTS receipts (
  receipt_id TEXT PRIMARY KEY,
  receipt_type TEXT NOT NULL,
  merkle_leaf_index INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  signature_ed25519 TEXT,
  signature_mldsa TEXT
);
CREATE INDEX IF NOT EXISTS idx_receipts_type ON receipts(receipt_type);
CREATE INDEX IF NOT EXISTS idx_receipts_created_at ON receipts(created_at);
```

### 11.2 Migrations approach

- Use Alembic (Phase 2) with an initial migration creating the tables above.
- Future schema evolution: additive columns only where possible; relationship/type remain TEXT to avoid churn.

---

## 12. Directory structure

Target repository layout (Phase 0 skeleton only; Phase 1 wires dependencies and real stubs):

```
AXIOM-BRAIN/
├── pyproject.toml
├── alembic.ini
├── DESIGN.md
├── README.md
├── LICENSE
├── .github/
│   └── workflows/
│       └── ci.yml
├── src/
│   └── axiom/
│       ├── __init__.py
│       ├── schema/
│       ├── ingest/
│       ├── mcp/
│       ├── studio/
│       ├── skills/
│       ├── policy/
│       ├── sign/
│       └── sources/
├── frontend/
│   ├── package.json
│   ├── src/
│   │   ├── components/
│   │   ├── lib/
│   │   ├── state/
│   │   └── styles/
│   └── public/
├── migrations/
│   └── versions/
├── policies/
│   └── intelligent.yaml
├── fixtures/
│   └── synthetic_company.json
└── tests/
    ├── __init__.py
    └── test_design_doc.py
```

---

## 13. Phase-by-phase contract checklist

This section maps each phase to the design contracts it depends on.

Phase 1 (Skeleton + dependencies):
- Depends on: §10, §12
- Adds: real dependency declarations, placeholder server/CLI entrypoints (stubs), CI wiring, repo metadata (`alembic.ini`), stubs for tool handlers (no business logic yet).

Phase 2 (Schema + storage):
- Depends on: §2, §3, §11
- Adds: Pydantic models, SQLite CRUD layer, Alembic migrations, unit tests for schema invariants.

Phase 3 (Synthetic + ingest):
- Depends on: §2, §3, §5, §11
- Adds: `SyntheticSource` connector stub + ingest pipeline skeleton + fixture normalization rules.

Phase 4 (Studio UI + 3D viz baseline):
- Depends on: §9, §10, §12
- Adds: WebSocket client/server stubs, baseline 3D visualization scaffolding, event subscription UX (not an IDE UI).

Phase 5 (Receipts + signing plumbing):
- Depends on: §4, §11
- Adds: receipt writer/reader, signature verification hooks, Merkle append log interface.

Phase 6 (MCP server + tools):
- Depends on: §6, §4, §7, §9
- Adds: MCP server implementation exposing all tools; policy check gate before action recording.

Phase 7 (Policy engine v1):
- Depends on: §7
- Adds: YAML loader, matcher, decision function, retry budget tracking, drift detection plumbing.

Phase 8 (Skills emitter v1):
- Depends on: §8, §2 (`process` entities), §4 (skill-load receipts)
- Adds: process-walker, SKILL.md emitter, signing, storage in `skills` table.

Phase 9 (Governance receipts + correction loop):
- Depends on: §4, §7, §6
- Adds: CORRECT/DENY receipt emission, agent-facing guidance return, approval queue integration.

Phase 10 (Hosted deployment scaffolding):
- Depends on: §10
- Adds: deployment manifests/scripts, secret configuration docs, environment parity docs.

Phase 11 (Hosting decision + production URL demo):
- Depends on: §10 (tradeoffs and required properties)
- Adds: selected backend/frontend platform configs, production domain (OD1), OAuth callback finalization.

Phase 12 (Linear connector):
- Depends on: §5, §2, §3, §9
- Adds: `LinearSource` connector (ingest + watch strategy), normalization rules, source status reporting.

Phase 13 (Additional connectors planning surface):
- Depends on: §5
- Adds: Slack/Gmail/Drive/GitHub connector scaffolds (still contract-level if roadmap says post-launch).

Phase 14 (Approvals + governance UX hardening):
- Depends on: §9, §6, §7
- Adds: approval queue UX in Studio, audit views for receipts, human-in-the-loop workflows.

Phase 15 (YC application drafting support):
- Depends on: §1–§14 (design defensibility)
- Adds: narrative artifacts; does not alter core contracts.

---

## 14. Open questions for dispatcher

These must be ruled before Phase 1 proceeds.

1. **Parent roadmap availability:** The referenced file `/mnt/user-data/outputs/AXIOM_BUILD_ROADMAP_2026-05-05.md` was not accessible in this environment. Provide its contents/path so this design can be validated for conformity (phases, OD decisions, citations, and any locked constraints not present in the dispatch).

2. **Default policy stance:** The schema above uses `default_decision: allow` (per dispatch example). Confirm whether AXIOM should be default-permissive (with CORRECT steering) or default-deny (with explicit allowlists) at launch.

3. **WebSocket delivery:** Confirm whether Studio uses a single WebSocket connection per browser session (recommended) and whether event replay/backfill is required (impacts event ids and pagination).

4. **Merkle anchoring:** Confirm the required Merkle tree flavor and anchoring cadence (e.g. RFC6962-style per-receipt append + optional checkpointing). The design assumes RFC6962-like leaf indexing.

5. **ML-DSA-65 library selection:** Confirm intended library surface (e.g. `pqcrypto` vs `cryptography` once FIPS 204 support is available). Phase 0 specifies the signing scheme string but not implementation details.

6. **Calibra integration mapping:** Which Calibra calls are canonical for AXIOM?
   - The environment’s existing Calibra-like code appears to expose `observe()` and MCP-layer `query()`/`recall()` patterns; confirm the final adapter methods and how they map to entity metadata (`calibra_state`, `calibra_confidence`).

7. **Connector watch strategy:** For Linear/Slack/Gmail, does Phase 12+ use webhooks (preferred) or polling (fallback)? This impacts `Source.watch()` semantics and required callback URL shapes.

8. **Receipt storage location:** The design uses `~/.axiom/receipts/...` per dispatch. Confirm whether production deployments also write receipts there or to a platform volume path (e.g. `/data/.axiom/receipts`) and whether receipts are also persisted in SQLite (`receipts` table) as canonical.

9. **Entity id format:** Confirm whether to standardize on ULID-based ids (`ent_<ulid>`) vs UUIDv7. Both are sortable; ULID is human-friendlier.

10. **Skills storage + discovery:** Are skills stored in DB only, filesystem only, or both? The design includes both (`skills` table + markdown bytes). Confirm desired canonical store.

