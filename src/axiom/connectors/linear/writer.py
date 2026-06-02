from __future__ import annotations

from typing import Any

import requests
from sqlalchemy.orm import Session, sessionmaker

from axiom.connectors.writer import ConnectorWriter
from axiom.policy import ActionRequest

API = "https://api.linear.app/graphql"


class LinearWriter(ConnectorWriter):
    def __init__(
        self,
        *,
        state: Any | None = None,
        session_factory: sessionmaker[Session] | None = None,
        policy_evaluator: Any | None = None,
    ) -> None:
        super().__init__(
            vendor="linear",
            session_factory=session_factory,
            policy_evaluator=policy_evaluator,
        )
        self.state = state

    def _perform_execute(self, action: ActionRequest, decision: Any) -> Any:
        del decision
        query, variables = _mutation_for_action(action)
        response = requests.post(
            API,
            json={"query": query, "variables": variables},
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {getattr(self.state, 'access_token', '')}",
                "Content-Type": "application/json",
            },
            timeout=15,
        )
        response.raise_for_status()
        return response.json()


def _mutation_for_action(action: ActionRequest) -> tuple[str, dict[str, Any]]:
    if action.intent == "comment":
        return (
            """
            mutation AxiomLinearComment($input: CommentCreateInput!) {
              commentCreate(input: $input) { success }
            }
            """,
            {
                "input": {
                    "issueId": action.payload["issue_id"],
                    "body": action.payload["body"],
                }
            },
        )
    if action.intent == "state_change":
        return (
            """
            mutation AxiomLinearStateChange($id: String!, $input: IssueUpdateInput!) {
              issueUpdate(id: $id, input: $input) { success }
            }
            """,
            {
                "id": action.payload["issue_id"],
                "input": {"stateId": action.payload["state_id"]},
            },
        )
    if action.intent == "assign":
        return (
            """
            mutation AxiomLinearAssign($id: String!, $input: IssueUpdateInput!) {
              issueUpdate(id: $id, input: $input) { success }
            }
            """,
            {
                "id": action.payload["issue_id"],
                "input": {"assigneeId": action.payload["assignee_id"]},
            },
        )
    if action.intent == "create_issue":
        return (
            """
            mutation AxiomLinearCreateIssue($input: IssueCreateInput!) {
              issueCreate(input: $input) { success issue { id identifier title } }
            }
            """,
            {"input": {key: value for key, value in action.payload.items() if key != "vendor"}},
        )
    raise ValueError(f"unsupported Linear intent: {action.intent}")
