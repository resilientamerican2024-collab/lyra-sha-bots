import unittest

from office_runtime.canonical_roster import (
    BASELINE_INTERNAL_TIERS,
    CANONICAL_OFFICES,
    CONTINUOUS_CAPABILITY_ADVANCEMENT,
)
from office_runtime.models import PrivilegeTier


class CanonicalRosterTests(unittest.TestCase):
    def test_exactly_nine_current_executive_offices(self):
        self.assertEqual(len(CANONICAL_OFFICES), 9)
        self.assertEqual(
            {record.office_number for record in CANONICAL_OFFICES.values()},
            {"I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX"},
        )

    def test_unique_officeholder_and_identity(self):
        records = list(CANONICAL_OFFICES.values())
        self.assertEqual(len({r.office_id for r in records}), 9)
        self.assertEqual(len({r.office_name for r in records}), 9)
        self.assertEqual(len({r.accountable_council_member for r in records}), 9)

    def test_baseline_privilege_does_not_grant_protected_or_founder_authority(self):
        self.assertEqual(
            BASELINE_INTERNAL_TIERS,
            (
                PrivilegeTier.IDENTITY,
                PrivilegeTier.INTERNAL_WORK,
                PrivilegeTier.INTERNAL_EXECUTION,
            ),
        )
        for record in CANONICAL_OFFICES.values():
            self.assertNotIn(PrivilegeTier.PROTECTED_CAPABILITY, record.permitted_capability_tiers)
            self.assertNotIn(PrivilegeTier.FOUNDER_GATE, record.permitted_capability_tiers)
            self.assertTrue(record.protected_capability_rule)
            self.assertTrue(record.founder_gates)

    def test_every_office_has_charter_boundaries_and_verification_expectation(self):
        for record in CANONICAL_OFFICES.values():
            self.assertIn("Executive-Office-Charter_", record.charter_source)
            self.assertTrue(record.jurisdiction)
            self.assertTrue(record.required_duties)
            self.assertTrue(record.prohibited_capabilities)
            self.assertTrue(record.verification_expectation)
            self.assertTrue(record.invocation_status)

    def test_continuous_capability_advancement_routing(self):
        doctrine = CONTINUOUS_CAPABILITY_ADVANCEMENT
        self.assertEqual(doctrine["resource_rule"], "OPEN FIRST -> PROVE NEED -> PAY FOR ADVANTAGE")
        self.assertTrue(doctrine["newer_is_not_automatically_better"])
        self.assertEqual(
            doctrine["routing"],
            {
                "security_licensing": "office-i-trust-security-compliance",
                "effectiveness_verification": "office-v-quality-verification",
                "cost_justification": "office-vi-resource-stewardship",
                "strategic_impact": "office-iv-vision-strategy",
                "operational_adoption": "office-ii-operations",
            },
        )


if __name__ == "__main__":
    unittest.main()
