from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid


class PrivilegeTier(int, Enum):
    IDENTITY = 0
    INTERNAL_WORK = 1
    INTERNAL_EXECUTION = 2
    PROTECTED_CAPABILITY = 3
    FOUNDER_GATE = 4


class AssignmentState(str, Enum):
    CREATED = "created"
    DISPATCHED = "dispatched"
    ACKNOWLEDGED = "acknowledged"
    EXECUTING = "executing"
    BLOCKED = "blocked"
    READY_FOR_VERIFICATION = "ready_for_verification"
    VERIFIED = "verified"
    REJECTED = "rejected"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class VerificationState(str, Enum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


@dataclass(frozen=True)
class FounderGate:
    gate_type: str
    reason: str
    required_action: str


@dataclass
class OfficeIdentity:
    office_id: str
    office_name: str
    council_member: str
    mission: str
    privilege_tier: PrivilegeTier
    allowed_capabilities: List[str] = field(default_factory=list)
    prohibited_capabilities: List[str] = field(default_factory=list)
    verifier_office: Optional[str] = None


@dataclass
class WorkerBinding:
    worker_id: str
    office_id: str
    runtime: str
    status: str = "unknown"
    last_heartbeat_at: Optional[str] = None
    current_assignment_id: Optional[str] = None


@dataclass
class EvidenceReceipt:
    receipt_id: str
    assignment_id: str
    producer_worker_id: str
    created_at: str
    evidence_type: str
    location: str
    digest: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Assignment:
    assignment_id: str
    originating_office: str
    receiving_office: str
    mission: str
    requested_outcome: str
    evidence_required: List[str]
    verification_route: Optional[str]
    dependencies: List[str] = field(default_factory=list)
    privilege_tier_required: PrivilegeTier = PrivilegeTier.INTERNAL_WORK
    state: AssignmentState = AssignmentState.CREATED
    created_at: str = field(default_factory=utc_now)
    dispatched_at: Optional[str] = None
    acknowledged_at: Optional[str] = None
    execution_started_at: Optional[str] = None
    blocked_at: Optional[str] = None
    ready_for_verification_at: Optional[str] = None
    completed_at: Optional[str] = None
    assigned_worker_id: Optional[str] = None
    blocker_reason: Optional[str] = None
    founder_gate: Optional[FounderGate] = None
    verification_state: VerificationState = VerificationState.PENDING
    evidence_receipt_ids: List[str] = field(default_factory=list)
    next_dependency: Optional[str] = None
    dependency_advanced_at: Optional[str] = None


@dataclass
class Handoff:
    handoff_id: str
    from_office: str
    to_office: str
    assignment_id: str
    purpose: str
    evidence_receipt_ids: List[str]
    created_at: str = field(default_factory=utc_now)
    acknowledged_at: Optional[str] = None


@dataclass
class RuntimeEvent:
    event_id: str
    event_type: str
    office_id: str
    assignment_id: Optional[str]
    worker_id: Optional[str]
    created_at: str
    payload: Dict[str, Any] = field(default_factory=dict)
