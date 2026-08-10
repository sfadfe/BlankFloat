import unittest

from blankfloat import routing
from blankfloat.routing import Analysis, Answer, ParseError, Signals


def analysis(**kwargs) -> Analysis:
    signals = Signals(**kwargs.pop("signals", {}))
    answers = [Answer(**a) for a in kwargs.pop("answers", [])]
    return Analysis(signals=signals, answers=answers, **kwargs)


class ExtractJsonTest(unittest.TestCase):
    def test_plain_object(self):
        self.assertEqual(routing.extract_json('{"route": "simple"}'), {"route": "simple"})

    def test_fenced_object(self):
        text = 'sure!\n```json\n{"route": "complex"}\n```\n'
        self.assertEqual(routing.extract_json(text), {"route": "complex"})

    def test_object_with_surrounding_prose(self):
        text = 'Here you go: {"route": "simple", "confidence": 0.9} hope it helps'
        self.assertEqual(routing.extract_json(text)["confidence"], 0.9)

    def test_rejects_garbage(self):
        with self.assertRaises(ParseError):
            routing.extract_json("no json here")


class NormalizeTest(unittest.TestCase):
    def test_invalid_route_rejected(self):
        with self.assertRaises(ParseError):
            routing.normalize({"route": "maybe"})

    def test_defaults_and_clamping(self):
        parsed = routing.normalize({"route": "SIMPLE", "confidence": 3.5, "language": "kr"})
        self.assertEqual(parsed.route, "simple")
        self.assertEqual(parsed.confidence, 1.0)
        self.assertEqual(parsed.language, "other")

    def test_answers_accept_plain_strings(self):
        parsed = routing.normalize({"route": "simple", "answers": ["광합성", "엽록체"]})
        self.assertEqual([a.id for a in parsed.answers], ["1", "2"])
        self.assertEqual(parsed.answers[0].text, "광합성")

    def test_answers_drop_empty_text(self):
        parsed = routing.normalize({"route": "simple", "answers": [{"id": "1", "text": "  "}]})
        self.assertEqual(parsed.answers, [])

    def test_outline_from_multiline_string(self):
        parsed = routing.normalize({"route": "complex", "prompt": "x", "outline": "- a\n- b"})
        self.assertEqual(parsed.outline, ["a", "b"])

    def test_max_expected_chars_from_text(self):
        parsed = routing.normalize(
            {"route": "simple", "signals": {"max_expected_chars": "약 300자"}}
        )
        self.assertEqual(parsed.signals.max_expected_chars, 300)


class GuardTest(unittest.TestCase):
    def test_user_mode_overrides_model(self):
        result = routing.apply_guards(
            analysis(route="complex", confidence=0.99, prompt="write"),
            user_mode="simple",
        )
        self.assertEqual(result.route, "simple")
        self.assertTrue(result.guard_notes)

    def test_low_confidence_complex_falls_back_to_simple(self):
        result = routing.apply_guards(
            analysis(route="complex", confidence=0.3, prompt="write",
                     answers=[{"id": "1", "text": "42"}])
        )
        self.assertEqual(result.route, "simple")
        self.assertIsNone(result.prompt)

    def test_low_confidence_complex_kept_when_no_answers(self):
        result = routing.apply_guards(analysis(route="complex", confidence=0.3, prompt="write"))
        self.assertEqual(result.route, "complex")

    def test_writing_signal_with_long_expected_length_promotes(self):
        result = routing.apply_guards(
            analysis(
                route="simple",
                confidence=0.8,
                prompt="write it",
                answers=[{"id": "1", "text": "short"}],
                signals={"has_writing": True, "max_expected_chars": 400},
            )
        )
        self.assertEqual(result.route, "complex")
        self.assertEqual(result.answers, [])

    def test_short_writing_stays_simple(self):
        result = routing.apply_guards(
            analysis(
                route="simple",
                confidence=0.8,
                answers=[{"id": "1", "text": "재미있었다"}],
                signals={"has_writing": True, "max_expected_chars": 60},
            )
        )
        self.assertEqual(result.route, "simple")

    def test_empty_simple_with_writing_becomes_complex(self):
        result = routing.apply_guards(
            analysis(route="simple", confidence=0.7, prompt="write it",
                     signals={"has_writing": True})
        )
        self.assertEqual(result.route, "complex")

    def test_empty_simple_without_writing_becomes_unreadable(self):
        result = routing.apply_guards(analysis(route="simple", confidence=0.7))
        self.assertEqual(result.route, "unreadable")

    def test_complex_without_prompt_downgrades(self):
        result = routing.apply_guards(analysis(route="complex", confidence=0.9))
        self.assertEqual(result.route, "unreadable")

    def test_forced_complex_without_prompt_downgrades(self):
        result = routing.apply_guards(
            analysis(route="simple", confidence=0.9, answers=[{"id": "1", "text": "42"}]),
            user_mode="complex",
        )
        self.assertEqual(result.route, "unreadable")

    def test_simple_clears_prompt_fields(self):
        result = routing.apply_guards(
            analysis(route="simple", confidence=0.9, prompt="leftover",
                     answers=[{"id": "1", "text": "42"}])
        )
        self.assertIsNone(result.prompt)
        self.assertIsNone(result.outline)


class TextHelpersTest(unittest.TestCase):
    def test_answers_as_text_marks_uncertain(self):
        parsed = routing.normalize(
            {
                "route": "simple",
                "answers": [
                    {"id": "1", "text": "광합성"},
                    {"id": "2", "text": "미토콘드리아 / 엽록체", "uncertain": True},
                ],
            }
        )
        self.assertEqual(
            routing.answers_as_text(parsed),
            "1) 광합성\n2) 미토콘드리아 / 엽록체 (?)",
        )

    def test_to_dict_round_trips_route(self):
        parsed = routing.normalize({"route": "unreadable", "reason": "blurry_crop"})
        payload = routing.to_dict(parsed)
        self.assertEqual(payload["route"], "unreadable")
        self.assertEqual(payload["reason"], "blurry_crop")
        self.assertIn("signals", payload)


if __name__ == "__main__":
    unittest.main()
