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


def scale_cues(cues: Iterable[Cue], factor: float) -> list[Cue]:
    """Multiply every timing by factor.

    Used for frame-rate conversion: a subtitle authored for a video at
    ``from_fps`` is retimed for ``to_fps`` with ``factor = from_fps / to_fps``.
    """

    if factor <= 0:
        raise ValueError("factor must be positive")
    return [replace(cue, start=cue.start * factor, end=cue.end * factor) for cue in cues]


def _split_text_chunks(text: str, parts: int, max_chars: int) -> list[str]:
    """Split text into about ``parts`` chunks, preferring word boundaries.

    Works for space-separated languages and for CJK text without spaces
    (falls back to character cuts when a single "word" is too long).

    ``max_chars`` caps each chunk when it is the driving limit; a value
    <= 0 disables the character rule (e.g. when the split is driven only
    by ``max_duration``) and the text is still divided into ``parts``
    roughly even chunks.
    """

    flat = " ".join(text.split())
    if parts <= 1 or not flat:
        return [flat] if flat else []
    target = max(1, len(flat) // parts)
    # Per-chunk hard ceiling: max_chars when it drives the split, otherwise
    # the target size itself (a duration-driven split of short text).
    ceiling = max_chars if max_chars > 0 else target
    chunks: list[str] = []
    rest = flat
    for _ in range(parts - 1):
        if not rest:
            break
        # Prefer a word boundary near the target size ...
        cut = rest.rfind(" ", 0, target + 1)
        if cut < target // 2 and ceiling > target:
            # ... but when max_chars drives the split, a later boundary up
            # to the ceiling is still better than a hard cut.
            cut = rest.rfind(" ", target + 1, min(len(rest), ceiling + 1))
        if cut < target // 2:  # no usable word boundary: hard cut (CJK etc.)
            cut = min(max(target, ceiling), len(rest))
            chunks.append(rest[:cut])
            rest = rest[cut:].lstrip()
        else:
            chunks.append(rest[:cut])
            rest = rest[cut + 1 :].lstrip()
    if rest:
        chunks.append(rest)
    # A long tail can remain if word boundaries were unfavourable; hard-split it.
    final: list[str] = []
    for chunk in chunks:
        while len(chunk) > ceiling * 2:
            final.append(chunk[:ceiling])
            chunk = chunk[ceiling:]
        final.append(chunk)
    return [c for c in final if c]


def split_cues(
    cues: Iterable[Cue],
    *,
    max_chars: int = 42,
    max_duration: float = 5.0,
) -> list[Cue]:
    """Split over-long cues into shorter ones (the classic "断句" step).

    A cue is split when its text exceeds ``max_chars`` characters or its
    duration exceeds ``max_duration`` seconds (when > 0). A ``max_chars``
    of 0 disables the character rule so the duration rule works on its own.
    The original time span is divided between the pieces in proportion to
    their text length.
    """

    result: list[Cue] = []
    for cue in cues:
        flat_len = len(" ".join(cue.text.split()))
        parts = 1
        if max_chars > 0 and flat_len > max_chars:
            parts = max(parts, -(-flat_len // max_chars))
        if max_duration > 0 and cue.duration > max_duration:
            parts = max(parts, int(cue.duration // max_duration) + 1)
        if parts <= 1:
            result.append(cue)
            continue
        chunks = _split_text_chunks(cue.text, parts, max_chars)
        if len(chunks) <= 1:
            result.append(cue)
            continue
        total = sum(len(c) for c in chunks) or 1
        span = cue.end - cue.start
        cursor = cue.start
        for i, chunk in enumerate(chunks):
            if i == len(chunks) - 1:
                piece_end = cue.end
            else:
                piece_end = cursor + span * (len(chunk) / total)
            result.append(Cue(start=cursor, end=piece_end, text=chunk))
            cursor = piece_end
    return result


def validate_cues(
    cues: Iterable[Cue],
    *,
    max_chars_per_line: int = 42,
    max_cps: float = 21.0,
    min_duration: float = 0.3,
    max_duration: float = 7.0,
) -> list[dict]:
    """Check cues for common quality problems; returns a list of issues.

    Each issue is a dict with ``cue`` (1-based position), ``level``
    ("error" or "warning"), ``kind`` and ``message``.
    """

    issues: list[dict] = []
    max_end_so_far = 0.0
    for pos, cue in enumerate(cues, start=1):
        def add(level: str, kind: str, message: str) -> None:
            issues.append({"cue": pos, "level": level, "kind": kind, "message": message})

        if not cue.text.strip():
            add("error", "empty", "cue has no text")
            continue
        if cue.end <= cue.start:
            add("error", "non_positive_duration", "end time is not after start time")
            continue
        if cue.start < max_end_so_far - 1e-9:
            add("warning", "overlap", "starts before a previous cue ends")
        max_end_so_far = max(max_end_so_far, cue.end)
        if cue.duration < min_duration:
            add("warning", "too_short", f"duration {cue.duration:.2f}s is below {min_duration}s")
        if cue.duration > max_duration:
            add("warning", "too_long", f"duration {cue.duration:.2f}s exceeds {max_duration}s")
        for line in cue.text.splitlines():
            if len(line) > max_chars_per_line:
                add("warning", "long_line", f"line has {len(line)} chars (limit {max_chars_per_line})")
                break
        chars = len(cue.text.replace("\n", ""))
        cps = chars / cue.duration if cue.duration > 0 else float("inf")
        if cps > max_cps:
            add("warning", "fast_cps", f"reading speed {cps:.1f} chars/s exceeds {max_cps}")
    return issues


def _format_ass_timestamp(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    total_cs = int(round(seconds * 100))
    hours, rem = divmod(total_cs, 360_000)
    minutes, rem = divmod(rem, 6_000)
    secs, cs = divmod(rem, 100)
    return f"{hours:d}:{minutes:02d}:{secs:02d}.{cs:02d}"


_ASS_HEADER = """[Script Info]
Title: SubForge export
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,48,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,2,0,2,10,10,30,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def write_ass(cues: Iterable[Cue]) -> str:
    """Write cues as a basic ASS/SSA file (default style, write-only export)."""

    lines = [_ASS_HEADER]
    for cue in cues:
        text = clean_text(cue.text).replace("\n", r"\N")
        lines.append(
            f"Dialogue: 0,{_format_ass_timestamp(cue.start)},{_format_ass_timestamp(cue.end)},Default,,0,0,0,,{text}"
        )
    return "\n".join(lines) + "\n"
