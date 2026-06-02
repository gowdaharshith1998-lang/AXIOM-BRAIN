"""SkillFile executor + CLI.

Executes a parsed SkillFile deterministically against the AXIOM storage and
governance primitives. There are no LLM calls: every step succeeds, pauses
(``require_approval``), or fails with a named ``SkillFileExecutionError``.

CLI::

    python -m axiom.skills.skill_file_runner run <path.skill.yaml> \\
        --trigger '<json>' --database-url <sqlalchemy-url>
"""

from __future__ import annotations

import argparse
import json
import string
import sys
import uuid
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from axiom.skills.skill_file import (
    SkillFile,
    SkillFileRun,
    Step,
    StepFetchEntity,
    StepIfThen,
    StepLogDecision,
    StepRequireApproval,
    StepResult,
    StepWriteEntity,
)


class SkillFileExecutionError(RuntimeError):
    """A SkillFile step failed during execution. Carries step id + reason."""

    def __init__(self, step_id: str, reason: str) -> None:
        super().__init__(f"step {step_id!r}: {reason}")
        self.step_id = step_id
        self.reason = reason


# ── Variable substitution: {a.b.c} ────────────────────────────────────────


class _DottedFormatter(string.Formatter):
    """Resolves ``{a.b.c}`` against a context dict via item/attr lookup.

    Unresolved paths render as ``<missing:a.b.c>`` rather than raising — a
    template typo degrades visibly instead of aborting the run.
    """

    def get_field(self, field_name: str, args: Any, kwargs: Any) -> tuple[Any, str]:
        parts = field_name.split(".")
        value: Any = kwargs.get(parts[0])
        for part in parts[1:]:
            if value is None:
                return (f"<missing:{field_name}>", field_name)
            if isinstance(value, dict):
                value = value.get(part)
            else:
                value = getattr(value, part, None)
        if value is None:
            return (f"<missing:{field_name}>", field_name)
        return (value, field_name)


_FORMATTER = _DottedFormatter()


def _resolve_string(template: str, context: dict[str, Any]) -> str:
    return _FORMATTER.vformat(template, (), context)


def _resolve_data(value: Any, context: dict[str, Any]) -> Any:
    """Recursively substitute ``{var}`` in strings nested in dicts/lists."""
    if isinstance(value, str):
        return _resolve_string(value, context)
    if isinstance(value, dict):
        return {key: _resolve_data(val, context) for key, val in value.items()}
    if isinstance(value, list):
        return [_resolve_data(item, context) for item in value]
    return value


# ── DSL condition evaluation ──────────────────────────────────────────────


class _SkillEvalContext:
    """Adapter exposing the SkillFile run context to the policy DSL evaluator.

    ``axiom.policy.dsl._resolve_path`` resolves any path root it does not
    special-case via ``getattr(context, root_name)``, so binding each run
    variable (``trigger`` and any fetched entities) as an attribute lets a
    condition reference ``trigger.payload.amount`` with no DSL modification.
    """

    def __init__(self, context: dict[str, Any]) -> None:
        # Defaults so the DSL never AttributeErrors on its special-cased roots.
        self.action = None
        self.passport = None
        self.entity = None
        self.session = None
        for key, value in context.items():
            setattr(self, key, value)


# ── Runner ────────────────────────────────────────────────────────────────


class SkillFileRunner:
    """Executes a parsed SkillFile.

    ``session_factory`` must be a ``sessionmaker`` bound to an Engine: the
    governance primitives ``chain_insert_receipt`` and ``create_approval_request``
    both require one.
    """

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def run(self, skill_file: SkillFile, trigger: dict[str, Any]) -> SkillFileRun:
        """Execute every top-level step in order. Stops at the first paused or
        failed step. Returns a ``SkillFileRun`` — never raises to the caller."""
        run_id = uuid.uuid4().hex
        context: dict[str, Any] = {"trigger": trigger}
        step_results: list[StepResult] = []

        for step in skill_file.steps:
            result = self._exec_step(step, context, trigger, run_id)
            step_results.append(result)
            if result.status == "paused":
                return SkillFileRun(
                    skill_file_name=skill_file.name,
                    status="paused",
                    step_results=step_results,
                    approval_id=result.detail.get("approval_id"),
                )
            if result.status == "failed":
                return SkillFileRun(
                    skill_file_name=skill_file.name,
                    status="failed",
                    step_results=step_results,
                    error=result.detail.get("error"),
                )

        final_receipt_id = next(
            (r.detail["receipt_id"] for r in reversed(step_results) if r.detail.get("receipt_id")),
            None,
        )
        return SkillFileRun(
            skill_file_name=skill_file.name,
            status="success",
            step_results=step_results,
            final_receipt_id=final_receipt_id,
        )

    def _exec_step(
        self,
        step: Step,
        context: dict[str, Any],
        trigger: dict[str, Any],
        run_id: str,
    ) -> StepResult:
        try:
            if isinstance(step, StepIfThen):
                return self._exec_if_then(step, context, trigger, run_id)
            if isinstance(step, StepFetchEntity):
                return self._exec_fetch_entity(step, context, run_id)
            if isinstance(step, StepWriteEntity):
                return self._exec_write_entity(step, context, run_id)
            if isinstance(step, StepRequireApproval):
                return self._exec_require_approval(step)
            if isinstance(step, StepLogDecision):
                return self._exec_log_decision(step, context, run_id)
        except SkillFileExecutionError as exc:
            return StepResult(
                step_id=step.id,
                step_type=step.type,
                status="failed",
                detail={"error": str(exc)},
            )
        # Unreachable — the parser only emits the 5 known step types.
        return StepResult(
            step_id=getattr(step, "id", "?"),
            step_type=getattr(step, "type", "unknown"),
            status="failed",
            detail={"error": f"unknown step type at runtime: {type(step).__name__}"},
        )

    def _exec_if_then(
        self,
        step: StepIfThen,
        context: dict[str, Any],
        trigger: dict[str, Any],
        run_id: str,
    ) -> StepResult:
        from axiom.policy.dsl import parse_predicate

        expr = parse_predicate(step.condition)
        eval_ctx = _SkillEvalContext(context)
        try:
            matched = bool(expr.evaluate(eval_ctx))
        except Exception as exc:  # noqa: BLE001 — any eval failure is a step failure
            raise SkillFileExecutionError(step.id, f"condition eval failed: {exc}") from exc

        if not matched:
            return StepResult(
                step_id=step.id,
                step_type="if_then",
                status="skipped",
                detail={"matched": False},
            )

        for nested in step.then:
            nested_result = self._exec_step(nested, context, trigger, run_id)
            if nested_result.status == "paused":
                return StepResult(
                    step_id=step.id,
                    step_type="if_then",
                    status="paused",
                    detail={
                        "matched": True,
                        "approval_id": nested_result.detail.get("approval_id"),
                    },
                )
            if nested_result.status == "failed":
                return StepResult(
                    step_id=step.id,
                    step_type="if_then",
                    status="failed",
                    detail={"matched": True, "error": nested_result.detail.get("error")},
                )
        return StepResult(
            step_id=step.id,
            step_type="if_then",
            status="executed",
            detail={"matched": True},
        )

    def _exec_fetch_entity(
        self, step: StepFetchEntity, context: dict[str, Any], run_id: str
    ) -> StepResult:
        from axiom.storage.crud import get_entity

        resolved = _resolve_string(step.query, context)
        if ":" not in resolved:
            raise SkillFileExecutionError(step.id, f"query must be '<type>:<id>', got {resolved!r}")
        entity_type, _, entity_id = resolved.partition(":")
        if not entity_id:
            raise SkillFileExecutionError(step.id, f"query has an empty entity id: {resolved!r}")

        with self.session_factory() as session:
            dto = get_entity(session, entity_id)
        if dto is None:
            raise SkillFileExecutionError(step.id, f"entity not found: {entity_id}")

        # Flatten data to the top level so {bind_to.field} substitution and DSL
        # paths resolve directly (e.g. {customer.name}).
        bound = {
            "id": dto.id,
            "type": dto.type,
            "name": (dto.data or {}).get("name", ""),
            **(dto.data or {}),
        }
        context[step.bind_to] = bound
        receipt_id = self._write_meta_receipt(
            run_id, step.id, "skill_file", f"fetched {entity_type}:{entity_id}"
        )
        return StepResult(
            step_id=step.id,
            step_type="fetch_entity",
            status="executed",
            detail={
                "bound_id": entity_id,
                "bind_to": step.bind_to,
                "receipt_id": receipt_id,
            },
        )

    def _exec_write_entity(
        self, step: StepWriteEntity, context: dict[str, Any], run_id: str
    ) -> StepResult:
        from axiom.storage.crud import create_entity

        resolved_data = _resolve_data(step.data, context)
        with self.session_factory() as session:
            dto = create_entity(
                session,
                type_=step.entity_type,
                data=resolved_data,
                cluster_id=step.cluster,
            )
        receipt_id = self._write_meta_receipt(
            run_id, step.id, step.cluster, f"wrote {step.entity_type}:{dto.id}"
        )
        return StepResult(
            step_id=step.id,
            step_type="write_entity",
            status="executed",
            detail={"entity_id": dto.id, "receipt_id": receipt_id},
        )

    def _exec_require_approval(self, step: StepRequireApproval) -> StepResult:
        # RESUME LOGIC: not implemented in initial build, follow-up.
        # require_approval halts the run and returns an approval_id; a future
        # build will resume execution once the approval is resolved.
        from axiom.govern.approvals import create_approval_request
        from axiom.policy.evaluator import ActionRequest, PolicyDecision

        action = ActionRequest(
            agent_name="skill_file_runner",
            intent="skill_file_step",
            target_entity_id=None,
            proposed_action=f"skill_file step {step.id}",
            idempotency_key=f"skill_file:approval:{uuid.uuid4().hex}",
            payload={},
        )
        decision = PolicyDecision(
            mode="pause",
            reason=f"step {step.id} requires approval from {step.role}",
            policy_id=f"skill_file.step.{step.id}",
            approval_required_role=step.role,
            approval_timeout_seconds=step.timeout_seconds,
        )
        try:
            approval = create_approval_request(self.session_factory, action, None, decision)
        except Exception as exc:  # noqa: BLE001
            raise SkillFileExecutionError(step.id, f"approval request failed: {exc}") from exc
        return StepResult(
            step_id=step.id,
            step_type="require_approval",
            status="paused",
            detail={"approval_id": approval.id, "role": step.role},
        )

    def _exec_log_decision(
        self, step: StepLogDecision, context: dict[str, Any], run_id: str
    ) -> StepResult:
        resolved_note = _resolve_string(step.note, context)
        receipt_id = self._write_meta_receipt(run_id, step.id, step.cluster, resolved_note)
        return StepResult(
            step_id=step.id,
            step_type="log_decision",
            status="executed",
            detail={"resolved_note": resolved_note, "receipt_id": receipt_id},
        )

    def _write_meta_receipt(self, run_id: str, step_id: str, cluster: str, reason: str) -> str:
        """Chain a meta-receipt for an executed step. A receipt failure fails
        the step (the audit trail is correctness, not optional observability)."""
        from axiom.govern.receipts import ReceiptInsert, chain_insert_receipt
        from axiom.schema.models import new_id

        payload = ReceiptInsert(
            id=new_id(),
            action_id=f"skill_file:{run_id}:{step_id}",
            agent_name="skill_file_runner",
            intent="skill_file_step",
            target_entity_id=None,
            cluster_id=cluster,
            decision="allow",
            reason=reason,
            policy_id=f"skill_file.step.{step_id}",
            guidance=None,
            suggested_alternative=None,
            signing_scheme="ed25519",
            signature="",
        )
        try:
            receipt, _created = chain_insert_receipt(self.session_factory, payload)
        except Exception as exc:  # noqa: BLE001
            raise SkillFileExecutionError(step_id, f"receipt chaining failed: {exc}") from exc
        return receipt.id


# ── Serialisation (shared by CLI + REST API) ──────────────────────────────


def run_to_dict(result: SkillFileRun) -> dict[str, Any]:
    """JSON-serialisable view of a SkillFileRun."""
    return {
        "skill_file_name": result.skill_file_name,
        "status": result.status,
        "approval_id": result.approval_id,
        "steps_executed": sum(1 for r in result.step_results if r.status == "executed"),
        "step_results": [
            {
                "step_id": r.step_id,
                "step_type": r.step_type,
                "status": r.status,
                "detail": r.detail,
            }
            for r in result.step_results
        ],
        "final_receipt_id": result.final_receipt_id,
        "error": result.error,
    }


# ── CLI ───────────────────────────────────────────────────────────────────


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="axiom.skills.skill_file_runner")
    sub = parser.add_subparsers(dest="command", required=True)
    run_p = sub.add_parser("run", help="parse and execute a SkillFile")
    run_p.add_argument("path", help="path to the .skill.yaml file")
    run_p.add_argument("--trigger", required=True, help="JSON trigger payload")
    run_p.add_argument("--database-url", required=True, help="SQLAlchemy database URL")
    args = parser.parse_args(argv)

    from axiom.schema.models import Base
    from axiom.skills.skill_file_parser import (
        SkillFileParseError,
        parse_skill_file_yaml,
    )
    from axiom.storage.db import init_engine

    try:
        with open(args.path, encoding="utf-8") as handle:
            yaml_text = handle.read()
    except OSError as exc:
        print(json.dumps({"status": "failed", "error": f"cannot read {args.path}: {exc}"}))
        return 1

    try:
        skill_file = parse_skill_file_yaml(yaml_text)
    except SkillFileParseError as exc:
        print(json.dumps({"status": "failed", "error": f"parse error: {exc}"}))
        return 1

    try:
        trigger = json.loads(args.trigger)
    except json.JSONDecodeError as exc:
        print(json.dumps({"status": "failed", "error": f"invalid --trigger JSON: {exc}"}))
        return 1

    # Route the standalone-CLI engine through the single-source engine factory
    # (P1-11) rather than building a rogue engine. This is the CLI entry point
    # only; the test/serving path builds schema via create_app()/ensure_* helpers.
    engine = init_engine(args.database_url)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, future=True)

    runner = SkillFileRunner(session_factory=session_factory)
    result = runner.run(skill_file, trigger=trigger)
    print(json.dumps(run_to_dict(result), indent=2))
    return 0 if result.status in ("success", "paused") else 1


if __name__ == "__main__":
    sys.exit(_main())
