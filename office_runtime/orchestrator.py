from __future__ import annotations

from typing import Dict, List

from .ledger import RuntimeLedger
from .models import (
    Assignment,
    AssignmentState,
    EvidenceReceipt,
    FounderGate,
    Handoff,
    OfficeIdentity,
    PrivilegeTier,
    RuntimeEvent,
    VerificationState,
    WorkerBinding,
    new_id,
    utc_now,
)
from .policies import assignment_needs_recovery
from .state_machine import transition


class RuntimeViolation(ValueError):
    pass


class OfficeRuntime:
    """Small control plane for bounded internal Office work.

    This does not grant protected credentials or Founder authority. It only
    coordinates work at or below each Office's configured privilege tier and
    writes receipts to the append-only ledger.

    Completion doctrine enforced here:
      * No evidence = not done.
      * If independent verification is required, no accepted verification =
        not complete.
      * A worker's assertion that work is finished never changes an assignment
        directly to COMPLETED.
    """

    def __init__(self, ledger: RuntimeLedger):
        self.ledger = ledger
        self.offices: Dict[str, OfficeIdentity] = {}
        self.workers: Dict[str, WorkerBinding] = {}
        self.assignments: Dict[str, Assignment] = {}
        self.receipts: Dict[str, EvidenceReceipt] = {}
        self.handoffs: Dict[str, Handoff] = {}

    @classmethod
    def from_ledger(cls, ledger: RuntimeLedger) -> "OfficeRuntime":
        runtime = cls(ledger)
        runtime.restore_from_ledger()
        return runtime

    def restore_from_ledger(self) -> None:
        """Rebuild current runtime state from append-only ledger snapshots.

        The ledger is the durable source for v0. Replaying it must not create
        new records or silently advance work; it only reconstructs the latest
        known state of Offices, workers, assignments, evidence and handoffs.
        """
        self.offices.clear()
        self.workers.clear()
        self.assignments.clear()
        self.receipts.clear()
        self.handoffs.clear()

        for record in self.ledger.records():
            record_type = record.get("record_type")
            payload = record.get("payload", {})

            if record_type == "office":
                office = OfficeIdentity(
                    office_id=payload["office_id"],
                    office_name=payload["office_name"],
                    council_member=payload["council_member"],
                    mission=payload["mission"],
                    privilege_tier=PrivilegeTier(payload["privilege_tier"]),
                    allowed_capabilities=list(payload.get("allowed_capabilities", [])),
                    prohibited_capabilities=list(payload.get("prohibited_capabilities", [])),
                    verifier_office=payload.get("verifier_office"),
                )
                self.offices[office.office_id] = office

            elif record_type in {"worker_binding", "heartbeat"}:
                worker = WorkerBinding(
                    worker_id=payload["worker_id"],
                    office_id=payload["office_id"],
                    runtime=payload["runtime"],
                    status=payload.get("status", "unknown"),
                    last_heartbeat_at=payload.get("last_heartbeat_at"),
                    current_assignment_id=payload.get("current_assignment_id"),
                )
                self.workers[worker.worker_id] = worker

            elif record_type == "assignment":
                founder_gate_payload = payload.get("founder_gate")
                founder_gate = (
                    FounderGate(**founder_gate_payload)
                    if founder_gate_payload else None
                )
                assignment = Assignment(
                    assignment_id=payload["assignment_id"],
                    originating_office=payload["originating_office"],
                    receiving_office=payload["receiving_office"],
                    mission=payload["mission"],
                    requested_outcome=payload["requested_outcome"],
                    evidence_required=list(payload.get("evidence_required", [])),
                    verification_route=payload.get("verification_route"),
                    dependencies=list(payload.get("dependencies", [])),
                    privilege_tier_required=PrivilegeTier(
                        payload.get("privilege_tier_required", PrivilegeTier.INTERNAL_WORK.value)
                    ),
                    state=AssignmentState(payload.get("state", AssignmentState.CREATED.value)),
                    created_at=payload.get("created_at", utc_now()),
                    dispatched_at=payload.get("dispatched_at"),
                    acknowledged_at=payload.get("acknowledged_at"),
                    execution_started_at=payload.get("execution_started_at"),
                    blocked_at=payload.get("blocked_at"),
                    ready_for_verification_at=payload.get("ready_for_verification_at"),
                    completed_at=payload.get("completed_at"),
                    assigned_worker_id=payload.get("assigned_worker_id"),
                    blocker_reason=payload.get("blocker_reason"),
                    founder_gate=founder_gate,
                    verification_state=VerificationState(
                        payload.get("verification_state", VerificationState.PENDING.value)
                    ),
                    evidence_receipt_ids=list(payload.get("evidence_receipt_ids", [])),
                    next_dependency=payload.get("next_dependency"),
                    dependency_advanced_at=payload.get("dependency_advanced_at"),
                )
                self.assignments[assignment.assignment_id] = assignment

            elif record_type == "evidence":
                receipt = EvidenceReceipt(
                    receipt_id=payload["receipt_id"],
                    assignment_id=payload["assignment_id"],
                    producer_worker_id=payload["producer_worker_id"],
                    created_at=payload["created_at"],
                    evidence_type=payload["evidence_type"],
                    location=payload["location"],
                    digest=payload.get("digest"),
                    metadata=dict(payload.get("metadata", {})),
                )
                self.receipts[receipt.receipt_id] = receipt

            elif record_type == "handoff":
                handoff = Handoff(
                    handoff_id=payload["handoff_id"],
                    from_office=payload["from_office"],
                    to_office=payload["to_office"],
                    assignment_id=payload["assignment_id"],
                    purpose=payload["purpose"],
                    evidence_receipt_ids=list(payload.get("evidence_receipt_ids", [])),
                    created_at=payload.get("created_at", utc_now()),
                    acknowledged_at=payload.get("acknowledged_at"),
                )
                self.handoffs[handoff.handoff_id] = handoff

    def _event(self, event_type: str, office_id: str, *, assignment_id: str | None = None,
               worker_id: str | None = None, payload: dict | None = None) -> RuntimeEvent:
        event = RuntimeEvent(
            event_id=new_id("evt"),
            event_type=event_type,
            office_id=office_id,
            assignment_id=assignment_id,
            worker_id=worker_id,
            created_at=utc_now(),
            payload=payload or {},
        )
        self.ledger.append("event", event)
        return event

    def register_office(self, office: OfficeIdentity) -> None:
        self.offices[office.office_id] = office
        self.ledger.append("office", office)

    def bind_worker(self, worker: WorkerBinding) -> None:
        if worker.office_id not in self.offices:
            raise RuntimeViolation(f"unknown office: {worker.office_id}")
        self.workers[worker.worker_id] = worker
        self.ledger.append("worker_binding", worker)
        self._event("worker_bound", worker.office_id, worker_id=worker.worker_id)

    def heartbeat(self, worker_id: str) -> None:
        worker = self.workers[worker_id]
        worker.last_heartbeat_at = utc_now()
        worker.status = "available" if worker.current_assignment_id is None else "working"
        self.ledger.append("heartbeat", worker)

    def create_assignment(self, assignment: Assignment) -> None:
        if assignment.originating_office not in self.offices:
            raise RuntimeViolation(f"unknown originating office: {assignment.originating_office}")
        if assignment.receiving_office not in self.offices:
            raise RuntimeViolation(f"unknown receiving office: {assignment.receiving_office}")
        self.assignments[assignment.assignment_id] = assignment
        self.ledger.append("assignment", assignment)
        self._event("assignment_created", assignment.originating_office,
                    assignment_id=assignment.assignment_id)

    def dispatch(self, assignment_id: str, worker_id: str) -> Assignment:
        assignment = self.assignments[assignment_id]
        worker = self.workers[worker_id]
        office = self.offices[assignment.receiving_office]
        if assignment.founder_gate is not None:
            raise RuntimeViolation(
                f"Founder gate blocks dispatch: {assignment.founder_gate.gate_type}"
            )
        if worker.office_id != assignment.receiving_office:
            raise RuntimeViolation("worker is not bound to receiving Office")
        if assignment.privilege_tier_required > office.privilege_tier:
            raise RuntimeViolation("assignment exceeds Office privilege tier")
        if worker.current_assignment_id not in (None, assignment_id):
            raise RuntimeViolation("worker already has another assignment")
        assignment.assigned_worker_id = worker_id
        transition(assignment, AssignmentState.DISPATCHED)
        worker.current_assignment_id = assignment_id
        worker.status = "working"
        self.ledger.append("worker_binding", worker)
        self.ledger.append("assignment", assignment)
        self._event("assignment_dispatched", assignment.receiving_office,
                    assignment_id=assignment_id, worker_id=worker_id)
        return assignment

    def acknowledge(self, assignment_id: str, worker_id: str) -> Assignment:
        assignment = self.assignments[assignment_id]
        if assignment.assigned_worker_id != worker_id:
            raise RuntimeViolation("only assigned worker may ACK")
        transition(assignment, AssignmentState.ACKNOWLEDGED)
        self.ledger.append("assignment", assignment)
        self._event("assignment_acknowledged", assignment.receiving_office,
                    assignment_id=assignment_id, worker_id=worker_id)
        return assignment

    def start(self, assignment_id: str, worker_id: str) -> Assignment:
        assignment = self.assignments[assignment_id]
        if assignment.assigned_worker_id != worker_id:
            raise RuntimeViolation("only assigned worker may execute")
        transition(assignment, AssignmentState.EXECUTING)
        self.ledger.append("assignment", assignment)
        self._event("execution_started", assignment.receiving_office,
                    assignment_id=assignment_id, worker_id=worker_id)
        return assignment

    def submit_evidence(self, assignment_id: str, worker_id: str, *, evidence_type: str,
                        location: str, digest: str | None = None, metadata: dict | None = None) -> EvidenceReceipt:
        assignment = self.assignments[assignment_id]
        if assignment.assigned_worker_id != worker_id:
            raise RuntimeViolation("only assigned worker may submit evidence")
        if not evidence_type.strip():
            raise RuntimeViolation("evidence type is required")
        if not location.strip():
            raise RuntimeViolation("evidence location is required")
        receipt = EvidenceReceipt(
            receipt_id=new_id("rcpt"),
            assignment_id=assignment_id,
            producer_worker_id=worker_id,
            created_at=utc_now(),
            evidence_type=evidence_type,
            location=location,
            digest=digest,
            metadata=metadata or {},
        )
        self.receipts[receipt.receipt_id] = receipt
        assignment.evidence_receipt_ids.append(receipt.receipt_id)
        self.ledger.append("evidence", receipt)
        self.ledger.append("assignment", assignment)
        self._event("evidence_submitted", assignment.receiving_office,
                    assignment_id=assignment_id, worker_id=worker_id,
                    payload={"receipt_id": receipt.receipt_id, "evidence_type": evidence_type})
        return receipt

    def create_handoff(self, assignment_id: str, *, from_office: str, to_office: str,
                       purpose: str) -> Handoff:
        assignment = self.assignments[assignment_id]
        if from_office not in self.offices or to_office not in self.offices:
            raise RuntimeViolation("handoff references unknown Office")
        if from_office not in {assignment.originating_office, assignment.receiving_office,
                               assignment.verification_route}:
            raise RuntimeViolation("handoff sender is outside assignment route")
        handoff = Handoff(
            handoff_id=new_id("hnd"),
            from_office=from_office,
            to_office=to_office,
            assignment_id=assignment_id,
            purpose=purpose,
            evidence_receipt_ids=list(assignment.evidence_receipt_ids),
        )
        self.handoffs[handoff.handoff_id] = handoff
        self.ledger.append("handoff", handoff)
        self._event("handoff_created", from_office, assignment_id=assignment_id,
                    payload={"handoff_id": handoff.handoff_id, "to_office": to_office})
        return handoff

    def acknowledge_handoff(self, handoff_id: str, receiving_office: str) -> Handoff:
        handoff = self.handoffs[handoff_id]
        if handoff.to_office != receiving_office:
            raise RuntimeViolation("only receiving Office may ACK handoff")
        handoff.acknowledged_at = utc_now()
        self.ledger.append("handoff", handoff)
        self._event("handoff_acknowledged", receiving_office,
                    assignment_id=handoff.assignment_id,
                    payload={"handoff_id": handoff_id})
        return handoff

    def ready_for_verification(self, assignment_id: str, worker_id: str) -> Assignment:
        assignment = self.assignments[assignment_id]
        if assignment.assigned_worker_id != worker_id:
            raise RuntimeViolation("only assigned worker may request verification")
        if not assignment.evidence_receipt_ids:
            raise RuntimeViolation("no evidence receipts: assignment cannot be verified")
        submitted_types = {
            self.receipts[receipt_id].evidence_type
            for receipt_id in assignment.evidence_receipt_ids
            if receipt_id in self.receipts
        }
        missing = sorted(set(assignment.evidence_required) - submitted_types)
        if missing:
            raise RuntimeViolation(f"required evidence missing: {', '.join(missing)}")
        transition(assignment, AssignmentState.READY_FOR_VERIFICATION)
        self.ledger.append("assignment", assignment)
        self._event("verification_requested", assignment.receiving_office,
                    assignment_id=assignment_id, worker_id=worker_id,
                    payload={"verification_route": assignment.verification_route})
        return assignment

    def accept_verification(self, assignment_id: str, verifier_office: str) -> Assignment:
        assignment = self.assignments[assignment_id]
        if assignment.verification_route != verifier_office:
            raise RuntimeViolation("wrong verification route")
        if not assignment.evidence_receipt_ids:
            raise RuntimeViolation("verification cannot accept an assignment with no evidence")
        transition(assignment, AssignmentState.VERIFIED)
        self.ledger.append("assignment", assignment)
        self._event("verification_accepted", verifier_office, assignment_id=assignment_id,
                    payload={"evidence_receipt_ids": list(assignment.evidence_receipt_ids)})
        return assignment

    def reject_verification(self, assignment_id: str, verifier_office: str,
                            *, reason: str) -> Assignment:
        assignment = self.assignments[assignment_id]
        if assignment.verification_route != verifier_office:
            raise RuntimeViolation("wrong verification route")
        if not reason.strip():
            raise RuntimeViolation("verification rejection requires a reason")
        transition(assignment, AssignmentState.REJECTED, reason=reason)
        self.ledger.append("assignment", assignment)
        self._event("verification_rejected", verifier_office, assignment_id=assignment_id,
                    payload={"reason": reason,
                             "evidence_receipt_ids": list(assignment.evidence_receipt_ids)})
        return assignment

    def recover_stale_assignment(self, assignment_id: str, replacement_worker_id: str,
                                 *, stale_after_seconds: int = 900) -> Assignment:
        assignment = self.assignments[assignment_id]
        if assignment.assigned_worker_id is None:
            raise RuntimeViolation("assignment has no worker to recover")
        stale_worker = self.workers[assignment.assigned_worker_id]
        if not assignment_needs_recovery(
            assignment, stale_worker, stale_after_seconds=stale_after_seconds
        ):
            raise RuntimeViolation("assignment is not stale")
        replacement = self.workers[replacement_worker_id]
        if replacement.office_id != assignment.receiving_office:
            raise RuntimeViolation("replacement worker belongs to wrong Office")
        if replacement.current_assignment_id not in (None, assignment_id):
            raise RuntimeViolation("replacement worker is busy")

        prior_worker_id = stale_worker.worker_id
        stale_worker.current_assignment_id = None
        stale_worker.status = "stale"
        replacement.current_assignment_id = assignment_id
        replacement.status = "working"
        assignment.assigned_worker_id = replacement_worker_id
        if assignment.state != AssignmentState.BLOCKED:
            transition(assignment, AssignmentState.BLOCKED, reason="stale worker heartbeat")
        transition(assignment, AssignmentState.DISPATCHED)
        self.ledger.append("worker_binding", stale_worker)
        self.ledger.append("worker_binding", replacement)
        self.ledger.append("assignment", assignment)
        self._event("stale_assignment_reassigned", assignment.receiving_office,
                    assignment_id=assignment_id, worker_id=replacement_worker_id,
                    payload={"prior_worker_id": prior_worker_id})
        return assignment

    def complete(self, assignment_id: str) -> Assignment:
        assignment = self.assignments[assignment_id]
        if assignment.founder_gate is not None:
            raise RuntimeViolation(
                f"Founder gate blocks completion: {assignment.founder_gate.gate_type}"
            )
        if not assignment.evidence_receipt_ids:
            raise RuntimeViolation("no evidence = not done; completion requires evidence")
        if assignment.verification_route is not None and assignment.state != AssignmentState.VERIFIED:
            raise RuntimeViolation("verified evidence is required before completion")
        transition(assignment, AssignmentState.COMPLETED)
        if assignment.assigned_worker_id:
            worker = self.workers[assignment.assigned_worker_id]
            worker.current_assignment_id = None
            worker.status = "available"
            self.ledger.append("worker_binding", worker)
        self.ledger.append("assignment", assignment)
        self._event("assignment_completed", assignment.receiving_office,
                    assignment_id=assignment_id, worker_id=assignment.assigned_worker_id,
                    payload={"next_dependency": assignment.next_dependency,
                             "evidence_receipt_ids": list(assignment.evidence_receipt_ids)})
        return assignment

    def advance_next_dependency(self, assignment_id: str, *, advancing_office: str) -> Assignment:
        """Record that Operations actually advanced the verified next dependency."""
        assignment = self.assignments[assignment_id]
        if assignment.state != AssignmentState.COMPLETED:
            raise RuntimeViolation("next dependency may advance only after completion")
        if assignment.founder_gate is not None:
            raise RuntimeViolation(
                f"Founder gate blocks dependency advancement: {assignment.founder_gate.gate_type}"
            )
        if not assignment.next_dependency:
            raise RuntimeViolation("assignment has no next dependency to advance")
        if advancing_office not in self.offices:
            raise RuntimeViolation("unknown advancing Office")
        if advancing_office != "diana":
            raise RuntimeViolation("only Operations may advance the shared next dependency")
        if assignment.dependency_advanced_at is not None:
            raise RuntimeViolation("next dependency has already been advanced")

        assignment.dependency_advanced_at = utc_now()
        self.ledger.append("assignment", assignment)
        self._event("next_dependency_advanced", advancing_office,
                    assignment_id=assignment_id,
                    payload={"next_dependency": assignment.next_dependency})
        return assignment

    def operations_board(self) -> List[dict]:
        """Return Diana's machine-readable live operations board."""
        rows: List[dict] = []
        for assignment in self.assignments.values():
            worker = (
                self.workers.get(assignment.assigned_worker_id)
                if assignment.assigned_worker_id else None
            )
            handoffs = [
                handoff for handoff in self.handoffs.values()
                if handoff.assignment_id == assignment.assignment_id
            ]
            verification_handoff_ack = any(
                handoff.to_office == assignment.verification_route
                and handoff.acknowledged_at is not None
                for handoff in handoffs
            ) if assignment.verification_route else None

            rows.append({
                "assignment_id": assignment.assignment_id,
                "originating_office": assignment.originating_office,
                "receiving_office": assignment.receiving_office,
                "state": assignment.state.value,
                "worker_id": assignment.assigned_worker_id,
                "worker_status": worker.status if worker else None,
                "worker_last_heartbeat_at": worker.last_heartbeat_at if worker else None,
                "acknowledged": assignment.acknowledged_at is not None,
                "execution_started": assignment.execution_started_at is not None,
                "evidence_count": len(assignment.evidence_receipt_ids),
                "verification_route": assignment.verification_route,
                "verification_state": assignment.verification_state.value,
                "verification_handoff_acknowledged": verification_handoff_ack,
                "founder_gate": (
                    assignment.founder_gate.gate_type
                    if assignment.founder_gate is not None else None
                ),
                "blocker_reason": assignment.blocker_reason,
                "next_dependency": assignment.next_dependency,
                "dependency_advanced": assignment.dependency_advanced_at is not None,
                "completed_at": assignment.completed_at,
            })
        return rows
