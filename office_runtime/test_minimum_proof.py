from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from office_runtime.ledger import RuntimeLedger
from office_runtime.models import Assignment, OfficeIdentity, PrivilegeTier, WorkerBinding, new_id
from office_runtime.orchestrator import OfficeRuntime, RuntimeViolation
from office_runtime.policies import detect_founder_gate


class MinimumRuntimeProof(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ledger = RuntimeLedger(Path(self.temp.name) / "runtime.jsonl")
        self.runtime = OfficeRuntime(self.ledger)

        self.runtime.register_office(OfficeIdentity(
            office_id="lex",
            office_name="Vision & Strategy",
            council_member="Lex",
            mission="Set portfolio direction and priorities without collapsing Founder authority.",
            privilege_tier=PrivilegeTier.INTERNAL_EXECUTION,
            allowed_capabilities=["prioritize", "recommend", "internal_handoff"],
            prohibited_capabilities=["spending", "publication_release", "contract_signature"],
            verifier_office="vera",
        ))
        self.runtime.register_office(OfficeIdentity(
            office_id="diana",
            office_name="Operations",
            council_member="Diana Sha",
            mission="Orchestrate authorized work, dispatch, follow through, recover stale work and advance dependencies.",
            privilege_tier=PrivilegeTier.INTERNAL_EXECUTION,
            allowed_capabilities=["dispatch", "ack_tracking", "dependency_advancement", "internal_handoff"],
            prohibited_capabilities=["spending", "publication_release", "contract_signature"],
            verifier_office="vera",
        ))
        self.runtime.register_office(OfficeIdentity(
            office_id="vera",
            office_name="Independent Verification",
            council_member="Vera",
            mission="Independently verify evidence and accept or reject bounded work.",
            privilege_tier=PrivilegeTier.INTERNAL_EXECUTION,
            allowed_capabilities=["verify_internal_evidence"],
            prohibited_capabilities=["self_approval_of_produced_work"],
        ))
        self.runtime.bind_worker(WorkerBinding("lex.worker.v0", "lex", "test-runtime"))
        self.runtime.bind_worker(WorkerBinding("diana.worker.v0", "diana", "test-runtime"))
        self.runtime.bind_worker(WorkerBinding("vera.worker.v0", "vera", "test-runtime"))
        for worker in self.runtime.workers:
            self.runtime.heartbeat(worker)

    def tearDown(self):
        self.temp.cleanup()

    def _dispatch_and_start(self, assignment: Assignment) -> None:
        self.runtime.create_assignment(assignment)
        self.runtime.dispatch(assignment.assignment_id, "diana.worker.v0")
        self.runtime.acknowledge(assignment.assignment_id, "diana.worker.v0")
        self.runtime.start(assignment.assignment_id, "diana.worker.v0")

    def test_lex_to_diana_to_vera_then_advance(self):
        assignment = Assignment(
            assignment_id=new_id("asg"),
            originating_office="lex",
            receiving_office="diana",
            mission="Convert approved portfolio priority into an executable internal dispatch plan.",
            requested_outcome="Dispatch-ready operations plan with next dependency identified.",
            evidence_required=["operations_plan"],
            verification_route="vera",
            privilege_tier_required=PrivilegeTier.INTERNAL_EXECUTION,
            next_dependency="activate first bounded Office worker",
        )
        assignment.founder_gate = detect_founder_gate(
            requested_capabilities=["dispatch", "internal_handoff"],
            privilege_tier_required=assignment.privilege_tier_required,
        )
        self.assertIsNone(assignment.founder_gate)

        self._dispatch_and_start(assignment)
        receipt = self.runtime.submit_evidence(
            assignment.assignment_id,
            "diana.worker.v0",
            evidence_type="operations_plan",
            location="ledger://proof/lex-diana-operations-plan",
            metadata={"next_dependency": assignment.next_dependency},
        )
        self.assertTrue(receipt.receipt_id)

        handoff = self.runtime.create_handoff(
            assignment.assignment_id,
            from_office="diana",
            to_office="vera",
            purpose="independent verification",
        )
        self.runtime.acknowledge_handoff(handoff.handoff_id, "vera")
        self.assertIsNotNone(handoff.acknowledged_at)

        self.runtime.ready_for_verification(assignment.assignment_id, "diana.worker.v0")
        self.runtime.accept_verification(assignment.assignment_id, "vera")
        completed = self.runtime.complete(assignment.assignment_id)

        self.assertEqual(completed.state.value, "completed")
        self.assertEqual(completed.verification_state.value, "accepted")
        self.assertEqual(completed.next_dependency, "activate first bounded Office worker")
        self.assertIsNone(self.runtime.workers["diana.worker.v0"].current_assignment_id)

        advanced = self.runtime.advance_next_dependency(
            assignment.assignment_id,
            advancing_office="diana",
        )
        self.assertIsNotNone(advanced.dependency_advanced_at)

        board = self.runtime.operations_board()
        self.assertEqual(len(board), 1)
        row = board[0]
        self.assertEqual(row["state"], "completed")
        self.assertTrue(row["acknowledged"])
        self.assertTrue(row["execution_started"])
        self.assertEqual(row["evidence_count"], 1)
        self.assertEqual(row["verification_state"], "accepted")
        self.assertTrue(row["verification_handoff_acknowledged"])
        self.assertTrue(row["dependency_advanced"])
        self.assertIsNone(row["founder_gate"])

        event_types = [r["payload"]["event_type"] for r in self.ledger.records("event")]
        self.assertIn("assignment_acknowledged", event_types)
        self.assertIn("handoff_acknowledged", event_types)
        self.assertIn("verification_accepted", event_types)
        self.assertIn("assignment_completed", event_types)
        self.assertIn("next_dependency_advanced", event_types)

    def test_dependency_cannot_advance_before_completion(self):
        assignment = Assignment(
            assignment_id=new_id("asg"),
            originating_office="lex",
            receiving_office="diana",
            mission="Prepare bounded operations work.",
            requested_outcome="Verified operations artifact.",
            evidence_required=["operations_artifact"],
            verification_route="vera",
            next_dependency="dispatch follow-on work",
        )
        self.runtime.create_assignment(assignment)
        with self.assertRaisesRegex(RuntimeViolation, "only after completion"):
            self.runtime.advance_next_dependency(
                assignment.assignment_id,
                advancing_office="diana",
            )

    def test_non_operations_office_cannot_advance_shared_dependency(self):
        assignment = Assignment(
            assignment_id=new_id("asg"),
            originating_office="lex",
            receiving_office="diana",
            mission="Prepare bounded operations work.",
            requested_outcome="Evidence-backed internal artifact.",
            evidence_required=[],
            verification_route=None,
            next_dependency="dispatch follow-on work",
        )
        self._dispatch_and_start(assignment)
        self.runtime.submit_evidence(
            assignment.assignment_id,
            "diana.worker.v0",
            evidence_type="execution_receipt",
            location="ledger://proof/dependency-advance",
        )
        self.runtime.complete(assignment.assignment_id)
        with self.assertRaisesRegex(RuntimeViolation, "only Operations"):
            self.runtime.advance_next_dependency(
                assignment.assignment_id,
                advancing_office="lex",
            )

    def test_founder_gate_blocks_dispatch(self):
        assignment = Assignment(
            assignment_id=new_id("asg"),
            originating_office="lex",
            receiving_office="diana",
            mission="Attempt reserved spending action.",
            requested_outcome="No dispatch without Founder authority.",
            evidence_required=[],
            verification_route="vera",
        )
        assignment.founder_gate = detect_founder_gate(
            requested_capabilities=["spending"],
            privilege_tier_required=PrivilegeTier.INTERNAL_EXECUTION,
        )
        self.assertIsNotNone(assignment.founder_gate)
        self.runtime.create_assignment(assignment)
        board = self.runtime.operations_board()
        self.assertEqual(board[0]["founder_gate"], assignment.founder_gate.gate_type)
        with self.assertRaises(RuntimeViolation):
            self.runtime.dispatch(assignment.assignment_id, "diana.worker.v0")

    def test_no_evidence_means_not_done_even_without_verification_route(self):
        assignment = Assignment(
            assignment_id=new_id("asg"),
            originating_office="lex",
            receiving_office="diana",
            mission="Bounded internal task that does not require independent Vera review.",
            requested_outcome="Internal completion with a durable receipt.",
            evidence_required=[],
            verification_route=None,
        )
        self._dispatch_and_start(assignment)
        with self.assertRaisesRegex(RuntimeViolation, "no evidence = not done"):
            self.runtime.complete(assignment.assignment_id)

        self.runtime.submit_evidence(
            assignment.assignment_id,
            "diana.worker.v0",
            evidence_type="execution_receipt",
            location="ledger://proof/internal-execution-receipt",
        )
        completed = self.runtime.complete(assignment.assignment_id)
        self.assertEqual(completed.state.value, "completed")

    def test_verification_cannot_be_requested_without_evidence(self):
        assignment = Assignment(
            assignment_id=new_id("asg"),
            originating_office="lex",
            receiving_office="diana",
            mission="Bounded internal operations work.",
            requested_outcome="Operations artifact.",
            evidence_required=[],
            verification_route="vera",
        )
        self._dispatch_and_start(assignment)
        with self.assertRaisesRegex(RuntimeViolation, "no evidence receipts"):
            self.runtime.ready_for_verification(assignment.assignment_id, "diana.worker.v0")

    def test_verification_cannot_be_bypassed(self):
        assignment = Assignment(
            assignment_id=new_id("asg"),
            originating_office="lex",
            receiving_office="diana",
            mission="Bounded internal operations work.",
            requested_outcome="Operations artifact.",
            evidence_required=["operations_artifact"],
            verification_route="vera",
        )
        self._dispatch_and_start(assignment)
        self.runtime.submit_evidence(
            assignment.assignment_id,
            "diana.worker.v0",
            evidence_type="operations_artifact",
            location="ledger://proof/unverified-artifact",
        )
        self.runtime.ready_for_verification(assignment.assignment_id, "diana.worker.v0")
        with self.assertRaises(RuntimeViolation):
            self.runtime.complete(assignment.assignment_id)

    def test_vera_rejection_routes_back_to_execution_not_completion(self):
        assignment = Assignment(
            assignment_id=new_id("asg"),
            originating_office="lex",
            receiving_office="diana",
            mission="Produce an operations artifact and correct it if Vera rejects it.",
            requested_outcome="Verified operations artifact.",
            evidence_required=["operations_artifact"],
            verification_route="vera",
        )
        self._dispatch_and_start(assignment)
        self.runtime.submit_evidence(
            assignment.assignment_id,
            "diana.worker.v0",
            evidence_type="operations_artifact",
            location="ledger://proof/rejected-artifact-v1",
        )
        self.runtime.ready_for_verification(assignment.assignment_id, "diana.worker.v0")
        rejected = self.runtime.reject_verification(
            assignment.assignment_id,
            "vera",
            reason="artifact does not satisfy requested outcome",
        )
        self.assertEqual(rejected.state.value, "rejected")
        self.assertEqual(rejected.verification_state.value, "rejected")
        with self.assertRaises(Exception):
            self.runtime.complete(assignment.assignment_id)

        self.runtime.start(assignment.assignment_id, "diana.worker.v0")
        self.runtime.submit_evidence(
            assignment.assignment_id,
            "diana.worker.v0",
            evidence_type="operations_artifact",
            location="ledger://proof/corrected-artifact-v2",
        )
        self.runtime.ready_for_verification(assignment.assignment_id, "diana.worker.v0")
        self.runtime.accept_verification(assignment.assignment_id, "vera")
        completed = self.runtime.complete(assignment.assignment_id)
        self.assertEqual(completed.state.value, "completed")

    def test_wrong_office_worker_cannot_accept_dispatch(self):
        assignment = Assignment(
            assignment_id=new_id("asg"),
            originating_office="lex",
            receiving_office="diana",
            mission="Bounded internal operations work.",
            requested_outcome="Operations artifact.",
            evidence_required=[],
            verification_route="vera",
        )
        self.runtime.create_assignment(assignment)
        with self.assertRaises(RuntimeViolation):
            self.runtime.dispatch(assignment.assignment_id, "lex.worker.v0")


if __name__ == "__main__":
    unittest.main()
