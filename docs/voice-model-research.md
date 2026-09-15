# Multi-Speaker TTS Model Research — Investor-Grade Podcast Production

**Date:** 2026-05-13 (initial), updated 2026-05-22 to add DramaBox
**Use case:** 10–20 min investor-grade podcast episodes, 2–3 distinct voices per episode, conversational tone, dense technical/financial content (numbers, acronyms, dollar amounts).
**Hardware in play:** bigboy (RTX 3090 + Quadro RTX 6000, 48GB total), midboy1 (2× P40), 2× Strix Halo, M2 Mac Studio, Hostinger KVM8 (no GPU).
**Bias:** open-weights, self-hosted; commercial APIs are fallback only.

---

## TL;DR Recommendation

1. **Primary (multi-speaker single-call): Microsoft VibeVoice-Large (7B)** on **bigboy** (RTX 3090 or RTX 6000). Single call generates the whole episode with up to 4 distinct speakers at 45 min in one pass — eliminates per-turn stitching artifacts. License: MIT (with research-only model-card note; weights themselves MIT). Production-tested on A Layer Below Ep 1 v4-v15.x.
2. **Primary (expressive / cinematic / per-turn): ResembleAI DramaBox** on **bigboy RTX 3090**. Prompt-driven expressive TTS built on Lightricks LTX-2.3 (3.3B). Single utterance per call (~24 GB peak), but quality and prosody substantially richer than VibeVoice — natural pauses, emphasis, conversational pacing. Best-fit when emotion or "documentary feel" beats matter more than throughput. Production-tested on A Layer Below Ep 1 v15.2 (2026-05-22). License: LTX-2 Community License.
3. **Fallback / A-B comparison: Higgs Audio v2 (3B base)** — Apache 2.0 (cleanest commercial license of the top tier), multi-speaker via `[SPEAKER0/1]` tags, single-pass dialogue, RTX 6000 24GB. Win-rates vs gpt-4o-mini-tts (75.7% emotions / 55.7% questions) are SOTA. No formal max length — chunk at ~5–8 min.

**The chosen model varies by episode goal.** For dense multi-voice exposition (deck-walks, news, long dialogue), use VibeVoice. For documentary-tone interview cuts, brand stings, or single-voice expressive narration, use DramaBox. A-B test on real scripts before locking in for a season.

---

## Comparison Table

| Model | Params | License | Multi-speaker (single call) | Max audio / call | VRAM | Voice cloning | Best hardware here |
|---|---|---|---|---|---|---|---|
| **VibeVoice-1.5B** | 3B total (1.5B LLM) | MIT (+ research-only use note) | Yes — up to 4 speakers | ~90 min | ~7 GB | Yes (reference clip) | bigboy 3090, Mac Studio (MLX) |
| **VibeVoice-Large / 7B** | ~9B total | MIT (+ same note) | Yes — up to 4 speakers | ~45 min | ~20 GB bf16, ~12 GB Q8, ~7 GB Q4 | Yes | bigboy 3090 or RTX 6000 |
| **DramaBox (ResembleAI, LTX-2.3 base)** | 3.3B (DiT) + 12B Gemma 4-bit encoder | LTX-2 Community License | **No — single utterance per call**, but voice-ref clones speaker identity per turn | ~45 s per chunk (auto-chunked for longer) | ~24 GB peak bf16 | Yes (10 s reference clip) | bigboy 3090 |
| **Higgs Audio v2** | 5.8B (3B LLM + adapters) | Apache 2.0 (+ Llama-3.2 derivative terms) | Yes — `[SPEAKER0/1]` tags | not formally specified; chunk ~5–8 min | ~18–24 GB (4-bit drops to ~8 GB community fork) | Yes (zero-shot) | bigboy RTX 6000 |
| **CosyVoice 2 (0.5B)** | 0.5B | Apache 2.0 | No native dialogue — stitch single-voice clips | Per-utterance; 150ms streaming latency | ~4–6 GB | Yes (zero-shot, 9 langs + 18 Chinese dialects) | anything, even Strix Halo |
| **Spark-TTS 0.5B** | 0.5B | Research-only (academic) | No — single voice per call | Short utterances | ~4 GB | Yes | anything |
| **Dia 1.6B (Nari Labs)** | 1.6B | Apache 2.0 | Yes — `[S1]/[S2]` tags, nonverbal cues | Short dialogues, ~30–45s sweet spot | ~10 GB | Yes | bigboy / midboy1 |
| **OuteTTS 1.0 (1B Llama variant)** | 1B | research; **0.6B variant is Apache 2.0** | Limited (one speaker per call, stitch) | ~30s natural | ~3–6 GB | Yes (5s ref) | anything, Mac Studio strong |
| **Sesame CSM-1B** | 1B | Apache 2.0 | Conversational context, but practical use is per-turn | Per-turn | ~6 GB | Limited | bigboy |
| **F5-TTS** | ~330M | CC-BY-NC (non-commercial!) | No — single voice, stitch | >3 min stable | ~6 GB | Yes (10s ref) | anything |
| **Chatterbox / Chatterbox Multilingual** | small | MIT | Multi-speaker conv. listed on 2026 roadmap; currently stitch | Short | ~4 GB | Yes | anything |
| **Kokoro-82M** | 82M | Apache 2.0 | **No** — 54 preset voices, single-speaker per call | Short | <1 GB, runs CPU | No cloning | Hostinger KVM8 if needed |
| **StyleTTS2** | small | MIT | No — single voice, stitch | Long stable | ~4 GB | Yes | anything |
| ElevenLabs (API) | n/a | commercial | Yes (Studio) | long | n/a | yes | n/a — ~$0.10–0.50/min, $330/mo Scale |
| Hume Octave 2 (API) | n/a | commercial | Yes | long | n/a | yes | n/a — $7.60/1M chars (~$0.10/min) |
| OpenAI gpt-realtime (API) | n/a | commercial | One voice per session; stitch turns | n/a | n/a | preset | n/a — ~$0.18–0.46/min uncached |

---

## Model-by-model notes

### Microsoft VibeVoice (the headline contender)
- **What it is:** Long-form, multi-speaker TTS designed explicitly for podcast generation. ICLR 2026 Oral. Built on Qwen2.5 1.5B (the "1.5B" model) or a larger LLM (the "Large"/7B). Uses a continuous tokenizer at 7.5 Hz (3200x compression vs raw 24kHz audio) which is what makes the 90-min context tractable.
- **Multi-speaker:** Genuine single-call dialogue. Format is `[1] line` / `[2] line` or `Speaker 1: line`. Reference audio per speaker is loaded once and held throughout the conversation. This is the killer feature for investor podcasts — turn-taking, prosody response between speakers, and laughter/interjection placement all happen in one pass.
- **VRAM (community-confirmed):** 1.5B ~6–7 GB; Large/7B bf16 ~20 GB; Large Q8 ~12 GB; Large Q4 ~7 GB. Both 24GB GPUs on bigboy can run the Large bf16 with headroom.
- **Quality:** SOTA on multi-speaker podcast benchmarks per the ICLR 2026 paper. Anecdotal community reports (HN, Patreon tutorials, ComfyUI ecosystem) consistently rank it above ElevenLabs Studio for multi-speaker dialogue specifically.
- **Numbers/acronyms:** Documentation explicitly says **no text normalization during training or inference** — relies on the underlying Qwen LLM to handle "$3.5M" and "ISRC". This is generally an asset (LLM knows how to verbalize numbers in context) but it's worth scripting an explicit pronunciation pass for unusual financial acronyms. **You should regression-test "SoundExchange", "ISRC", "MLC DPID", "C-Corp", and dollar amounts before locking this in.**
- **License risk:** Code and weights are MIT, but Microsoft added a model-use note saying "research and development purposes only" and the 7B was temporarily yanked then restored after misuse reports. The MIT license itself is the binding instrument; the note is best read as a CYA disclaimer, but verify with counsel before commercial release. Community forks (`vibevoice-community/VibeVoice`, `vibevoice/VibeVoice-7B`) are mirrored and active.
- **Apple Silicon:** Confirmed working on M4 Max 128GB for both 1.5B and 7B via MLX. M2 Mac Studio should handle 1.5B comfortably; 7B depends on unified memory size — likely yes on a maxed-out config, marginal otherwise.
- **Strix Halo:** No first-party support; rocm/AMD path is untested. Skip Strix Halo for VibeVoice.

### DramaBox by ResembleAI (the expressive / documentary contender)
- **What it is:** Prompt-driven expressive TTS by Resemble AI, fine-tuned on Lightricks LTX-2.3 (3.3B audio-only branch). The prompt itself controls speaker identity, emotion, delivery style, laughs, sighs, pauses; an optional 10-second voice reference clones the target timbre. IC-LoRA fine-tune merged into the base. Built 2025–2026; we adopted on 2026-05-22.
- **Prompt format:** `<speaker description>, "actual line text"`. Example: `'A warm, curious mezzo-soprano female voice speaks, "A few weeks ago in Charleston..."'`. Inline emotional cues (`She laughs, "..."` / `His voice rises with fury, "..."`) are honored at inference time.
- **Multi-speaker:** **No genuine multi-speaker single call.** You generate each turn separately with the appropriate voice reference. Voice cloning is the primary mechanism for keeping a speaker consistent across turns. This is the main tradeoff vs VibeVoice — you need a splice/concat step, but per-turn quality is higher.
- **Quality:** Substantially more expressive prosody than VibeVoice — natural pauses, emphasis on stressed words, breath placement, conversational pacing. Voice cloning fidelity is competitive with the top tier (10-second reference). Output goes through LTX BigVGAN bandwidth-extension to 48 kHz.
- **VRAM:** ~24 GB peak in bf16 (3.3B DiT at 6.6 GB + 1.9 GB audio components + ~8 GB Gemma 4-bit text encoder + inference overhead). Cleanly displaces VibeVoice 7B on the same 3090 if you swap them; both don't fit at once on a 24 GB card.
- **Speed:** ~33 s wall time to render ~45 s of audio on a 3090 (~0.7× realtime). A 13-minute deck-walk script with ~55 turns took ~15 minutes total render + a brief splice/mix. Faster than realtime, but per-turn overhead is real.
- **Numbers/acronyms:** Inherits Gemma-12B as text encoder, so handles "$5M", "ISRC", "MLC", "C-Corp" cleanly without text normalization. Still worth regression-testing brand-specific words ("Magic's", "Majiks", "Stransky") — we saw VibeVoice mispronounce "Magic's" as "Magix" consistently; DramaBox's first pass was visibly better on these.
- **Long-form auto-chunking:** Built-in. If estimated duration > 45 s, the model splits, generates each chunk, and crossfades them. We don't need to chunk in user code for long paragraphs.
- **License:** LTX-2 Community License. Open weights, broadly permissive for non-competitive commercial use; verify exact terms before redistribution.
- **Setup notes (on bigboy as of 2026-05-22):** Install at `/home/muut/dev/DramaBox`. Venv at `.venv/`. Requires `mamba-ssm` + (optionally) `causal-conv1d` for the super-resolution path; install via pre-built wheels from `state-spaces/mamba` GitHub releases (no nvcc available on the host). Also needs `resampy` for the audio resampler path when voice refs are not at 24 kHz. Cache lives at `/home/muut/.cache/dramabox/` (~16 GB once warm).
- **Voice refs we have:** Reused VibeVoice voice library at `/opt/vibevoice-models/voices/` — copied `en-Alice_woman.wav` → `assets/voices/aria_alice.wav` and `en-Carter_man.wav` → `assets/voices/beck_carter.wav` for A Layer Below.
- **Watermarking:** All DramaBox output is invisibly watermarked with Resemble Perth by default. Set `watermark=False` only if you have a specific reason (it's a tradeoff vs detectability).
- **When to choose DramaBox over VibeVoice:**
  - Documentary-style cuts where prosody depth > throughput
  - Brand stings, intros, single-narrator beats
  - Episodes where you want emotional shifts or expressive delivery
  - You're willing to trade single-call multi-speaker convenience for per-turn quality
- **When to stay on VibeVoice:**
  - Dense back-and-forth dialogue between 2-4 speakers (cross-turn prosody adaptation matters)
  - Very long single-pass episodes (45+ min)
  - You need the simplicity of one call → one episode

### Higgs Audio v2 (the cleanest-license alternative)
- **What it is:** Boson AI's audio foundation model on top of Llama-3.2-3B with a "DualFFN" audio adapter. Pretrained on 10M+ hours.
- **Multi-speaker:** Yes — `[SPEAKER0]` / `[SPEAKER1]` tags, speaker characteristics declared in a `scene` role (e.g., "SPEAKER0: feminine, calm broadcast tone"). Single-pass dialogue.
- **Quality:** 75.7% win rate vs `gpt-4o-mini-tts` on Emotions, 55.7% on Questions (EmergentTTS-Eval). SOTA on Seed-TTS Eval and ESD.
- **VRAM:** Boson's own blog says "RTX 4090 for efficient inference"; community reports ~18–20 GB for full feature set. Quantized community forks (Paxurux 4/6/8-bit) drop to ~8 GB.
- **Long-context:** No formal max length advertised; demos use `max_new_tokens=2000`. **Plan to chunk a 15-min episode into 3–5 calls and concat** — this is the main drawback vs VibeVoice.
- **License:** Apache 2.0 weights — by far the cleanest commercial position of the top tier. Caveat: the underlying Llama-3.2 derivative license requires you to keep transparency notices when redistributing the combined checkpoint.

### CosyVoice 2 (the multilingual workhorse, but not dialogue-native)
- Apache 2.0, 0.5B, streaming, 150ms latency. 9 languages + 18 Chinese dialects. Best-in-class CER on Seed-TTS hard set. **No single-call multi-speaker dialogue** — you generate each speaker's turn separately and stitch. Fine for short clips, painful for natural-feeling podcasts (no cross-turn prosody adaptation).
- Strong cross-lingual zero-shot cloning. If the podcast goes multilingual later, this is the model.

### Spark-TTS 0.5B
- LLM-based on Qwen2.5, novel BiCodec tokenizer. Strong intelligibility (CER second only to closed-source Seed-TTS on Chinese; English WER second to F5-TTS). **Single speaker per call, no dialogue mode.** License is academic/research only — disqualifies it for commercial podcast unless that posture changes.

### Dia 1.6B (Nari Labs)
- Apache 2.0, designed for dialogue, `[S1]`/`[S2]` tags, can do laughs/sighs/coughs in-line. **Best-in-class for short punchy dialogue scenes (~30–45s).** Less stable past a few minutes — wrong tool for 15-min investor episodes.

### OuteTTS 1.0
- Two variants: 1B Llama-based (research), 0.6B (Apache 2.0). DAC codec, multilingual, voice cloning from 5s reference. Built for short utterances. Same stitching problem as CosyVoice for podcasts.

### Sesame CSM-1B (Maya/Miles)
- Apache 2.0, Llama backbone, Mimi codec. Designed for conversational *context* (model adapts to prior turns) more than dialogue *generation*. Practical use is still per-turn synthesis with conversational priors. Worth watching but not the right shape for monologue/dialogue podcast scripts.

### F5-TTS
- Excellent voice cloning, strong long-form stability (>3 min), MOS at the top of the open-weights pack. **License is CC-BY-NC** — non-commercial. Disqualified for an investor podcast you'd ever monetize or share commercially.

### Chatterbox / Chatterbox Multilingual (Resemble AI)
- MIT license, beat ElevenLabs in blind preference (63.75%) per Resemble's benchmark. **Multi-speaker conversation generation is on the public 2026 roadmap — not shipped.** Today it's single-voice clone + stitch. Track for a Q3/Q4 2026 release.

### Kokoro-82M
- Apache 2.0, ~$1/M chars, runs on CPU. **No voice cloning, no multi-speaker dialogue, 54 fixed voices.** Wrong tool here. Useful as the Hostinger KVM8 emergency fallback or for low-stakes show notes intros.

### StyleTTS2
- Excellent naturalness for long-form *narration*. Single voice per call; stitch for dialogue. Solid backup if VibeVoice/Higgs both flake on a specific voice clone.

### Commercial mentions (brief)
- **ElevenLabs Studio**: gold standard for one-off; ~$0.10–0.50/min depending on tier. At 15-min episodes weekly that's $6–30/episode just in compute — fine financially, but the owner's stated preference is self-hosted and the open-weights gap has closed.
- **Hume Octave 2**: $7.60/1M chars (~$0.10/min), 11+ languages, multi-speaker, emotional intelligence is its actual differentiator. Worth a benchmark if VibeVoice voices feel flat.
- **OpenAI gpt-realtime**: $0.18–0.46/min uncached. Single voice per session; not built for podcast dialogue. Use for live agents, not podcast production.

---

## Recommended pipeline

```
Script (markdown w/ [1]/[2]/[3] tags)
   │
   ▼
Voice reference library (10–20s WAV per speaker, stored once)
   │
   ▼
VibeVoice-Large (bf16) on bigboy:RTX 6000 (24GB)
   ├─ single call per episode (≤45 min ceiling — covers 15–20 min episodes easily)
   ├─ 4-speaker max in one pass
   └─ outputs 24kHz WAV
   │
   ▼
Loudness normalize (-16 LUFS for podcast) + EQ pass + intro/outro stitch in Majiks-Screen or ffmpeg
   │
   ▼
Publish
```

**Single-call vs stitching:** Generate the entire episode as one VibeVoice call. The whole reason to pick VibeVoice over Higgs/Dia/CosyVoice is the single-pass multi-speaker dialogue — chunking discards that advantage. Reserve chunking for episodes over the 45-min ceiling or for retrying a single bad section.

**Why bigboy RTX 6000 not the 3090:** Identical 24GB, but the RTX 6000 Turing is the quieter / steady-workload card in that rig per the hardware notes. Keep the 3090 free for parallel work (Higgs A-B, song gen, etc.).

**Mac Studio M2:** Use for development, voice-reference scrubbing, and Q4-quantized 1.5B test runs (the MLX path is real and active on `mlx-audio`). Not your production endpoint unless the Mac Studio is the maxed-RAM config.

**Don't bother with Strix Halo or midboy1 P40s for TTS:** P40 Pascal has limited fp16 — usable in a pinch with Q4/Q8 quants but slow. Strix Halo's iGPU + ROCm story for these specific models is unvalidated; skip.

---

## Open questions to relay to the owner

1. **License posture on VibeVoice's "research-only" model-use note.** The MIT license is binding on its face, but does the owner want counsel review before commercial publication? If yes, Higgs Audio v2 (Apache 2.0) becomes the prudent primary even at the cost of long-context chunking.
2. **Mac Studio M2 unified memory size.** If it's a 64GB+ config, the 7B model is viable on it for development. If it's 32GB or less, stick to 1.5B on the Mac.
3. **Do we need >45 min episodes?** Current spec is 10–20 min, well under the ceiling. If long-format (e.g., founder interviews) is on the roadmap, that affects model choice — Higgs+chunking becomes equally viable.
4. **How polished do the voices need to be?** If the answer is "Hume Octave 2 emotional richness," budget a parallel commercial fallback. If it's "indistinguishable from a real podcaster," VibeVoice-Large is currently the open-weights ceiling.

---

## What to test before committing

- **Run the same 90-second 3-speaker investor-pitch script through VibeVoice-Large (Q8) and Higgs Audio v2.** Compare on: (a) handling of "$3.5M", "ISRC", "SoundExchange", "PRO royalties"; (b) speaker distinctness; (c) prosody on financial-detail-heavy sentences; (d) artifacts at speaker turns.
- **Time both end-to-end on bigboy.** Episode-length runtime matters for the publish cadence. Community reports suggest VibeVoice ~1–2x realtime on a 3090; Higgs similar with quants.
- **Validate the voice cloning quality on the actual host's voice reference.** Both models clone from short clips, but the failure modes (over-smoothed prosody, accent drift) only show up on real reference audio.

Sources:
- [Microsoft VibeVoice GitHub](https://github.com/microsoft/VibeVoice)
- [VibeVoice-1.5B model card (HF)](https://huggingface.co/microsoft/VibeVoice-1.5B)
- [VibeVoice ICLR 2026 paper](https://arxiv.org/abs/2508.19205)
- [VibeVoice community fork](https://github.com/vibevoice-community/VibeVoice)
- [Higgs Audio v2 (Boson AI) blog](https://www.boson.ai/blog/higgs-audio-v2)
- [Higgs Audio v2 3B base (HF)](https://huggingface.co/bosonai/higgs-audio-v2-generation-3B-base)
- [CosyVoice 2 project page](https://funaudiollm.github.io/cosyvoice2/)
- [Spark-TTS paper](https://arxiv.org/abs/2503.01710)
- [OuteTTS 1.0 blog](https://outeai.com/blog/outetts-1-0-release)
- [Nari Labs Dia GitHub](https://github.com/nari-labs/dia)
- [Sesame CSM GitHub](https://github.com/SesameAILabs/csm)
- [Chatterbox (Resemble AI)](https://github.com/resemble-ai/chatterbox)
- [Kokoro-82M model card](https://huggingface.co/hexgrad/Kokoro-82M)
- [TTS Arena leaderboard](https://tts-agi-tts-arena-v2.hf.space/leaderboard)
- [BentoML 2026 open-source TTS roundup](https://www.bentoml.com/blog/exploring-the-world-of-open-source-text-to-speech-models)
- [mlx-audio (Apple Silicon)](https://github.com/Blaizzy/mlx-audio)
- [Hume Octave 2 launch](https://www.hume.ai/blog/octave-2-launch)
- [ElevenLabs pricing 2026](https://elevenlabs.io/pricing)
- [OpenAI gpt-realtime pricing](https://openai.com/index/introducing-gpt-realtime/)
