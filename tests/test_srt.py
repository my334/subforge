import unittest

from subforge.srt import (
    Cue,
    clean_cues,
    parse_srt,
    parse_timestamp,
    parse_vtt,
    scale_cues,
    shift_cues,
    split_cues,
    validate_cues,
    write_ass,
    write_srt,
    write_vtt,
)


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

    def test_parse_vtt_without_blank_line_after_header(self):
        # A cue directly after the WEBVTT header (no blank line) used to
        # be discarded along with the header; only the header line is
        # dropped now.
        cues = parse_vtt("WEBVTT\n00:00:01,000 --> 00:00:03,000\nHello world\n")
        self.assertEqual(len(cues), 1)
        self.assertEqual(cues[0].text, "Hello world")
        self.assertEqual(cues[0].start, 1.0)

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

    def test_scale_cues_for_fps_conversion(self):
        cues = parse_srt(SAMPLE_SRT)
        scaled = scale_cues(cues, 2.0)
        self.assertEqual(scaled[0].start, 2.0)
        self.assertEqual(scaled[0].end, 7.0)
        identity = scale_cues(cues, 25 / 25)
        self.assertEqual(identity[1].start, cues[1].start)

    def test_split_long_cue_keeps_timing_span(self):
        long_text = " ".join(["word"] * 30)  # 149 chars
        cue = Cue(start=10.0, end=16.0, text=long_text)
        pieces = split_cues([cue], max_chars=30, max_duration=0)
        self.assertGreaterEqual(len(pieces), 4)
        self.assertEqual(pieces[0].start, 10.0)
        self.assertEqual(pieces[-1].end, 16.0)
        for prev, cur in zip(pieces, pieces[1:]):
            self.assertAlmostEqual(prev.end, cur.start, places=6)
        for piece in pieces:
            self.assertLessEqual(len(piece.text), 34)  # max_chars + one word

    def test_split_cjk_text_without_spaces(self):
        cue = Cue(start=0.0, end=6.0, text="这是一个没有空格的长句子用来测试中文断句功能是否正常工作")
        pieces = split_cues([cue], max_chars=10, max_duration=0)
        self.assertGreaterEqual(len(pieces), 3)
        self.assertEqual("".join(p.text for p in pieces), cue.text)

    def test_validate_reports_overlap_and_errors(self):
        issues = validate_cues(parse_srt(SAMPLE_SRT))
        kinds = {i["kind"] for i in issues}
        self.assertIn("overlap", kinds)  # cue 2 starts at 3.25, cue 1 ends at 3.5
        bad = validate_cues([Cue(start=1.0, end=1.0, text="x"), Cue(start=2.0, end=3.0, text="  ")])
        levels = {(i["cue"], i["level"]) for i in bad}
        self.assertIn((1, "error"), levels)
        self.assertIn((2, "error"), levels)

    def test_validate_no_false_overlap_for_unsorted_disjoint_cues(self):
        # Disjoint cues out of chronological order must not be reported
        # as overlapping (the old max-end-so-far check did exactly that),
        # while a genuinely overlapping pair is still caught in either order.
        disjoint = validate_cues(
            [Cue(start=10.0, end=12.0, text="later"), Cue(start=0.0, end=2.0, text="earlier")]
        )
        self.assertNotIn("overlap", {i["kind"] for i in disjoint})
        reversed_overlap = validate_cues(
            [Cue(start=6.0, end=9.0, text="b"), Cue(start=5.0, end=8.0, text="a")]
        )
        self.assertIn("overlap", {i["kind"] for i in reversed_overlap})

    def test_split_by_duration_with_short_text(self):
        # Duration-driven split must work even when the text is shorter
        # than max_chars (previously it silently produced a single chunk).
        cue = Cue(start=0.0, end=11.0, text=" ".join(["word"] * 6))  # 30 chars
        pieces = split_cues([cue], max_chars=42, max_duration=5.0)
        self.assertGreaterEqual(len(pieces), 2)
        self.assertEqual(pieces[0].start, 0.0)
        self.assertEqual(pieces[-1].end, 11.0)
        for prev, cur in zip(pieces, pieces[1:]):
            self.assertAlmostEqual(prev.end, cur.start, places=6)
        self.assertEqual(
            " ".join(p.text for p in pieces), " ".join(cue.text.split())
        )

    def test_split_by_duration_with_max_chars_disabled(self):
        cue = Cue(start=0.0, end=11.0, text="这是一个没有空格的长句子用来测试中文断句功能是否正常工作")
        pieces = split_cues([cue], max_chars=0, max_duration=5.0)
        self.assertGreaterEqual(len(pieces), 2)
        self.assertEqual(pieces[0].start, 0.0)
        self.assertEqual(pieces[-1].end, 11.0)
        self.assertEqual("".join(p.text for p in pieces), cue.text)

    def test_parse_timestamp_rejects_out_of_range_fields(self):
        self.assertEqual(parse_timestamp("00:59:59,999"), 3599.999)
        for bad in ("00:60:00,000", "00:75:00,000", "00:00:60,000", "00:00:90,500"):
            with self.assertRaises(ValueError):
                parse_timestamp(bad)

    def test_parse_timestamp_accepts_three_digit_hours(self):
        # format_timestamp already writes 100+ hours for very long videos,
        # but the parser only accepted 1-2 digit hours, so such a cue was
        # silently dropped on re-parse instead of round-tripping.
        self.assertEqual(parse_timestamp("100:00:00,000"), 360000.0)
        cues = parse_srt("1\n100:00:00,000 --> 100:00:02,500\nLong stream\n")
        self.assertEqual(len(cues), 1)
        self.assertEqual(cues[0].start, 360000.0)
        self.assertEqual(cues[0].end, 360002.5)
        self.assertEqual(
            parse_srt(write_srt(cues))[0].start, cues[0].start
        )

    def test_parse_srt_skips_cue_with_out_of_range_timestamp(self):
        text = (
            "1\n00:75:00,000 --> 00:00:05,000\nBad cue\n\n"
            "2\n00:00:06,000 --> 00:00:08,000\nGood cue\n"
        )
        cues = parse_srt(text)
        self.assertEqual(len(cues), 1)
        self.assertEqual(cues[0].text, "Good cue")

    def test_parse_vtt_accepts_short_mm_ss_timestamps(self):
        # WebVTT allows MM:SS.mmm for cues under one hour; such cues used
        # to be silently dropped because the timing regex required hours.
        cues = parse_vtt("WEBVTT\n\n00:01.000 --> 00:03.500\nHello short\n")
        self.assertEqual(len(cues), 1)
        self.assertEqual(cues[0].start, 1.0)
        self.assertEqual(cues[0].end, 3.5)
        self.assertEqual(cues[0].text, "Hello short")
        self.assertEqual(parse_timestamp("01:02.500"), 62.5)
        # Short-form cues still round-trip through the (HH:MM:SS) writer.
        reparsed = parse_vtt(write_vtt(cues))
        self.assertEqual(reparsed[0].start, 1.0)
        self.assertEqual(reparsed[0].end, 3.5)

    def test_write_ass(self):
        out = write_ass(parse_srt(SAMPLE_SRT))
        self.assertIn("[Events]", out)
        self.assertIn("Dialogue: 0,0:00:01.00,0:00:03.50,Default", out)
        self.assertIn("Hello world.", out)  # tags stripped by clean_text


if __name__ == "__main__":
    unittest.main()
