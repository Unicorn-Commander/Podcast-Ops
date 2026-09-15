# Theme & Music Agent — Handoff Prompt

> Use this as the initial prompt for a fresh agent picking up the theme/music work after conversation compaction.
> Paste the section below as the agent's task brief.

---

## The brief

You are continuing work on **The Layer Above**, an investor-grade podcast produced by Magic Unicorn (parent network) about strategic plays across the portfolio. Season 1 is a 5-episode deep dive into Majik's Studio — currently a division of Magic Unicorn in collaboration with Brightwater Labs, planning to spin out as Majik's Studio Inc.

All 5 episodes have been scripted and rendered to audio via VibeVoice 7B. The remaining work is **production polish** — theme music, episode-specific stings, music clip integration, brand frames, mastering.

### Key files to read first

1. `Podcast-Ops/docs/THEME-AND-MUSIC-PIPELINE.md` — full context on what works, what didn't, ACE-Step API, lessons
2. `Podcast-Ops/shows/magic-unicorn/the-layer-above/season-1-majiks/source/source-of-truth.md` — verified facts the scripts pull from
3. `Podcast-Ops/shows/magic-unicorn/the-layer-above/season-1-majiks/episodes/ep01-the-window/script.md` — example script with brand framing
4. `Podcast-Ops/shows/magic-unicorn/the-layer-above/assets/theme-candidates/` — three earlier theme candidates (none landed — too long, no voice-over)

### Where things run

- **bigboy** (host `magicunicorn`, SSH `ssh magicunicorn`): NVIDIA RTX 3090 + Quadro RTX 6000, ~40GB combined VRAM
- **ACE-Step API server**: `http://localhost:8001` on bigboy, on GPU 1 (Quadro RTX 6000). DiT model loaded; LLM portion failed to load due to OOM (we don't need it — we pass explicit prompts).
- **VibeVoice 7B**: `http://localhost:8885` on bigboy, on GPU 0 (RTX 3090). Loaded and rendering production episodes.

### Current state of theme songs

Three candidates rendered, **none landed**. Shafen's feedback: 20-second pure-instrumental intros lose listener attention. We need shorter format with voice-over.

### What to do next (in order)

**1. Generate new theme candidates with shorter format.** Default to 5-8 seconds, sting-style, not pure-music-anthem. Generate ~6 candidates with diverse style prompts:
- Specific musical structures (`opens on Em pad, kick on beat 5, piano note Bb at 0:03`) — not adjective stacking
- Reference real podcast intros explicitly (`like the first 4 seconds of The Daily`)
- Genre + era specificity (`early 2010s indie-folk, kalimba motif, no drums`)

**2. Pair the locked theme with a voice-over brand frame.** Brand-frame text:
> *Welcome to The Layer Above — a Magic Unicorn show about the layer we're building above the incumbents. Sovereign infrastructure. Full agentic ecosystems. Owned by their creators. Season One: Majik's Studio. I'm Margot. With me — Daniel.*
That's the v1. Refine if Aaron has new framing. Render through VibeVoice with Alice voice (Margot's locked voice). Mix theme-sting → voice → music-bed-under-voice → fade to cold open.

**3. Decide per-episode variation.** Either:
- Single theme repeats verbatim each episode (simpler)
- Per-episode variation of the same theme motif (more production value, ~10s ACE-Step time per variation)
- Or hybrid: locked show theme + episode-specific 2-3s segment-transition stings

**4. Build the music-clip splicer.** Cue language to add to scripts:
```
[CLIP: filename.wav @0:08-0:14, fade-in 0.3s, fade-out 0.3s]
```
ffmpeg-based post-render splicer. Music catalog is at `/Volumes/Studio Storage/Majiks-Lyric-Videos/output/` (2,008 lyric videos across ~20 AI artist personas).

**5. Test VibeVoice quantized (Q8 first, then maybe exl3).** Goal: render time from ~15 min/episode → ~5 min/episode. Q8 weights from Hugging Face. Standup on bigboy alongside existing bf16 service. A/B Ep 1 audio quality.

**6. Assemble final episodes.** For each of 5 episodes:
- Theme sting → brand frame voice (with music bed) → cold open
- Music clips spliced at marked positions in the script
- Episode-specific outro music → "The Layer Above is a Magic Unicorn production..." outro voice
- Master to -16 LUFS via ffmpeg loudnorm
- Export WAV + MP3 256k

### ACE-Step usage quick reference

```bash
# Health
ssh magicunicorn "curl http://localhost:8001/health"

# Generate
ssh magicunicorn "curl -sS -X POST http://localhost:8001/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    \"model\": \"acestep/acestep-v15-turbo\",
    \"messages\": [{\"role\": \"user\", \"content\": \"<prompt>\"}],
    \"modalities\": [\"audio\", \"text\"],
    \"audio_config\": {\"duration\": 6, \"format\": \"wav\", \"bpm\": 90, \"instrumental\": true},
    \"guidance_scale\": 7.0
  }' \
  --max-time 60 -o /tmp/out.json"
```

Extract base64 audio from `response['choices'][0]['message']['audio'][0]['audio_url']['url']` (matches `data:audio/wav;base64,...`).

### VibeVoice usage quick reference

```bash
# Health (7B)
ssh magicunicorn "curl http://localhost:8885/health"

# Render multi-voice episode
ssh magicunicorn "curl -sS -X POST http://localhost:8885/podcast \
  -H 'Content-Type: application/json' \
  -d '{
    \"script\": [{\"speaker_id\": \"S1\", \"text\": \"...\"}, {\"speaker_id\": \"S2\", \"text\": \"...\"}],
    \"voices\": {\"S1\": \"alice\", \"S2\": \"carter\"},
    \"format\": \"wav\"
  }' --max-time 1800 -o /tmp/ep.wav"
```

### Voice cast (locked for Season 1)

| Role | Voice ID | Persona |
|---|---|---|
| Margot (host) | `alice` | Mezzo female, warm + curious |
| Daniel (analyst) | `carter` | Tenor male, crisp + skeptical |
| Priya (technical, Ep 2 only) | `maya` | Mezzo female, slightly slower, technical depth |
| Marcus (regulatory, Ep 3 only) | `frank` | Baritone male, unhurried, says ISRC as "iz-rik" |
| Lena (product, Ep 4 only) | `maya` | Same voice as Priya — different episode/role |
| Eitan (VC, Ep 5 only) | `samuel` | Indian English baritone |

### Don't break

- The folder structure: `Podcast-Ops/shows/magic-unicorn/the-layer-above/season-1-majiks/`
- The verified facts in `source-of-truth.md` — don't make up new claims
- The cast (Margot=alice, Daniel=carter, etc.) — don't switch mid-series
- The hub-and-spoke structure (Ep 1 is standalone full pitch, Eps 2-5 are deep-dives)

### Done means

All 5 episodes:
- Theme sting + brand-frame intro
- Multi-voice episode body (already rendered, just needs assembly)
- Music clips at scripted positions
- Episode outro + brand-frame outro
- Mastered to -16 LUFS
- Exported as WAV + MP3

All 5 dropped Sunday night as a coherent series launch.
