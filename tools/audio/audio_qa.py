#!/usr/bin/env python3
"""
Audio QA pipeline for Podcast-Ops episodes.

All heavy lifting runs on bigboy:
  - faster-whisper-large-v3 transcription (Quadro RTX 6000)
  - ffmpeg silencedetect + ebur128 loudness analysis (bigboy CPU)
Mac only does the cheap text-diff between whisper transcript and the script.

Outputs a qa-report.md punch list with timestamps the user can scan in 30s.

Usage:
  audio_qa.py <audio.mp3> [--script <script.md>] [--out <qa-report.md>]

Examples:
  audio_qa.py shows/.../audio/alb-ep01-v15.1-FINAL.mp3
  audio_qa.py shows/.../audio/alb-ep01-v15.1-FINAL.mp3 --script shows/.../script.md
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

WHISPER_URL = os.environ.get("WHISPER_URL", "http://100.126.207.157:8092")
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "Systran/faster-whisper-large-v3")
BIGBOY_SSH = os.environ.get("BIGBOY_SSH", "magicunicorn")
REMOTE_WORKDIR = "/tmp/audio-qa"

# Thresholds for the punch list
SILENCE_MIN_DB = -45.0          # below this is "silence"
SILENCE_MIN_DUR = 1.2           # report silences longer than this (seconds)
CLIP_HEADROOM_DBTP = -0.5       # true-peak above this is potential clipping
LUFS_TARGET = -16.0             # podcast target (loosely)
LUFS_RANGE_MAX = 8.0            # loudness range > this is uneven
WORD_CONF_LOW = 0.55            # whisper word probability below this is "uncertain"


@dataclass
class Word:
    start: float
    end: float
    text: str
    prob: float

    @property
    def clean(self) -> str:
        return re.sub(r"[^a-z0-9' ]", "", self.text.strip().lower())


def fmt_ts(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:d}:{s:02d}"


def upload_to_bigboy(local_path: Path) -> str:
    remote_path = f"{REMOTE_WORKDIR}/{local_path.name}"
    subprocess.run([
        "ssh", BIGBOY_SSH, f"mkdir -p {REMOTE_WORKDIR}"
    ], check=True)
    subprocess.run([
        "scp", "-q", str(local_path), f"{BIGBOY_SSH}:{remote_path}"
    ], check=True)
    return remote_path


def whisper_transcribe(local_path: Path) -> list[Word]:
    """POST audio file to faster-whisper-server, return word-level timestamps."""
    import urllib.request

    boundary = f"----audio-qa-{int(time.time()*1000)}"
    body = []
    body.append(f"--{boundary}\r\n".encode())
    body.append(b'Content-Disposition: form-data; name="model"\r\n\r\n')
    body.append(WHISPER_MODEL.encode() + b"\r\n")
    for k, v in [
        ("response_format", "verbose_json"),
        ("timestamp_granularities[]", "word"),
        ("language", "en"),
    ]:
        body.append(f"--{boundary}\r\n".encode())
        body.append(f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode())
        body.append(f"{v}\r\n".encode())
    body.append(f"--{boundary}\r\n".encode())
    body.append(
        f'Content-Disposition: form-data; name="file"; filename="{local_path.name}"\r\n'.encode()
    )
    body.append(b"Content-Type: audio/mpeg\r\n\r\n")
    with open(local_path, "rb") as f:
        body.append(f.read())
    body.append(f"\r\n--{boundary}--\r\n".encode())
    payload = b"".join(body)

    req = urllib.request.Request(
        f"{WHISPER_URL}/v1/audio/transcriptions",
        data=payload,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    print(f"  [whisper] POST {WHISPER_URL}/v1/audio/transcriptions ({len(payload)/1024/1024:.1f} MiB)")
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=600) as r:
        data = json.loads(r.read())
    print(f"  [whisper] done in {time.time()-t0:.1f}s")

    words: list[Word] = []
    for w in data.get("words", []):
        words.append(Word(
            start=w.get("start", 0.0),
            end=w.get("end", 0.0),
            text=w.get("word", ""),
            prob=w.get("probability", 1.0),
        ))
    return words


def ssh_run(cmd: str) -> str:
    r = subprocess.run(
        ["ssh", BIGBOY_SSH, cmd],
        capture_output=True, text=True, check=False
    )
    return r.stdout + r.stderr


def ffmpeg_silence(remote_path: str) -> list[tuple[float, float]]:
    """Returns list of (start, duration) silences > SILENCE_MIN_DUR."""
    out = ssh_run(
        f"ffmpeg -hide_banner -nostats -i {remote_path} "
        f"-af silencedetect=noise={SILENCE_MIN_DB}dB:d={SILENCE_MIN_DUR} "
        f"-f null - 2>&1"
    )
    starts = [float(m.group(1)) for m in re.finditer(r"silence_start: ([0-9.]+)", out)]
    durs = [float(m.group(1)) for m in re.finditer(r"silence_duration: ([0-9.]+)", out)]
    return list(zip(starts, durs))


def ffmpeg_loudness(remote_path: str) -> dict:
    """EBU R128 integrated loudness + LRA + true peak."""
    out = ssh_run(
        f"ffmpeg -hide_banner -nostats -i {remote_path} "
        f"-af ebur128=peak=true -f null - 2>&1 | tail -30"
    )
    m_i = re.search(r"I:\s+(-?[0-9.]+) LUFS", out)
    m_lra = re.search(r"LRA:\s+([0-9.]+) LU", out)
    m_tp = re.search(r"True peak:[\s\S]*?Peak:\s+(-?[0-9.]+) dBFS", out)
    return {
        "lufs_integrated": float(m_i.group(1)) if m_i else None,
        "lra": float(m_lra.group(1)) if m_lra else None,
        "true_peak_dbfs": float(m_tp.group(1)) if m_tp else None,
        "raw": out[-800:],
    }


def cleanup_remote(remote_path: str) -> None:
    ssh_run(f"rm -f {remote_path}")


# ── Script diff ──────────────────────────────────────────────────────────────

SECTION_RE = re.compile(r"^##\s*§([0-9.]+)", re.MULTILINE)
SPEAKER_RE = re.compile(r"^\*\*([A-Z][A-Za-z ]+):\*\*\s*$", re.MULTILINE)


def parse_script_words(script_path: Path) -> list[str]:
    """Strip markdown + frontmatter, extract spoken words in script order."""
    text = script_path.read_text()
    # strip YAML frontmatter at top: --- ... ---
    text = re.sub(r"\A---\n[\s\S]*?\n---\n", "", text)
    # strip "production notes" / metadata sections (anything after a trailing
    # `## Notes` / `## Production notes` / `## Editorial notes` header)
    text = re.split(
        r"\n##\s+(?:notes|production notes|editorial notes|cut content|appendix|outro notes|metadata)\b",
        text, maxsplit=1, flags=re.IGNORECASE
    )[0]
    # remove fenced code
    text = re.sub(r"```[\s\S]*?```", " ", text)
    # remove blockquotes
    text = re.sub(r"^>.+$", " ", text, flags=re.MULTILINE)
    # remove markdown headers
    text = re.sub(r"^#.+$", " ", text, flags=re.MULTILINE)
    # remove bracketed cues [INTRO MUSIC] / [pause] / [SFX] etc.
    text = re.sub(r"\[[^\]]*\]", " ", text)
    # remove italicized stage directions *like this*
    text = re.sub(r"\*[^*\n]+\*", " ", text)
    # remove speaker labels like **ARIA:**  (do this before stripping **)
    text = SPEAKER_RE.sub(" ", text)
    text = re.sub(r"\*\*", " ", text)
    # split words, strip punctuation
    words = re.findall(r"[a-z0-9']+", text.lower())
    return words


def diff_transcript_vs_script(
    whisper_words: list[Word], script_words: list[str]
) -> list[tuple[str, float, str]]:
    """
    Returns list of (kind, timestamp_seconds, message) findings.
    kind ∈ {'dropped','garbled','extra'}
    """
    w_clean = [w.clean for w in whisper_words]
    sm = difflib.SequenceMatcher(a=script_words, b=w_clean, autojunk=False)
    findings: list[tuple[str, float, str]] = []

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        # estimate timestamp from whisper words if any nearby
        ts = whisper_words[max(0, min(j1, len(whisper_words)-1))].start if whisper_words else 0
        a_slice = " ".join(script_words[i1:i2])[:80]
        b_slice = " ".join(w_clean[j1:j2])[:80]
        if tag == "delete":
            # in script but missing in audio
            if len(a_slice.split()) >= 2:
                findings.append(("dropped", ts, f'script: "…{a_slice}…" → audio: (missing)'))
        elif tag == "insert":
            if len(b_slice.split()) >= 2:
                findings.append(("extra", ts, f'audio: "…{b_slice}…" → script: (not present)'))
        elif tag == "replace":
            if len(a_slice.split()) >= 1 or len(b_slice.split()) >= 1:
                findings.append((
                    "garbled", ts,
                    f'script: "…{a_slice}…" → audio: "…{b_slice}…"'
                ))
    return findings


# ── Report ───────────────────────────────────────────────────────────────────

def build_report(
    audio_path: Path,
    whisper_words: list[Word],
    silences: list[tuple[float, float]],
    loudness: dict,
    script_diffs: list[tuple[str, float, str]] | None,
) -> str:
    duration = whisper_words[-1].end if whisper_words else 0
    low_conf = [w for w in whisper_words if w.prob < WORD_CONF_LOW]

    lines = []
    lines.append(f"# Audio QA — {audio_path.name}\n")
    lines.append(f"Duration: **{fmt_ts(duration)}** ({duration:.1f}s)  ")
    lines.append(f"Words: **{len(whisper_words)}**  ")
    lines.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

    # Loudness summary
    lines.append("## Loudness (EBU R128)\n")
    lufs = loudness.get("lufs_integrated")
    lra = loudness.get("lra")
    tp = loudness.get("true_peak_dbfs")
    def flag(ok: bool) -> str:
        return "✅" if ok else "⚠️"

    if lufs is not None:
        lufs_ok = -18 <= lufs <= -14
        lines.append(f"- {flag(lufs_ok)} Integrated: **{lufs:.1f} LUFS** (podcast target ~{LUFS_TARGET:.0f})")
    if lra is not None:
        lra_ok = lra <= LUFS_RANGE_MAX
        lines.append(f"- {flag(lra_ok)} Loudness Range: **{lra:.1f} LU** (target ≤ {LUFS_RANGE_MAX:.0f})")
    if tp is not None:
        tp_ok = tp <= CLIP_HEADROOM_DBTP
        lines.append(f"- {flag(tp_ok)} True peak: **{tp:.2f} dBFS** (target ≤ {CLIP_HEADROOM_DBTP})")

    # Silences
    lines.append(f"\n## Silences > {SILENCE_MIN_DUR}s\n")
    if not silences:
        lines.append("None detected.")
    else:
        for start, dur in silences:
            tag = "⚠️" if dur > 2.5 else "📝"
            lines.append(f"- {tag} **[{fmt_ts(start)}]** {dur:.2f}s gap")

    # Low-confidence words
    lines.append(f"\n## Low-confidence words (whisper p < {WORD_CONF_LOW})\n")
    if not low_conf:
        lines.append("None — clean transcription.")
    else:
        # cluster nearby low-conf words into runs
        runs = []
        cur = [low_conf[0]]
        for w in low_conf[1:]:
            if w.start - cur[-1].end < 2.0:
                cur.append(w)
            else:
                runs.append(cur); cur = [w]
        runs.append(cur)
        for run in runs:
            text = " ".join(w.text.strip() for w in run)
            avg_p = sum(w.prob for w in run) / len(run)
            tag = "⚠️" if avg_p < 0.35 else "📝"
            lines.append(f"- {tag} **[{fmt_ts(run[0].start)}]** \"{text}\" (avg p={avg_p:.2f})")

    # Script diff (only if script provided)
    if script_diffs is not None:
        # bucket and limit
        dropped = [f for f in script_diffs if f[0] == "dropped"][:20]
        garbled = [f for f in script_diffs if f[0] == "garbled"][:30]
        extra = [f for f in script_diffs if f[0] == "extra"][:20]

        lines.append("\n## Dropped words (in script, missing in audio)\n")
        if not dropped:
            lines.append("None.")
        else:
            for _, ts, msg in dropped:
                lines.append(f"- ⚠️ **[{fmt_ts(ts)}]** {msg}")

        lines.append("\n## Garbled words (heard differently than scripted)\n")
        if not garbled:
            lines.append("None.")
        else:
            for _, ts, msg in garbled:
                lines.append(f"- 📝 **[{fmt_ts(ts)}]** {msg}")

        lines.append("\n## Extra words (in audio, not scripted)\n")
        if not extra:
            lines.append("None.")
        else:
            for _, ts, msg in extra:
                lines.append(f"- 📝 **[{fmt_ts(ts)}]** {msg}")

    lines.append("\n---")
    lines.append("\n*Heavy compute ran on bigboy GPU 1 (Quadro RTX 6000) + bigboy ffmpeg. Mac only did the text diff.*")
    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("audio", help="Path to audio file (.mp3/.wav)")
    ap.add_argument("--script", help="Optional path to script.md for diff analysis")
    ap.add_argument("--out", help="Output qa-report.md path (default: alongside audio)")
    ap.add_argument("--keep-remote", action="store_true", help="Don't delete remote audio after analysis")
    args = ap.parse_args()

    audio_path = Path(args.audio).expanduser().resolve()
    if not audio_path.exists():
        print(f"ERROR: audio not found: {audio_path}", file=sys.stderr)
        return 1

    out_path = Path(args.out) if args.out else audio_path.with_suffix(".qa-report.md")
    print(f"Audio: {audio_path}")
    print(f"Whisper: {WHISPER_URL}  model={WHISPER_MODEL}")
    print(f"Remote: {BIGBOY_SSH}:{REMOTE_WORKDIR}")
    print()

    print("[1/4] Uploading to bigboy…")
    remote_path = upload_to_bigboy(audio_path)

    print("[2/4] Running whisper-large-v3 on bigboy GPU…")
    words = whisper_transcribe(audio_path)
    print(f"  → {len(words)} words transcribed")

    print("[3/4] Running ffmpeg analysis on bigboy…")
    silences = ffmpeg_silence(remote_path)
    loudness = ffmpeg_loudness(remote_path)
    print(f"  → {len(silences)} silences, LUFS={loudness.get('lufs_integrated')}, "
          f"TP={loudness.get('true_peak_dbfs')}")

    script_diffs = None
    if args.script:
        print("[4/4] Diffing transcript vs script (local)…")
        script_words = parse_script_words(Path(args.script))
        script_diffs = diff_transcript_vs_script(words, script_words)
        print(f"  → {len(script_diffs)} script anomalies")
    else:
        print("[4/4] (no script provided — skipping diff)")

    report = build_report(audio_path, words, silences, loudness, script_diffs)
    out_path.write_text(report)
    print(f"\n✓ Report: {out_path}")

    if not args.keep_remote:
        cleanup_remote(remote_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
