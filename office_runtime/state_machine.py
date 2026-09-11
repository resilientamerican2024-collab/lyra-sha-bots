from __future__ import annotations

from typing import Dict, Set

from .models import Assignment, AssignmentState, VerificationState, utc_now


_ALLOWED: Dict[AssignmentState, Set[AssignmentState]] = {
    AssignmentState.CREATED: {AssignmentState.DISPATCHED, AssignmentState.CANCELLED},
    AssignmentState.DISPATCHED: {AssignmentState.ACKNOWLEDGED, AssignmentState.BLOCKED, AssignmentState.CANCELLED},
    AssignmentState.ACKNOWLEDGED: {AssignmentState.EXECUTING, AssignmentState.BLOCKED, AssignmentState.CANCELLED},
    AssignmentState.EXECUTING: {AssignmentState.BLOCKED, AssignmentState.READY_FOR_VERIFICATION, AssignmentState.COMPLETED},
    AssignmentState.BLOCKED: {AssignmentState.DISPATCHED, AssignmentState.ACKNOWLEDGED, AssignmentState.EXECUTING, AssignmentState.CANCELLED},
    AssignmentState.READY_FOR_VERIFICATION: {AssignmentState.VERIFIED, AssignmentState.REJECTED},
    AssignmentState.REJECTED: {AssignmentState.EXECUTING, AssignmentState.BLOCKED, AssignmentState.CANCELLED},
    AssignmentState.VERIFIED: {AssignmentState.COMPLETED},
    AssignmentState.COMPLETED: set(),
    AssignmentState.CANCELLED: set(),
}


class InvalidTransition(ValueError):
    pass


def transition(assignment: Assignment, target: AssignmentState, *, reason: str | None = None) -> Assignment:
    if target not in _ALLOWED[assignment.state]:
        raise InvalidTransition(f"{assignment.state.value} -> {target.value} is not allowed")

    now = utc_now()
    assignment.state = target

    if target == AssignmentState.DISPATCHED:
        assignment.dispatched_at = now
    elif target == AssignmentState.ACKNOWLEDGED:
        assignment.acknowledged_at = now
    elif target == AssignmentState.EXECUTING:
        assignment.execution_started_at = now
        assignment.blocker_reason = None
    elif target == AssignmentState.BLOCKED:
        assignment.blocked_at = now
        assignment.blocker_reason = reason or "unspecified blocker"
    elif target == AssignmentState.READY_FOR_VERIFICATION:
        assignment.ready_for_verification_at = now
        assignment.verification_state = VerificationState.PENDING
    elif target == AssignmentState.VERIFIED:
        assignment.verification_state = VerificationState.ACCEPTED
    elif target == AssignmentState.REJECTED:
        assignment.verification_state = VerificationState.REJECTED
        assignment.blocker_reason = reason or "verification rejected"
    elif target == AssignmentState.COMPLETED:
        assignment.completed_at = now

    return assignment


def can_advance_without_founder(assignment: Assignment) -> bool:
    return assignment.founder_gate is None


def requires_verification(assignment: Assignment) -> bool:
    return assignment.verification_route is not None
