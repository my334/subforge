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
    shift_cues,
    write_srt,
    write_txt,
    write_vtt,
)


def _read_cues(path: Path) -> list[Cue]:
    text = path.read_text(encoding="utf-8-sig")
    suffix = path.suffix.lower()
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
    else:
        raise SystemExit("Output must end in .srt, .vtt, or .txt")
    path.write_text(content, encoding="utf-8")


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
    data = {
        "cues": len(cues),
        "starts_at": round(cues[0].start, 3),
        "ends_at": round(max(cue.end for cue in cues), 3),
        "duration_seconds": round(max(cue.end for cue in cues) - cues[0].start, 3),
        "average_chars_per_cue": round(total_chars / len(cues), 2),
    }
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        for key, value in data.items():
            print(f"{key}: {value}")
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
