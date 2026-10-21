# SubForge

**SubForge** is a small, dependency-light toolkit for people who make, clean up,
translate, or publish video subtitles.

The core is pure Python standard library: it parses and writes **SRT** and
**WebVTT**, converts subtitles to plain text, shifts timings, removes caption
tags, repairs overlaps, and prints basic statistics. Optional commands use
`ffmpeg` for audio extraction / hard-subtitle burning and `faster-whisper`
for speech-to-subtitle transcription.

SubForge 是一个小而实用的**视频字幕工具箱**：核心功能零第三方依赖，支持
SRT / WebVTT 字幕解析、格式转换、时间轴平移、字幕清洗、重叠修复和统计；
可选命令通过 `ffmpeg` 抽取音频、烧录硬字幕，通过 `faster-whisper` 把语音转成字幕。

## Why this exists · 为什么做这个

Subtitle files look simple, but real production work is full of small annoyances:
exports from one platform do not import cleanly into another, timings drift,
HTML tags leak into captions, and two cues overlap by a few frames. SubForge
focuses on those boring but important fixes, with a CLI that is easy to script
in a video workflow.

字幕文件看起来简单，真做视频时却全是小麻烦：平台之间格式不兼容、时间轴漂移、
HTML 标签混进字幕、相邻字幕重叠几帧。SubForge 就解决这些“琐碎但重要”的问题，
并且能方便地接进自动化视频处理流程。

## Install · 安装

```bash
pip install .
```

For speech transcription support:

```bash
pip install '.[whisper]'
```

`ffmpeg` is only needed for `extract-audio` and `burn` commands.

只有用到 `extract-audio` 和 `burn` 时才需要安装 `ffmpeg`。

## Quick start · 快速开始

Convert SRT to WebVTT:

```bash
subforge convert examples/sample.srt sample.vtt
```

Shift every cue 1.25 seconds later:

```bash
subforge shift sample.srt sample.shifted.srt --seconds 1.25
```

Clean tags and repair overlaps:

```bash
subforge clean sample.srt sample.clean.srt
```

Inspect a subtitle file:

```bash
subforge info examples/sample.srt
```

Extract mono 16 kHz audio for speech recognition:

```bash
subforge extract-audio lecture.mp4 lecture.wav
```

Transcribe audio/video to SRT (requires the `whisper` extra and downloads a model):

```bash
subforge transcribe lecture.wav lecture.srt --model small --language zh
```

Burn subtitles into a video (requires ffmpeg):

```bash
subforge burn lecture.mp4 lecture.srt lecture.hardsub.mp4
```

## Command overview · 命令一览

| Command | What it does |
| --- | --- |
| `convert` | Convert between `.srt`, `.vtt`, and `.txt` |
| `shift` | Move all cue timings by a number of seconds |
| `clean` | Remove HTML/ASS tags, drop empty cues, repair overlaps |
| `info` | Print cue count, duration and average cue length |
| `extract-audio` | Use ffmpeg to extract 16 kHz mono WAV audio |
| `transcribe` | Use faster-whisper to create subtitles from audio/video |
| `burn` | Use ffmpeg to burn subtitles into a video file |

## Development · 开发

Run the tests with only the standard library:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

## Roadmap · 后续计划

- ASS/SSA parsing and style-preserving conversion
- SRT translation providers with bilingual output
- Better long-line splitting for short-video captions
- A tiny local web UI for drag-and-drop conversion

## License · 许可

MIT — see [LICENSE](LICENSE).
