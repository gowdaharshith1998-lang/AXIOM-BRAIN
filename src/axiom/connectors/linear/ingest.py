from __future__ import annotations

from typing import Any, cast

import requests  # type: ignore[import-untyped]

API = "https://api.linear.app/graphql"


def fetch_teams(state: Any) -> list[dict[str, Any]]:
    payload = _graphql(
        state.access_token,
        """
        query AxiomLinearTeamsAndIssues {
          teams { nodes { id name key } }
          issues { nodes { id title identifier team { id name } project { id name } } }
        }
        """,
    )
    return list(payload.get("data", {}).get("teams", {}).get("nodes", []))


def fetch_issues_for_team(state: Any, team_id: str) -> list[dict[str, Any]]:
    payload = _graphql(
        state.access_token,
        """
        query AxiomLinearIssues($teamId: String!) {
          issues(filter: { team: { id: { eq: $teamId } } }) {
            nodes { id title identifier team { id name } project { id name } state { id name } }
          }
        }
        """,
        {"teamId": team_id},
    )
    return list(payload.get("data", {}).get("issues", {}).get("nodes", []))


def fetch_projects(state: Any) -> list[dict[str, Any]]:
    payload = _graphql(
        state.access_token,
        """
        query AxiomLinearProjects {
          projects { nodes { id name state targetDate } }
        }
        """,
    )
    return list(payload.get("data", {}).get("projects", {}).get("nodes", []))


def normalize_team(team: dict[str, Any]) -> dict[str, Any]:
    team_id = str(team["id"])
    return {
        "nick": f"team:{team_id}",
        "type": "team",
        "source_id": f"linear:team:{team_id}",
        "cluster_id": "engineering_code",
        "data": {"vendor": "linear", **team},
    }


def normalize_issue(issue: dict[str, Any]) -> dict[str, Any]:
    issue_id = str(issue["id"])
    return {
        "nick": f"issue:{issue_id}",
        "type": "ticket",
        "source_id": f"linear:issue:{issue_id}",
        "cluster_id": "engineering_code",
        "data": {"vendor": "linear", **issue},
    }


def normalize_project(project: dict[str, Any]) -> dict[str, Any]:
    project_id = str(project["id"])
    return {
        "nick": f"project:{project_id}",
        "type": "project",
        "source_id": f"linear:project:{project_id}",
        "cluster_id": "engineering_code",
        "data": {"vendor": "linear", **project},
    }


def normalize_cycle(cycle: dict[str, Any]) -> dict[str, Any]:
    cycle_id = str(cycle["id"])
    return {
        "nick": f"cycle:{cycle_id}",
        "type": "cycle",
        "source_id": f"linear:cycle:{cycle_id}",
        "cluster_id": "engineering_code",
        "data": {"vendor": "linear", **cycle},
    }


def team_to_issue_edge(team_nick: str, issue_nick: str) -> dict[str, Any]:
    return {
        "source_nick": team_nick,
        "target_nick": issue_nick,
        "relationship": "team_has_issue",
        "data": {},
    }


def project_to_issue_edge(project_nick: str, issue_nick: str) -> dict[str, Any]:
    return {
        "source_nick": project_nick,
        "target_nick": issue_nick,
        "relationship": "project_has_issue",
        "data": {},
    }


def _graphql(
    token: str,
    query: str,
    variables: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = requests.post(
        API,
        json={"query": query, "variables": variables or {}},
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        timeout=15,
    )
    response.raise_for_status()
    return cast(dict[str, Any], response.json())
