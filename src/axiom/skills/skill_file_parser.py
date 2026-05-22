"""SkillFile YAML parser — deny-by-default, no silent degradation.

Parses + validates SkillFile YAML into the frozen dataclasses in
``axiom.skills.skill_file``. The 5 step types are the entire surface; an
unknown step type or any structural problem raises ``SkillFileParseError``.

Security: YAML is parsed with ``yaml.safe_load`` (never ``yaml.load``).
"""

from __future__ import annotations

from typing import Any

import yaml

from axiom.skills.skill_file import (
    SkillFile,
    Step,
    StepFetchEntity,
    StepIfThen,
    StepLogDecision,
    StepRequireApproval,
    StepWriteEntity,
    TriggerMatcher,
)


class SkillFileParseError(ValueError):
    """Raised when a SkillFile YAML fails to parse or validate."""


_STEP_TYPES = {
    "if_then",
    "fetch_entity",
    "write_entity",
    "require_approval",
    "log_decision",
}


def parse_skill_file_yaml(text: str) -> SkillFile:
    """Parse and validate SkillFile YAML.

    Raises ``SkillFileParseError`` on any syntax or structural problem — the
    caller (store / API / CLI) surfaces the message verbatim to the user.
    """
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise SkillFileParseError(f"invalid YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise SkillFileParseError("SkillFile must be a YAML mapping at the top level")

    for required in ("name", "description", "version", "when_triggered_by", "steps"):
        if required not in raw:
            raise SkillFileParseError(f"missing required field: {required}")

    triggers_raw = raw["when_triggered_by"]
    if not isinstance(triggers_raw, list) or not triggers_raw:
        raise SkillFileParseError("when_triggered_by must be a non-empty list")
    triggers = [_parse_trigger(t) for t in triggers_raw]

    steps_raw = raw["steps"]
    if not isinstance(steps_raw, list) or not steps_raw:
        raise SkillFileParseError("steps must be a non-empty list")
    steps = [_parse_step(s) for s in steps_raw]

    try:
        version = int(raw["version"])
    except (TypeError, ValueError) as exc:
        raise SkillFileParseError(
            f"version must be an integer, got {raw['version']!r}"
        ) from exc

    return SkillFile(
        name=str(raw["name"]),
        description=str(raw["description"]),
        version=version,
        when_triggered_by=triggers,
        steps=steps,
    )


def _parse_trigger(raw: Any) -> TriggerMatcher:
    if not isinstance(raw, dict):
        raise SkillFileParseError(f"trigger must be a mapping, got {type(raw).__name__}")
    if "intent" not in raw:
        raise SkillFileParseError("trigger missing required field: intent")
    source = raw.get("source")
    if source is not None and not isinstance(source, list):
        raise SkillFileParseError("trigger.source must be a list of strings")
    return TriggerMatcher(intent=str(raw["intent"]), source=source)


def _require(raw: dict[str, Any], key: str, step_type: str, step_id: str) -> Any:
    if key not in raw or raw[key] is None:
        raise SkillFileParseError(
            f"{step_type} step {step_id!r} missing required field: {key}"
        )
    return raw[key]


def _parse_step(raw: Any) -> Step:
    if not isinstance(raw, dict):
        raise SkillFileParseError(f"step must be a mapping, got {type(raw).__name__}")

    step_type = raw.get("type")
    if step_type not in _STEP_TYPES:
        raise SkillFileParseError(
            f"unknown step type: {step_type!r}. allowed: {sorted(_STEP_TYPES)}"
        )

    step_id = raw.get("id")
    if not step_id or not isinstance(step_id, str):
        raise SkillFileParseError(f"{step_type} step missing required field: id")

    if step_type == "if_then":
        condition = _require(raw, "condition", "if_then", step_id)
        if not isinstance(condition, str):
            raise SkillFileParseError(
                f"if_then step {step_id!r}: condition must be a string"
            )
        # Validate the DSL condition parses now, so a bad condition is rejected
        # at save time rather than blowing up mid-run.
        from axiom.policy.dsl import parse_predicate

        try:
            parse_predicate(condition)
        except Exception as exc:  # noqa: BLE001 — any DSL parse error is a parse error
            raise SkillFileParseError(
                f"if_then step {step_id!r}: condition unparseable: {exc}"
            ) from exc
        then_raw = raw.get("then", [])
        if not isinstance(then_raw, list):
            raise SkillFileParseError(f"if_then step {step_id!r}: then must be a list")
        return StepIfThen(
            id=step_id,
            type="if_then",
            condition=condition,
            then=[_parse_step(s) for s in then_raw],
        )

    if step_type == "fetch_entity":
        return StepFetchEntity(
            id=step_id,
            type="fetch_entity",
            query=str(_require(raw, "query", "fetch_entity", step_id)),
            bind_to=str(_require(raw, "bind_to", "fetch_entity", step_id)),
        )

    if step_type == "write_entity":
        data = _require(raw, "data", "write_entity", step_id)
        if not isinstance(data, dict):
            raise SkillFileParseError(
                f"write_entity step {step_id!r}: data must be a mapping"
            )
        return StepWriteEntity(
            id=step_id,
            type="write_entity",
            cluster=str(_require(raw, "cluster", "write_entity", step_id)),
            entity_type=str(_require(raw, "entity_type", "write_entity", step_id)),
            data=data,
        )

    if step_type == "require_approval":
        timeout = raw.get("timeout_seconds", 3600)
        try:
            timeout = int(timeout)
        except (TypeError, ValueError) as exc:
            raise SkillFileParseError(
                f"require_approval step {step_id!r}: timeout_seconds must be an integer"
            ) from exc
        return StepRequireApproval(
            id=step_id,
            type="require_approval",
            role=str(_require(raw, "role", "require_approval", step_id)),
            timeout_seconds=timeout,
        )

    if step_type == "log_decision":
        return StepLogDecision(
            id=step_id,
            type="log_decision",
            cluster=str(_require(raw, "cluster", "log_decision", step_id)),
            note=str(_require(raw, "note", "log_decision", step_id)),
        )

    raise SkillFileParseError(f"unreachable: step type {step_type!r}")
