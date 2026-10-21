"""Core subtitle parsing and writing helpers.

The core of SubForge intentionally uses only the Python standard library.
It understands SRT and WebVTT, can write SRT / WebVTT / plain text, shift
timings, and clean common caption problems such as HTML tags and overlaps.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import re
from typing import Iterable, List


_TIME_RE = re.compile(
    r"(?P<h>\d{1,2}):(?P<m>\d{2}):(?P<s>\d{2})[,.](?P<ms>\d{3})"
)
_TIMING_RE = re.compile(
    r"(?P<start>\d{1,2}:\d{2}:\d{2}[,.]\d{3})\s+-->\s+"
    r"(?P<end>\d{1,2}:\d{2}:\d{2}[,.]\d{3})(?:\s+.*)?$"
)
_TAG_RE = re.compile(r"<[^>]+>|\{\\[^}]+\}|\{[^}]+\}")


@dataclass
class Cue:
    """One subtitle cue."""

    start: float  # seconds
    end: float  # seconds
    text: str
    index: int | None = None

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


def parse_timestamp(value: str) -> float:
    """Parse HH:MM:SS,mmm or HH:MM:SS.mmm into seconds."""

    match = _TIME_RE.fullmatch(value.strip())
    if not match:
        raise ValueError(f"Invalid timestamp: {value!r}")
    hours = int(match.group("h"))
    minutes = int(match.group("m"))
    seconds = int(match.group("s"))
    millis = int(match.group("ms"))
    return hours * 3600 + minutes * 60 + seconds + millis / 1000


def format_timestamp(seconds: float, *, vtt: bool = False) -> str:
    """Format seconds as HH:MM:SS,mmm (SRT) or HH:MM:SS.mmm (VTT)."""

    if seconds < 0:
        seconds = 0.0
    total_ms = int(round(seconds * 1000))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    sep = "." if vtt else ","
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{sep}{millis:03d}"


def _parse_blocks(text: str) -> list[list[str]]:
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []
    return [block.splitlines() for block in re.split(r"\n\s*\n", text) if block.strip()]


def parse_srt(text: str) -> list[Cue]:
    """Parse SRT content into cues."""

    cues: list[Cue] = []
    for lines in _parse_blocks(text):
        if not lines:
            continue
        timing_pos = None
        for i, line in enumerate(lines):
            if "-->" in line:
                timing_pos = i
                break
        if timing_pos is None:
            continue
        match = _TIMING_RE.match(lines[timing_pos].strip())
        if not match:
            continue
        index = None
        if timing_pos > 0:
            maybe_index = lines[0].strip()
            if maybe_index.isdigit():
                index = int(maybe_index)
        cues.append(
            Cue(
                start=parse_timestamp(match.group("start")),
                end=parse_timestamp(match.group("end")),
                text="\n".join(lines[timing_pos + 1 :]).strip(),
                index=index,
            )
        )
    return cues


def parse_vtt(text: str) -> list[Cue]:
    """Parse WebVTT content into cues.

    NOTE blocks and cue settings are ignored; cue identifiers are accepted
    but not preserved because SRT has no equivalent field.
    """

    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if text.startswith("WEBVTT"):
        # Drop the header line (and optional header metadata lines up to the
        # first blank line) before the generic block parser sees it.
        parts = re.split(r"\n\s*\n", text, maxsplit=1)
        text = parts[1] if len(parts) == 2 else ""

    cues: list[Cue] = []
    for lines in _parse_blocks(text):
        if not lines or lines[0].startswith("NOTE"):
            continue
        timing_pos = None
        for i, line in enumerate(lines):
            if "-->" in line:
                timing_pos = i
                break
        if timing_pos is None:
            continue
        match = _TIMING_RE.match(lines[timing_pos].strip())
        if not match:
            continue
        cues.append(
            Cue(
                start=parse_timestamp(match.group("start")),
                end=parse_timestamp(match.group("end")),
                text="\n".join(lines[timing_pos + 1 :]).strip(),
            )
        )
    return cues


def write_srt(cues: Iterable[Cue]) -> str:
    blocks = []
    for i, cue in enumerate(cues, start=1):
        blocks.append(
            f"{i}\n{format_timestamp(cue.start)} --> {format_timestamp(cue.end)}\n{cue.text.strip()}"
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def write_vtt(cues: Iterable[Cue]) -> str:
    blocks = ["WEBVTT"]
    for cue in cues:
        blocks.append(
            f"{format_timestamp(cue.start, vtt=True)} --> {format_timestamp(cue.end, vtt=True)}\n{cue.text.strip()}"
        )
    return "\n\n".join(blocks) + "\n"


def write_txt(cues: Iterable[Cue]) -> str:
    lines = [cue.text.strip().replace("\n", " ") for cue in cues if cue.text.strip()]
    return "\n".join(lines) + ("\n" if lines else "")


def shift_cues(cues: Iterable[Cue], offset_seconds: float) -> list[Cue]:
    """Return cues shifted by offset_seconds; cues ending before 0 are dropped."""

    shifted: list[Cue] = []
    for cue in cues:
        start = cue.start + offset_seconds
        end = cue.end + offset_seconds
        if end <= 0:
            continue
        shifted.append(replace(cue, start=max(0.0, start), end=end))
    return shifted


def clean_text(text: str) -> str:
    """Remove HTML/ASS tags and normalize whitespace inside one cue."""

    text = _TAG_RE.sub("", text)
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def clean_cues(cues: Iterable[Cue], *, fix_overlaps: bool = True, min_duration: float = 0.4) -> list[Cue]:
    """Clean cue text, drop empties, optionally repair overlaps."""

    cleaned: list[Cue] = []
    for cue in cues:
        text = clean_text(cue.text)
        if not text:
            continue
        end = cue.end
        if end <= cue.start:
            end = cue.start + min_duration
        cleaned.append(replace(cue, text=text, end=end))

    cleaned.sort(key=lambda c: (c.start, c.end))
    if fix_overlaps:
        for prev, cur in zip(cleaned, cleaned[1:]):
            if cur.start < prev.end:
                cur.start = prev.end
                if cur.end <= cur.start:
                    cur.end = cur.start + min_duration
    return cleaned
