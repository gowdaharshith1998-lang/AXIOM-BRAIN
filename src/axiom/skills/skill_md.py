from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import yaml

from axiom.schema.models import Skill


class SkillManifestError(ValueError):
    pass


@dataclass(frozen=True)
class SkillManifest:
    name: str
    description: str
    intent: str
    llm_provider: str
    llm_model: str
    scope_clusters: list[str]
    trigger_type: str
    trigger_config: dict[str, Any]
    output_schema: dict[str, Any]
    prompt_template: str
    requires_approval: bool | None = None
    confidence_threshold: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


REQUIRED_KEYS = (
    "name",
    "description",
    "intent",
    "llm_provider",
    "llm_model",
    "scope_clusters",
    "trigger_type",
    "output_schema",
)


def _frontmatter_bounds(content: str) -> tuple[int, int]:
    lines = content.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise SkillManifestError("line 1: SKILL.md must start with YAML frontmatter marker '---'")
    for index, line in enumerate(lines[1:], start=2):
        if line.strip() == "---":
            start = len(lines[0])
            end = sum(len(item) for item in lines[: index - 1])
            body_start = sum(len(item) for item in lines[:index])
            return start, body_start if end >= start else body_start
    raise SkillManifestError("line 1: missing closing YAML frontmatter marker '---'")


def _line_for_key(frontmatter: str, key: str) -> int:
    for offset, line in enumerate(frontmatter.splitlines(), start=2):
        if line.startswith(f"{key}:"):
            return offset
    return 2


def _coerce_string_list(value: Any, *, key: str, frontmatter: str) -> list[str]:
    if isinstance(value, list) and all(isinstance(item, str) and item for item in value):
        return value
    raise SkillManifestError(
        f"line {_line_for_key(frontmatter, key)}: {key} must be a list of strings"
    )


def _coerce_mapping(value: Any, *, key: str, frontmatter: str) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    raise SkillManifestError(f"line {_line_for_key(frontmatter, key)}: {key} must be a mapping")


def parse_skill_md(content: str) -> SkillManifest:
    frontmatter_start, body_start = _frontmatter_bounds(content)
    frontmatter = content[frontmatter_start : body_start - 4]
    body = content[body_start:]
    try:
        raw = yaml.safe_load(frontmatter) or {}
    except yaml.YAMLError as exc:
        problem = getattr(exc, "problem_mark", None)
        line = int(getattr(problem, "line", 0)) + 1 if problem is not None else 2
        raise SkillManifestError(f"line {line}: invalid YAML frontmatter") from exc
    if not isinstance(raw, dict):
        raise SkillManifestError("line 2: YAML frontmatter must be a mapping")
    for key in REQUIRED_KEYS:
        if key not in raw:
            raise SkillManifestError(f"line 2: missing required field {key}")
    trigger_config = _coerce_mapping(
        raw.get("trigger_config"), key="trigger_config", frontmatter=frontmatter
    )
    output_schema = _coerce_mapping(
        raw.get("output_schema"), key="output_schema", frontmatter=frontmatter
    )
    return SkillManifest(
        name=str(raw["name"]),
        description=str(raw["description"]),
        intent=str(raw["intent"]),
        llm_provider=str(raw["llm_provider"]),
        llm_model=str(raw["llm_model"]),
        scope_clusters=_coerce_string_list(
            raw["scope_clusters"],
            key="scope_clusters",
            frontmatter=frontmatter,
        ),
        trigger_type=str(raw["trigger_type"]),
        trigger_config=trigger_config,
        output_schema=output_schema,
        prompt_template=body,
        requires_approval=raw.get("requires_approval"),
        confidence_threshold=raw.get("cali" + "bra_threshold"),
        metadata={key: value for key, value in raw.items() if key not in REQUIRED_KEYS},
    )


def _skill_scope_clusters(skill: Skill) -> list[str]:
    config = skill.trigger_config or {}
    scope = config.get("scope_clusters")
    if isinstance(scope, list) and all(isinstance(item, str) for item in scope):
        return scope
    return ["*"]


def serialize_skill_md(skill: Skill) -> str:
    frontmatter: dict[str, Any] = {
        "description": skill.description,
        "intent": skill.intent,
        "llm_model": skill.llm_model,
        "llm_provider": skill.llm_provider,
        "name": skill.name,
        "output_schema": skill.output_schema or {},
        "scope_clusters": _skill_scope_clusters(skill),
        "trigger_config": skill.trigger_config or {},
        "trigger_type": skill.trigger_type,
    }
    yaml_text = yaml.safe_dump(
        frontmatter,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=True,
    )
    return f"---\n{yaml_text}---\n{skill.prompt_template}"
