"""Fail-closed capability policy for orchestrator tool calls."""

from __future__ import annotations

from dataclasses import dataclass


class PolicyDenied(RuntimeError):
    pass


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    capability: str
    reason: str


class PolicyEngine:
    LEVELS = {"read": 0, "disposable_write": 1, "real_write": 2, "remote_deploy": 3}

    def authorize(
        self,
        *,
        capability: str,
        project_id: str | None = None,
        project_fingerprint: str | None = None,
        target_confirmed: bool = False,
        disposable_project: bool = False,
        remote_authorized: bool = False,
    ) -> PolicyDecision:
        if capability not in self.LEVELS:
            raise PolicyDenied("unknown_capability")
        if capability == "read":
            return PolicyDecision(True, capability, "read_only")
        if not project_id or project_id == "current":
            raise PolicyDenied("project_required")
        if not project_fingerprint:
            raise PolicyDenied("project_fingerprint_required")
        if capability == "disposable_write":
            if not disposable_project:
                raise PolicyDenied("disposable_project_required")
            return PolicyDecision(True, capability, "disposable_project_confirmed")
        if capability == "real_write":
            if not target_confirmed:
                raise PolicyDenied("target_confirmation_required")
            return PolicyDecision(True, capability, "real_project_authorized")
        if capability == "remote_deploy":
            if not remote_authorized:
                raise PolicyDenied("remote_authorization_required")
            return PolicyDecision(True, capability, "remote_deployment_authorized")
        raise PolicyDenied("policy_denied")
