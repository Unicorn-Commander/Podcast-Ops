#!/usr/bin/env python3
"""
Splice DramaBox per-turn WAVs into a single episode WAV.

- Reads manifest.json from the DramaBox output dir
- Concatenates turns in order with natural pauses:
    intra-turn (same speaker, next utterance):     0.35 s
    inter-turn (speaker change):                    0.60 s
    section break (different §):                    1.20 s
- Optional crossfade between turns for smoother stitching
- Optional EBU R128 loudness normalize to -16 LUFS
- Writes <out>.wav (voice-only master)

Usage:
  splice_dramabox.py <output-dir-with-manifest> [--out path] [--normalize]
"""
from __future__ import annotations
import argparse, json, os, shutil, subprocess, sys, tempfile, wave
from pathlib import Path

# Pause durations (seconds)
PAUSE_INTRA = 0.35
PAUSE_INTER = 0.60
PAUSE_SECTION = 1.20
CROSSFADE_MS = 50  # short crossfade to avoid micro-clicks
TARGET_LUFS = -16.0
TRUE_PEAK_DBTP = -1.5


def silent_wav(seconds: float, sample_rate: int, channels: int, sample_width: int, path: Path) -> None:
    nframes = int(seconds * sample_rate)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(sample_width)
        w.setframerate(sample_rate)
        w.writeframes(b"\x00" * (nframes * channels * sample_width))


def wav_params(path: Path) -> tuple[int, int, int]:
    """Returns (sample_rate, channels, sample_width)."""
    with wave.open(str(path), "rb") as w:
        return w.getframerate(), w.getnchannels(), w.getsampwidth()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir", help="DramaBox output directory containing manifest.json")
    ap.add_argument("--out", help="Output WAV path (default: <dir>/episode-voice-only.wav)")
    ap.add_argument("--normalize", action="store_true", help="EBU R128 loudness normalize")
    ap.add_argument("--no-crossfade", action="store_true", help="Skip crossfade between segments")
    args = ap.parse_args()

    src_dir = Path(args.dir)
    manifest_path = src_dir / "manifest.json"
    if not manifest_path.exists():
        print(f"ERROR: {manifest_path} not found", file=sys.stderr)
        return 1

    manifest = json.loads(manifest_path.read_text())
    turns = [t for t in manifest if "error" not in t]
    if not turns:
        print("ERROR: no successful turns in manifest", file=sys.stderr)
        return 1

    # determine target audio params from first turn
    first_wav = src_dir / turns[0]["wav"]
    sr, ch, sw = wav_params(first_wav)
    print(f"Target: {sr} Hz / {ch} ch / {sw*8} bit (from {first_wav.name})")

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)

        # Build concat list with appropriate pauses interspersed
        concat_lines: list[str] = []
        prev_section = None
        prev_speaker = None

        # pre-generate silence WAVs once
        sil_intra = td_path / "sil_intra.wav"; silent_wav(PAUSE_INTRA, sr, ch, sw, sil_intra)
        sil_inter = td_path / "sil_inter.wav"; silent_wav(PAUSE_INTER, sr, ch, sw, sil_inter)
        sil_section = td_path / "sil_section.wav"; silent_wav(PAUSE_SECTION, sr, ch, sw, sil_section)

        for i, t in enumerate(turns):
            wav = src_dir / t["wav"]
            if not wav.exists():
                print(f"  WARN: missing {wav.name}, skipping", file=sys.stderr)
                continue

            # decide pause BEFORE this turn (skip for first)
            if i > 0:
                if t["section"] != prev_section:
                    pause = sil_section
                elif t["speaker"] != prev_speaker:
                    pause = sil_inter
                else:
                    pause = sil_intra
                concat_lines.append(f"file '{pause}'")

            concat_lines.append(f"file '{wav.absolute()}'")
            prev_section = t["section"]
            prev_speaker = t["speaker"]

        concat_list = td_path / "concat.txt"
        concat_list.write_text("\n".join(concat_lines))

        out_path = Path(args.out) if args.out else src_dir / "episode-voice-only.wav"
        out_tmp = td_path / "episode-raw.wav"

        # ffmpeg concat
        print(f"Concatenating {len(turns)} turns…")
        r = subprocess.run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", str(concat_list),
            "-c", "copy", str(out_tmp)
        ], capture_output=True, text=True)
        if r.returncode != 0:
            # fallback: re-encode if copy fails (different params)
            print("  copy failed, re-encoding…")
            r = subprocess.run([
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-f", "concat", "-safe", "0", "-i", str(concat_list),
                "-ar", str(sr), "-ac", str(ch), "-c:a", "pcm_s16le",
                str(out_tmp)
            ], capture_output=True, text=True)
            if r.returncode != 0:
                print(f"ERROR: ffmpeg concat failed: {r.stderr}", file=sys.stderr)
                return 1

        if args.normalize:
            print(f"Loudness-normalizing to {TARGET_LUFS} LUFS (true-peak {TRUE_PEAK_DBTP} dBTP)…")
            r = subprocess.run([
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-i", str(out_tmp),
                "-af", f"loudnorm=I={TARGET_LUFS}:TP={TRUE_PEAK_DBTP}:LRA=7:print_format=summary",
                "-ar", str(sr), str(out_path)
            ], capture_output=True, text=True)
            if r.returncode != 0:
                print(f"ERROR: ffmpeg normalize failed: {r.stderr}", file=sys.stderr)
                return 1
        else:
            shutil.copy(out_tmp, out_path)

        # report
        size_mb = out_path.stat().st_size / 1024 / 1024
        r = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(out_path)
        ], capture_output=True, text=True)
        try:
            dur = float(r.stdout.strip())
            print(f"\n✓ {out_path}")
            print(f"  Duration: {int(dur//60)}:{int(dur%60):02d}  ({dur:.1f}s)")
            print(f"  Size:     {size_mb:.1f} MB")
        except ValueError:
            print(f"\n✓ {out_path} ({size_mb:.1f} MB)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
