# LSA Office Runtime Harness v0

Status: construction branch only. Not production-wired.

## Purpose
Turn Council Offices into persistent, charter-bound operating units that can continue authorized work without requiring Ingrid to remain in an interactive chat session.

## Core rule
OFFICE != MODEL != RUNTIME != MACHINE.

An Office remains the accountable organizational unit even when the underlying AI/runtime changes.

## Completion doctrine
- No evidence = not done.
- EXECUTED is not VERIFIED.
- If independent verification is required, no accepted verification = not complete.
- A worker assertion cannot directly convert work to COMPLETED.
- Vera rejection routes work back to correction/execution and re-verification.
- Naming a next dependency is not the same as advancing it; dependency advancement is a separate durable event.

## Progressive privilege
- Tier 0 — Constitutional identity: Office, charter, mission, responsibilities, prohibitions.
- Tier 1 — Internal reasoning/work: receive assignments, research, analyze, draft, communicate internally, produce artifacts/recommendations.
- Tier 2 — Internal execution: ACK work, update approved internal state/queues, create internal deliverables, hand work to another Office, advance authorized dependencies.
- Tier 3 — Protected capability: sensitive data, protected services, credential-mediated or privileged actions. Requires stronger Hamilton/Vera controls.
- Tier 4 — Founder gate: spending, publication/release, contracts/signatures, banking/tax/identity, destructive/irreversible actions, constitutional/governance authority.

Permanent privileged seating is NOT a prerequisite for Tier 1/2 Office operation.

## Common runtime contract
Every Office must have:
1. office_id
2. accountable_council_member
3. charter/mission binding
4. allowed_capabilities
5. prohibited_capabilities
6. durable inbox
7. durable outbox
8. assignment_id
9. ACK state
10. worker binding
11. heartbeat
12. execution evidence receipt
13. inter-Office handoff envelope
14. stale-work timer
15. Founder-gate detector
16. verification route
17. next-dependency state
18. audit ledger

## Required assignment lifecycle
ASSIGNED -> ACKNOWLEDGED -> EXECUTING -> EVIDENCE_READY -> VERIFYING -> VERIFIED|REJECTED -> COMPLETED -> NEXT_DEPENDENCY_ADVANCED

If no ACK: dispatch failed.
If ACK but no execution evidence inside SLA: stale-work recovery begins.
If rejected: diagnose/correct/retest within authority.
If Founder action is NONE and an authorized next step exists: execute the next step.

## Diana live operations board
The harness exposes a machine-readable operations board derived from runtime state rather than narrative status reporting. For each assignment Diana can inspect:
- accountable originating and receiving Offices
- bound worker and current worker status
- worker heartbeat
- ACK state
- execution-start state
- evidence count
- Vera/verification route and state
- verification handoff ACK
- true Founder gate, if any
- blocker reason
- next dependency
- whether that dependency was actually advanced
- completion timestamp

This distinction is deliberate: ASSIGNED, WORKING, VERIFIED, COMPLETED and ADVANCED are different states.

## Restart durability
The filesystem JSONL ledger is append-only and the runtime can rebuild current Office, worker, assignment, evidence, handoff and dependency-advancement state from that ledger after a process restart. Replay reconstructs state only; it does not silently execute or advance work.

## Inter-Office assignment envelope
- assignment_id
- originating_office
- receiving_office
- project_or_asset
- mission_context
- requested_outcome
- authority_boundary
- required_evidence
- SLA
- dependencies
- verification_route
- founder_gate_if_any

## Initial activation order
1. Lex / Vision & Strategy — Tier 1/2
2. Diana / Operations — Tier 1/2
3. Atlas / Technology & Infrastructure — Tier 1/2, protected actions remain Tier 3
4. Gloria / Creative — Tier 1/2
5. Marisol / applicable Office scope — Tier 1/2
6. Julian / applicable Office scope — Tier 1/2
7. Marquez / Resource Stewardship — Tier 1/2
8. Hamilton / Trust-Security-Compliance-Governance — Tier 1/2 plus policy enforcement role
9. Vera / independent verification — Tier 1/2 with independence preserved; protected verification escalates to Tier 3
10. Scout / Discovery — continue authorized sandbox Tier 1/2; permanent-seat protected capabilities remain separately gated

## Acceptance tests
A. Ingrid leaves for six hours. Authorized work continues and receipts exist.
B. Interactive ChatGPT is closed. Office queues/workers continue.
C. Underlying model/runtime changes. Office identity, charter, queue, evidence, and obligations persist.
D. Diana detects unfinished authorized work with Founder action NONE. The next system event is dispatch/execution, not merely an email to Ingrid.
E. Dispatch to an Office without a reachable worker is recorded as failed, never as WORKING.
F. Process restarts do not erase ACK, evidence, verification, completion or dependency-advancement state.
G. No assignment can be marked complete merely because a worker says it is done.

## Source findings informing v0
- The older Rooted Ready Life Agent OS is phase/approval driven and explicitly requires Ingrid approval at every phase, so it is not the unattended pattern to replicate.
- The existing Lyra-Sha bot repositories contain reusable execution pieces, but not a shared Council Office runtime.
- Existing Scout, launchd, email-intake, scheduled-task, Diana-reporting, Hamilton/Vera, and THIS IS US components show that persistent unattended pieces already exist; v0 connects them through a common Office contract instead of rebuilding each Office separately.

## Non-goals for v0
- Do not merge legacy repositories.
- Do not alter production bot behavior on this branch.
- Do not bypass Hamilton/Vera protections.
- Do not reopen retired Badge #001 or legacy Keychain paths.
- Do not regenerate THIS IS US Artifact 006.
- Do not require privileged seating for ordinary Tier 1/2 internal work.
