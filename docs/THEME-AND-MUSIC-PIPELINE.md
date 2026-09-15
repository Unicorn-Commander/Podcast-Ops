# Theme + Music Pipeline — How We Did It

> Documentation of the ACE-Step music generation work for *The Layer Above* and the broader podcast network. Captures what works, what didn't, and what to try next.
>
> Last updated: 2026-05-14 · Context: Theme song attempt #1 didn't land — Shafen flagged that 20-second intros lose listener attention.

---

## What we have working

### ACE-Step API server on bigboy
- **Location:** `/home/muut/models/ACE-Step-1.5/`
- **Start command:** `cd /home/muut/models/ACE-Step-1.5 && CUDA_VISIBLE_DEVICES=1 bash start_api_server.sh`
- **Port:** `8001`
- **Loaded model:** `acestep-v15-turbo` (speed-optimized variant)
- **GPU placement:** Quadro RTX 6000 (GPU 1) — uses ~12GB
- **Patched:** `CHECK_UPDATE="false"` in `start_api_server.sh` to skip interactive update prompt
- **Health:** `curl http://localhost:8001/health`

### Generation endpoint
- **POST `/v1/chat/completions`** — OpenAI-compatible
- **Returns:** chat completion JSON with `message.audio[].audio_url.url` as `data:audio/wav;base64,...`

### Working request schema
```json
{
  "model": "acestep/acestep-v15-turbo",
  "messages": [{"role": "user", "content": "<style prompt>"}],
  "modalities": ["audio", "text"],
  "audio_config": {
    "duration": 20,
    "format": "wav",
    "bpm": 90,
    "instrumental": true
  },
  "guidance_scale": 7.0
}
```

### Extraction pattern
```python
import json, base64, re
d = json.load(open('response.json'))
audio_list = d['choices'][0]['message']['audio']
url = audio_list[0]['audio_url']['url']
m = re.match(r'data:audio/[^;]+;base64,(.+)', url)
audio_bytes = base64.b64decode(m.group(1))
open('out.wav', 'wb').write(audio_bytes)
```

### Performance
- ~13 seconds per 20s clip on Quadro RTX 6000
- Output: 48kHz stereo 16-bit WAV, ~3.8 MB per 20s

### Folder layout
```
Podcast-Ops/shows/magic-unicorn/the-layer-above/
├── assets/
│   └── theme-candidates/
│       ├── 01-tense-minimal-investor.wav      (didn't land)
│       ├── 02-warmer-tech-show.wav            (didn't land)
│       └── 03-music-industry-strings.wav      (didn't land)
└── ...
```

---

## What didn't land — and why

**Attempt #1 candidates (didn't land):**
1. *Tense minimal cinematic podcast intro instrumental. Low synth pad with single piano motif. Investor podcast vibe. Restrained sophisticated.* 90 bpm, 20s
2. *Warm polished tech podcast intro instrumental. Keyboard-driven, slightly anthem-y, modern. Like All-In or 20VC opening.* 100 bpm, 20s
3. *Music industry credibility intro instrumental. Layered strings with light percussion. Like NPR Music or Switched on Pop opening.* 95 bpm, 20s

**Feedback (Shafen):** people will lose interest. 20 seconds of pure instrumental at the top is too long. Listener wants content.

**Lessons:**
- 20s intros only work if there's voice-over going *over* them
- Pure-music intros should be 3-8s max as a sting
- Anthem-style energy usually beats brooding-minimal for "tune in next time"
- ACE-Step prompts heavy on adjectives may not produce as distinctive a result as prompts that reference specific musical structures

---

## Recommended next-attempt strategy

### Option A: Sting + voice-over (preferred for The Layer Above)
- 5-8s music sting at top, dramatically fades to a low bed
- Margot's brand-frame voice-over plays over the bed
- Music swells briefly at the brand-frame outro
- Total intro length: ~12-18s of which only ~5s is pure music

### Option B: Custom-per-episode theme variation
- Same base motif, different arrangement per episode
- Ep 1 (the window): tense, builds
- Ep 2 (product loop): rhythmic, kinetic
- Ep 3 (the moat): heavier, authoritative
- Ep 4 (ecosystem): expansive, layered
- Ep 5 (the bet): tense reprise + finance-coded

Each ~5-8s, generated in ~10s of ACE-Step time = cheap to produce.

### Option C: Hybrid
- Locked 5-8s show theme as the anchor (consistent identity)
- Plus 1-2s episode-specific bridges between segments
- Plus 10-15s outro

### What NOT to do
- 20+s pure-music intro with no voice
- Long intros on episodic content (only OK for prestige interview shows with celebrity guests)
- Over-produced cinematic openings (signals "this is marketing")

---

## ACE-Step prompt patterns that may work better next time

**Specific musical structures > adjective stacking:**
- Bad: *"sophisticated cinematic tense restrained"*
- Better: *"opens on a sustained Em pad, kick enters on beat 5, single piano note Bb high in the mix at 0:03"*

**Reference real podcast intros explicitly:**
- *"like the first 6 seconds of Reply All's intro"*
- *"like the first 4 seconds of The Daily"*

**Genre + era specificity:**
- *"early 2010s indie-folk acoustic intro, kalimba motif, no drums"*
- *"late 90s trip-hop, 90 bpm, dusty drums"*

**Length matching the bumper format:**
- Generate 6-second stings, not 20-second pieces
- Use `audio_config.duration: 6`

---

## Music strategy for The Layer Above (per-show direction)

| Asset | Purpose | Length | Style direction |
|---|---|---|---|
| Show theme bumper | Top of every episode | 5-8s | Distinctive, signature, repeats verbatim each episode |
| Segment transitions | Between major beats inside an episode | 1-2s | Subtle, unobtrusive sting |
| Outro music | End of episode | 8-12s | Reprises theme motif, resolves down |
| Episode-specific stings | When script mentions a specific moment | 2-3s | Topic-coded (e.g. financial sting when discussing $30M post) |
| Music clips from catalog | When script references the 800 songs | 5-8s each | Drawn from `/Volumes/Studio Storage/Majiks-Lyric-Videos/output/` |

---

## Music strategy for other shows (planned)

| Show | Music direction |
|---|---|
| **Build In Public** | Warmer, more energetic, indie-hacker coded. Synth-pop or chiptune leanings. |
| **Tech Tuesday** | Technical/dev-coded. Lo-fi or vaporwave. Calmer, work-listening register. |
| **Mechanicals** | Music industry-coded. Live instruments, vintage textures. Reverent. |
| **Own The Master** | Diverse, sampling from the catalog. Each episode references a different track. |
| **Music live stream** | Continuous Majik's catalog with DJ stings between tracks. |
| **Technical/platform show** | Minimal, near-silent intros. Mostly substance. |

---

## VibeVoice quantization — to test next

**Why test:** Current VibeVoice 7B bf16 takes ~15 min to render a 14-min episode on RTX 3090. Quantization could speed this up significantly without major quality loss.

**Options on Hugging Face:**
- `gguf-org/vibevoice-gguf` — Q4/Q6/Q8 quantizations of VibeVoice-1.5B (need 7B equivalent)
- `mozer/comfyUI-vibevoice-exl3` — exl3 quantization for VibeVoice-7B, claims realtime on RTX 3090 with 4-bit

**Plan:**
1. Stand up Q8 7B variant alongside current bf16 (different port)
2. Re-render Ep 1 with same script, same voices
3. A/B listen: quality difference vs speed difference
4. Decide whether to lock Q8 as production default

**VRAM math:**
- bf16: ~20GB
- Q8: ~12GB
- Q4: ~7GB

Q8 is the safe quality/speed pick. Q4 only if Q8 doesn't show meaningful speedup.

**Speed expectations (community-reported, unverified):**
- Q8: ~30-50% faster than bf16
- exl3 4-bit: claimed "realtime on RTX 3090" — would be 3-4x faster than current bf16 setup

---

## Open questions for next session

1. **Theme format locked?** Sting + voice-over (Option A), per-episode variation (Option B), or hybrid (Option C)?
2. **Per-episode music or one-show theme?**
3. **VibeVoice quantization — Q8 or exl3 first?** Q8 is safer, exl3 is faster but harder to wire up (ComfyUI-bound).
4. **Music clip strategy for the references in scripts** — random pick, hand-curated, or AI-selected matching script context?
5. **Should ACE-Step-generated podcast assets get ISRCs + provenance certs too?** (The meta-flex angle — every audio asset in our shows is Majik's-registered.)

---

## How a future agent picks this up

See `THEME-AGENT-HANDOFF.md` in this same folder for a self-contained prompt that brings a fresh agent up to speed without needing the full conversation history.
