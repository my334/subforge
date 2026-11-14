# Changelog

All notable changes to SubForge are documented here.

## Unreleased

- **CLI** fix: a missing `.ass`/`.ssa` input file now reports "input file
  not found" instead of "ASS/SSA input is not supported yet" — the format
  guard ran before the file was read, so a mistyped filename looked like a
  format problem. A real `.ass`/`.ssa` file still reports the format as
  unsupported, as before.
- **`info`** fix: `info --json` on a file with no cues now prints valid
  JSON (`{"cues": 0, ...}` with null start/end) instead of plain text
  ("No cues found"), which broke scripts parsing stdout as JSON. The
  plain-text output is unchanged.
- **CLI** fix: reading a file that contains no parseable subtitle cues now
  prints a warning to stderr ("no subtitle cues found in ...") instead of
  silently writing an empty output file and reporting success ("Converted
  0 cues"). The exit code and output are unchanged — a genuinely empty
  subtitle file is still valid — but feeding the wrong file or format is
  now visible instead of quiet.
- **Writing** fix: blank lines inside cue text no longer survive into
  written SRT / WebVTT files. A blank line terminates a cue block, so
  writing such a cue out and reading it back silently dropped everything
  after the blank line; writers now collapse blank lines so the file
  round-trips losslessly.
- **Parsing** fix: timestamps with 100+ hours are now accepted. The writer
  already produced them for very long videos (e.g. `100:00:00,000`), but
  the parser's hour field only allowed 1-2 digits, so such a cue was
  silently dropped on re-parse instead of round-tripping.
- **`validate`** fix: overlap detection now checks real interval overlap
  against earlier cues instead of "starts before the latest end seen so
  far", so disjoint cues listed out of chronological order (e.g. 10-12s
  followed by 0-2s) are no longer falsely reported as overlapping, while
  genuinely overlapping pairs are still caught in either order.
- **`split`** fix: the `--max-duration` rule now actually splits cues whose
  text is shorter than `--max-chars` (previously such cues were never
  split, and `--max-chars 0` disabled splitting entirely). Word-boundary
  preference now favors cuts near the target chunk size, so
  duration-driven pieces come out roughly even.
- **`info`** fix: `starts_at` and `duration_seconds` now reflect the full
  time span (min start / max end) instead of assuming the first cue is the
  earliest, so unsorted cue files report correct statistics.

## 0.2.0 — 2026-10-21

Feature batch inspired by established subtitle tools (VideoLingo /
VideoCaptioner-style sentence splitting, ffsubsync-style sync work,
Subtitle Edit-style checking, Aegisub's ASS ecosystem):

- **`validate`** — new quality checker: reports overlaps, non-positive or
  extreme durations, over-long lines and reading-speed (chars/second)
  problems, with `--strict` and `--json` modes for scripting.
- **`split`** — new command that splits over-long cues into shorter ones
  (the classic 断句 step), preferring word boundaries, with proportional
  timing; works for CJK text without spaces too.
- **`fps`** — new command to retime subtitles between frame rates
  (e.g. 25 → 23.976), the standard fix when subtitles drift against a
  differently-encoded video.
- **`convert`** can now export **ASS** (`.ass`, basic default style,
  write-only for now).
- Unit tests grew from 4 to 9, covering all new behaviour.

## 0.1.0 — 2026-10-21

- Initial public release.
- Parse and write SRT / WebVTT, export plain text.
- `convert` / `shift` / `clean` / `info` commands; pure standard-library core.
- Optional `ffmpeg` helpers (`extract-audio`, `burn`) and optional
  `faster-whisper` transcription.
- Example subtitle, bilingual README, MIT license.
