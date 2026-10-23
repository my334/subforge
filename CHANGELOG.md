# Changelog

All notable changes to SubForge are documented here.

## Unreleased

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
