"""Command line interface for SubForge."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

from .srt import (
    Cue,
    clean_cues,
    parse_srt,
    parse_vtt,
    scale_cues,
    shift_cues,
    split_cues,
    validate_cues,
    write_ass,
    write_srt,
    write_txt,
    write_vtt,
)


def _read_cues(path: Path) -> list[Cue]:
    suffix = path.suffix.lower()
    if suffix == ".ass":
        raise SystemExit("ASS input is not supported yet (ASS is an export-only format for now).")
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        raise SystemExit(f"Error: input file not found: {path}") from None
    except OSError as exc:
        detail = exc.strerror or str(exc)
        raise SystemExit(f"Error: cannot read input file {path}: {detail}") from None
    if suffix == ".vtt":
        return parse_vtt(text)
    if suffix == ".srt":
        return parse_srt(text)
    # Be forgiving for files shared without a helpful extension.
    cues = parse_srt(text)
    return cues if cues else parse_vtt(text)


def _write_cues(path: Path, cues: list[Cue]) -> None:
    suffix = path.suffix.lower()
    if suffix == ".srt":
        content = write_srt(cues)
    elif suffix == ".vtt":
        content = write_vtt(cues)
    elif suffix == ".txt":
        content = write_txt(cues)
    elif suffix == ".ass":
        content = write_ass(cues)
    else:
        raise SystemExit("Output must end in .srt, .vtt, .txt, or .ass")
    try:
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        # Mirror the clear input-file errors: an unwritable output path
        # (missing parent directory, a directory, no permission) used to
        # surface as a raw traceback instead of a usable message.
        detail = exc.strerror or str(exc)
        raise SystemExit(f"Error: cannot write output file {path}: {detail}") from None


def _require_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("ffmpeg was not found. Install ffmpeg first, then retry this command.")
    return ffmpeg


def cmd_convert(args: argparse.Namespace) -> int:
    cues = _read_cues(args.input)
    _write_cues(args.output, cues)
    print(f"Converted {len(cues)} cues -> {args.output}")
    return 0


def cmd_shift(args: argparse.Namespace) -> int:
    cues = shift_cues(_read_cues(args.input), args.seconds)
    _write_cues(args.output, cues)
    print(f"Shifted {len(cues)} cues by {args.seconds:+.3f}s -> {args.output}")
    return 0


def cmd_clean(args: argparse.Namespace) -> int:
    cues = clean_cues(
        _read_cues(args.input),
        fix_overlaps=not args.keep_overlaps,
        min_duration=args.min_duration,
    )
    _write_cues(args.output, cues)
    print(f"Cleaned {len(cues)} cues -> {args.output}")
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    cues = _read_cues(args.input)
    if not cues:
        print("No cues found")
        return 0
    total_chars = sum(len(cue.text.replace("\n", "")) for cue in cues)
    # Use the full span, not the first cue: input cues are not guaranteed to
    # be in chronological order.
    starts_at = min(cue.start for cue in cues)
    ends_at = max(cue.end for cue in cues)
    data = {
        "cues": len(cues),
        "starts_at": round(starts_at, 3),
        "ends_at": round(ends_at, 3),
        "duration_seconds": round(ends_at - starts_at, 3),
        "average_chars_per_cue": round(total_chars / len(cues), 2),
    }
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        for key, value in data.items():
            print(f"{key}: {value}")
    return 0


def cmd_fps(args: argparse.Namespace) -> int:
    if args.from_fps <= 0 or args.to_fps <= 0:
        raise SystemExit("Frame rates must be positive numbers")
    factor = args.from_fps / args.to_fps
    cues = scale_cues(_read_cues(args.input), factor)
    _write_cues(args.output, cues)
    print(f"Retimed {len(cues)} cues from {args.from_fps} fps to {args.to_fps} fps (x{factor:.6f}) -> {args.output}")
    return 0


def cmd_split(args: argparse.Namespace) -> int:
    cues = split_cues(
        _read_cues(args.input),
        max_chars=args.max_chars,
        max_duration=args.max_duration,
    )
    _write_cues(args.output, cues)
    print(f"Split into {len(cues)} cues -> {args.output}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    cues = _read_cues(args.input)
    issues = validate_cues(
        cues,
        max_chars_per_line=args.max_chars_per_line,
        max_cps=args.max_cps,
    )
    if args.json:
        print(json.dumps({"cues": len(cues), "issues": issues}, ensure_ascii=False, indent=2))
    elif not issues:
        print(f"OK: {len(cues)} cues, no issues found")
    else:
        for issue in issues:
            print(f"cue {issue['cue']}: [{issue['level']}] {issue['kind']} - {issue['message']}")
        errors = sum(1 for i in issues if i["level"] == "error")
        print(f"{len(issues)} issue(s): {errors} error(s), {len(issues) - errors} warning(s)")
    has_error = any(i["level"] == "error" for i in issues)
    if has_error or (args.strict and issues):
        return 1
    return 0


def cmd_extract_audio(args: argparse.Namespace) -> int:
    ffmpeg = _require_ffmpeg()
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(args.input),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        str(args.output),
    ]
    subprocess.run(cmd, check=True)
    print(f"Extracted audio -> {args.output}")
    return 0


def cmd_burn(args: argparse.Namespace) -> int:
    ffmpeg = _require_ffmpeg()
    subtitle_path = str(args.subtitles).replace("'", "'\\''")
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(args.input),
        "-vf",
        f"subtitles='{subtitle_path}'",
        "-c:a",
        "copy",
        str(args.output),
    ]
    subprocess.run(cmd, check=True)
    print(f"Burned subtitles -> {args.output}")
    return 0


def cmd_transcribe(args: argparse.Namespace) -> int:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise SystemExit(
            "faster-whisper is not installed. Install the optional extra: "
            "pip install 'subforge[whisper]'"
        )

    model = WhisperModel(args.model, device="auto", compute_type="auto")
    segments, _info = model.transcribe(
        str(args.input),
        language=args.language or None,
        vad_filter=True,
    )
    cues = [
        Cue(start=float(seg.start), end=float(seg.end), text=seg.text.strip())
        for seg in segments
        if seg.text.strip()
    ]
    _write_cues(args.output, cues)
    print(f"Transcribed {len(cues)} cues -> {args.output}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="subforge", description="Video subtitle toolkit")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("convert", help="Convert between SRT, VTT and TXT")
    p.add_argument("input", type=Path)
    p.add_argument("output", type=Path)
    p.set_defaults(func=cmd_convert)

    p = sub.add_parser("shift", help="Shift all subtitle timings by seconds")
    p.add_argument("input", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--seconds", type=float, required=True, help="Example: 1.5 or -0.75")
    p.set_defaults(func=cmd_shift)

    p = sub.add_parser("clean", help="Remove tags, empty cues and repair overlaps")
    p.add_argument("input", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--keep-overlaps", action="store_true")
    p.add_argument("--min-duration", type=float, default=0.4)
    p.set_defaults(func=cmd_clean)

    p = sub.add_parser("info", help="Show basic statistics for a subtitle file")
    p.add_argument("input", type=Path)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("fps", help="Retime subtitles between frame rates (e.g. 25 -> 23.976)")
    p.add_argument("input", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--from-fps", type=float, required=True)
    p.add_argument("--to-fps", type=float, required=True)
    p.set_defaults(func=cmd_fps)

    p = sub.add_parser("split", help="Split over-long cues into shorter ones")
    p.add_argument("input", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--max-chars", type=int, default=42, help="0 disables the character rule")
    p.add_argument("--max-duration", type=float, default=5.0, help="Seconds; 0 disables the duration rule")
    p.set_defaults(func=cmd_split)

    p = sub.add_parser("validate", help="Check subtitles for overlaps, timing and readability problems")
    p.add_argument("input", type=Path)
    p.add_argument("--max-chars-per-line", type=int, default=42)
    p.add_argument("--max-cps", type=float, default=21.0, help="Max reading speed in chars/second")
    p.add_argument("--strict", action="store_true", help="Exit non-zero on warnings too")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("extract-audio", help="Extract 16kHz mono audio with ffmpeg")
    p.add_argument("input", type=Path)
    p.add_argument("output", type=Path)
    p.set_defaults(func=cmd_extract_audio)

    p = sub.add_parser("burn", help="Burn subtitles into a video with ffmpeg")
    p.add_argument("input", type=Path, help="Input video")
    p.add_argument("subtitles", type=Path, help="SRT/VTT subtitle file")
    p.add_argument("output", type=Path, help="Output video")
    p.set_defaults(func=cmd_burn)

    p = sub.add_parser("transcribe", help="Transcribe audio/video to subtitles with faster-whisper")
    p.add_argument("input", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--model", default="small", help="Whisper model size, e.g. tiny, base, small, medium")
    p.add_argument("--language", default="", help="Language code such as zh or en; empty = auto-detect")
    p.set_defaults(func=cmd_transcribe)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except subprocess.CalledProcessError as exc:
        print(f"Command failed with exit code {exc.returncode}", file=sys.stderr)
        return exc.returncode or 1


if __name__ == "__main__":
    raise SystemExit(main())
