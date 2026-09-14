import unittest

import pr_proof


class ScoreTests(unittest.TestCase):
    def test_narrow_claim_with_material_change_is_surprising(self):
        flags = {k: False for k in (
            "behavior", "dependency", "config", "authority",
            "failure", "tests", "input", "assumption", "contradiction"
        )}
        flags["behavior"] = True
        flags["failure"] = True
        surprise, alignment = pr_proof.scores(
            "Refactor only",
            "No behavior change.",
            flags,
        )
        self.assertGreaterEqual(surprise, 70)
        self.assertLessEqual(alignment, 25)

    def test_intent_alignment_rewards_declared_change(self):
        flags = {k: False for k in (
            "behavior", "dependency", "config", "authority",
            "failure", "tests", "input", "assumption", "contradiction"
        )}
        flags["dependency"] = True
        surprise, alignment = pr_proof.scores(
            "Bump dependency",
            "Upgrade package only.",
            flags,
        )
        self.assertEqual(alignment, 100)
        self.assertLess(surprise, 30)

    def test_authority_failure_untested_blocks(self):
        findings = [
            pr_proof.Finding("authority", "review", "authority"),
            pr_proof.Finding("failure_modes", "review", "failure"),
            pr_proof.Finding("tests", "review", "untested"),
        ]
        impact, verdict = pr_proof.posture(findings, 50, 70)
        self.assertEqual(impact, "HIGH")
        self.assertEqual(verdict, "BLOCK")


if __name__ == "__main__":
    unittest.main()
