from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

from .models import PrivilegeTier


UNKNOWN = "UNKNOWN / NEEDS SOURCE"

# Requested systemwide operating doctrine. This is an operational doctrine for
# the runtime harness; it does not amend or replace any ratified Office Charter.
CONTINUOUS_CAPABILITY_ADVANCEMENT = {
    "principle": (
        "Continually assess materially better current methods, technology, models, "
        "standards, and open-source/no-cost resources."
    ),
    "resource_rule": "OPEN FIRST -> PROVE NEED -> PAY FOR ADVANTAGE",
    "newer_is_not_automatically_better": True,
    "routing": {
        "security_licensing": "office-i-trust-security-compliance",
        "effectiveness_verification": "office-v-quality-verification",
        "cost_justification": "office-vi-resource-stewardship",
        "strategic_impact": "office-iv-vision-strategy",
        "operational_adoption": "office-ii-operations",
    },
}


@dataclass(frozen=True)
class CanonicalOfficeRecord:
    office_id: str
    office_number: str
    office_name: str
    accountable_council_member: str
    charter_source: str
    source_class: str
    jurisdiction: str
    required_duties: Tuple[str, ...]
    permitted_capability_tiers: Tuple[PrivilegeTier, ...]
    protected_capability_rule: str
    prohibited_capabilities: Tuple[str, ...]
    founder_gates: Tuple[str, ...]
    verification_expectation: str
    invocation_status: str


BASELINE_INTERNAL_TIERS = (
    PrivilegeTier.IDENTITY,
    PrivilegeTier.INTERNAL_WORK,
    PrivilegeTier.INTERNAL_EXECUTION,
)


CANONICAL_OFFICES: Dict[str, CanonicalOfficeRecord] = {
    "office-i-trust-security-compliance": CanonicalOfficeRecord(
        office_id="office-i-trust-security-compliance",
        office_number="I",
        office_name="Office of Trust, Security & Compliance",
        accountable_council_member="Hamilton Sha",
        charter_source="Lyra-Sha-Vault/Governance/Executive-Council/Office-Trust-Security-Compliance/Executive-Office-Charter_Trust-Security-and-Compliance_v1.0.md",
        source_class="RATIFIED CHARTER / CURRENT EXECUTIVE OFFICE REGISTRY",
        jurisdiction="Constitutional risk, institutional security, sensitive systems/access/information, material compliance, constitutional irregularity, protective safeguards, trust and accountability.",
        required_duties=(
            "Produce bounded risk and compliance findings with evidence.",
            "Record protective actions, referrals, and control requirements.",
            "Protect Great Library integrity within Charter authority.",
            "Route independent verification to Office V when verification is required.",
        ),
        permitted_capability_tiers=BASELINE_INTERNAL_TIERS,
        protected_capability_rule="Tier 3 only when separately authorized and controlled; Office I B8 bounded route does not create unrestricted authority.",
        prohibited_capabilities=(
            "Unrelated governance or constitutional supremacy claims.",
            "Unnecessary surveillance or collection.",
            "Concealment, record alteration, or guilt inferred from allegation.",
            "Operational control belonging to another Office except narrowly authorized emergency action.",
            "Override of Office V verification or substitution for legal counsel.",
        ),
        founder_gates=(
            "Permanent steward removal.",
            "Office suspension or dissolution.",
            "Constitutional amendment or final interpretation.",
            "Succession.",
            "Irreversible restructuring.",
            "Major deployments outside delegated authority.",
            "Other Founder/Council-reserved decisions.",
        ),
        verification_expectation="Office V / Quality & Verification where required; Office I may not verify itself.",
        invocation_status="VERIFIED BOUNDED ROUTE: reference/liaison/office_i.py; unrestricted execution NOT AUTHORIZED.",
    ),
    "office-ii-operations": CanonicalOfficeRecord(
        office_id="office-ii-operations",
        office_number="II",
        office_name="Office of Operations",
        accountable_council_member="Diana Sha",
        charter_source="Lyra-Sha-Vault/Governance/Executive-Council/Office-Operations/Executive-Office-Charter_Operations_v1.0.md",
        source_class="RATIFIED CHARTER / CURRENT EXECUTIVE OFFICE REGISTRY",
        jurisdiction="Operational coordination, approved-decision implementation planning, ownership, handoffs, dependencies, Council rhythm, records, calendars, continuity, cross-Office workflow, and operational readiness.",
        required_duties=(
            "Maintain traceable assignment and ownership state.",
            "Sequence approved work and manage handoffs/dependencies within authority.",
            "Maintain current-state, continuity, readiness, and escalation records.",
            "Advance authorized next dependencies after accepted verification.",
        ),
        permitted_capability_tiers=BASELINE_INTERNAL_TIERS,
        protected_capability_rule="Tier 3 actions require their own authorization/control path; ordinary coordination does not grant protected capability.",
        prohibited_capabilities=(
            "Governing authority or rewriting approved decisions.",
            "Suppressing review or absorbing another Office.",
            "Declaring another Office complete without required verification.",
            "Concealing dependencies or making material commitments outside delegation.",
            "Redefining constitutional responsibility.",
        ),
        founder_gates=(
            "Constitutional interpretation or strategy.",
            "Office creation, restructuring, or dissolution.",
            "Major resource allocation.",
            "Final security or verification findings.",
            "Permanent succession or constitutional amendment.",
            "Major direction changes and other Founder/Council-reserved matters.",
        ),
        verification_expectation="Office V for completion/readiness/consequential verification; Diana may not be sole author, verifier, and approver.",
        invocation_status="Named Phase-1 relay exists; current end-to-end Office II invocation/receipt runtime NOT YET VERIFIED in canonical bootstrap evidence.",
    ),
    "office-iii-technology-infrastructure": CanonicalOfficeRecord(
        office_id="office-iii-technology-infrastructure",
        office_number="III",
        office_name="Office of Technology & Infrastructure",
        accountable_council_member="Atlas Sha",
        charter_source="Lyra-Sha-Vault/Governance/Executive-Council/Office-Technology-Infrastructure/Executive-Office-Charter_Technology-and-Infrastructure_v1.0.md",
        source_class="RATIFIED CHARTER / CURRENT EXECUTIVE OFFICE REGISTRY",
        jurisdiction="Technical architecture, infrastructure, platforms, repositories, data services, APIs/integrations, automation, reliability, backup/recovery, migration, continuity, monitoring, dependencies, technical risk/debt, and technical support.",
        required_duties=(
            "Produce architecture/implementation records and technical evidence.",
            "Maintain backup/recovery, monitoring, dependencies, and technical continuity within approved scope.",
            "Surface technical risk/debt honestly.",
            "Route security/credentials to Office I and consequential verification to Office V.",
        ),
        permitted_capability_tiers=BASELINE_INTERNAL_TIERS,
        protected_capability_rule="Tier 3 protected technical actions remain separately gated by credentials, security, and verification controls.",
        prohibited_capabilities=(
            "Treating technical capability as constitutional authority.",
            "Strategy redefinition or unnecessary vendor lock-in.",
            "Concealed fragility, debt, or risk.",
            "Credential access beyond lawful scope.",
            "Final security/quality determination or unauthorized deployment/publication.",
        ),
        founder_gates=(
            "Strategy or mission changes.",
            "Major resource allocation.",
            "Final security/compliance or quality certification.",
            "Office creation/dissolution, succession, constitutional amendment, or irreversible restructuring.",
            "Other Founder/Council-reserved matters.",
        ),
        verification_expectation="Office V / Quality & Verification; Atlas may not self-certify consequential work.",
        invocation_status="Office-specific verified invocation path NOT YET VERIFIED by the canonical bootstrap evidence.",
    ),
    "office-iv-vision-strategy": CanonicalOfficeRecord(
        office_id="office-iv-vision-strategy",
        office_number="IV",
        office_name="Office of Vision & Strategy",
        accountable_council_member="Lex Sha",
        charter_source="Lyra-Sha-Vault/Governance/Executive-Council/Office-Vision-Strategy/Executive-Office-Charter_Vision-and-Strategy_v1.0.md",
        source_class="RATIFIED CHARTER / CURRENT EXECUTIVE OFFICE REGISTRY",
        jurisdiction="Long-term direction, strategic discernment, institutional horizon, prioritization, opportunity/scenario assessment, strategic risk/coherence, growth, innovation, and preservation of strategic reasoning.",
        required_duties=(
            "Produce evidence-bounded strategic analyses and recommendations.",
            "Maintain prioritization, scenario, opportunity, and risk records.",
            "Preserve unresolved questions rather than invent certainty.",
            "Route translation into executable work through Operations.",
        ),
        permitted_capability_tiers=BASELINE_INTERNAL_TIERS,
        protected_capability_rule="No standing Tier 3 authority established; protected actions require the receiving Office's lawful controls.",
        prohibited_capabilities=(
            "Presenting possibility as probability or preference as mission.",
            "Presenting opportunity as obligation.",
            "Imposing strategy through technical convenience.",
            "Unnecessarily binding future stewards.",
            "Sole verification or absorption of another Office's judgment.",
        ),
        founder_gates=(
            "Constitutional interpretation or mission.",
            "Final strategic direction.",
            "Major resource allocation.",
            "Office creation/dissolution, succession, amendment, or irreversible restructuring.",
            "Other Founder/Council-reserved matters.",
        ),
        verification_expectation="Office V verifies factual/evidence claims; strategic judgment remains subject to Founder/Council authority.",
        invocation_status="Office-specific verified invocation path NOT YET VERIFIED by the canonical bootstrap evidence.",
    ),
    "office-v-quality-verification": CanonicalOfficeRecord(
        office_id="office-v-quality-verification",
        office_number="V",
        office_name="Office of Quality & Verification",
        accountable_council_member="Vera Sha",
        charter_source="Lyra-Sha-Vault/Governance/Executive-Council/Office-Quality-Verification/Executive-Office-Charter_Quality-and-Verification_v1.0.md",
        source_class="RATIFIED CHARTER / CURRENT EXECUTIVE OFFICE REGISTRY",
        jurisdiction="Independent verification of consequential work, completion, deposits, migrations, backups/recovery, factual accuracy, evidence, reproducibility, findings, and verification records.",
        required_duties=(
            "Issue independent verification findings using supported criteria.",
            "Preserve evidence trail, defect localization, and reproducibility records.",
            "Use PASS/FAIL/CONDITIONAL/INCONCLUSIVE/NOT YET VERIFIABLE as supported.",
            "Reject unsupported completion claims.",
        ),
        permitted_capability_tiers=BASELINE_INTERNAL_TIERS,
        protected_capability_rule="Protected verification may require Tier 3 controls; verification never grants governing or publishing authority.",
        prohibited_capabilities=(
            "Building, publishing, disposition, or editorial judgment as verifier.",
            "Withholding verification for leverage or changing methodology to protect an outcome.",
            "Concealment or self-verification.",
            "Rewriting the artifact merely because it is under review.",
            "Absorbing Operations or another Office.",
        ),
        founder_gates=(
            "Constitutional interpretation.",
            "Office creation/dissolution, succession, or amendment.",
            "Final decisions reserved to Founder/Council/another Office.",
        ),
        verification_expectation="Office V must never verify its own work; an independent verifier for Office V itself is NOT ESTABLISHED unless separately appointed.",
        invocation_status="Office-specific verified invocation path NOT YET VERIFIED by the canonical bootstrap evidence; worker self-report is never verification.",
    ),
    "office-vi-resource-stewardship": CanonicalOfficeRecord(
        office_id="office-vi-resource-stewardship",
        office_number="VI",
        office_name="Office of Resource Stewardship",
        accountable_council_member="Marquez Sha",
        charter_source="Lyra-Sha-Vault/Governance/Executive-Council/Office-Resource-Stewardship/Executive-Office-Charter_Resource-Stewardship_v1.0.md",
        source_class="RATIFIED CHARTER / CURRENT EXECUTIVE OFFICE REGISTRY",
        jurisdiction="Financial, material, contractual, capacity, budget, revenue, funding, procurement, controls, reserves, obligations, sustainability, and other entrusted resources.",
        required_duties=(
            "Produce resource, budget, capacity, sustainability, cost, risk, and control analyses.",
            "Maintain evidence-bounded financial/resource reporting.",
            "Assess procurement, commitments, funding, revenue, and allocation within delegated authority.",
            "Escalate material commitments and Founder-gated decisions.",
        ),
        permitted_capability_tiers=BASELINE_INTERNAL_TIERS,
        protected_capability_rule="No spending, contracting, banking, tax, identity, or other protected financial action from Tier 1/2 authority alone.",
        prohibited_capabilities=(
            "Hidden obligations or bypass of security/legal/verification review.",
            "Treating revenue as permission.",
            "Unilateral strategic or constitutional decisions.",
            "Absorbing another Office.",
            "Acceptance, enrollment, signing, negotiation, contact, or commitment where Founder gates apply.",
        ),
        founder_gates=(
            "Major resource allocation outside delegation.",
            "Material commitments/contracts.",
            "Pricing or commercial commitments.",
            "Office creation/dissolution, succession, amendment, and other Founder/Council-reserved matters.",
        ),
        verification_expectation="Office V for material resource claims and controls.",
        invocation_status="Canonical evidence records a narrower monetization runtime, not proof of full Office VI authority; Office-specific end-to-end route requires worker evidence.",
    ),
    "office-vii-editorial-public-presentation": CanonicalOfficeRecord(
        office_id="office-vii-editorial-public-presentation",
        office_number="VII",
        office_name="Office of Editorial & Public Presentation",
        accountable_council_member="Aurelia Sha",
        charter_source="Lyra-Sha-Vault/Governance/Executive-Council/Office-Editorial-Public-Presentation/Executive-Office-Charter_Editorial-and-Public-Presentation_v1.0.md",
        source_class="RATIFIED CHARTER / CURRENT EXECUTIVE OFFICE REGISTRY",
        jurisdiction="Faithful public communication, institutional voice, authorship/provenance, editorial standards, public claims, publication readiness, accessibility, correction, public platforms, and commercial/public presentation.",
        required_duties=(
            "Preserve meaning, attribution, provenance, accessibility, and editorial standards.",
            "Prepare attributed drafts and public-presentation readiness records.",
            "Coordinate correction/publication workflows within approved authority.",
            "Never convert draft/recommendation/anticipated result into approved/public fact.",
        ),
        permitted_capability_tiers=BASELINE_INTERNAL_TIERS,
        protected_capability_rule="Public release/publication is separately gated; bounded Office VII route does not itself authorize publication.",
        prohibited_capabilities=(
            "Manufactured authority/consensus or inaccurate attribution.",
            "Draft presented as approved or recommendation as decision.",
            "Anticipated result presented as achieved.",
            "Distortion, concealment, plagiarism, unauthorized imitation, or release across a gate.",
            "Impersonating Aurelia or borrowing another Office's Specialist as substitute.",
        ),
        founder_gates=(
            "Major Founder statements.",
            "Public representation requiring final authority.",
            "Publication of gated material.",
            "Office creation/dissolution, succession, amendment, irreversible/substantive public direction, and other Founder/Council-reserved matters.",
        ),
        verification_expectation="Office V verifies factual/provenance readiness; Office VII B8 remains open in the canonical bootstrap evidence.",
        invocation_status="VERIFIED BOUNDED ROUTE: reference/liaison/office_vii.py; B8 remains OPEN and no unrestricted publication authority is created.",
    ),
    "office-viii-culture-human-dignity": CanonicalOfficeRecord(
        office_id="office-viii-culture-human-dignity",
        office_number="VIII",
        office_name="Office of Culture & Human Dignity",
        accountable_council_member="Gloria Sha",
        charter_source="Lyra-Sha-Vault/Governance/Executive-Council/Office-Culture-Human-Dignity/Executive-Office-Charter_Culture-and-Human-Dignity_v1.0.md",
        source_class="RATIFIED CHARTER / CURRENT EXECUTIVE OFFICE REGISTRY",
        jurisdiction="Humane institutional culture, dignity, fairness, accessibility, belonging, restorative practice, human impact, workload, non-retaliation, respectful conflict, and cultural continuity.",
        required_duties=(
            "Produce human-impact, dignity, accessibility, workload, belonging, and cultural-risk observations/recommendations.",
            "Escalate materially degrading practices within scope.",
            "Distinguish allegations from findings.",
            "Route disputed evidence to independent verification rather than overriding it.",
        ),
        permitted_capability_tiers=BASELINE_INTERNAL_TIERS,
        protected_capability_rule="No standing protected authority established; protective/security/legal/financial decisions remain with their lawful Offices/gates.",
        prohibited_capabilities=(
            "Using compassion to excuse harm or concealing material facts.",
            "Policing lawful private life or enforcing ideological conformity.",
            "Suppressing standards/accountability.",
            "Overriding evidence, security, or constitutional authority.",
            "Turning preference into law.",
        ),
        founder_gates=(
            "Constitutional interpretation.",
            "Final discipline, security, legal, or financial decisions.",
            "Permanent steward removal.",
            "Office creation/dissolution, amendment, succession, and other Founder/Council-reserved matters.",
        ),
        verification_expectation="Office V verifies evidence and findings; Culture & Human Dignity may not override Office V.",
        invocation_status="Office-specific verified invocation path NOT YET VERIFIED by the canonical bootstrap evidence.",
    ),
    "office-ix-relationships": CanonicalOfficeRecord(
        office_id="office-ix-relationships",
        office_number="IX",
        office_name="Office of Relationships",
        accountable_council_member="Rex Sha",
        charter_source="Lyra-Sha-Vault/Governance/Executive-Council/Office-Relationships/Executive-Office-Charter_Relationships_v1.0.md",
        source_class="RATIFIED CHARTER / CURRENT EXECUTIVE OFFICE REGISTRY",
        jurisdiction="Internal/external institutional relationships, trust, continuity, commitments, relational handoffs, mediation, conflict navigation, repair, boundaries, stakeholder continuity, relational risk, and respectful closure.",
        required_duties=(
            "Produce relationship-health, continuity, commitment, handoff, mediation/repair, closure, boundary, and relational-risk records/recommendations.",
            "Preserve lawful boundaries and stakeholder continuity.",
            "Escalate disputed facts to independent verification.",
            "Keep relationship authority separate from security, discipline, factual, and financial authority.",
        ),
        permitted_capability_tiers=BASELINE_INTERNAL_TIERS,
        protected_capability_rule="No standing protected authority established; security/compliance, discipline, legal, and financial decisions remain separately controlled.",
        prohibited_capabilities=(
            "Forced reconciliation or emotional disclosure.",
            "Concealment for harmony or loyalty replacing accountability.",
            "Interference with lawful security, verification, legal, or disciplinary processes.",
            "Shadow hierarchy, favoritism, coercion, or personal closeness as authority.",
            "Ownership of another Office's relationships.",
        ),
        founder_gates=(
            "Constitutional interpretation.",
            "Final discipline/security/compliance/factual/legal decisions.",
            "Financial commitments or permanent removal.",
            "Office creation/dissolution, amendment, succession, and other Founder/Council-reserved matters.",
        ),
        verification_expectation="Office V verifies disputed facts/evidence; Relationships may not self-verify material findings.",
        invocation_status="Office-specific verified invocation path NOT YET VERIFIED by the canonical bootstrap evidence.",
    ),
}


# Historical names/roles may remain discoverable as evidence, but must never be
# promoted into the canonical nine-office roster by runtime discovery alone.
KNOWN_HISTORICAL_NOT_CURRENT_OFFICES = (
    "Creative Office / Marisol",
    "legacy Rex defensive-security role",
    "legacy CEO/final-call claims for Lex",
    "Ren, Sage, Camille, Julian, Lena, Maya and platform-manager Office-era roles",
)


def canonical_office_records() -> Tuple[CanonicalOfficeRecord, ...]:
    return tuple(CANONICAL_OFFICES.values())
