#!/usr/bin/env python3
"""Render a two-host podcast script through DramaBox (expressive TTS) on bigboy.

Self-contained. Parses a script.md (frontmatter cast + `## § N` sections +
`**SPEAKER:**` turns), renders each turn through DramaBox (model loaded once),
splices the per-turn WAVs with natural pauses, loudness-normalizes to -16 LUFS,
and writes <out>/episode-voice-only.wav + <out>/episode-FINAL.mp3.

Designed to run ON bigboy (RTX 3090) with /home/muut/dev/DramaBox/.venv.

Script format (mirrors the existing Layer Above / A Layer Below episodes):
  ---
  cast:
    aria: host    # voice: alice
    beck: host    # voice: carter
  ---
  ## § 0 · Cold open
  **ARIA:**
  [amused] Some spoken line. *emphasis* is fine.
  **BECK:**
  A reply.

A leading [delivery cue] on a turn is folded into the voice style; any other
[bracketed] stage directions are stripped. Long turns are split on sentence
boundaries so each generation stays short and clean.

Usage:
  render_suite_dramabox.py <script.md> <out_dir> [--resume] [--dm 0.85] [--dry] [--smoke]
"""
from __future__ import annotations
import argparse, json, os, re, subprocess, sys, time, wave
from pathlib import Path

REPO = Path("/home/muut/dev/DramaBox")
ASSETS = REPO / "assets" / "voices"


def _ref(*names: str) -> str:
    for n in names:
        p = ASSETS / n
        if p.exists():
            return str(p)
    return str(ASSETS / names[0])


# voice id (from `# voice: <id>` in frontmatter) -> reference wav + DramaBox style description
VOICES = {
    "alice": {
        "ref": _ref("aria_alice.wav"),
        "desc": "A warm, curious, upbeat female podcast host, friendly and conversational, with clean natural studio sound",
    },
    "carter": {
        "ref": _ref("beck_carter_norm.wav", "beck_carter.wav"),
        "desc": "A crisp, dry, witty male podcast co-host, quick and lightly skeptical, with clean natural studio sound",
    },
}

PAUSE_INTRA = 0.16      # same speaker, next sub-chunk
PAUSE_INTER = 0.28      # speaker change (tightened 2026-06-06 — Aaron: gaps too long)
PAUSE_SECTION = 0.60    # new section
TARGET_LUFS = -16.0
TRUE_PEAK = -1.5
MAX_CHARS = 300         # split longer turns into sentence-grouped sub-chunks

FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
CAST_RE = re.compile(r"^\s*(\w+):\s*[\w-]+\s*#\s*voice:\s*([\w-]+)", re.MULTILINE)
SECTION_RE = re.compile(r"^##\s+§\s*([0-9.]+)\s*[·•.\-]?\s*(.+?)\s*$", re.MULTILINE)
SPEAKER_RE = re.compile(r"^\*\*([A-Za-z][A-Za-z0-9]*)\:\*\*\s*$", re.MULTILINE)
PROD_RE = re.compile(r"^#+\s+Production notes\b", re.MULTILINE | re.IGNORECASE)
LEAD_CUE_RE = re.compile(r"^\s*\[([^\]]+)\]\s*")
BRACKET_RE = re.compile(r"\[[^\]]*\]")
EMPH_RE = re.compile(r"\*+([^*]+)\*+")


def parse_cast(fm: str) -> dict:
    out = {}
    for m in CAST_RE.finditer(fm):
        out[m.group(1).upper()] = m.group(2).lower()
    return out


def split_sections(body: str):
    pn = PROD_RE.search(body)
    if pn:
        body = body[:pn.start()]
    ms = list(SECTION_RE.finditer(body))
    if not ms:
        return [("0", "intro", body)]
    out = []
    for i, m in enumerate(ms):
        start = m.end()
        end = ms[i + 1].start() if i + 1 < len(ms) else len(body)
        out.append((m.group(1), m.group(2).strip(), body[start:end]))
    return out


def clean_text(chunk: str):
    cue = None
    mc = LEAD_CUE_RE.match(chunk)
    if mc:
        cue = mc.group(1).strip()
        chunk = chunk[mc.end():]
    chunk = re.sub(r"^---\s*$", "", chunk, flags=re.MULTILINE)
    chunk = BRACKET_RE.sub("", chunk)
    chunk = EMPH_RE.sub(r"\1", chunk)
    text = " ".join(l.strip() for l in chunk.splitlines() if l.strip())
    text = re.sub(r"\s+", " ", text).strip()
    text = text.replace('"', "'")  # inner quotes would clash with the prompt delimiter
    return text, cue


def sentence_chunks(text: str, max_chars: int = MAX_CHARS):
    if len(text) <= max_chars:
        return [text]
    parts = re.split(r"(?<=[.!?])\s+", text)
    chunks, cur = [], ""
    for p in parts:
        if not cur:
            cur = p
        elif len(cur) + 1 + len(p) <= max_chars:
            cur += " " + p
        else:
            chunks.append(cur)
            cur = p
    if cur:
        chunks.append(cur)
    return chunks


def parse_turns(section_body: str, cast: dict):
    ms = list(SPEAKER_RE.finditer(section_body))
    turns = []
    for i, m in enumerate(ms):
        spk = m.group(1).upper()
        if spk not in cast:
            continue
        start = m.end()
        end = ms[i + 1].start() if i + 1 < len(ms) else len(section_body)
        text, cue = clean_text(section_body[start:end])
        if text:
            turns.append((spk, cast[spk], text, cue))
    return turns


def build_units(script_path: Path):
    raw = script_path.read_text()
    fm = FM_RE.match(raw)
    if not fm:
        sys.exit(f"no frontmatter in {script_path}")
    cast = parse_cast(fm.group(1))
    if not cast:
        sys.exit("could not parse cast (need lines like `aria: host  # voice: alice`)")
    body = raw[fm.end():]
    units = []
    idx = 0
    for sec_id, sec_title, sec_body in split_sections(body):
        for spk, voice_id, text, cue in parse_turns(sec_body, cast):
            if voice_id not in VOICES:
                sys.exit(f"unknown voice id {voice_id!r} for speaker {spk!r}")
            for chunk in sentence_chunks(text):
                units.append({
                    "idx": idx, "section": sec_id, "speaker": spk,
                    "voice_id": voice_id, "cue": cue, "text": chunk,
                    "wav": f"turn_{idx:03d}.wav",
                })
                idx += 1
    return cast, units


def build_desc(voice_id: str, cue):
    base = VOICES[voice_id]["desc"]
    return f"{base}, delivered {cue}" if cue else base


def load_server():
    sys.path.insert(0, str(REPO / "src"))
    sys.path.insert(0, str(REPO / "ltx2"))
    from model_downloader import get_all_paths
    from inference_server import TTSServer
    paths = get_all_paths()
    print("[render] loading DramaBox model ...", flush=True)
    t = time.time()
    server = TTSServer(
        checkpoint=paths["transformer"], full_checkpoint=paths["audio_components"],
        gemma_root=paths["gemma_root"], device="cuda", compile_model=False,
    )
    print(f"[render] model loaded in {time.time()-t:.1f}s", flush=True)
    return server


def wav_params(path: Path):
    with wave.open(str(path), "rb") as w:
        return w.getframerate(), w.getnchannels(), w.getsampwidth()


def silent_wav(seconds, sr, ch, sw, path: Path):
    n = int(seconds * sr)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(ch); w.setsampwidth(sw); w.setframerate(sr)
        w.writeframes(b"\x00" * (n * ch * sw))


def splice(out_dir: Path, manifest, dm_label: str):
    out_dir = Path(out_dir).resolve()  # concat list needs absolute paths for silence + turns
    turns = [t for t in manifest if t.get("wav") and (out_dir / t["wav"]).exists()]
    if not turns:
        sys.exit("no rendered turns to splice")
    sr, ch, sw = wav_params(out_dir / turns[0]["wav"])
    print(f"[splice] target {sr} Hz / {ch}ch / {sw*8}bit from {turns[0]['wav']}", flush=True)
    tmp = out_dir / "_tmp_splice"
    tmp.mkdir(exist_ok=True)
    sil = {}
    for nm, dur in (("intra", PAUSE_INTRA), ("inter", PAUSE_INTER), ("section", PAUSE_SECTION)):
        sil[nm] = tmp / f"sil_{nm}.wav"
        silent_wav(dur, sr, ch, sw, sil[nm])

    lines, prev_sec, prev_spk = [], None, None
    for i, t in enumerate(turns):
        if i > 0:
            if t["section"] != prev_sec:
                gap = sil["section"]
            elif t["speaker"] != prev_spk:
                gap = sil["inter"]
            else:
                gap = sil["intra"]
            lines.append(f"file '{gap}'")
        lines.append(f"file '{(out_dir / t['wav']).absolute()}'")
        prev_sec, prev_spk = t["section"], t["speaker"]
    concat = tmp / "concat.txt"
    concat.write_text("\n".join(lines))

    raw = tmp / "raw.wav"
    r = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                        "-f", "concat", "-safe", "0", "-i", str(concat),
                        "-c", "copy", str(raw)], capture_output=True, text=True)
    if r.returncode != 0:
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                        "-f", "concat", "-safe", "0", "-i", str(concat),
                        "-ar", str(sr), "-ac", str(ch), "-c:a", "pcm_s16le", str(raw)],
                       check=True)

    voice_only = out_dir / "episode-voice-only.wav"
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(raw),
                    "-af", f"loudnorm=I={TARGET_LUFS}:TP={TRUE_PEAK}:LRA=9",
                    "-ar", str(sr), str(voice_only)], check=True)

    final_mp3 = out_dir / "episode-FINAL.mp3"
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(voice_only),
                    "-c:a", "libmp3lame", "-q:a", "2", str(final_mp3)], check=True)

    for p in tmp.iterdir():
        p.unlink()
    tmp.rmdir()

    pr = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                         "-of", "default=nw=1:nk=1", str(voice_only)], capture_output=True, text=True)
    try:
        dur = float(pr.stdout.strip())
        print(f"\n[done] {final_mp3}\n       duration {int(dur//60)}:{int(dur%60):02d}  ({dur:.1f}s)  dm={dm_label}", flush=True)
    except ValueError:
        print(f"\n[done] {final_mp3}", flush=True)
    return voice_only, final_mp3


def render_units(server, out_dir: Path, units, dm: float, resume: bool):
    manifest_path = out_dir / "manifest.json"
    total = len(units)
    t0 = time.time()
    for u in units:
        out_wav = out_dir / u["wav"]
        if resume and out_wav.exists() and out_wav.stat().st_size > 1024:
            print(f"  [{u['idx']+1}/{total}] skip (exists) {u['wav']}", flush=True)
            continue
        desc = build_desc(u["voice_id"], u["cue"])
        prompt = f'{desc}, "{u["text"]}"'
        ref = VOICES[u["voice_id"]]["ref"]
        ts = time.time()
        try:
            server.generate_to_file(prompt=prompt, output=str(out_wav), voice_ref=ref,
                                    cfg_scale=2.5, stg_scale=1.5, duration_multiplier=dm,
                                    seed=42 + u["idx"])
            u["secs"] = round(time.time() - ts, 1)
            print(f"  [{u['idx']+1}/{total}] {u['speaker']:5} {u['secs']:5.1f}s  {u['text'][:54]!r}", flush=True)
        except Exception as e:  # noqa
            u["error"] = str(e)
            print(f"  [{u['idx']+1}/{total}] FAIL {u['speaker']}: {e}", flush=True)
        manifest_path.write_text(json.dumps(units, indent=2))
    print(f"[render] {total} units in {time.time()-t0:.1f}s wall", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("script_path", type=Path)
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--dm", type=float, default=0.85, help="duration_multiplier (0.85 = natural conversational)")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--dry", action="store_true", help="parse + print units, no model/GPU")
    ap.add_argument("--smoke", action="store_true", help="render 2 throwaway turns to validate env")
    ap.add_argument("--splice-only", action="store_true", help="re-splice existing turns from manifest.json (no model load)")
    args = ap.parse_args()
    args.out_dir = args.out_dir.resolve()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    if args.splice_only:
        manifest = json.loads((args.out_dir / "manifest.json").read_text())
        splice(args.out_dir, manifest, str(args.dm))
        return 0

    if args.smoke:
        units = [
            {"idx": 0, "section": "0", "speaker": "ARIA", "voice_id": "alice", "cue": "amused",
             "text": "Smoke test one. If you can hear me clearly, the warm host voice works.", "wav": "turn_000.wav"},
            {"idx": 1, "section": "0", "speaker": "BECK", "voice_id": "carter", "cue": "deadpan",
             "text": "Smoke test two. And the dry co-host voice works too. Ship it.", "wav": "turn_001.wav"},
        ]
        server = load_server()
        render_units(server, args.out_dir, units, args.dm, resume=False)
        splice(args.out_dir, units, str(args.dm))
        return 0

    cast, units = build_units(args.script_path)
    words = sum(len(u["text"].split()) for u in units)
    print(f"[render] cast={cast}  units={len(units)}  words≈{words}  est_audio≈{words/165:.1f}min")
    if args.dry:
        for u in units:
            tag = f"[{u['cue']}] " if u["cue"] else ""
            print(f"  {u['idx']:03d} §{u['section']:>3} {u['speaker']:5} {tag}{u['text'][:90]}")
        return 0

    server = load_server()
    render_units(server, args.out_dir, units, args.dm, args.resume)
    splice(args.out_dir, units, str(args.dm))
    return 0


if __name__ == "__main__":
    sys.exit(main())
