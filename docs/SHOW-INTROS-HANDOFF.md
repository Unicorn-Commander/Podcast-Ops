# Show Intros — Production Handoff

> Self-contained brief for an agent (or you) producing the cold-open intro for
> any show in the Magic Unicorn / Brightwater Labs / Majik's Studio podcast
> network. Each show is a separate section; the "Shared resources" section
> after the shows lists every path, server, GPU, voice, and command you'll
> need.
>
> Last updated: 2026-05-14

---

## 1 · The shows

### 1.1 The Layer Above — *Magic Unicorn flagship*

- **Tagline.** The layer above the incumbents.
- **Audience.** Investors, partners, technical operators who don't read decks.
- **Register.** Editorial-investor, theatrical hype at the cold open, then crisp analysis.
- **Cadence.** Season-based. Season 1 = 5 episodes on Majik's Studio (already rendered).
- **Format.** Multi-voice hosted (Margot + Daniel + rotating specialist).
- **Locked cast (S1).** Margot=alice, Daniel=carter, Priya=maya, Marcus=frank (says "iz-rik"), Lena=maya, Eitan=samuel.
- **Status (intro).** v2 announcer demos rendered with frank + samuel over 4 catalog music beds in `shows/magic-unicorn/the-layer-above/assets/theme-candidates/intro-demos/intro-v2-*`. Format = BIP-style theatrical announcer + music bed + applause swell, 30s total.
- **Pinned script (current best read).** *"Ladies… and gentlemen… A Magic Unicorn production. We bring you… The. Layer. Above. Season One: Majik's Studio. Five episodes. One thesis. One window. Your host… Margot. Your analyst… Daniel. The layer above the incumbents… starts now."*
- **Intro-specific guidance.**
  - Don't say "Live from…" — show is recorded, not live.
  - Don't pin to a specific year/date in the intro; the show needs to age.
  - Voice should be a baritone the listener will associate with the show (frank or samuel both work; alice/carter are reserved for the host roles in the body).

### 1.2 Build In Public — *Aaron's weekly, Magic Unicorn brand*

- **Tagline.** Two founders shipping a local-first AI ecosystem out loud.
- **Audience.** Builders, founders, technical viewers watching live or in catch-up.
- **Register.** Boxing-announcer hype at the cold open, then casual two-host conversation.
- **Cadence.** Tuesdays 9 PM ET, YouTube livestream + AI-clipped recaps.
- **Format.** Two-host live (Aaron + Shafen).
- **Status (intro).** Already produced — `/Volumes/Studio Storage/Development/buildinpublic/public/audio/announcer-e1-fixed-with-applause.mp3`. This is the reference template the Layer Above intro adapts.
- **Pinned script (delivered, do not change without consult).** *"Ladies and gentlemen! Live from Charleston, South Carolina! Aaron Stransky, the O-G Unicorn, of Magic Unicorn! From Frisco, Texas! Mister Shafen Khan, Brightwater Labs! For your Tuesday night, we bring you... Build. In. Public!"*
- **Music bed.** `/Volumes/Studio Storage/Development/buildinpublic/public/audio/music/version-20.flac`.
- **Side note.** This show is also being productized — eventually "Build in Public as a service" gets sold to other companies, each gets their own branded BIP show. So the intro template needs to be parameterizable (different names + different cities + different show titles).

### 1.3 Tech Tuesday — *Shafen's weekly, Brightwater Labs*

- **Tagline.** Latest apps, platforms, and implementations.
- **Audience.** Practitioners — engineers, IT managers, technical decision-makers.
- **Register.** Less hype than Build In Public; more "what shipped this week" with demos.
- **Cadence.** Weekly Tuesday.
- **Format.** Likely single host (Shafen), guest demos.
- **Status (intro).** Not started.
- **Suggested intro direction.** Lighter than BIP boxing-announcer style. Think *The Daily* meets a developer-focused show — crisp open with a brief music sting, voice-over identifying the show + host + week, drop into the cold open. ~12-18s total intro, not 30s.
- **Voice suggestion.** carter (tenor, crisp) reading "This is Tech Tuesday. I'm Shafen Khan. From Brightwater Labs in Frisco, Texas. This week…" or similar. Or render Shafen's actual voice if he provides reference audio.
- **Music direction.** Something tech-coded — Live Wire or Neon Dispatch catalog tracks, or an ACE-Step generation in lo-fi/synthwave register.

### 1.4 Mechanicals — *Majik's Studio, music industry*

- **Tagline.** What the music industry actually pays for (and why most artists never see it).
- **Audience.** Music industry insiders, songwriters, indie labels, publishers, sync supervisors.
- **Register.** Industry-credible. Slightly insider. Layered strings + light percussion vibe — *NPR Music* meets *Switched on Pop*.
- **Cadence.** Biweekly.
- **Format.** Single or two-host editorial.
- **Status (intro).** Not started.
- **Suggested intro direction.** Editorial-reverent, not hype. Live instrumentation feel. Music bed should sound like real session players, not synth-pop. ~15-20s.
- **Voice suggestion.** alice or maya (warmer female register, sets the editorial tone).
- **Music direction.** Berkshire Line tracks (live indie folk vibe) work well here, OR ACE-Step generated string-and-piano editorial bed.

### 1.5 Own The Master — *Majik's Studio, music creators*

- **Tagline.** Build something they can't take from you.
- **Audience.** Creators, indie artists, AI-music creators thinking about ownership + rights.
- **Register.** Empowering, anthemic. The pitch is sovereignty.
- **Cadence.** Weekly.
- **Format.** Host + featured creator interviews.
- **Status (intro).** Not started.
- **Suggested intro direction.** Anthemic and warm. Less theatrical than Layer Above, more "you-belong-here". ~15-20s.
- **Voice suggestion.** A different host voice than Layer Above. Try maya (mezzo female warm) or samuel for sophisticated baritone.
- **Music direction.** Each episode could open with a clip from a *different* catalog track — the master tape itself becomes the intro. Rotating intros via the music-clip splicer pattern.

### 1.6 [Music live stream] — *Majik's Studio, 24/7 broadcast*

- **Tagline.** TBD.
- **Naming candidates (Aaron's list).** Hit Drop, Majiks Radio, Live Wire, etc.
- **Audience.** Casual listeners + Majiks superfans.
- **Format.** Continuous music stream of Majik's catalog with DJ stings between tracks.
- **Status (intro).** Not started — needs name first.
- **Suggested intro direction.** Stream "rejoin the broadcast" sting — 3-5s ID stinger that plays every N tracks ("You're listening to [show name]"). Plus a more elaborate 15s top-of-hour intro.
- **Voice suggestion.** carter or a hype-FM voice. Could test multiple.

### 1.7 [Technical/platform show] — *Majik's Studio, internals*

- **Tagline.** TBD.
- **Naming candidates (Aaron's list).** Under the Hood, Shipped, Release Notes, etc.
- **Audience.** Engineers, infra-curious technical viewers.
- **Register.** Substance-first. Minimal intro fluff.
- **Status (intro).** Not started.
- **Suggested intro direction.** ~5-8s intro stinger only. No theatrical announcer. Pure-instrument or tone-pad with brief voice ID. Think Vergecast or Connected.

---

## 2 · Standard intro recipe (30-second BIP-style template)

This is the recipe used for both Build In Public and Layer Above. Adapt as needed per show.

### Mix structure

```
t=0.0      music fanfare hits at full volume
t=0.5      music fade-in completes
t=1.8      announcer voice-over begins; music ducks to ~-18 dB bed
t=~25      voice-over winds down toward final line
t=25.5     applause SFX swells in (-7 dB)
t=26.5     music returns to full volume
t=29.5     music + applause fade out (2s tail)
t=32       end
```

### Build pipeline

1. **Script.** Match the show register. Period-period-period crescendo lines work great ("The. Layer. Above."). End with an action verb ("starts now", "begins now", "we go").
2. **Render voice.** VibeVoice 7B `/podcast` endpoint, single-speaker monologue with one of the locked voices. See voice list below.
3. **Broadcast-process the voice.** Run through `broadcast_process.sh` (HPF + EQ + compression + light reverb + loudnorm to -16 LUFS).
4. **Pick a music bed.** Either from Majiks catalog (extract first ~33s with ffmpeg) or generate via ACE-Step (full 30-45s instrumental, then trim).
5. **Mix.** Use `build_announcer_intro.sh` — handles delays, ducking, applause, master-bus loudnorm.
6. **Export.** WAV (master) + MP3 256k (preview).

---

## 3 · Shared resources

### 3.1 Compute (bigboy)

- **Host.** SSH alias `magicunicorn` (Tailscale 192.168.10.10).
- **OS user.** `muut` for ACE-Step. Most other services run as root in Docker.
- **GPU 0 — NVIDIA RTX 3090.** 24 GB Ampere. Native bf16. Best home for ACE-Step SFT (8.4 GB loaded, leaves 16 GB free for inference). Normally hosts VibeVoice 7B (~21 GB) — only one of the two at a time fits.
- **GPU 1 — Quadro RTX 6000 (Turing).** 23 GB total, but pre-Ampere = no bf16, models load as fp32 = 17 GB just for turbo. Contested by Shafen's `/app` service (1.4 GB), faster-whisper, two uvicorns (~4 GB). Usable for ACE-Step turbo at low quality only. **Avoid** for SFT/base — won't fit alongside the other tenants.
- **Don't disturb on GPU 1.** PID 15882 (Shafen's `/app`), 15470 (faster-whisper). These are someone else's services.

### 3.2 ACE-Step (music generation)

- **Repo on disk.** `/home/muut/models/ACE-Step-1.5/` (on bigboy).
- **Three DiT checkpoints available**: `acestep-v15-turbo` (distilled, 2-8 steps default, fast but MIDI-feel for short clips), `acestep-v15-base` (full base, 30 step default), `acestep-v15-sft` (supervised fine-tune, production quality — **recommend this**).
- **API port.** `localhost:8001` (on bigboy).
- **Endpoint.** `POST /v1/chat/completions` (OpenAI-compatible).
- **Health.** `GET /health`.
- **Start command (recommended).** `bash /Volumes/Studio Storage/Development/Podcast-Ops/tools/audio/start_acestep_sft.sh` — handles env propagation correctly (the upstream `start_api_server.sh` overrides `ACESTEP_INIT_LLM=auto` and ignores env, so it loads the LM and OOMs; this script bypasses that by calling the venv binary directly).
- **Stop command.** `ssh magicunicorn "pkill -9 -f acestep-api"` then verify with `pgrep -af acestep-api`. Watch out for the nohup'd parent `bash start_api_server.sh` if you used the default launcher — kill that too or it'll respawn the child.
- **Request schema.**
  ```json
  {
    "model": "acestep/acestep-v15-sft",
    "messages": [{"role": "user", "content": "<style prompt>"}],
    "modalities": ["audio", "text"],
    "audio_config": {
      "duration": 30,
      "format": "wav",
      "bpm": 90,
      "instrumental": true
    },
    "guidance_scale": 7.0,
    "inference_steps": 60
  }
  ```
- **Audio extraction.** `data['choices'][0]['message']['audio'][0]['audio_url']['url']` matches `data:audio/wav;base64,...`. Decode base64, write to file.
- **Lessons learned (read these).**
  - Turbo defaults to 2-8 inference steps internally — fast but quality is MIDI-thin on short instrumentals.
  - For intro music, generate **30-45s full instrumentals** (model develops timbre over a longer window), then trim to taste. Don't try to generate 5-8s stings directly.
  - Catalog-style prompts (genre + mood + instrument list, natural-language) beat structural prompts ("Em pad at 0:00, Bb piano at 0:02").
  - Reference specific intros for style ("like the first 6 seconds of NPR Throughline").
  - `instrumental: true` reduces vocal hallucinations.
  - Increasing `inference_steps` past API default (8) → noticeable quality improvement up to ~60. Diminishing returns past 60.
- **Tool to batch-generate.** `tools/audio/generate_stings.py` reads a JSON spec (list of `{slug, prompt, duration, bpm, inference_steps}`), writes WAVs to an output dir. SCP the script + spec to bigboy, run there.
- **Hosted alternative — `api.acemusic.ai`.** Same OpenAI-compatible API, no local GPU contention. Bearer auth (`Authorization: Bearer <key>`). The key is not in standard locations on this machine — Aaron has it elsewhere (1Password / personal store). Ask before using if you need this.

### 3.3 VibeVoice (voice generation)

- **Container.** `vibevoice-7b` on bigboy (`docker start vibevoice-7b` / `docker stop vibevoice-7b`).
- **API port.** `localhost:8885` (mapped from container's 8882).
- **Endpoint.** `POST /podcast` for multi-speaker dialogue/monologue.
- **Health.** `GET /health` reports model load state.
- **Voices (18 total, samples on bigboy under `/app/voices/`).**
  - `alice` — mezzo female, warm + curious (Margot / hosts in Layer Above)
  - `carter` — tenor male, crisp + skeptical (Daniel / analyst)
  - `frank` — baritone male, theatrical gravitas (Marcus / regulatory / announcer)
  - `maya` — mezzo female, slightly slower + technical (Priya, Lena)
  - `samuel` — Indian English baritone, sophisticated (Eitan / VC / international announcer)
  - `mary` — mezzo female with built-in music bed (`_bgm`) — useful for self-mixed intros
  - `anchen`, `bowen`, `xinran` — Chinese speakers (Mandarin)
  - + `en-<name>_<gender>` aliases for the English voices
- **Request schema.**
  ```json
  {
    "script": [
      {"speaker_id": "S1", "text": "Ladies and gentlemen..."},
      {"speaker_id": "S2", "text": "Glad to be here."}
    ],
    "voices": {"S1": "frank", "S2": "carter"},
    "format": "wav"
  }
  ```
- **Output.** 24 kHz mono WAV, ~1.2 MB per 25s.
- **Time-on-3090.** ~22 s wall-clock for a 30s render. (Q8 quantization not yet tested — task #35 if speed matters.)
- **GPU footprint.** ~21 GB on the 3090. **Conflicts with ACE-Step SFT on the same card** — only one fits.

### 3.4 Music catalog (Majiks)

- **Location.** `/Volumes/Studio Storage/Majiks-Lyric-Videos/output/`
- **Format.** MP4 lyric videos (audio embedded — extract with `ffmpeg -vn -ac 2 -ar 48000 ...`).
- **Volume.** ~2,008 tracks across 20+ AI personas.
- **Personas (full list).**
  A-A-Ron, Berkshire Line, Chief, DD-214, Dust & Wire, La Primera, Lawman, Live Wire, Muckraker, Neon Dispatch, OG Unicorn, Pluff Mud Prophet, Radio Static, Salt & Code, Silk Edition, Stransky After Dark, Street Wire, Sweetgrass Prism, Thee Magic Unicorn, Unconventional Technologist.
- **Plus `kids__captain-curious-*` series** for the Majiks Kids vertical.
- **Recommended intros (mapped per show register).**
  - **Editorial/investor (Layer Above):** OG Unicorn, Thee Magic Unicorn, Neon Dispatch.
  - **Hype/anthem (Build In Public, Own The Master):** A-A-Ron ("Built Different", "The Unconventional"), Chief, Live Wire.
  - **Editorial-folk (Mechanicals):** Berkshire Line.
  - **Cinematic:** Neon Dispatch ("Drums of the Ancestors"), Lawman.
  - **Techy:** Salt & Code, Live Wire, Neon Dispatch ("Circuits", "Digital Rain"), Unconventional Technologist.
- **Caveat.** Some tracks have lyric-prompt-contamination (Aaron flagged ~2008 in `/Volumes/Studio Storage/Majiks-Lyric-Videos/art-qa-flagged.csv` etc.) — listen before committing to a track for production.
- **Extract 33s for an intro bed.**
  ```bash
  ffmpeg -y -ss 0 -t 33 -i "/path/to/Persona - Title.mp4" -vn -ac 2 -ar 48000 -c:a pcm_s16le bed.wav
  ```

### 3.5 Tools (already built, in this repo)

| Path | What it does |
|---|---|
| `tools/audio/generate_stings.py` | Batch-generate ACE-Step audio from a JSON spec. Pass-through `inference_steps` and `guidance_scale`. Defaults to `acestep/acestep-v15-sft`. |
| `tools/audio/start_acestep_sft.sh` | Launch the ACE-Step server with SFT + LM-disabled + memory-fragmentation fix. Bypasses the upstream wrapper script that overrides env vars. |
| `tools/audio/build_announcer_intro.sh` | Mix announcer voice + music bed + applause into a 30s broadcast-style intro. Explicit volume schedule (music ducks to -18 dB during VO), +4 dB voice boost, applause swell, -14 LUFS master. |
| `/Volumes/Studio Storage/Development/buildinpublic/scripts/broadcast_process.sh` | Voice mastering chain (HPF 80 Hz + body bump 300 Hz + presence 2.5 kHz + 3:1 compression + light reverb + loudnorm). Outputs `-processed.wav` (-16 LUFS) + `-loud.wav` (-10 LUFS). |
| `/Volumes/Studio Storage/Development/buildinpublic/public/audio/applause.wav` | 5-second applause SFX. Reusable across shows. |

### 3.6 Brand frame voice-overs (for editorial intros)

If you want a less-theatrical, more-editorial intro (e.g., for the platform/technical show), here's a tighter format:

- ~15s total, voice-only with subtle music bed (no applause).
- alice voice: *"This is [show name]. A [parent brand] show. I'm [host]. Today…"*
- Pull a music bed at 20% volume, no ducking needed if it's subtle.

We rendered a Layer Above editorial brand-frame earlier — `shows/magic-unicorn/the-layer-above/season-1-majiks/source/brand-frame.wav` — as a reference for this style.

---

## 4 · Quick-start: produce an intro from scratch

Assuming neither ACE-Step nor VibeVoice is running. Replace `<show>` and friends.

```bash
# 1. Start VibeVoice on bigboy (Docker container, on GPU 0)
ssh magicunicorn "docker start vibevoice-7b"

# 2. Wait for it
until ssh magicunicorn "curl -sS http://localhost:8885/health 2>/dev/null | grep -q 'model_loaded.:true'"; do sleep 5; done

# 3. Write your script (locally)
cat > /tmp/<show>-announcer.json <<'EOF'
{
  "script": [{"speaker_id": "S1", "text": "..."}],
  "voices": {"S1": "frank"},
  "format": "wav"
}
EOF

# 4. Render
scp /tmp/<show>-announcer.json magicunicorn:/tmp/
ssh magicunicorn "curl -sS -X POST http://localhost:8885/podcast \
  -H 'Content-Type: application/json' \
  -d @/tmp/<show>-announcer.json --max-time 600 \
  -o /tmp/<show>-announcer-raw.wav"

# 5. Pull back
scp magicunicorn:/tmp/<show>-announcer-raw.wav ./<show>-announcer-raw.wav

# 6. Broadcast-process the voice
bash /Volumes/Studio\ Storage/Development/buildinpublic/scripts/broadcast_process.sh \
  ./<show>-announcer-raw.wav \
  ./<show>-announcer-processed.wav \
  ./<show>-announcer-loud.wav

# 7. Pick a music bed (extract from a catalog track)
ffmpeg -y -ss 0 -t 33 \
  -i "/Volumes/Studio Storage/Majiks-Lyric-Videos/output/Persona - Title.mp4" \
  -vn -ac 2 -ar 48000 -c:a pcm_s16le ./<show>-music-bed.wav

# 8. Mix
bash /Volumes/Studio\ Storage/Development/Podcast-Ops/tools/audio/build_announcer_intro.sh \
  ./<show>-announcer-processed.wav \
  ./<show>-music-bed.wav \
  /Volumes/Studio\ Storage/Development/buildinpublic/public/audio/applause.wav \
  ./<show>-intro.wav

# 9. MP3 preview
ffmpeg -y -i ./<show>-intro.wav -c:a libmp3lame -b:a 256k ./<show>-intro.mp3
```

### Optional: use ACE-Step for the music bed instead of catalog

```bash
# Stop VibeVoice first to free the 3090
ssh magicunicorn "docker stop vibevoice-7b"

# Start ACE-Step SFT on the 3090
bash /Volumes/Studio\ Storage/Development/Podcast-Ops/tools/audio/start_acestep_sft.sh
until ssh magicunicorn "curl -sS http://localhost:8001/health 2>/dev/null | grep -q 'models_initialized.:true'"; do sleep 8; done

# Generate a 30-45s instrumental
cat > /tmp/music-spec.json <<'EOF'
[{
  "slug": "show-theme",
  "prompt": "cinematic editorial podcast theme, full instrumental, ascending strings, sustained pad, single piano motif, builds to a hopeful resolve, 30 seconds",
  "duration": 30,
  "bpm": 80,
  "inference_steps": 60
}]
EOF
scp /Volumes/Studio\ Storage/Development/Podcast-Ops/tools/audio/generate_stings.py /tmp/music-spec.json magicunicorn:/tmp/
ssh magicunicorn "python3 /tmp/generate_stings.py /tmp/music-spec.json /tmp/music-out"
scp magicunicorn:/tmp/music-out/show-theme.wav ./<show>-music-bed.wav

# Then swap back to VibeVoice for the voice
ssh magicunicorn "pkill -9 -f acestep-api"
ssh magicunicorn "docker start vibevoice-7b"
# ... continue with step 2 above
```

---

## 5 · What's already in the repo

- **Layer Above S1 episode body audio (5 eps, rendered).** Under `shows/magic-unicorn/the-layer-above/season-1-majiks/episodes/ep0X-*/`. These are *episode audio*, not the intro — kept for body-mix work later.
- **Layer Above brand-frame editorial voice-over.** `shows/magic-unicorn/the-layer-above/season-1-majiks/source/brand-frame.wav`. Alice + Carter. Use as reference for editorial-register intros.
- **Layer Above intro v2 demos.** `shows/magic-unicorn/the-layer-above/assets/theme-candidates/intro-demos/intro-v2-*.mp3` — 5 candidates with 4 music beds + 1 voice-comparison. Pick the winner and rebuild the master at higher fidelity.
- **Layer Above music beds (extracted catalog tracks).** `shows/magic-unicorn/the-layer-above/assets/music-beds/*.wav`.

---

## 6 · Open questions

1. **Pick a winner for Layer Above** from the 5 v2 demos — which music + which voice combination ships. Or do another iteration.
2. **Names for the two unnamed shows** (music live stream + technical/platform).
3. **Hosted ACE Music API key** if we want to bypass the local GPU contention entirely.
4. **Per-show voice cast lock-in** — if Layer Above's alice/carter/frank/maya/samuel cast is reused for other shows, we need clear rules so listeners don't get confused (e.g., "carter on Tech Tuesday is a different character than Daniel on Layer Above"). Easier rule: each show picks distinct voices from the 18-voice pool.
