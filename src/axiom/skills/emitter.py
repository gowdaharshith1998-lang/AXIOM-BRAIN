from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any, cast

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from axiom.schema.models import Edge, Entity, Skill
from axiom.skills.registry import register_skill_with_session, skill_to_dict
from axiom.skills.skill_md import SkillManifest

SkillEventCallback = Callable[[str, dict[str, Any]], None]


def slugify_skill_name(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    return slug or "compiled_process"


def manifest_to_dict(manifest: SkillManifest) -> dict[str, Any]:
    return {
        "name": manifest.name,
        "description": manifest.description,
        "intent": manifest.intent,
        "llm_provider": manifest.llm_provider,
        "llm_model": manifest.llm_model,
        "scope_clusters": manifest.scope_clusters,
        "trigger_type": manifest.trigger_type,
        "trigger_config": manifest.trigger_config,
        "output_schema": manifest.output_schema,
        "prompt_template": manifest.prompt_template,
        "metadata": manifest.metadata,
    }


def _entity_title(entity: Entity) -> str:
    data = entity.data or {}
    for key in ("title", "name", "subject", "label"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return entity.id


def _text_fragments(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (int, float, bool)):
        return [str(value)]
    if isinstance(value, list):
        return [part for item in value for part in _text_fragments(item)]
    if isinstance(value, dict):
        return [part for item in value.values() for part in _text_fragments(item)]
    return []


class ProcessSkillEmitter:
    def __init__(self, session: Session) -> None:
        self.session = session

    def emit_all(self) -> list[SkillManifest]:
        rows = (
            self.session.execute(select(Entity).where(Entity.type == "process").order_by(Entity.id))
            .scalars()
            .all()
        )
        return [self.emit_one(row.id) for row in rows]

    def emit_one(self, process_entity_id: str) -> SkillManifest:
        entity = self.session.get(Entity, process_entity_id)
        if entity is None or entity.type != "process":
            raise LookupError(f"process entity not found: {process_entity_id}")
        name = _entity_title(entity)
        return SkillManifest(
            name=slugify_skill_name(name or entity.id),
            description=str((entity.data or {}).get("description") or f"Compiled skill for {name}"),
            intent=self.infer_intent_from_process(entity),
            llm_provider="anthropic",
            llm_model="claude-3-haiku-20240307",
            scope_clusters=[entity.cluster_id] if entity.cluster_id else ["*"],
            trigger_type="manual",
            trigger_config={"process_entity_id": entity.id},
            output_schema=self.infer_output_schema(entity),
            prompt_template=self.render_prompt_from_process(entity),
            metadata={"process_entity_id": entity.id},
        )

    def infer_intent_from_process(self, entity: Entity) -> str:
        haystack = " ".join(_text_fragments(entity.data or {})).lower()
        if "classify" in haystack or "classification" in haystack:
            return "classify"
        if "summarize" in haystack or "summary" in haystack:
            return "summarize"
        if "extract" in haystack or "extraction" in haystack:
            return "extract"
        return "transform"

    def infer_output_schema(self, _entity: Entity) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "result": {"type": "string"},
                "rationale": {"type": "string"},
            },
            "required": ["result"],
        }

    def render_prompt_from_process(self, entity: Entity) -> str:
        data = entity.data or {}
        lines = [
            f"Follow this process: {_entity_title(entity)}",
            "",
        ]
        description = data.get("description")
        if isinstance(description, str) and description.strip():
            lines.extend(["Description:", description.strip(), ""])
        steps = data.get("steps")
        if isinstance(steps, list) and steps:
            lines.append("Steps:")
            for index, step in enumerate(steps, start=1):
                lines.append(f"{index}. {step}")
            lines.append("")
        linked = self._linked_context(entity)
        if linked:
            lines.extend(["Linked context:", *linked, ""])
        lines.extend(
            [
                "Input:",
                "{{input}}",
                "",
                "Return JSON matching the output schema.",
            ]
        )
        return "\n".join(lines)

    def _linked_context(self, entity: Entity) -> list[str]:
        edges = (
            self.session.execute(
                select(Edge).where(or_(Edge.source_id == entity.id, Edge.target_id == entity.id))
            )
            .scalars()
            .all()
        )
        context: list[str] = []
        for edge in edges:
            other_id = edge.target_id if edge.source_id == entity.id else edge.source_id
            other = self.session.get(Entity, other_id)
            if other is None:
                continue
            data = other.data or {}
            detail = data.get("summary") or data.get("description") or data.get("body") or ""
            suffix = f": {detail}" if isinstance(detail, str) and detail.strip() else ""
            context.append(f"- {other.type} {_entity_title(other)}{suffix}")
        return context


def compile_skills_from_processes(
    session: Session,
    *,
    dry_run: bool = False,
    process_ids: list[str] | None = None,
    event_callback: SkillEventCallback | None = None,
) -> list[SkillManifest | Skill]:
    emitter = ProcessSkillEmitter(session)
    manifests = (
        [emitter.emit_one(process_id) for process_id in process_ids]
        if process_ids
        else emitter.emit_all()
    )
    if dry_run:
        return cast(list[SkillManifest | Skill], manifests)

    compiled: list[Skill] = []
    for manifest in manifests:
        row = session.execute(select(Skill).where(Skill.name == manifest.name)).scalar_one_or_none()
        trigger_config = {
            **manifest.trigger_config,
            "scope_clusters": manifest.scope_clusters,
        }
        if row is None:
            row = register_skill_with_session(
                session,
                name=manifest.name,
                description=manifest.description,
                intent=manifest.intent,
                prompt_template=manifest.prompt_template,
                llm_provider=manifest.llm_provider,
                llm_model=manifest.llm_model,
                output_schema=manifest.output_schema,
                trigger_config=trigger_config,
                trigger_type=manifest.trigger_type,
                created_by="process_skill_emitter",
            )
        else:
            row.description = manifest.description
            row.intent = manifest.intent
            row.prompt_template = manifest.prompt_template
            row.output_schema = manifest.output_schema
            row.llm_provider = manifest.llm_provider
            row.llm_model = manifest.llm_model
            row.trigger_type = manifest.trigger_type
            row.trigger_config = trigger_config
            session.add(row)
            session.commit()
            session.refresh(row)
        compiled.append(row)
        if event_callback is not None:
            event_callback(
                "skill_compiled",
                {
                    "skill": skill_to_dict(row),
                    "process_id": manifest.metadata.get("process_entity_id"),
                },
            )
    return cast(list[SkillManifest | Skill], compiled)
