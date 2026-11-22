import io
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from subforge.cli import (
    _read_cues,
    _write_cues,
    cmd_burn,
    cmd_clean,
    cmd_extract_audio,
    cmd_fps,
    cmd_info,
    cmd_shift,
    cmd_split,
    cmd_transcribe,
    cmd_validate,
)
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

    def test_missing_ass_input_reports_not_found_not_unsupported(self):
        # The ASS/SSA guard used to run before the file was read, so a
        # mistyped .ass filename reported "not supported" instead of
        # "not found" and looked like a format problem.
        for name in ("no-such-file.ass", "no-such-file.ssa"):
            with self.assertRaises(SystemExit) as ctx:
                _read_cues(Path(name))
            message = str(ctx.exception)
            self.assertIn("not found", message)
            self.assertIn(name, message)

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
            video = Path(tmpdir) / "in.mp4"
            video.write_bytes(b"fake video")
            args = Namespace(
                input=video, subtitles=subtitles, output=Path("out.mp4")
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

    def test_extract_audio_missing_input_gives_clear_error(self):
        # A mistyped video path used to be handed straight to ffmpeg,
        # which dumped its full startup banner and ended with a cryptic
        # "Command failed with exit code 254". The missing file must be
        # reported up front, and ffmpeg must never be invoked.
        args = Namespace(input=Path("no-such-video.mp4"), output=Path("out.wav"))
        with (
            patch("subforge.cli._require_ffmpeg", return_value="ffmpeg"),
            patch("subforge.cli.subprocess.run") as fake_run,
        ):
            with self.assertRaises(SystemExit) as ctx:
                cmd_extract_audio(args)
        self.assertIn("not found", str(ctx.exception))
        self.assertIn("no-such-video.mp4", str(ctx.exception))
        fake_run.assert_not_called()

    def test_burn_missing_input_video_gives_clear_error(self):
        # Same mistyped-path problem as extract-audio; the subtitle check
        # already existed, the video check did not. A real subtitle file
        # is used so the failure is about the video, not the subtitles.
        with tempfile.TemporaryDirectory() as tmpdir:
            subtitles = Path(tmpdir) / "subs.srt"
            subtitles.write_text("1\n00:00:00,000 --> 00:00:01,000\nHi\n")
            args = Namespace(
                input=Path("no-such-video.mp4"),
                subtitles=subtitles,
                output=Path("out.mp4"),
            )
            with (
                patch("subforge.cli._require_ffmpeg", return_value="ffmpeg"),
                patch("subforge.cli.subprocess.run") as fake_run,
            ):
                with self.assertRaises(SystemExit) as ctx:
                    cmd_burn(args)
            self.assertIn("not found", str(ctx.exception))
            self.assertIn("no-such-video.mp4", str(ctx.exception))
            fake_run.assert_not_called()

    def test_transcribe_missing_input_gives_clear_error(self):
        # The input check runs before the faster-whisper import and the
        # model load, so a typo fails fast instead of after the model
        # was loaded — and the error is about the file, not the extra.
        args = Namespace(
            input=Path("no-such-audio.wav"),
            output=Path("out.srt"),
            model="small",
            language="",
        )
        with self.assertRaises(SystemExit) as ctx:
            cmd_transcribe(args)
        self.assertIn("not found", str(ctx.exception))
        self.assertIn("no-such-audio.wav", str(ctx.exception))

    def test_clean_negative_min_duration_gives_clear_error(self):        # clean --min-duration -1 used to run and write a cue whose end
        # was before its start; it must fail up front with a usable
        # message instead of producing a file validate would reject.
        args = Namespace(
            input=Path("examples/sample.srt"),
            output=Path("out.srt"),
            keep_overlaps=False,
            min_duration=-1,
        )
        with self.assertRaises(SystemExit) as ctx:
            cmd_clean(args)
        self.assertIn("min-duration", str(ctx.exception))

    def test_split_negative_limits_give_clear_error(self):
        # split --max-chars -5 / --max-duration -1 used to be accepted
        # and silently behave like "disabled" (0 disables a rule, so a
        # negative limit can only be a typo): the command then split
        # nothing and still reported success. Like clean and fps, it
        # must fail up front with a usable message instead.
        for kwargs in (
            {"max_chars": -1, "max_duration": 5.0},
            {"max_chars": 42, "max_duration": -1.0},
        ):
            args = Namespace(
                input=Path("examples/sample.srt"),
                output=Path("out.srt"),
                **kwargs,
            )
            with self.assertRaises(SystemExit) as ctx:
                cmd_split(args)
            message = str(ctx.exception)
            self.assertIn("must not be negative", message)

    def test_validate_non_positive_limits_give_clear_error(self):
        # validate --max-cps -5 / --max-chars-per-line 0 used to be
        # accepted and then flag every cue (a 3.7 chars/s cue was
        # reported as too fast at a -5 limit): like clean and split,
        # it must fail up front with a usable message instead.
        for kwargs in (
            {"max_chars_per_line": 0, "max_cps": 21.0},
            {"max_chars_per_line": 42, "max_cps": -5.0},
        ):
            args = Namespace(
                input=Path("examples/sample.srt"),
                strict=False,
                json=False,
                **kwargs,
            )
            with self.assertRaises(SystemExit) as ctx:
                cmd_validate(args)
            self.assertIn("must be positive", str(ctx.exception))

    def test_non_finite_numeric_options_give_clear_error(self):
        # argparse accepts "nan" and "inf" as floats, and the limit
        # checks only compare against 0, so such values used to sail
        # through: --seconds inf crashed in format_timestamp with a
        # raw OverflowError traceback, --min-duration nan poisoned a
        # zero-duration cue into a NaN end time, and --max-duration /
        # --max-cps nan silently disabled the rule. All five float
        # options must now fail up front with a usable message.
        cases = [
            (
                cmd_shift,
                Namespace(
                    input=Path("examples/sample.srt"),
                    output=Path("out.srt"),
                    seconds=float("inf"),
                ),
            ),
            (
                cmd_shift,
                Namespace(
                    input=Path("examples/sample.srt"),
                    output=Path("out.srt"),
                    seconds=float("nan"),
                ),
            ),
            (
                cmd_clean,
                Namespace(
                    input=Path("examples/sample.srt"),
                    output=Path("out.srt"),
                    keep_overlaps=False,
                    min_duration=float("nan"),
                ),
            ),
            (
                cmd_fps,
                Namespace(
                    input=Path("examples/sample.srt"),
                    output=Path("out.srt"),
                    from_fps=float("inf"),
                    to_fps=25.0,
                ),
            ),
            (
                cmd_fps,
                Namespace(
                    input=Path("examples/sample.srt"),
                    output=Path("out.srt"),
                    from_fps=25.0,
                    to_fps=float("nan"),
                ),
            ),
            (
                cmd_split,
                Namespace(
                    input=Path("examples/sample.srt"),
                    output=Path("out.srt"),
                    max_chars=42,
                    max_duration=float("nan"),
                ),
            ),
            (
                cmd_validate,
                Namespace(
                    input=Path("examples/sample.srt"),
                    max_chars_per_line=42,
                    max_cps=float("inf"),
                    strict=False,
                    json=False,
                ),
            ),
        ]
        for func, args in cases:
            with self.assertRaises(SystemExit) as ctx:
                func(args)
            self.assertIn("must be a finite number", str(ctx.exception))

    def test_fps_extreme_rates_give_clear_error(self):
        # Two finite frame rates can still overflow their ratio
        # (1e308 / 1e-308 -> inf) or underflow it to zero (1e-308 /
        # 1e308); scale_cues then raised a raw ValueError traceback
        # instead of a usable message.
        for from_fps, to_fps in ((1e308, 1e-308), (1e-308, 1e308)):
            args = Namespace(
                input=Path("examples/sample.srt"),
                output=Path("out.srt"),
                from_fps=from_fps,
                to_fps=to_fps,
            )
            with self.assertRaises(SystemExit) as ctx:
                cmd_fps(args)
            self.assertIn("retiming factor", str(ctx.exception))

    def test_split_tiny_max_duration_gives_clear_error(self):
        # --max-duration 1e-308 on a multi-second cue overflowed the
        # piece count and crashed with a raw OverflowError traceback.
        args = Namespace(
            input=Path("examples/sample.srt"),
            output=Path("out.srt"),
            max_chars=42,
            max_duration=1e-308,
        )
        with self.assertRaises(SystemExit) as ctx:
            cmd_split(args)
        self.assertIn("too small", str(ctx.exception))

    def test_split_zero_limits_still_disable_rules(self):
        # 0 still means "that rule is off": with both rules off the
        # file passes through unchanged instead of erroring.
        args = Namespace(
            input=Path("examples/sample.srt"),
            output=Path("out.srt"),
            max_chars=0,
            max_duration=0,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "out.srt"
            args.output = out
            self.assertEqual(cmd_split(args), 0)
            self.assertEqual(len(_read_cues(out)), 3)

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

    def test_info_json_on_empty_file_is_still_json(self):
        # info --json on a file with no cues used to print plain text
        # ("No cues found"), which broke scripts parsing stdout as
        # JSON — exactly the empty files --json exists to handle.
        # The plain-text form is unchanged; only --json emits JSON.
        args = Namespace(input=Path("x.srt"), json=True)
        with patch("subforge.cli._read_cues", return_value=[]):
            buf = io.StringIO()
            with patch("sys.stdout", buf):
                self.assertEqual(cmd_info(args), 0)
        data = json.loads(buf.getvalue())
        self.assertEqual(data["cues"], 0)
        self.assertIsNone(data["starts_at"])
        self.assertIsNone(data["ends_at"])
        self.assertEqual(data["duration_seconds"], 0.0)

    def test_info_plain_text_on_empty_file_unchanged(self):
        args = Namespace(input=Path("x.srt"), json=False)
        with patch("subforge.cli._read_cues", return_value=[]):
            buf = io.StringIO()
            with patch("sys.stdout", buf):
                self.assertEqual(cmd_info(args), 0)
        self.assertEqual(buf.getvalue().strip(), "No cues found")

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
