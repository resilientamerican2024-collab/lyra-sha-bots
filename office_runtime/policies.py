from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from .models import Assignment, AssignmentState, FounderGate, PrivilegeTier, WorkerBinding


FOUNDER_GATE_TYPES = {
    "spending",
    "publication_release",
    "contract_signature",
    "banking_tax_identity",
    "destructive_irreversible",
    "founder_required_auth",
    "constitutional_governance",
}


def detect_founder_gate(*, requested_capabilities: Iterable[str],
                        privilege_tier_required: PrivilegeTier) -> FounderGate | None:
    requested = {cap.strip().lower() for cap in requested_capabilities}
    matched = sorted(requested.intersection(FOUNDER_GATE_TYPES))
    if privilege_tier_required >= PrivilegeTier.FOUNDER_GATE or matched:
        gate_type = matched[0] if matched else "founder_authority"
        return FounderGate(
            gate_type=gate_type,
            reason="Requested action crosses a reserved Founder boundary.",
            required_action="Founder must explicitly authorize this reserved action.",
        )
    return None


def heartbeat_is_stale(worker: WorkerBinding, *, now: datetime | None = None,
                       stale_after_seconds: int = 900) -> bool:
    if worker.last_heartbeat_at is None:
        return True
    current = now or datetime.now(timezone.utc)
    last = datetime.fromisoformat(worker.last_heartbeat_at)
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return (current - last).total_seconds() > stale_after_seconds


def assignment_needs_recovery(assignment: Assignment, worker: WorkerBinding,
                              *, now: datetime | None = None,
                              stale_after_seconds: int = 900) -> bool:
    if assignment.state not in {
        AssignmentState.DISPATCHED,
        AssignmentState.ACKNOWLEDGED,
        AssignmentState.EXECUTING,
        AssignmentState.BLOCKED,
    }:
        return False
    return heartbeat_is_stale(worker, now=now, stale_after_seconds=stale_after_seconds)
