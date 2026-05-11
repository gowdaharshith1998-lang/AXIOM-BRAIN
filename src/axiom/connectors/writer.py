from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from axiom.govern.policy_evaluator import get_policy_evaluator
from axiom.govern.receipts import ReceiptInsert, chain_insert_receipt
from axiom.policy import ActionRequest
from axiom.schema.models import new_id


class ConnectorWriteBlocked(RuntimeError):  # noqa: N818 - spec names this exception.
    pass


class ConnectorWriter(ABC):
    def __init__(
        self,
        *,
        vendor: str,
        session_factory: sessionmaker[Session] | None = None,
        policy_evaluator: Any | None = None,
    ) -> None:
        self.vendor = vendor
        self.session_factory = session_factory
        self.policy_evaluator: Any = policy_evaluator or get_policy_evaluator(session_factory)

    def propose_action(self, intent: str, payload: dict[str, Any]) -> ActionRequest:
        merged_payload = {"vendor": self.vendor, **payload}
        return ActionRequest(
            agent_name=f"connector:{self.vendor}",
            intent=intent,
            target_entity_id=payload.get("target_entity_id"),
            proposed_action=f"{self.vendor}.{intent}",
            idempotency_key=payload.get("idempotency_key"),
            payload=merged_payload,
        )

    def execute(
        self,
        action: ActionRequest,
        decision: Any | None = None,
        *,
        passport: Any = None,
    ) -> Any:
        policy_decision = decision or self.policy_evaluator.evaluate(action, passport, None)
        mode = getattr(policy_decision, "mode", getattr(policy_decision, "decision", "deny"))
        if mode != "allow" and getattr(policy_decision, "approval_id", None) is None:
            self._chain_receipt(action, policy_decision, str(mode))
            raise ConnectorWriteBlocked(
                f"connector write blocked by policy_id={policy_decision.policy_id}: "
                f"{policy_decision.reason}"
            )
        result = self._perform_execute(action, policy_decision)
        self._chain_receipt(action, policy_decision, "allow")
        return result

    @abstractmethod
    def _perform_execute(self, action: ActionRequest, decision: Any) -> Any: ...

    def _chain_receipt(self, action: ActionRequest, decision: Any, receipt_decision: str) -> None:
        if self.session_factory is None:
            return
        chain_insert_receipt(
            self.session_factory,
            ReceiptInsert(
                id=f"connector_receipt_{new_id()}",
                action_id=action.idempotency_key or f"connector:{new_id()}",
                agent_name=action.agent_name,
                intent=action.intent,
                target_entity_id=action.target_entity_id,
                cluster_id=None,
                decision=receipt_decision,
                reason=str(getattr(decision, "reason", "")),
                policy_id=str(getattr(decision, "policy_id", "")),
                guidance=getattr(decision, "guidance", None),
                suggested_alternative=str(getattr(decision, "suggested_alternative", None))
                if getattr(decision, "suggested_alternative", None) is not None
                else None,
                signing_scheme="ed25519",
                signature="",
                passport_id=getattr(action, "passport_id", None),
                demo_flag=False,
            ),
        )
