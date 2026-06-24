"""Request-type registry + triage classifier (§6, DECISIONS #8).

Loads config/request_types.yaml and classifies an inbound event (Crowdin webhook
event name) or a free-text /loc request into a request type with a handler:

  auto  → run the deterministic RAG pipeline
  human → open a ticket and @-route it in Slack

New request types are added as DATA (a YAML row), never code. That is
requirement #1 ("flexible: supports an increasing number of use cases").
The catch-all `unknown` row routes anything unrecognised to a human
(requirement #2: "knows when to loop in a member").
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import yaml

from app.config import CONFIG_DIR

REGISTRY_PATH = CONFIG_DIR / "request_types.yaml"


@dataclass
class RequestType:
    name: str
    handler: str            # auto | human
    sla_hours: int
    default_assignee: str
    description: str
    events: list[str]
    keywords: list[str]


@lru_cache
def load_registry() -> list[RequestType]:
    data = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    out = []
    for row in data.get("request_types", []):
        match = row.get("match", {}) or {}
        out.append(RequestType(
            name=row["name"],
            handler=row.get("handler", "human"),
            sla_hours=int(row.get("sla_hours", 24)),
            default_assignee=row.get("default_assignee", "@loc-lead"),
            description=row.get("description", ""),
            events=[e.lower() for e in (match.get("events") or [])],
            keywords=[k.lower() for k in (match.get("keywords") or [])],
        ))
    return out


def classify_event(event_name: str) -> RequestType:
    """Map a Crowdin webhook event name to a request type (first match wins)."""
    name = (event_name or "").lower()
    registry = load_registry()
    for rt in registry:
        if name in rt.events:
            return rt
    # Wildcard catch-all (events: ["*"]) → the last/unknown row.
    for rt in registry:
        if "*" in rt.events:
            return rt
    return registry[-1]


def classify_text(text: str) -> RequestType:
    """Map a free-text /loc request to a request type by keyword (first match)."""
    blob = (text or "").lower()
    registry = load_registry()
    for rt in registry:
        if any(kw != "*" and kw in blob for kw in rt.keywords):
            return rt
    for rt in registry:
        if "*" in rt.keywords:
            return rt
    return registry[-1]


def is_auto(rt: RequestType) -> bool:
    return rt.handler == "auto"
