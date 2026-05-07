"""Canonical semantic clusters for Phase 5.7 self-organizing brain.

Seven cluster regions span the operating surface of a software company.
The brain renders one lobe per cluster so a founder can read the company's
shape at overview zoom.
"""

from __future__ import annotations

from typing import TypedDict


class ClusterSpec(TypedDict):
    label: str
    color: str
    keywords: tuple[str, ...]


SEMANTIC_CLUSTERS: dict[str, ClusterSpec] = {
    "billing_payments": {
        "label": "Billing & Payments",
        "color": "#FF79C6",
        "keywords": (
            "invoice",
            "payment",
            "refund",
            "stripe",
            "billing",
            "subscription",
            "charge",
            "checkout",
        ),
    },
    "incidents_ops": {
        "label": "Incidents & Ops",
        "color": "#FF5555",
        "keywords": (
            "incident",
            "outage",
            "alert",
            "p1",
            "p0",
            "runbook",
            "postmortem",
            "oncall",
        ),
    },
    "engineering_code": {
        "label": "Engineering & Code",
        "color": "#7CFC9F",
        "keywords": (
            "code",
            "pr",
            "merge",
            "deploy",
            "test",
            "bug",
            "feature",
            "commit",
            "branch",
        ),
    },
    "people_teams": {
        "label": "People & Teams",
        "color": "#F1FA8C",
        "keywords": (
            "hire",
            "onboard",
            "team",
            "performance",
            "1:1",
            "review",
            "growth_plan",
        ),
    },
    "decisions_policy": {
        "label": "Decisions & Policy",
        "color": "#BD93F9",
        "keywords": (
            "decision",
            "policy",
            "approved",
            "rfc",
            "proposal",
            "spec",
            "design_doc",
        ),
    },
    "customer_support": {
        "label": "Customer Support",
        "color": "#8BE9FD",
        "keywords": (
            "customer",
            "ticket",
            "support",
            "complaint",
            "escalation",
            "feedback",
            "csat",
        ),
    },
    "growth_product": {
        "label": "Growth & Product",
        "color": "#50FA7B",
        "keywords": (
            "growth",
            "experiment",
            "metric",
            "analytics",
            "funnel",
            "retention",
            "acquisition",
            "roadmap",
        ),
    },
}


CLUSTER_IDS: tuple[str, ...] = tuple(SEMANTIC_CLUSTERS.keys())
DEFAULT_CLUSTER_ID: str = "decisions_policy"


def is_valid_cluster_id(cluster_id: str | None) -> bool:
    return isinstance(cluster_id, str) and cluster_id in SEMANTIC_CLUSTERS
