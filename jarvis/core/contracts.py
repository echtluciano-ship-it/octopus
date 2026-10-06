from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class JarvisError(RuntimeError):
    """Base error for controlled JARVIS failures."""


class PolicyDenied(JarvisError):
    """Raised when an agent requests a capability it does not own."""


class NeedsReview(JarvisError):
    """Raised when a request cannot be resolved safely."""


@dataclass(frozen=True)
class PlannedAction:
    intent: str
    tool: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    tool: str
    data: dict[str, Any]
    evidence: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AuditDecision:
    approved: bool
    checks: list[str]
    problems: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class JarvisResponse:
    run_id: str
    status: str
    answer: str
    evidence: list[str]
    audit: AuditDecision
