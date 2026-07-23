import unittest

from framenet_mapper import map_text
from framenet_registry import registry
from dependency_parser import dependency_parser


class FrameNetMapperTests(unittest.TestCase):
    def test_d25_threshold(self):
        result = map_text(
            "A 25 - Maternity benefits - Minor attached disentitlement (D25) is imposed "
            "if the client has not accumulated at least 600 insurable hours."
        )
        self.assertEqual(result["eventCount"], 1)
        event = result["events"][0]
        self.assertEqual(event["eventType"], "PenaltyImposition")
        self.assertEqual(event["frame"], "Rewards_and_punishments")
        self.assertEqual(event["penaltyCode"]["code"], "D25")
        self.assertEqual(event["ruleCondition"]["expression"]["operator"], "lessThan")
        self.assertEqual(event["ruleCondition"]["expression"]["right"], 600)
        if registry.available:
            self.assertEqual(event["frameNet"]["frameId"], 216)
            self.assertIn("Response_action", event["frameElements"])
            self.assertEqual(event["frameNet"]["frameElementValidation"]["invalid"], [])

    def test_negative_imposition(self):
        result = map_text("The officer does not impose a D25 on the client.")
        self.assertEqual(result["events"][0]["polarity"], "negative")
        self.assertEqual(result["events"][0]["frameElements"]["Agent"]["text"], "The officer")

    def test_termination(self):
        result = map_text("A D42 is terminated when the suspension ends.")
        event = result["events"][0]
        self.assertEqual(event["eventType"], "PenaltyTermination")
        self.assertEqual(event["frame"], "Activity_stop")
        self.assertEqual(event["penaltyCode"]["code"], "D42")
        if registry.available:
            self.assertEqual(event["frameNet"]["target"]["lexicalUnit"], "terminate.v")

    def test_termination_condition_excludes_main_clause(self):
        result = map_text(
            "If the information on file allows for the disentitlement to be terminated, "
            "it is terminated on the Friday of the week before the conversion week."
        )
        event = result["events"][0]
        self.assertEqual(event["trigger"].lower(), "terminated")
        self.assertEqual(
            event["ruleCondition"]["text"],
            "the information on file allows for the disentitlement to be terminated",
        )
        self.assertEqual(
            event["frameElements"]["Time"]["text"],
            "on the Friday of the week before the conversion week",
        )

    @unittest.skipUnless(registry.available, "FrameNet 1.7 corpus is not installed")
    def test_official_lu_and_fe_validation(self):
        result = map_text("The officer imposes a monetary penalty (D70) on the client.")
        event = result["events"][0]
        self.assertEqual(event["frameNet"]["target"]["lexicalUnit"], "penalty.n")
        self.assertEqual(event["frameNet"]["validationStatus"], "validated_exact_lu")
        self.assertIn("Response_action", event["frameNet"]["frameElementValidation"]["valid"])

    def test_rescission_remains_domain_only(self):
        event = map_text("The officer rescinds D25.")["events"][0]
        self.assertEqual(event["eventType"], "PenaltyRescission")
        self.assertIsNone(event["frame"])
        self.assertEqual(event["frameNet"]["validationStatus"], "domain_event_only")

    @unittest.skipUnless(registry.available, "FrameNet 1.7 corpus is not installed")
    def test_unmatched_sentence_gets_candidate_frames(self):
        result = map_text("The applicant receives correspondence after filing.")
        self.assertEqual(result["candidateEventCount"], 1)
        event = result["events"][0]
        self.assertEqual(event["eventType"], "FrameNetCandidate")
        self.assertEqual(event["mappingStatus"], "candidate_only")
        self.assertGreater(len(event["candidateFrames"]), 0)
        self.assertIn("matchedLexicalUnit", event["candidateFrames"][0])

    def test_task2_permission_maps_to_permission_frame(self):
        event = map_text("A Level 1 officer can terminate the disentitlement if the file allows it.")[
            "events"
        ][0]
        self.assertEqual(event["eventType"], "DeonticPermission")
        self.assertEqual(event["frame"], "Deny_or_grant_permission")
        self.assertEqual(event["frameElements"]["Authority"]["text"], "Level 1 officer")

    def test_task2_evidence_requirement_maps_to_submitting_documents(self):
        event = map_text("The client must provide a signed statement attesting to the pregnancy.")[
            "events"
        ][0]
        self.assertEqual(event["eventType"], "EvidenceRequirement")
        self.assertEqual(event["frame"], "Submitting_documents")
        self.assertEqual(event["frameElements"]["Documents"]["text"], "a signed statement")

    def test_task2_system_behavior_maps_to_cause_change(self):
        event = map_text("The system automatically changes the sex code to 8 and displays both weeks.")[
            "events"
        ][0]
        self.assertEqual(event["eventType"], "SystemEffect")
        self.assertEqual(event["frame"], "Cause_change")
        self.assertEqual(event["frameElements"]["Agent"]["text"], "The system")

    def test_task2_diagnostic_inference_precedes_generic_permission(self):
        event = map_text(
            "Based on the letter that was sent, the officer can determine the reason the D15 is imposed."
        )["events"][0]
        self.assertEqual(event["eventType"], "DiagnosticInference")
        self.assertEqual(event["frame"], "Coming_to_believe")

    def test_task2_numeric_limit_remains_non_frame_structured_rule(self):
        event = map_text("Up to 15 weeks may be paid and the maximum cannot be exceeded.")["events"][0]
        self.assertEqual(event["eventType"], "QuantifiedLimit")
        self.assertIsNone(event["frame"])
        self.assertEqual(event["mappingStatus"], "non_frame_structured_rule")

    @unittest.skipUnless(dependency_parser.available, "spaCy dependency model is not installed")
    def test_dependency_parser_extracts_passive_agent_and_time(self):
        event = map_text(
            "The claimant's penalty was suspended by the department until Friday."
        )["events"][0]
        self.assertEqual(event["frameElements"]["Agent"]["text"], "the department")
        self.assertEqual(event["frameElements"]["Time"]["text"], "until Friday")
        self.assertEqual(event["extractionEvidence"]["Agent"]["method"], "dependency_parse")
        self.assertEqual(
            event["dependencyAnalysis"]["roles"]["agent"]["relation"],
            "passive_agent",
        )

    @unittest.skipUnless(dependency_parser.available, "spaCy dependency model is not installed")
    def test_dependency_parser_handles_unlisted_active_agent(self):
        event = map_text(
            "Unless the claimant responds, the department imposes penalty (D25)."
        )["events"][0]
        self.assertEqual(event["frameElements"]["Agent"]["text"], "the department")
        self.assertEqual(event["ruleCondition"]["text"], "the claimant responds")
        self.assertEqual(event["extractionEvidence"]["Condition"]["method"], "dependency_parse")


if __name__ == "__main__":
    unittest.main()
