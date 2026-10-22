import unittest
from pathlib import Path

from subforge.cli import _read_cues


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


if __name__ == "__main__":
    unittest.main()
