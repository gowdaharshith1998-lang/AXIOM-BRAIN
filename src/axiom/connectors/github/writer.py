from __future__ import annotations

import re
from typing import Any

import requests
from sqlalchemy.orm import Session, sessionmaker

from axiom.connectors.writer import ConnectorWriter
from axiom.policy import ActionRequest

ISSUE_RE = re.compile(
    r"https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/(?:issues|pull)/(?P<number>\d+)"
)


class GitHubWriter(ConnectorWriter):
    def __init__(
        self,
        *,
        state: Any | None = None,
        session_factory: sessionmaker[Session] | None = None,
        policy_evaluator: Any | None = None,
    ) -> None:
        super().__init__(
            vendor="github",
            session_factory=session_factory,
            policy_evaluator=policy_evaluator,
        )
        self.state = state

    def _perform_execute(self, action: ActionRequest, decision: Any) -> Any:
        del decision
        token = str(getattr(self.state, "access_token", ""))
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if action.intent == "comment":
            owner, repo, number = _parse_issue_url(str(action.payload["issue_url"]))
            response = requests.post(
                f"https://api.github.com/repos/{owner}/{repo}/issues/{number}/comments",
                json={"body": action.payload["body"]},
                headers=headers,
                timeout=15,
            )
        elif action.intent == "label":
            owner, repo, number = _parse_issue_url(str(action.payload["issue_url"]))
            response = requests.post(
                f"https://api.github.com/repos/{owner}/{repo}/issues/{number}/labels",
                json={"labels": action.payload["labels"]},
                headers=headers,
                timeout=15,
            )
        elif action.intent == "close":
            owner, repo, number = _parse_issue_url(str(action.payload["issue_url"]))
            response = requests.patch(
                f"https://api.github.com/repos/{owner}/{repo}/issues/{number}",
                json={"state": "closed"},
                headers=headers,
                timeout=15,
            )
        elif action.intent == "merge":
            owner, repo, number = _parse_issue_url(str(action.payload["pr_url"]))
            response = requests.put(
                f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}/merge",
                json={"merge_method": action.payload.get("method", "merge")},
                headers=headers,
                timeout=15,
            )
        else:
            raise ValueError(f"unsupported GitHub intent: {action.intent}")
        response.raise_for_status()
        return response.json()


def _parse_issue_url(url: str) -> tuple[str, str, str]:
    match = ISSUE_RE.fullmatch(url)
    if match is None:
        raise ValueError(f"unsupported GitHub issue URL: {url}")
    return match.group("owner"), match.group("repo"), match.group("number")
