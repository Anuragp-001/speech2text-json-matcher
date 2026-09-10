import unittest

from matcher import comparison_metrics, extract_reference, choose_mode


class MatchingTests(unittest.TestCase):
    def test_identical_transcript_scores_100(self):
        metrics = comparison_metrics("Hello, world!", "hello world")
        self.assertEqual(metrics["matchScore"], 100.0)
        self.assertEqual(metrics["wordAccuracy"], 100.0)
        self.assertEqual(metrics["wer"], 0.0)

    def test_extra_word_reduces_score(self):
        metrics = comparison_metrics("hello world", "hello brave world")
        self.assertLess(metrics["matchScore"], 100.0)
        self.assertGreater(metrics["wer"], 0.0)

    def test_timestamp_json_extracts(self):
        payload = [
            {"start_time": 0.0, "end_time": 1.0, "speaker_type": "owner", "transcript": "hello"},
            {"start_time": 1.0, "end_time": 2.0, "speaker_type": "client", "transcript": "there"},
        ]
        text, segments = extract_reference(payload)
        self.assertEqual(text, "hello there")
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0]["speaker"], "owner")

    def test_auto_mode_for_romanized_text(self):
        self.assertEqual(choose_mode("haan main theek hun"), "translit")

    def test_auto_mode_for_devanagari(self):
        self.assertEqual(choose_mode("हाँ मैं ठीक हूँ"), "transcribe")


if __name__ == "__main__":
    unittest.main()
