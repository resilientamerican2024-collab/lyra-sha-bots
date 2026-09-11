from __future__ import annotations

from typing import Dict

from .ledger import RuntimeLedger
from .models import (
    Assignment,
    AssignmentState,
    EvidenceReceipt,
    OfficeIdentity,
    RuntimeEvent,
    WorkerBinding,
    new_id,
    utc_now,
)
from .state_machine import transition


class RuntimeViolation(ValueError):
    pass


class OfficeRuntime:
    """Small control plane for bounded internal Office work.

    This does not grant protected credentials or Founder authority. It only
    coordinates work at or below each Office's configured privilege tier and
    writes receipts to the append-only ledger.
    """

    def __init__(self, ledger: RuntimeLedger):
        self.ledger = ledger
        self.offices: Dict[str, OfficeIdentity] = {}
        self.workers: Dict[str, WorkerBinding] = {}
        self.assignments: Dict[str, Assignment] = {}
        self.receipts: Dict[str, EvidenceReceipt] = {}

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

    def ready_for_verification(self, assignment_id: str, worker_id: str) -> Assignment:
        assignment = self.assignments[assignment_id]
        if assignment.assigned_worker_id != worker_id:
            raise RuntimeViolation("only assigned worker may request verification")
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
        transition(assignment, AssignmentState.VERIFIED)
        self.ledger.append("assignment", assignment)
        self._event("verification_accepted", verifier_office, assignment_id=assignment_id)
        return assignment

    def complete(self, assignment_id: str) -> Assignment:
        assignment = self.assignments[assignment_id]
        if assignment.founder_gate is not None:
            raise RuntimeViolation(
                f"Founder gate blocks completion: {assignment.founder_gate.gate_type}"
            )
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
                    payload={"next_dependency": assignment.next_dependency})
        return assignment
