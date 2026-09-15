# Podcast-Ops

**Multi-tenant podcast production platform.** Turns a source-of-truth document and a voice cast into multi-voice podcast episodes via a swarm of LLM-powered agents that humans can interrupt and edit at any step.

A [Magic Unicorn Unconventional Technology & Stuff Inc.](https://magicunicorn.tech) project.

**Status:** v0.1 scaffolding · **License:** Proprietary

---

## What this is

Podcast-Ops is the production rail for podcasts that need:

- **Multi-voice narrative scripts** (one host + 3–6 named speakers per episode, not interviews).
- **Factual rigor** — every assertion grounded in a verified source-of-truth document.
- **Multi-tenant operation** — Magic Unicorn's shows live alongside Kevin Holloway's EdTech weekly alongside the BIP build-in-public recap.
- **Agent-assisted production** — Producer, Researcher, Scriptwriter, Renderer agents draft; humans review and approve.
- **Filesystem-primary state** — every show is a folder, every episode a sub-folder, scripts are markdown, audit logs are JSONL. Git-friendly. Editor-friendly.

First show in production: **`majiks-pitch-investor-2026`** — a 5-episode investor-facing podcast about Majiks, the music publishing platform.

---

## Quickstart (eventual)

> Heads up: v0.1 is in scaffolding. The CLI commands below describe the intended quickstart once v0.1 ships. Today, the `shows/majiks-pitch-investor-2026/` directory exists with source-of-truth + 14 voice profiles drafted + Ep 1 script drafted; the rest of the toolchain is being built.

### Prereqs
- Python 3.13 + `uv`
- Node 22 + `pnpm` (for v0.2 web app)
- A Redis instance (for render queue)
- Access to `bigboy` over Tailscale (for VibeVoice / DramaBox rendering on RTX 3090)
- A Brigade instance (`BRIGADE_BASE_URL`, `BRIGADE_API_KEY`)

### Clone + configure
```bash
git clone https://git.unicorncommander.ai/magic-unicorn/podcast-ops.git
cd podcast-ops
cp .env.example .env
# Fill in BRIGADE_BASE_URL, BRIGADE_API_KEY, LITELLM_BASE_URL, REDIS_URL
uv sync --all-packages
```

### Make an episode

```bash
# (1) Create the show + first episode (already exists for the Majiks pitch)
podcast-ops show list
podcast-ops episode create majiks-pitch-investor-2026 ep01-the-window

# (2) Run the agent pipeline
podcast-ops research majiks-pitch-investor-2026 ep01-the-window
podcast-ops outline  majiks-pitch-investor-2026 ep01-the-window
# Human edits outline.md
podcast-ops script   majiks-pitch-investor-2026 ep01-the-window
# Human edits script.md
podcast-ops render   majiks-pitch-investor-2026 ep01-the-window
podcast-ops export   majiks-pitch-investor-2026 ep01-the-window --format mp3
```

### Run the API + web GUI (v0.2)

```bash
docker compose up -d postgres redis
uv run uvicorn podcast_ops_api.main:app --reload --port 8500
cd apps/web && pnpm install && pnpm dev
```

API at `http://localhost:8500`, web at `http://localhost:5174`.

---

## Directory layout

```
Podcast-Ops/
├── apps/
│   ├── api/          # FastAPI server (Python 3.13)
│   └── web/          # Next.js 15 GUI (v0.2)
├── packages/
│   ├── core/         # Pydantic types: Show, Episode, Voice, Script, Segment
│   ├── voice/        # VoiceAdapter (VibeVoice, DramaBox, ElevenLabs, Higgs)
│   ├── script/       # Script format parser + validator + VibeVoice/DramaBox emitter
│   └── research/     # Source-of-truth + claim verification + citation tracking
├── tools/
│   ├── cli/          # `podcast-ops` headless CLI (the v0.1 surface)
│   └── voice-render/ # Audio worker (runs on bigboy GPU)
├── shows/            # CONTENT. Each show is its own folder. Git-tracked.
│   └── majiks-pitch-investor-2026/
│       ├── show.yaml
│       ├── source/source-of-truth.md
│       ├── voices/<persona>.md + <persona>.wav
│       ├── episodes/ep01-the-window/
│       │   ├── episode.yaml
│       │   ├── outline.md
│       │   ├── script.md
│       │   ├── research/claims.jsonl
│       │   ├── render/episode.wav
│       │   └── run.jsonl
│       └── exports/
├── infra/            # Alembic migrations, Docker compose, Traefik
└── docs/
    ├── ARCHITECTURE.md         # Full system architecture
    ├── AGENTS.md               # The 7 agent personas + system prompts + I/O contracts
    └── voice-model-research.md # TTS model comparison + recommendation
```

---

## How it fits with the rest of the stack

| Service | Role |
|---|---|
| **Brigade** (`brigade.magicunicorn.dev`) | LLM-with-tools backend. Every agent's reasoning goes through Brigade → LiteLLM. |
| **LiteLLM** (commander) | Routes model calls to bigboy/midboy1 GPUs or hosted models. |
| **Keycloak** (`auth.unicorncommander.ai`) | SSO. `uchub` realm, `uc_uid` claim is canonical user ID. |
| **Bigboy GPU** | Voice rendering host. VibeVoice 7B (multi-speaker single-call) and DramaBox (expressive per-turn) both on RTX 3090; only one loaded at a time (~20–24 GB each). |
| **Majiks-Producer** | Sibling content production platform (video-first). Podcast-Ops will eventually share asset model + Nextcloud delivery surface. |
| **Stable** | Sibling FastAPI + LiveKit pattern source for chat/voice rooms. |
| **Listing-Ops** | Sibling `*-Ops` project. Same monorepo layout and conventions. |

---

## Status

**v0.1 (current, in scaffolding):**
- Show scaffolding done — `shows/majiks-pitch-investor-2026/` created
- Source-of-truth verified + drafted
- 14 voice profiles drafted (6 main + 8 vertical) — reference WAVs need recording
- 5 episode outlines drafted
- Ep 1 script drafted (~1,940 words, ~12 min target)
- Architecture + agent definitions complete
- `tools/voice-render` worker — pending implementation
- CLI commands — pending implementation
- Episode 1 (`ep01-the-window`) — target: rendered + reviewed within 14 days

**v0.2 (next):**
- `apps/api` FastAPI service
- `apps/web` Next.js GUI with episode workspace
- Yjs live collaboration on scripts
- Director + Editor agents
- Kevin Holloway's tenant onboarded

**v1.0 (later):**
- Brigade inbound API + automated runs (BIP weekly)
- Source connectors (Forgejo, project-ops, EdTech news)
- Publication targets (Spotify, YouTube)

---

## Docs

- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — full system architecture, data model, multi-tenancy, agent orchestration, Brigade integration, voice rendering pipeline, federation, phased roadmap.
- **[docs/AGENTS.md](docs/AGENTS.md)** — the 7 agent personas with system prompts, input/output contracts, tool access, and human-review hooks.
- **[docs/voice-model-research.md](docs/voice-model-research.md)** — TTS model comparison. VibeVoice-Large (7B) on bigboy RTX 6000 is the v0.1 pick.

---

© Magic Unicorn Unconventional Technology & Stuff Inc.

## Producer rail exporter

The read-only [`podcast-ops-export`](tools/exporter/README.md) CLI inventories candidate renders and pushes only operator-selected artifacts through Producer's versioned ingest contract. Studio script/render/mix tools remain authoritative and unchanged.
