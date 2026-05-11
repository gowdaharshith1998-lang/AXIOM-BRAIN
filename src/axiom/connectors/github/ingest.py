from __future__ import annotations

from typing import Any

import requests  # type: ignore[import-untyped]

API = "https://api.github.com"


def fetch_initial_repos(state: Any) -> list[dict[str, Any]]:
    return _get_paginated("/user/repos", state.access_token)


def fetch_issues(state: Any, repo: str) -> list[dict[str, Any]]:
    return _get_paginated(f"/repos/{repo}/issues", state.access_token)


def fetch_pull_requests(state: Any, repo: str) -> list[dict[str, Any]]:
    return _get_paginated(f"/repos/{repo}/pulls", state.access_token)


def normalize_repo(repo: dict[str, Any]) -> dict[str, Any]:
    repo_id = str(repo["id"])
    return {
        "nick": f"repo:{repo_id}",
        "type": "repo",
        "source_id": f"github:repo:{repo_id}",
        "cluster_id": "engineering_code",
        "data": {"vendor": "github", **repo},
    }


def normalize_issue(repo_name: str, issue: dict[str, Any]) -> dict[str, Any]:
    issue_id = str(issue["id"])
    return {
        "nick": f"issue:{issue_id}",
        "type": "ticket",
        "source_id": f"github:issue:{issue_id}",
        "cluster_id": "engineering_code",
        "data": {"vendor": "github", "repo": repo_name, **issue},
    }


def normalize_pull_request(repo_name: str, pull_request: dict[str, Any]) -> dict[str, Any]:
    pr_id = str(pull_request["id"])
    return {
        "nick": f"pr:{pr_id}",
        "type": "pull_request",
        "source_id": f"github:pr:{pr_id}",
        "cluster_id": "engineering_code",
        "data": {"vendor": "github", "repo": repo_name, **pull_request},
    }


def repo_to_issue_edge(repo_nick: str, issue_nick: str) -> dict[str, Any]:
    return {
        "source_nick": repo_nick,
        "target_nick": issue_nick,
        "relationship": "repo_has_issue",
        "data": {},
    }


def repo_to_pr_edge(repo_nick: str, pr_nick: str) -> dict[str, Any]:
    return {
        "source_nick": repo_nick,
        "target_nick": pr_nick,
        "relationship": "repo_has_pull_request",
        "data": {},
    }


def _get_paginated(path: str, token: str) -> list[dict[str, Any]]:
    url: str | None = f"{API}{path}"
    rows: list[dict[str, Any]] = []
    while url:
        response = requests.get(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=15,
        )
        response.raise_for_status()
        rows.extend(response.json())
        url = _next_link(response.headers.get("Link", ""))
    return rows


def _next_link(link_header: str) -> str | None:
    for part in link_header.split(","):
        section = part.strip()
        if 'rel="next"' not in section:
            continue
        start = section.find("<")
        end = section.find(">")
        if start >= 0 and end > start:
            return section[start + 1 : end]
    return None
