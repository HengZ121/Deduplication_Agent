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
