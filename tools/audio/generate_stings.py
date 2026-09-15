#!/usr/bin/env python3
"""Generate ACE-Step stings from a JSON spec.

Usage:
    generate_stings.py <spec.json> <output_dir> [--host http://localhost:8001]

Spec format (list of objects):
    [
      {
        "slug": "04-foo",
        "prompt": "specific musical structure prompt...",
        "duration": 6,
        "bpm": 80,
        "guidance_scale": 7.0
      },
      ...
    ]

Designed to be copied to the ACE-Step host (typically bigboy) and run there
against the local API server. No external Python deps; stdlib only.
"""
import argparse
import base64
import json
import os
import re
import sys
import time
import urllib.request


def generate(host: str, prompt: str, duration: int, bpm: int,
             guidance_scale: float, inference_steps: int,
             model: str = "acestep/acestep-v15-sft") -> bytes:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "modalities": ["audio", "text"],
        "audio_config": {
            "duration": duration,
            "format": "wav",
            "bpm": bpm,
            "instrumental": True,
        },
        "guidance_scale": guidance_scale,
        "inference_steps": inference_steps,
    }
    req = urllib.request.Request(
        f"{host}/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=240) as r:
        data = json.loads(r.read())
    audio_url = data["choices"][0]["message"]["audio"][0]["audio_url"]["url"]
    m = re.match(r"data:audio/[^;]+;base64,(.+)", audio_url)
    if not m:
        raise ValueError(f"unrecognized audio_url prefix: {audio_url[:80]!r}")
    return base64.b64decode(m.group(1))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("spec", help="path to JSON spec file")
    ap.add_argument("output_dir", help="directory to write .wav files into")
    ap.add_argument("--host", default="http://localhost:8001",
                    help="ACE-Step API base URL (default: http://localhost:8001)")
    args = ap.parse_args()

    with open(args.spec) as f:
        items = json.load(f)
    os.makedirs(args.output_dir, exist_ok=True)

    failures: list[tuple[str, str]] = []
    for i, item in enumerate(items, 1):
        slug = item["slug"]
        duration = int(item.get("duration", 6))
        bpm = int(item.get("bpm", 90))
        guidance_scale = float(item.get("guidance_scale", 7.0))
        inference_steps = int(item.get("inference_steps", 60))
        prompt = item["prompt"]
        out_path = os.path.join(args.output_dir, f"{slug}.wav")
        print(f"[{i}/{len(items)}] {slug} ({duration}s @ {bpm}bpm gs={guidance_scale} steps={inference_steps})", flush=True)
        t0 = time.time()
        try:
            wav = generate(args.host, prompt, duration, bpm, guidance_scale, inference_steps)
            with open(out_path, "wb") as f:
                f.write(wav)
            print(f"  -> {out_path} ({len(wav):,} bytes, {time.time() - t0:.1f}s)", flush=True)
        except Exception as e:
            print(f"  FAILED: {e}", flush=True)
            failures.append((slug, str(e)))

    if failures:
        print(f"\n{len(failures)} failures:", file=sys.stderr)
        for slug, err in failures:
            print(f"  {slug}: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
