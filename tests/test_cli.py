import io
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from subforge.cli import _read_cues, cmd_info


class CliInputTests(unittest.TestCase):
    def test_missing_input_file_gives_clear_error(self):
        with self.assertRaises(SystemExit) as ctx:
            _read_cues(Path("no-such-file.srt"))
        message = str(ctx.exception)
        self.assertIn("not found", message)
        self.assertIn("no-such-file.srt", message)

    def test_directory_as_input_gives_clear_error(self):
        with self.assertRaises(SystemExit) as ctx:
            _read_cues(Path("."))
        self.assertIn("cannot read input file", str(ctx.exception))

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
