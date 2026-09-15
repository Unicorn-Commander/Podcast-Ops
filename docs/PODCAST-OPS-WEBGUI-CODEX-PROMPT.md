# Podcast-Ops WebGUI — Codex Build Prompt

> Paste this into Codex (or any capable coding agent — Claude Code, Cursor, Continue) as the initial brief. It's self-contained: the agent shouldn't need to ask follow-up questions before starting.

---

## Mission

Build a web-based studio for **Podcast-Ops** at `/Volumes/Studio Storage/Development/Podcast-Ops/` that lets a single user (Aaron Stransky) iterate on AI-generated podcast episodes the way he currently does with a chat-based agent.

It is not a podcast distribution tool. It is not a hosting platform. It is the **studio** — the place where you write the script, pick the voices, render the audio, listen back, annotate what's wrong, and iterate. The existing chat-based workflow is the gold standard; the WebGUI should make every dial that workflow exposes available in a faster, more visual interface.

## Existing pipeline (what already works)

Don't rebuild any of this. Wrap it.

| Tool | Path | What it does |
|---|---|---|
| `render_episode.py` | `tools/audio/render_episode.py` | Parses `script.md` → calls VibeVoice 7B on bigboy → returns episode WAV. Chunks by section. |
| `build_episode_mix.sh` | `tools/audio/build_episode_mix.sh` | Voice WAV + music bed → mastered podcast WAV with intro music sting, music-fade-under-voice, clean middle, outro swell. `MUSIC_OFF=1` makes a voice-only master. |
| `generate_stings.py` | `tools/audio/generate_stings.py` | ACE-Step 1.5 SFT music generation from JSON spec. |
| `start_acestep_sft.sh` | `tools/audio/start_acestep_sft.sh` | Launches ACE-Step API server on bigboy's 3090 with the right env. |

## Infrastructure (already running on bigboy)

- **VibeVoice 7B** TTS — `http://magicunicorn:8885/podcast` and `/voices` — Docker container `vibevoice-7b`, mounts `/opt/vibevoice-models/voices` so cloned voices persist across recreates. Env var `VIBEVOICE_DDPM_STEPS` controls diffusion quality (default 10, currently set to 50). 18 voices including a cloned `aaron` voice; more clones can be added by dropping a 24 kHz mono WAV into the mounted voices folder.
- **ACE-Step 1.5 SFT** music gen — `http://magicunicorn:8001/v1/chat/completions` — Docker container, on GPU 1.
- **Music catalog** — `/tank/media/majiks/lyric-videos/output/` on bigboy, 2,000+ MP4s across ~20 artist personas (OG Unicorn, Berkshire Line, Neon Dispatch, etc.). Audio extracts to 48 kHz stereo with `ffmpeg -vn`.
- **Brigade** LLM orchestrator + agents — already used for chat-style assistant work.
- **Project Ops** REST API — `https://api.projectops.magicunicorn.dev/api/v1/` — for storing episode metadata as projects + tasks if useful.

SSH alias `magicunicorn` already works from Aaron's Mac. Tools talk to bigboy via SSH + curl (see existing scripts for the pattern).

## Repo layout (already exists)

```
/Volumes/Studio Storage/Development/Podcast-Ops/
├── docs/                   # design docs, handoffs, this prompt
├── shows/
│   └── magic-unicorn/
│       └── a-layer-below/
│           └── season-1-majiks/
│               └── episodes/
│                   └── ep01-creative-ai-suite/
│                       ├── script.md
│                       └── audio/  # all rendered + mixed WAVs/MP3s
├── tools/
│   └── audio/              # the existing pipeline scripts
├── tests/
│   └── voice-clones/       # comparison WAVs
└── apps/                   # web app goes here — currently empty
```

Add the new web app under `apps/web/`. Use a sibling `apps/api/` for the FastAPI backend that wraps the existing tools.

## What to build

### 1. Backend — `apps/api/` (FastAPI, Python 3.13)

A thin REST + WebSocket service that wraps the existing tools and exposes everything as JSON.

Required endpoints:
- `GET /shows` — list shows, seasons, episodes from filesystem
- `GET /shows/{show}/seasons/{season}/episodes/{ep}` — full episode state (script, all audio versions, render history)
- `GET /shows/{show}/seasons/{season}/episodes/{ep}/script` — raw script.md
- `PUT /shows/{show}/seasons/{season}/episodes/{ep}/script` — save edited script.md (writes to filesystem)
- `POST /shows/{show}/seasons/{season}/episodes/{ep}/render` — kick off a render. Body: `{ "version": "v12", "ddpm_steps": 50, "cfg_scale": 1.3, "sections": "all" | ["§1", "§3"] }`. Returns a render job ID.
- `GET /render-jobs/{job_id}` — poll render status. Or WebSocket `ws://.../render-jobs/{job_id}/stream` for real-time progress.
- `POST /shows/{show}/seasons/{season}/episodes/{ep}/mix` — mix a rendered voice WAV with a music bed. Body: `{ "voice_wav": "v12-voice-only.wav", "music_bed": "og_unicorn__echoes_in_code_part_ii_.wav", "mode": "music_under_voice" | "music_off", "intro_hot_s": 3.5, "intro_fade_s": 4.0, "outro_s": 7.0 }`.
- `GET /voices` — list all VibeVoice voices (proxies `/voices` from bigboy:8885)
- `POST /voices/clone` — upload a reference audio file, transcode to 24 kHz mono WAV, install into bigboy's voice mount. Body: multipart `{ name, file }`.
- `GET /music-beds` — list music beds + extracts already present on disk
- `POST /music-beds/extract` — extract a fresh 33-second bed from a catalog track. Body: `{ "source_mp4": "OG Unicorn - Echoes in Code (Part II).mp4", "start_s": 0, "duration_s": 33, "slug": "..." }`
- `POST /ai/script-edit` — proxy to Brigade for inline AI script edits. Body: `{ "current_script": "...", "instruction": "make §3 tighter", "model": "claude-3.5-haiku" }`. Returns edited script + diff.
- `POST /ai/generate-script` — proxy to Brigade for end-to-end script generation. Body: `{ "topic": "...", "show": "a-layer-below", "format": "documentary-2host", "target_minutes": 9 }`. Returns a complete script.md.

Backend stores:
- Episode metadata (versions, render params used, render times, mix params used) in `episode.state.json` next to `script.md`
- Annotations / TODOs in `episode.annotations.jsonl` (one JSONL line per annotation: `{ timestamp, version, time_s, text }`)
- Render job state in memory or sqlite; doesn't need persistence past a session

Backend invokes existing tools by `subprocess.run` — don't rewrite the audio pipeline, shell out to it.

### 2. Frontend — `apps/web/` (Next.js 15, React, Tailwind)

Single-page app, three-pane layout:

```
┌──────────────────────────┬─────────────────────────────────┐
│  Episode tree (left)     │  Script editor (center)         │
│                          │                                 │
│  ▾ A Layer Below         │  ┌─────────────────────────┐    │
│    ▾ Season 1: Majiks    │  │ frontmatter ────────    │    │
│      ▸ Ep 1: Creative AI │  │ cast: aria, beck        │    │
│      ▸ Ep 2: ...         │  │ ddpm_steps: 50          │    │
│                          │  ├─────────────────────────┤    │
│  ▾ Tech Tuesday          │  │ ## § 0 · Cold open      │    │
│    ▸ Ep 1: ...           │  │ **ARIA:** A few weeks…  │    │
│                          │  │ **BECK:** And the other │    │
│  [+ New show]            │  │ ...                     │    │
│  [+ Voice clone]         │  └─────────────────────────┘    │
│  [Voices: 18 + aaron]    │                                 │
│                          │  [ AI edit ] [ Render section ] │
│                          │  [ Render all ] [ Mix ] [ Open ]│
├──────────────────────────┴─────────────────────────────────┤
│  Audio + annotations (bottom, full width)                  │
│  ┌─ v9-FINAL.mp3 ────────────────────────────────────┐     │
│  │ ▶ ░░▒▒▓▓███▓▓▒▒░░ ──── 4:32 / 11:20 ⨂ underwater │     │
│  └────────────────────────────────────────────────────┘    │
│  ┌─ v11-FINAL.mp3 ───────────────────────────────────┐     │
│  │ ▶ ░░░▒▒▓▓███▓▓▒▒░ ──── 0:00 / 10:42              │     │
│  └────────────────────────────────────────────────────┘    │
│  [Compare v9 ↔ v11]  [Add annotation at 4:32]              │
└────────────────────────────────────────────────────────────┘
```

Required features (must-haves):

- **Markdown editor with frontmatter side-pane.** CodeMirror or Monaco. Live word count + estimated render time + estimated audio duration (target ~165 wpm). Speaker tags (`**ARIA:**`, `**BECK:**`) get syntax-highlighted.
- **Voice cast picker.** Side panel maps each speaker in the frontmatter to a voice from `/voices`. Hover plays a 2-second voice sample.
- **Section-level render.** Click any `## § N` section, render JUST that section, swap into the existing concat without re-rendering the rest. This is the killer feature — Aaron currently re-renders entire 10-minute episodes to fix a 30-second line read.
- **Audio player with annotation.** Click on the waveform to annotate "this part is garbled" or "swap word here". Annotations persist + are visible alongside the script (line-anchored where possible).
- **Side-by-side version comparison.** Two audio players, same scrub position synced. Hear v9 vs v11 at 4:32 in parallel.
- **AI script edit.** Highlight a section, type "make this tighter" → backend proxies Brigade → returns edited section with diff. Aaron approves/rejects.
- **Render parameters inspector.** DDPM steps, CFG scale, model name — all editable per render. Defaults pulled from frontmatter.
- **Mix controls.** Music bed picker, intro hot/fade durations, outro length, master target LUFS. Live MP3 export with `[Open in Finder]` button.
- **Voice clone uploader.** Drag-drop audio file (m4a/wav/mp3) → name the voice → backend transcodes + installs to bigboy → appears in voice picker immediately.

Nice-to-haves (build only if cheap to add):

- Music bed auditioning from the catalog (search by artist/persona, extract 33s or custom length, save to `assets/music-beds/`)
- Show-level brand brief editor (the source-of-truth doc, frontmatter for all episodes in the show)
- Schedule view (which episodes are rendering, queued, completed)
- Project Ops integration (each episode = a task; render-done → comment posted to task)

### 3. Tech stack

- **Frontend**: Next.js 15 (App Router), React 19, TypeScript, Tailwind CSS, shadcn/ui for components, Wavesurfer.js for waveforms, Monaco editor for markdown, TanStack Query for server state
- **Backend**: Python 3.13, FastAPI, Pydantic v2, `httpx` for proxying to bigboy, `uvicorn` for the server. Run as `apps/api/run.sh`.
- **Auth**: Single-user (Aaron), no auth needed on the API for local dev. Add a bearer-token check for production deployment.
- **Storage**: filesystem-as-state (existing pattern). No new database required. Optional sqlite for render-job tracking.
- **Hosting**: localhost during dev; eventually deploy under `podcast-ops.magicunicorn.dev` with Traefik like the other Magic Unicorn services.

### 4. Brand + look

The aesthetic should match Magic Unicorn / Magic's Studio properties — clean, technical, slightly playful. Look at:
- `https://majiks.online` — the streaming + marketplace surface
- `https://academy.magicunicorn.dev` — the education layer
- `https://media.magicunicorn.dev` — the sync surface

Avoid: corporate SaaS look, generic dashboard chrome, NPR-podcast-app aesthetic. Lean into "this is a studio, not a CMS."

Dark mode by default. Type-driven, not icon-heavy. The script editor is the hero — it should be the most beautiful thing in the app.

### 5. Acceptance criteria

The build is done when Aaron can:

1. Open the WebGUI at `http://localhost:3000`
2. See his existing A Layer Below Ep 1 in the episode tree
3. Open it in the script editor, edit the cold open
4. Hit "Render section §0" and see progress in real-time, listen back in <5 minutes
5. Drop a new music bed in, hit "Mix", get a new MP3
6. Hear v9 vs v12 side-by-side and add an annotation at a specific timestamp
7. Drag-drop a new voice clone reference, name it, see it in the voice picker, hear it render
8. Edit a section with "make this tighter" → AI returns edited version → approve → re-render

If those eight steps work end-to-end, the v1 is shipped. Everything else is iteration.

## What NOT to do

- Don't rewrite `render_episode.py` or `build_episode_mix.sh`. Shell out.
- Don't migrate to a database. Filesystem-as-state is the design.
- Don't build user accounts or multi-tenancy. Single user.
- Don't build the topic queue + cron scheduler (that's a separate Project Ops project — `PROJ-2026-000079`, the Brigade Pipeline Buildout).
- Don't build distribution / publishing (Spotify, YouTube, podcast host upload). Out of scope for v1.
- Don't theme around the show "A Layer Below" specifically — the studio supports any show. A Layer Below is just the first one in it.

## Where to look for context

- `docs/SHOW-INTROS-HANDOFF.md` — show-network architecture, voice cast, music catalog map
- `shows/magic-unicorn/a-layer-below/season-1-majiks/episodes/ep01-creative-ai-suite/script.md` — the canonical script.md format
- `tools/audio/render_episode.py` — the chunked rendering pipeline + frontmatter parsing rules
- `tools/audio/build_episode_mix.sh` — the mix pattern + tunables
- The episode's `audio/` folder has 11 versions of the same episode at different parameters — useful reference for what "versions" means in practice

## First commit

Scaffold both apps with `npx create-next-app@latest apps/web` and a hand-rolled FastAPI skeleton at `apps/api/`. Implement the minimum end-to-end loop: load script.md, edit it, save it, kick a full render, poll for completion, play the result. Everything else builds on that loop.

Then iterate.
