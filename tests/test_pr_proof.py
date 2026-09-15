import unittest
from unittest import mock

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


    def test_cross_representation_contradiction_requires_surviving_disagreement(self):
        with mock.patch.object(pr_proof, "files_changed", return_value=["config/retry.yaml"]), \
             mock.patch.object(pr_proof, "diff_lines", return_value=([], [])), \
             mock.patch.object(
                 pr_proof,
                 "cross_representation_contradictions",
                 return_value=["rollback_enabled: false @ config/retry.yaml <> true @ README.md"],
             ):
            findings, flags = pr_proof.analyze_diff("base", "head")
        self.assertTrue(flags["contradiction"])
        self.assertTrue(any(f.category == "contradictions" for f in findings))

    def test_declaration_change_alone_is_not_a_contradiction(self):
        with mock.patch.object(pr_proof, "files_changed", return_value=["config/retry.yaml"]), \
             mock.patch.object(pr_proof, "diff_lines", return_value=(["count: 5"], ["count: 3"])), \
             mock.patch.object(pr_proof, "cross_representation_contradictions", return_value=[]):
            findings, flags = pr_proof.analyze_diff("base", "head")
        self.assertFalse(flags["contradiction"])
        self.assertFalse(any(f.category == "contradictions" for f in findings))

    def test_extracts_retry_declarations_across_representations(self):
        doc = "- retry count is 5\n- timeout is 10 seconds\n- rollback is enabled\n"
        cfg = "retry:\n  count: 5\n  timeout_seconds: 10\n  rollback_enabled: false\n"
        self.assertIn(("retry_count", "5"), pr_proof.extract_declarations("README.md", doc))
        self.assertIn(("timeout_seconds", "10"), pr_proof.extract_declarations("README.md", doc))
        self.assertIn(("rollback_enabled", "true"), pr_proof.extract_declarations("README.md", doc))
        self.assertIn(("rollback_enabled", "false"), pr_proof.extract_declarations("config.yaml", cfg))


    def test_render_quotes_evidence(self):
        proof = pr_proof.Proof(
            version="0.1.0",
            base="main",
            head="HEAD",
            changed_files=1,
            findings=[
                pr_proof.Finding(
                    "assumptions",
                    "review",
                    "Assumption changed",
                    ["# cache must be available"],
                )
            ],
            surprise_score=50,
            intent_alignment=50,
            overall_impact="MODERATE",
            verdict="REVIEW",
            proof_hash="abc",
        )
        rendered = pr_proof.render(proof)
        self.assertIn("`# cache must be available`", rendered)
        self.assertNotIn("\n  - # cache must be available", rendered)


    def test_spoofed_marker_comment_is_not_owned(self):
        spoofed = {
            "body": pr_proof.MARKER + "\nforged",
            "user": {"login": "attacker", "type": "User"},
        }
        owned = {
            "body": pr_proof.MARKER + "\nreal",
            "user": {"login": "github-actions[bot]", "type": "Bot"},
        }
        self.assertFalse(pr_proof.is_own_proof_comment(spoofed))
        self.assertTrue(pr_proof.is_own_proof_comment(owned))


if __name__ == "__main__":
    unittest.main()
