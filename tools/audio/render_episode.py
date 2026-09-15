#!/usr/bin/env python3
"""Render a Layer Above episode script through VibeVoice.

Parses a script.md, splits it into ## § N sections, renders each section as
a separate VibeVoice request (works around VibeVoice's DPM-solver IndexError
on long generations), then concatenates the resulting WAVs with a brief
silence between sections.

Usage:
  render_episode.py <path/to/script.md> <output.wav> [--host http://localhost:8885]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
CAST_VOICE_RE = re.compile(r"^\s*(\w+):\s*[\w-]+\s*#\s*voice:\s*([\w-]+)", re.MULTILINE)
SPEAKER_RE = re.compile(r"^\*\*([A-Z][A-Z0-9]+)\:\*\*\s*$", re.MULTILINE)
STAGE_DIR_RE = re.compile(r"\[[^\]]*\]")
SECTION_RE = re.compile(r"^##\s+§\s+(\d+)\s*[·•\.-]?\s*(.+?)\s*$", re.MULTILINE)
PRODUCTION_NOTES_RE = re.compile(r"^#+\s+Production notes\b", re.MULTILINE | re.IGNORECASE)


def parse_cast(frontmatter: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for m in CAST_VOICE_RE.finditer(frontmatter):
        character, voice = m.group(1), m.group(2)
        mapping[character.upper()] = voice
    return mapping


def split_into_sections(body: str) -> list[tuple[str, str]]:
    """Return [(section_label, section_body), ...] split on ## § headers.

    Stops at the production-notes section.
    """
    # Cut off production notes.
    pn = PRODUCTION_NOTES_RE.search(body)
    if pn:
        body = body[:pn.start()]
    matches = list(SECTION_RE.finditer(body))
    sections: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        # Use loop index for the filename so non-integer section labels
        # (e.g., "§ 0.5") don't collide with integer ones (e.g., "§ 0").
        label = f"section-{i:02d}"
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        sections.append((label, body[start:end]))
    return sections


def parse_turns(section_body: str, voice_map: dict[str, str]) -> list[tuple[str, str]]:
    """Extract (voice_id, text) tuples from one section's body."""
    turns: list[tuple[str, str]] = []
    matches = list(SPEAKER_RE.finditer(section_body))
    for i, m in enumerate(matches):
        character = m.group(1).upper()
        if character not in voice_map:
            print(f"  warning: unknown speaker {character!r}, skipping turn", file=sys.stderr)
            continue
        voice = voice_map[character]
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(section_body)
        chunk = section_body[start:end]
        # Drop horizontal rules.
        chunk = re.sub(r"^---\s*$", "", chunk, flags=re.MULTILINE)
        # Strip stage directions in [brackets].
        chunk = STAGE_DIR_RE.sub("", chunk)
        # Strip markdown emphasis around individual words (keep the words).
        chunk = re.sub(r"\*+([^*]+)\*+", r"\1", chunk)
        # Collapse whitespace.
        text = " ".join(line.strip() for line in chunk.splitlines() if line.strip())
        if not text:
            continue
        turns.append((voice, text))
    return turns


def build_payload(turns: list[tuple[str, str]]) -> dict:
    voice_to_speaker: dict[str, str] = {}
    speaker_to_voice: dict[str, str] = {}
    script: list[dict[str, str]] = []
    for voice, text in turns:
        if voice not in voice_to_speaker:
            sid = f"S{len(voice_to_speaker) + 1}"
            voice_to_speaker[voice] = sid
            speaker_to_voice[sid] = voice
        sid = voice_to_speaker[voice]
        script.append({"speaker_id": sid, "text": text})
    return {"script": script, "voices": speaker_to_voice, "format": "wav"}


def render_section(host: str, payload: dict, out_path: Path, timeout_s: int = 1800) -> None:
    req = urllib.request.Request(
        f"{host}/podcast",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as r:
        wav = r.read()
    out_path.write_bytes(wav)


def concat_wavs(wav_paths: list[Path], out_path: Path, silence_s: float = 0.6) -> None:
    """Concatenate WAVs with a brief silence between each section."""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        list_path = f.name
        # Build a concat list using a silent WAV interleaved.
        silence_path = Path(list_path).with_suffix(".silence.wav")
        # Generate silence at the same sample rate VibeVoice uses (24kHz mono).
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-t", str(silence_s),
             "-i", "anullsrc=r=24000:cl=mono",
             "-c:a", "pcm_s16le", str(silence_path)],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for i, p in enumerate(wav_paths):
            f.write(f"file '{p}'\n")
            if i < len(wav_paths) - 1:
                f.write(f"file '{silence_path}'\n")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path,
         "-c", "copy", str(out_path)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    os.unlink(list_path)
    if silence_path.exists():
        os.unlink(silence_path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("script_path", type=Path)
    ap.add_argument("output_wav", type=Path)
    ap.add_argument("--host", default="http://localhost:8885")
    ap.add_argument("--silence-s", type=float, default=0.6,
                    help="silence between sections in seconds (default 0.6)")
    ap.add_argument("--keep-sections", action="store_true",
                    help="keep per-section WAVs in <output>.sections/")
    args = ap.parse_args()
    args.output_wav = args.output_wav.resolve()  # concat list is written in /tmp; section paths must be absolute

    text = args.script_path.read_text()
    fm_match = FRONTMATTER_RE.match(text)
    if not fm_match:
        print(f"no frontmatter found in {args.script_path}", file=sys.stderr)
        return 1
    frontmatter = fm_match.group(1)
    body = text[fm_match.end():]

    voice_map = parse_cast(frontmatter)
    if not voice_map:
        print("could not parse cast voices from frontmatter", file=sys.stderr)
        return 1
    print(f"[render-episode] cast: {voice_map}")

    sections = split_into_sections(body)
    if not sections:
        print("no ## § sections found — falling back to whole-body render", file=sys.stderr)
        sections = [("whole", body)]
    print(f"[render-episode] {len(sections)} sections")

    args.output_wav.parent.mkdir(parents=True, exist_ok=True)
    section_dir = (
        args.output_wav.with_suffix("").parent
        / (args.output_wav.stem + ".sections")
    )
    section_dir.mkdir(parents=True, exist_ok=True)

    section_wavs: list[Path] = []
    total_start = time.time()
    for label, body_sec in sections:
        turns = parse_turns(body_sec, voice_map)
        if not turns:
            print(f"  {label}: no dialogue, skipping")
            continue
        payload = build_payload(turns)
        section_path = section_dir / f"{label}.wav"
        print(f"  {label}: {len(turns)} turns -> {section_path.name}", flush=True)
        t0 = time.time()
        try:
            render_section(args.host, payload, section_path)
        except Exception as e:
            print(f"  {label}: FAILED — {e}", file=sys.stderr, flush=True)
            return 1
        size = section_path.stat().st_size
        print(f"    done ({size:,} bytes, {time.time() - t0:.1f}s)", flush=True)
        section_wavs.append(section_path)

    if not section_wavs:
        print("no sections rendered", file=sys.stderr)
        return 1

    print(f"[render-episode] concatenating {len(section_wavs)} sections")
    concat_wavs(section_wavs, args.output_wav, silence_s=args.silence_s)
    final_size = args.output_wav.stat().st_size
    print(f"[render-episode] {args.output_wav} ({final_size:,} bytes, total {time.time() - total_start:.1f}s)")

    if not args.keep_sections:
        for p in section_wavs:
            p.unlink()
        section_dir.rmdir()

    return 0


if __name__ == "__main__":
    sys.exit(main())
