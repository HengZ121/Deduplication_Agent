import unittest

from framenet_mapper import map_text


class FrameNetMapperTests(unittest.TestCase):
    def test_d25_threshold(self):
        result = map_text(
            "A 25 - Maternity benefits - Minor attached disentitlement (D25) is imposed "
            "if the client has not accumulated at least 600 insurable hours."
        )
        self.assertEqual(result["eventCount"], 1)
        event = result["events"][0]
        self.assertEqual(event["frame"], "Rewards_and_punishments")
        self.assertEqual(event["penaltyCode"]["code"], "D25")
        self.assertEqual(event["ruleCondition"]["expression"]["operator"], "lessThan")
        self.assertEqual(event["ruleCondition"]["expression"]["right"], 600)

    def test_negative_imposition(self):
        result = map_text("The officer does not impose a D25 on the client.")
        self.assertEqual(result["events"][0]["polarity"], "negative")
        self.assertEqual(result["events"][0]["frameElements"]["Agent"]["text"], "The officer")

    def test_termination(self):
        result = map_text("A D42 is terminated when the suspension ends.")
        event = result["events"][0]
        self.assertEqual(event["frame"], "PenaltyTermination")
        self.assertEqual(event["penaltyCode"]["code"], "D42")

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


if __name__ == "__main__":
    unittest.main()
