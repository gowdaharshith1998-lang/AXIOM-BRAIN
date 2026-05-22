"""SkillFile DB store — load / save / versioning.

Backs the REST API. A SkillFile has one ``skill_files`` row (current promoted
state) and an append-only ``skill_file_versions`` history. Invalid saves are
recorded in history for audit but never promoted to ``current_version``
(deny-by-default).

Version numbers are monotonic across the whole history — an invalid save still
consumes a version number, so a later valid save can never collide with it.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from axiom.schema.models import SkillFileRow, SkillFileVersionRow, new_id
from axiom.skills.skill_file_parser import SkillFileParseError, parse_skill_file_yaml


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class StoredSkillFile:
    id: str
    name: str
    yaml_text: str
    current_version: int
    description: str
    validation_status: str  # "valid" | "invalid" | "unknown"
    validation_errors: list[str]
    updated_at: str


def _describe(yaml_text: str) -> str:
    """Best-effort description from YAML; empty string if it does not parse."""
    try:
        return parse_skill_file_yaml(yaml_text).description
    except SkillFileParseError:
        return ""


def _to_stored(session: Session, row: SkillFileRow) -> StoredSkillFile:
    latest = (
        session.query(SkillFileVersionRow)
        .filter_by(skill_file_id=row.id, version=row.current_version)
        .one_or_none()
    )
    validation_status = latest.validation_status if latest else "unknown"
    validation_errors = (
        json.loads(latest.validation_errors)
        if latest and latest.validation_errors
        else []
    )
    return StoredSkillFile(
        id=row.id,
        name=row.name,
        yaml_text=row.yaml_text,
        current_version=row.current_version,
        description=_describe(row.yaml_text),
        validation_status=validation_status,
        validation_errors=validation_errors,
        updated_at=row.updated_at,
    )


def list_skill_files(session: Session) -> list[StoredSkillFile]:
    rows = session.query(SkillFileRow).order_by(SkillFileRow.name).all()
    return [_to_stored(session, row) for row in rows]


def get_skill_file(session: Session, name: str) -> StoredSkillFile | None:
    row = session.query(SkillFileRow).filter_by(name=name).one_or_none()
    if row is None:
        return None
    return _to_stored(session, row)


def _max_version(session: Session, skill_file_id: str) -> int:
    return (
        session.query(func.max(SkillFileVersionRow.version))
        .filter_by(skill_file_id=skill_file_id)
        .scalar()
        or 0
    )


def save_skill_file(
    session: Session,
    name: str,
    yaml_text: str,
    saved_by: str | None = None,
) -> StoredSkillFile:
    """Save a new version.

    Validates first. A valid save is promoted (``current_version`` advances to
    the new version number). An invalid save is still recorded in history for
    audit but is NOT promoted — the previous valid version stays current.

    Raises ``SkillFileParseError`` only when the very first save of a name is
    invalid (there is no prior valid state to fall back to).
    """
    errors: list[str] = []
    try:
        parsed = parse_skill_file_yaml(yaml_text)
        if parsed.name != name:
            errors.append(
                f"name in YAML ({parsed.name!r}) must match the URL slug ({name!r})"
            )
    except SkillFileParseError as exc:
        errors.append(str(exc))

    now = _now_iso()
    row = session.query(SkillFileRow).filter_by(name=name).one_or_none()

    # ── First save of this name ──────────────────────────────────────────
    if row is None:
        if errors:
            raise SkillFileParseError(
                f"cannot create {name!r}: {'; '.join(errors)}"
            )
        row = SkillFileRow(
            id=new_id(),
            name=name,
            yaml_text=yaml_text,
            current_version=1,
            created_at=now,
            updated_at=now,
            created_by=saved_by,
        )
        session.add(row)
        session.add(
            SkillFileVersionRow(
                id=new_id(),
                skill_file_id=row.id,
                version=1,
                yaml_text=yaml_text,
                saved_at=now,
                saved_by=saved_by,
                validation_status="valid",
                validation_errors=None,
            )
        )
        session.commit()
        return _to_stored(session, row)

    next_version = _max_version(session, row.id) + 1

    # ── Invalid save — record for audit, do not promote ──────────────────
    if errors:
        session.add(
            SkillFileVersionRow(
                id=new_id(),
                skill_file_id=row.id,
                version=next_version,
                yaml_text=yaml_text,
                saved_at=now,
                saved_by=saved_by,
                validation_status="invalid",
                validation_errors=json.dumps(errors),
            )
        )
        session.commit()
        return StoredSkillFile(
            id=row.id,
            name=row.name,
            yaml_text=row.yaml_text,  # unchanged — the last valid YAML
            current_version=row.current_version,  # unchanged
            description=_describe(row.yaml_text),
            validation_status="invalid",
            validation_errors=errors,
            updated_at=now,
        )

    # ── Valid save — record and promote ──────────────────────────────────
    session.add(
        SkillFileVersionRow(
            id=new_id(),
            skill_file_id=row.id,
            version=next_version,
            yaml_text=yaml_text,
            saved_at=now,
            saved_by=saved_by,
            validation_status="valid",
            validation_errors=None,
        )
    )
    row.yaml_text = yaml_text
    row.current_version = next_version
    row.updated_at = now
    session.commit()
    return _to_stored(session, row)


def list_versions(session: Session, name: str) -> list[dict[str, Any]]:
    row = session.query(SkillFileRow).filter_by(name=name).one_or_none()
    if row is None:
        return []
    versions = (
        session.query(SkillFileVersionRow)
        .filter_by(skill_file_id=row.id)
        .order_by(SkillFileVersionRow.version.desc())
        .all()
    )
    return [
        {
            "version": v.version,
            "saved_at": v.saved_at,
            "saved_by": v.saved_by,
            "validation_status": v.validation_status,
            "validation_errors": (
                json.loads(v.validation_errors) if v.validation_errors else []
            ),
        }
        for v in versions
    ]


def seed_from_disk(session: Session, library_dir: str = "skills/library") -> int:
    """One-time seed: load any ``*.skill.yaml`` from ``library_dir`` that is not
    already in the DB. Idempotent — existing names are skipped."""
    if not os.path.isdir(library_dir):
        return 0
    count = 0
    for filename in sorted(os.listdir(library_dir)):
        if not filename.endswith(".skill.yaml"):
            continue
        path = os.path.join(library_dir, filename)
        try:
            with open(path, encoding="utf-8") as handle:
                yaml_text = handle.read()
            parsed = parse_skill_file_yaml(yaml_text)
        except (OSError, SkillFileParseError):
            continue
        if session.query(SkillFileRow).filter_by(name=parsed.name).one_or_none():
            continue
        save_skill_file(session, name=parsed.name, yaml_text=yaml_text, saved_by="seed")
        count += 1
    return count
