#!/usr/bin/env python3
"""Tests for domain frame narrowing and lexical-sense suppression."""

from __future__ import annotations

import unittest

from domain_frame_canonicalizer import canonicalizer


class DomainFrameCanonicalizerTests(unittest.TestCase):
    def canonicalize(self, sentence: str, *frames: str):
        return canonicalizer.canonicalize(sentence, frames)

    def test_meet_conditions_selects_standard_not_social_meeting(self) -> None:
        result = self.canonicalize(
            "The client must meet the eligibility conditions.",
            "Meet_specifications",
            "Assemble",
            "Come_together",
        )
        self.assertIn("Meet_specifications", result.canonical_frames)
        self.assertIn("Assemble", result.explicitly_suppressed_frames)
        self.assertNotIn("Come_together", result.canonical_frames)

    def test_administrative_file_rejects_grooming(self) -> None:
        result = self.canonicalize(
            "The officer reviews the information on file and refers the issue.",
            "Grooming",
            "Submitting_documents",
            "Scrutiny",
        )
        self.assertIn("Grooming", result.explicitly_suppressed_frames)
        self.assertIn("administrative_file_reference", result.structured_knowledge)

    def test_document_submission_maps_to_submitting_documents(self) -> None:
        result = self.canonicalize(
            "The client must submit the signed form to the officer.",
            "Grooming",
            "Submitting_documents",
        )
        self.assertIn("Submitting_documents", result.canonical_frames)
        self.assertIn("Grooming", result.explicitly_suppressed_frames)

    def test_set_conditions_rejects_consistency_frames(self) -> None:
        result = self.canonicalize(
            "The client set conditions on accepting employment.",
            "Cause_change_of_consistency",
            "Change_of_consistency",
        )
        self.assertIn("administrative_setting", result.structured_knowledge)
        self.assertIn("Cause_change_of_consistency", result.explicitly_suppressed_frames)
        self.assertNotIn("Cause_change_of_consistency", result.canonical_frames)

    def test_conditions_set_out_do_not_imply_cause_change(self) -> None:
        result = self.canonicalize(
            "The officer reviews the conditions set out in the legislation.",
            "Cause_change",
            "Cause_change_of_consistency",
        )
        self.assertNotIn("Cause_change", result.canonical_frames)
        self.assertIn("administrative_setting", result.structured_knowledge)

    def test_rate_is_structured_quantity(self) -> None:
        result = self.canonicalize(
            "The weekly benefit rate is 55 percent of earnings.",
            "Rate_quantification",
            "Relational_quantity",
            "Proportion",
        )
        self.assertEqual("structured_non_frame", result.status)
        self.assertEqual(("rate_or_ratio",), result.structured_knowledge)

    def test_determine_from_evidence_maps_to_coming_to_believe(self) -> None:
        result = self.canonicalize(
            "Based on the letter, the officer determines the reason for separation.",
            "Coming_to_believe",
            "Deciding",
            "Control",
        )
        self.assertIn("Coming_to_believe", result.canonical_frames)
        self.assertNotIn("Deciding", result.canonical_frames)

    def test_procedural_must_maps_to_obligation(self) -> None:
        result = self.canonicalize(
            "The officer must include the required documents.",
            "Have_as_requirement",
            "Imposing_obligation",
            "Needing",
        )
        self.assertIn("Imposing_obligation", result.canonical_frames)
        self.assertIn("Have_as_requirement", result.canonical_frames)
        self.assertIn("Needing", result.explicitly_suppressed_frames)

    def test_estimate_collapses_to_assessing(self) -> None:
        result = self.canonicalize(
            "The officer estimates the client's insurable earnings.",
            "Estimating",
            "Estimated_value",
            "Assessing",
        )
        self.assertEqual(("Assessing",), result.canonical_frames)
        self.assertIn("Estimated_value", result.explicitly_suppressed_frames)

    def test_resume_collapses_to_activity_resume(self) -> None:
        result = self.canonicalize(
            "The client will resume collecting the remaining benefit weeks.",
            "Activity_resume",
            "Process_resume",
        )
        self.assertEqual(("Activity_resume",), result.canonical_frames)
        self.assertIn("Process_resume", result.explicitly_suppressed_frames)

    def test_unresolved_inventory_candidate_stays_reviewable(self) -> None:
        result = self.canonicalize("A short ambiguous sentence.", "Request", "Statement")
        self.assertEqual("needs_review", result.status)
        self.assertEqual(("Request",), result.review_candidates)

    def test_information_noun_does_not_trigger_communication(self) -> None:
        result = self.canonicalize("The information is available on file.", "Communication")
        self.assertNotIn("Communication", result.canonical_frames)

    def test_does_not_apply_is_not_a_request(self) -> None:
        result = self.canonicalize("This provision does not apply to the client.", "Request")
        self.assertNotIn("Request", result.canonical_frames)

    def test_apply_for_duration_is_not_a_request(self) -> None:
        result = self.canonicalize(
            "Extensions always apply for the first 4 weeks of the claim.",
            "Request",
        )
        self.assertNotIn("Request", result.canonical_frames)

    def test_client_applying_for_benefits_is_a_request(self) -> None:
        result = self.canonicalize(
            "The client may apply for parental benefits.",
            "Request",
        )
        self.assertIn("Request", result.canonical_frames)

    def test_program_name_is_not_employment_status(self) -> None:
        result = self.canonicalize(
            "Employment Insurance procedures are updated annually.",
            "Being_employed",
        )
        self.assertNotIn("Being_employed", result.canonical_frames)

    def test_accepting_employment_is_employment_status(self) -> None:
        result = self.canonicalize(
            "The client accepted employment with a new employer.",
            "Being_employed",
        )
        self.assertIn("Being_employed", result.canonical_frames)

    def test_employer_role_alone_is_not_employment_status(self) -> None:
        result = self.canonicalize(
            "The officer contacts the employer for more information.",
            "Being_employed",
        )
        self.assertNotIn("Being_employed", result.canonical_frames)

    def test_option_list_is_filtered_as_artifact(self) -> None:
        result = self.canonicalize(
            "Select the reason for issuing the amended T4E: change of name or repayment rate.",
            "Request",
            "Rate_quantification",
        )
        self.assertEqual("filtered_artifact", result.status)


if __name__ == "__main__":
    unittest.main()
