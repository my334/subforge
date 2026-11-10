import io
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from subforge.cli import _read_cues, _write_cues, cmd_burn, cmd_info
from subforge.srt import Cue


class CliInputTests(unittest.TestCase):
    def test_missing_input_file_gives_clear_error(self):
        with self.assertRaises(SystemExit) as ctx:
            _read_cues(Path("no-such-file.srt"))
        message = str(ctx.exception)
        self.assertIn("not found", message)
        self.assertIn("no-such-file.srt", message)

    def test_non_utf8_input_gives_clear_error(self):
        # A GBK-encoded SRT (still common for Chinese subtitles) used to
        # crash with a raw UnicodeDecodeError traceback instead of a
        # usable message, like the other unreadable-input cases.
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "gbk.srt"
            path.write_bytes(
                "1\n00:00:01,000 --> 00:00:03,000\n你好世界\n".encode("gbk")
            )
            with self.assertRaises(SystemExit) as ctx:
                _read_cues(path)
        message = str(ctx.exception)
        self.assertIn("not valid UTF-8", message)
        self.assertIn("gbk.srt", message)

    def test_ssa_input_gives_clear_error(self):
        # .ssa is the older sibling of .ass and just as export-only; it
        # used to fall through to the SRT parser and silently parse to
        # zero cues, so a convert would quietly write an empty file.
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "subs.ssa"
            path.write_text(
                "[Script Info]\nTitle: x\n\n[Events]\n"
                "Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,Hello\n"
            )
            with self.assertRaises(SystemExit) as ctx:
                _read_cues(path)
        message = str(ctx.exception)
        self.assertIn("not supported", message)
        self.assertIn("SSA", message)

    def test_directory_as_input_gives_clear_error(self):
        with self.assertRaises(SystemExit) as ctx:
            _read_cues(Path("."))
        self.assertIn("cannot read input file", str(ctx.exception))

    def test_output_to_missing_directory_gives_clear_error(self):
        # The input side already reports unreadable files clearly, but an
        # unwritable output path used to surface as a raw traceback.
        with self.assertRaises(SystemExit) as ctx:
            _write_cues(
                Path("no-such-dir/out.srt"),
                [Cue(start=1.0, end=2.0, text="Hi")],
            )
        message = str(ctx.exception)
        self.assertIn("cannot write output file", message)
        self.assertIn("no-such-dir/out.srt", message)

    def test_burn_missing_subtitle_file_gives_clear_error(self):
        args = Namespace(
            input=Path("in.mp4"),
            subtitles=Path("no-such-subs.srt"),
            output=Path("out.mp4"),
        )
        with patch("subforge.cli._require_ffmpeg", return_value="ffmpeg"):
            with self.assertRaises(SystemExit) as ctx:
                cmd_burn(args)
        self.assertIn("not found", str(ctx.exception))
        self.assertIn("no-such-subs.srt", str(ctx.exception))

    def test_burn_stages_special_filename_for_ffmpeg(self):
        # A subtitle path with a quote and a colon used to be handed to
        # ffmpeg's filter parser verbatim and fail there; burn must instead
        # stage an identical copy under a safe name and clean it up.
        with tempfile.TemporaryDirectory() as tmpdir:
            subtitles = Path(tmpdir) / "it's: tricky.srt"
            content = "1\n00:00:00,000 --> 00:00:01,000\nHi\n"
            subtitles.write_text(content)
            args = Namespace(
                input=Path("in.mp4"), subtitles=subtitles, output=Path("out.mp4")
            )
            seen = {}

            def fake_run(cmd, check):
                vf = cmd[cmd.index("-vf") + 1]
                staged = Path(vf[len("subtitles='") : -1])
                seen["staged"] = staged
                seen["content"] = staged.read_text()
                self.assertNotEqual(staged, subtitles)
                self.assertNotIn("'", staged.name)
                self.assertNotIn(":", staged.name)

            with (
                patch("subforge.cli._require_ffmpeg", return_value="ffmpeg"),
                patch("subforge.cli.subprocess.run", side_effect=fake_run),
            ):
                self.assertEqual(cmd_burn(args), 0)
            self.assertEqual(seen["content"], content)
            self.assertFalse(seen["staged"].exists())

    def test_valid_input_does_not_warn(self):
        buf = io.StringIO()
        with patch("sys.stderr", buf):
            cues = _read_cues(Path("examples/sample.srt"))
        self.assertEqual(len(cues), 3)
        self.assertEqual(buf.getvalue(), "")

    def test_garbage_input_warns_about_zero_cues(self):
        # A file with no parseable cues used to flow silently into the
        # writing commands, which then wrote an empty output file and
        # reported success ("Converted 0 cues") — the same quiet
        # failure the .ssa guard already fixed for ASS input. A
        # warning on stderr flags the likely wrong file/format without
        # breaking scripts (exit code and output are unchanged).
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "garbage.srt"
            path.write_text(
                "This is not a subtitle file.\nJust some random text.\n"
            )
            buf = io.StringIO()
            with patch("sys.stderr", buf):
                cues = _read_cues(path)
        self.assertEqual(cues, [])
        self.assertIn("no subtitle cues found", buf.getvalue())
        self.assertIn("garbage.srt", buf.getvalue())

    def test_info_uses_full_time_span_for_unsorted_cues(self):
        # Cues out of chronological order: the first cue must not be
        # assumed to be the earliest.
        cues = _read_cues(Path("examples/sample.srt"))
        reversed_cues = list(reversed(cues))
        args = Namespace(input=Path("x.srt"), json=False)
        with patch("subforge.cli._read_cues", return_value=reversed_cues):
            buf = io.StringIO()
            with patch("sys.stdout", buf):
                self.assertEqual(cmd_info(args), 0)
        lines = dict(line.split(": ", 1) for line in buf.getvalue().splitlines())
        expected_start = min(c.start for c in cues)
        expected_end = max(c.end for c in cues)
        self.assertEqual(float(lines["starts_at"]), round(expected_start, 3))
        self.assertEqual(float(lines["ends_at"]), round(expected_end, 3))
        self.assertEqual(
            float(lines["duration_seconds"]),
            round(expected_end - expected_start, 3),
        )


if __name__ == "__main__":
    unittest.main()
