import unittest

from subforge.srt import clean_cues, parse_srt, parse_vtt, shift_cues, write_srt, write_vtt


SAMPLE_SRT = """1
00:00:01,000 --> 00:00:03,500
Hello <i>world</i>.

2
00:00:03,250 --> 00:00:05,000
Second line
"""


class SubtitleTests(unittest.TestCase):
    def test_parse_and_write_srt(self):
        cues = parse_srt(SAMPLE_SRT)
        self.assertEqual(len(cues), 2)
        self.assertEqual(cues[0].start, 1.0)
        self.assertEqual(cues[0].end, 3.5)
        out = write_srt(cues)
        self.assertIn("00:00:01,000 --> 00:00:03,500", out)

    def test_vtt_round_trip(self):
        cues = parse_srt(SAMPLE_SRT)
        vtt = write_vtt(cues)
        self.assertTrue(vtt.startswith("WEBVTT"))
        parsed = parse_vtt(vtt)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[1].text, "Second line")

    def test_shift_drops_finished_cues(self):
        cues = parse_srt(SAMPLE_SRT)
        shifted = shift_cues(cues, -2.0)
        self.assertEqual(len(shifted), 2)
        self.assertEqual(shifted[0].start, 0.0)
        self.assertEqual(shifted[0].end, 1.5)

    def test_clean_removes_tags_and_repairs_overlap(self):
        cues = clean_cues(parse_srt(SAMPLE_SRT))
        self.assertEqual(cues[0].text, "Hello world.")
        self.assertGreaterEqual(cues[1].start, cues[0].end)


if __name__ == "__main__":
    unittest.main()
