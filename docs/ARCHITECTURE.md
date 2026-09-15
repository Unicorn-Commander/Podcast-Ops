# Podcast-Ops — Architecture

**Version:** v0.1 (scaffolding)
**Last updated:** 2026-05-13
**Status:** In scaffolding. First show in production: `majiks-pitch-investor-2026`.

---

## 1. System Overview

**Podcast-Ops is a multi-tenant podcast production platform.** It turns a source-of-truth document and a voice cast into a multi-voice audio podcast, via an agent swarm (Producer + Researcher + Scriptwriter + Renderer) that humans can interrupt and edit at any step.

It is operated by two kinds of users:

- **Humans** — owner (Aaron), collaborators, future client creators (Kevin Holloway). They draft, review, edit, and approve.
- **Agents** — Claude-powered subagents that draft outlines, scripts, and renders. Always supervised; always overridable.

The output is a finished episode: one `.wav` (and `.mp3` derivative), with the underlying script, outline, and audit log preserved alongside it.

Three target use cases, designed for from day one:

1. **Majiks pitch podcast** (v0.1 target, in production) — 5 episodes, 6 main voices + 8 vertical voices, dense factual content. Investor-facing.
2. **Kevin Holloway EdTech** (v0.2 target) — different tenant, different voice library, different brand kit, different LLM model preferences.
3. **Build-In-Public weekly recap** (v0.3 target) — recurring show, automated by Brigade, ingests Forgejo commits + project-ops activity as source material.

---

## 2. The Show / Episode / Asset Model

**Authoritative state is on the filesystem.** Postgres is a denormalized index for search and the GUI; if Postgres goes away, the show survives. If the filesystem goes away, the show is gone.

### Layout

```
shows/<show-slug>/
  show.yaml                          # Top-level show config (cast, brand, defaults)
  source/
    source-of-truth.md               # The authoritative content. Hand-curated.
    research/                        # Verified claims + citations (Researcher writes here)
      claims.jsonl
      sources.jsonl
  voices/
    <persona-slug>.md                # Voice profile (frontmatter + persona prose)
    <persona-slug>.wav               # 30-60s reference audio for cloning
  episodes/
    ep01-<slug>/
      episode.yaml                   # Episode metadata, status, agent runs
      outline.md                     # Outliner output, human-editable
      script.md                      # Scriptwriter output, human-editable
      script.vibevoice.txt           # Renderer-format derivative
      render/
        episode.wav                  # Final rendered audio
        per-scene/
          scene-01.wav
          scene-02.wav
        intermediates/               # Per-render-attempt artifacts
      run.jsonl                      # Audit log: every agent run with inputs/outputs/timestamps
  exports/
    ep01-final-2026-05-20.mp3        # Published artifacts
    ep01-final-2026-05-20.wav
```

### Domain Entities

| Entity | Lives In | Identifier |
|---|---|---|
| **Show** | `shows/<show-slug>/show.yaml` | slug |
| **Voice** (a.k.a. Persona) | `shows/<show-slug>/voices/<persona-slug>.md` + .wav | `(show_slug, persona_slug)` |
| **Episode** | `shows/<show-slug>/episodes/<ep-slug>/episode.yaml` | `(show_slug, ep_slug)` |
| **Script** | `shows/<show-slug>/episodes/<ep-slug>/script.md` | one per episode, versioned via git |
| **Segment** | A `## Scene N` block inside `script.md` | `(show, ep, scene_num)` |
| **Asset** (rendered audio) | `shows/<show-slug>/episodes/<ep-slug>/render/*.wav` | path |
| **Tenant** | `tenants/<tenant-slug>.yaml` at repo root + Keycloak group | slug |

A Show belongs to a Tenant (`tenant_slug` in `show.yaml`). Voices belong to a Show, but can be marked `shared_with: [...tenant_slugs]` for cross-tenant reuse.

### Why filesystem-as-state

- **Git-friendly** — every script revision is a commit; review = diff; rollback = `git checkout`.
- **LLM-friendly** — Claude can read/write files directly without a DB.
- **Human-friendly** — owner edits a `.md` in his editor of choice; no need to log into a webapp.
- **Shareable** — `cp -r shows/majiks-pitch-investor-2026 /share/with/kevin` is a valid handoff.
- **DB-as-index pattern** — Postgres mirrors the disk via a filesystem-watcher in `apps/api`. Schema in `infra/migrations/`. If we ever migrate to S3-backed storage, the watcher is the only thing that changes.

### Episode State Machine (in `episode.yaml`)

```yaml
status: scripting          # draft | outlining | researching | scripting | reviewing | rendering | rendered | mastered | published
last_agent_run:
  agent: scriptwriter
  at: 2026-05-13T18:30:00Z
  duration_s: 245
  output: script.md
human_locks:               # Files the human owns; agents must not overwrite without permission
  - script.md
```

---

## 3. Multi-Tenancy

Borrowed from Majiks-Producer §6. Adapted for filesystem-primary state.

### Tenant model

```
Tenant (magic-unicorn)
  ├── Workspace (majiks)
  │     └── Show (majiks-pitch-investor-2026)
  │           ├── Episode (ep01-the-window)
  │           ├── Episode (ep02-make-music-that-lives-somewhere)
  │           └── ...
  └── Workspace (bip)
        └── Show (bip-weekly)

Tenant (kevin-holloway)
  └── Workspace (edtech)
        └── Show (edtech-this-week)
```

- **Tenant** = billing + auth boundary. One Keycloak group per tenant.
- **Workspace** = brand boundary. One per "creative property."
- **Show** = recurring content unit.
- `uc_uid` from Keycloak is the canonical user ID. Membership is stored in Postgres (`memberships` table) with role: `owner | producer | editor | reviewer`.

### Tenancy enforcement

- **Filesystem:** every show lives under `shows/<show-slug>/`. The `show.yaml` carries `tenant: magic-unicorn` and `workspace: majiks`. Group filesystem ownership and POSIX perms enforce read access where it matters.
- **Database (when introduced):** every row has `tenant_id`. RLS policies enforce `current_setting('app.tenant_id') = tenant_id`. Identical to Majiks-Producer's plan.
- **API:** FastAPI `Depends(get_tenant)` resolves Keycloak JWT → tenant_id → sets the Postgres session variable. Same pattern as Listing-Ops `apps/api/src/listing_ops_api/auth/`.

### Per-tenant resources

| Resource | Per-tenant | Shared |
|---|---|---|
| Voice library | default | Voices can be marked `shared_with: [tenants]` |
| Brand assets (intro music, logo, color tokens) | yes | — |
| LLM model preferences (which Brigade agent, which LiteLLM model) | yes | Defaults inherited from platform |
| Agent definitions (Producer, Researcher, etc.) | Shared by default | Tenants can override with custom system prompts |
| Source connectors (Kevin's Forgejo ≠ Aaron's Forgejo) | yes | — |

### "Tenant 0" semantics

We have ONE Magic Unicorn tenant. Its workspaces partition the work: `majiks` (the company), `bip` (build-in-public). This avoids the "is BIP a tenant or a workspace?" ambiguity from earlier prose.

---

## 4. Component Breakdown

```
Podcast-Ops/
├── apps/
│   ├── api/          # FastAPI server (Python 3.13)
│   │   └── src/podcast_ops_api/
│   │       ├── main.py
│   │       ├── config.py
│   │       ├── auth/          # Keycloak OIDC (lifted from Stable)
│   │       ├── api/v1/        # REST routes
│   │       │   ├── shows.py
│   │       │   ├── episodes.py
│   │       │   ├── scripts.py
│   │       │   ├── voices.py
│   │       │   ├── agents.py
│   │       │   ├── render.py
│   │       │   ├── brigade.py     # Endpoints Brigade calls
│   │       │   └── webhooks.py
│   │       ├── agents/        # Producer, Researcher, Scriptwriter, Renderer, ...
│   │       ├── services/      # Show, episode, voice, render services
│   │       ├── filesystem/    # File-watcher, path resolver, tenant scoping
│   │       └── ws/            # WebSocket for live GUI updates
│   └── web/          # Next.js 15 GUI (deferred to v0.2)
│       └── src/...
├── packages/
│   ├── core/         # Python: pydantic types for Show, Episode, Voice, Script, Segment
│   ├── voice/        # Python: VoiceAdapter abstract class + impls
│   │   └── src/podcast_ops_voice/
│   │       ├── adapter.py            # ABC
│   │       ├── vibevoice_adapter.py  # multi-speaker single-call (dense dialogue)
│   │       ├── dramabox_adapter.py   # expressive per-turn TTS (docu/single-narrator)
│   │       ├── elevenlabs_adapter.py
│   │       └── higgs_adapter.py      # stub for v0.2
│   ├── script/       # Python: script schema, parser, validator
│   │   └── src/podcast_ops_script/
│   │       ├── schema.py
│   │       ├── parser.py             # parses script.md → typed Script
│   │       ├── vibevoice_emitter.py  # emits Speaker N: format
│   │       └── validator.py          # lints scripts: voice-line balance, banned-phrase check
│   └── research/     # Python: source-of-truth parsing, claim verification, citation linking
├── tools/
│   ├── cli/          # uv-installed CLI: `podcast-ops <cmd>`
│   │   └── src/podcast_ops_cli/
│   │       ├── __main__.py
│   │       └── commands/
│   │           ├── outline.py
│   │           ├── research.py
│   │           ├── script.py
│   │           ├── render.py
│   │           ├── show.py             # create/list shows
│   │           └── episode.py          # create/list episodes
│   └── voice-render/ # The audio worker. Runs on bigboy. Pulls from a Redis queue.
│       └── src/podcast_ops_voice_render/
│           ├── worker.py
│           └── vibevoice_runner.py
├── shows/            # CONTENT. Each show is a directory.
│   └── majiks-pitch-investor-2026/
│       ├── show.yaml
│       ├── source/
│       ├── voices/
│       ├── episodes/
│       └── exports/
├── infra/
│   ├── migrations/   # Alembic (when Postgres comes online)
│   ├── compose/
│   │   ├── docker-compose.yml          # api + postgres + redis
│   │   ├── docker-compose.bigboy.yml   # voice-render worker on bigboy
│   │   └── docker-compose.prod.yml
│   └── traefik/
└── docs/
    ├── ARCHITECTURE.md  # this file
    ├── AGENTS.md
    └── voice-model-research.md
```

### Package responsibilities

#### `packages/core`
Pydantic types only. No I/O. Pure schema.
- `Show`, `Workspace`, `Tenant`
- `Episode`, `Outline`, `EpisodeStatus` enum
- `Voice`, `VoiceCast` (per-episode mapping of role → voice)
- `Script`, `Scene`, `Line`, `Cue` (music/SFX), `VocalDirection`
- `RenderJob`, `RenderResult`
- `AgentRun` (audit log row)

#### `packages/voice`
Pluggable TTS. One interface:
```python
class VoiceAdapter(Protocol):
    async def render(
        self,
        script: VibeVoiceScript,           # speaker_id → lines
        cast: dict[str, VoiceReference],   # speaker_id → wav path or external ID
        options: RenderOptions,
    ) -> RenderResult: ...
```
v0.1 ships `VibeVoiceAdapter` (Bigboy, 7B model). v0.2 ships `ElevenLabsAdapter`. v0.3 considers `HiggsAdapter`.

#### `packages/script`
- Parses Markdown scripts into typed `Script` objects.
- Validates: every voice line maps to a declared cast member; no banned phrases (from each voice profile's "What they NEVER say" list); scene markers parse; SFX cues balance.
- Emits VibeVoice's `Speaker N:` format from a typed `Script`.

**Script format (in `script.md`):**

```markdown
---
episode: ep01-the-window
status: draft
cast:
  HOST: margot-reeve
  ANALYST: daniel-park
duration_target_min: 12
---

# Episode 1 — The Window

[INTRO MUSIC: tense rising synth, 8 seconds, fade under HOST]

## Scene 1 — Cold open (30s)

HOST (warm, slightly pulled-back): Five days ago, the most downloaded music app on the Apple App Store wasn't Spotify...
```

Frontmatter is YAML. `## Scene N` are scene markers. `[BRACKETED TEXT]` is a cue (music/SFX/direction). `SPEAKER:` starts a line; `(parenthetical)` after the speaker name is a vocal direction passed to the renderer.

#### `packages/research`
Reads `source/source-of-truth.md`. Provides:
- Claim-extraction (returns `Claim(text, status, source)` rows)
- Citation lookup (`get_source(claim_id)`)
- Pre-flight check on a `script.md`: every factual claim must have a backing source-of-truth section reference.

The Majiks pitch source already has explicit `Use-as-written` quotes and a §12 "Claims to NOT use in audio" list — this package surfaces both during script validation.

#### `apps/api`
FastAPI service. Mirrors Stable's `server/app/` layout exactly. Auth via Keycloak (`uchub` realm). REST under `/api/v1/`; WebSocket at `/ws` for live GUI updates.

#### `apps/web` (v0.2)
Next.js 15. NextAuth → Keycloak. Pages: dashboard, show overview, episode workspace (Outline / Script / Timeline tabs), voice library, render-job detail.

#### `tools/cli`
The v0.1 surface. Every operation has a CLI. The GUI in v0.2 just wraps these.

```
podcast-ops show create <slug> --tenant magic-unicorn --workspace majiks
podcast-ops show list
podcast-ops episode create <show> <ep-slug>
podcast-ops outline <show> <ep>                  # Outliner agent
podcast-ops research <show> <ep>                 # Researcher agent
podcast-ops script <show> <ep>                   # Scriptwriter agent
podcast-ops script validate <show> <ep>          # script linter
podcast-ops render <show> <ep>                   # enqueue render job
podcast-ops render status <show> <ep>
podcast-ops export <show> <ep> --format mp3 --bitrate 256k
```

#### `tools/voice-render`
Lives on bigboy. Listens to Redis queue `podcast-ops:render-jobs`. Pulls jobs, runs VibeVoice 7B, writes WAV to `shows/<show>/episodes/<ep>/render/`. Reports back via Redis pub/sub channel `podcast-ops:render-events`.

This is the only piece that must run on a specific host. Everything else can run anywhere.

---

## 5. Agent Orchestration

### The Swarm

```
                 ┌─────────────────────────┐
                 │  SHOW PRODUCER (lead)   │
                 │  • Owns episode state   │
                 │  • Routes work          │
                 │  • Surfaces decisions   │
                 └────────────┬────────────┘
                              │ spawns
       ┌──────────────┬───────┼────────┬──────────────┬──────────────┐
       ▼              ▼       ▼        ▼              ▼              ▼
  ┌────────┐  ┌──────────┐ ┌───────┐ ┌──────┐  ┌──────────┐  ┌──────────┐
  │RESEARCH│  │ OUTLINER │ │SCRIPT │ │VOICE │  │ DIRECTOR │  │ RENDERER │
  │  ER    │  │          │ │WRITER │ │CASTER│  │ (review) │  │          │
  └────────┘  └──────────┘ └───────┘ └──────┘  └──────────┘  └──────────┘
                                                                   │
                                                                   ▼
                                                              ┌────────┐
                                                              │ EDITOR │
                                                              │ (mix)  │
                                                              └────────┘
```

**v0.1 ships 4 of these:** Producer, Researcher, Scriptwriter, Renderer. Voice Caster folded into Scriptwriter. Director and Editor folded into Renderer until episode 1 sounds right.

### How they communicate

**Filesystem is the message bus. Plus a Redis queue for render jobs.**

When the Producer agent decides to spawn the Scriptwriter, it doesn't push a message into a queue. It:
1. Writes `episodes/<ep>/agent-runs/<run-id>.input.json` (Scriptwriter's inputs: outline path, source-of-truth path, voice cast path).
2. Invokes the Scriptwriter via `tools/cli` (synchronously, in v0.1, as a subprocess) or via a FastAPI internal endpoint (asynchronously, in v0.2).
3. Scriptwriter reads its inputs, writes `script.md`, appends a row to `episodes/<ep>/run.jsonl`.
4. Producer reads `run.jsonl`, sees the new row, and decides what to do next.

This means: **any agent can be inspected, restarted, or replaced by a human** at any point. The human just edits `script.md` directly and the Producer picks up where it left off based on `run.jsonl`.

### `run.jsonl` (the audit log)

Each line is a JSON record:
```json
{"ts":"2026-05-13T18:30:00Z","agent":"scriptwriter","run_id":"r_a8f2","model":"brigade:lt-content","status":"started","inputs":{"outline":"outline.md","source_of_truth":"../../source/source-of-truth.md","cast":"voices/"}}
{"ts":"2026-05-13T18:34:55Z","agent":"scriptwriter","run_id":"r_a8f2","status":"completed","outputs":{"script":"script.md"},"tokens":24503,"cost_usd":0.18}
{"ts":"2026-05-13T19:12:01Z","agent":"human","actor":"aaron","action":"edit","path":"script.md","diff_summary":"reordered scene 2 and 3, tightened HOST opening"}
```

Same format Brigade uses for agent traces. Diffable, greppable, supports a UI on top.

### How humans insert themselves

- **At any time:** open `script.md` (or `outline.md`) in their editor, edit, save. The Producer agent does not write to human-locked files without explicit unlock.
- **Via CLI:** `podcast-ops episode lock <show> <ep> script.md` adds `script.md` to `human_locks` in `episode.yaml`. `unlock` removes it.
- **Via GUI (v0.2):** an episode workspace shows the agent timeline; humans click "Edit" on any output and the file unlocks for them.
- **Review approval:** human runs `podcast-ops episode approve <show> <ep>` which moves the episode to the next status (e.g. `scripting → rendering`).

### Why not LangGraph / CrewAI / etc.

Three reasons we don't use a framework:
1. **The state lives on disk, not in-memory.** Most agent frameworks assume in-memory shared state.
2. **Each agent is a single LLM call with structured I/O.** They aren't ReAct loops. Frameworks add ceremony without value.
3. **Brigade already provides function calling.** We don't need our own tool-calling loop; Brigade has `execute_tool_loop`.

---

## 6. Brigade Integration

### How Brigade fits

Brigade is **the LLM-with-tools backend**, not the workflow engine.

```
Podcast-Ops Producer agent
        │
        │ (1) "Write a script for ep01 using these inputs"
        ▼
Brigade /api/v1/agents/scriptwriter/chat
        │
        │ (2) Function call → web_search, file_read (Brigade MCP tools)
        ▼
LiteLLM (commander)
        │
        │ (3) routes to bigboy or midboy1 GPUs
        ▼
Model (Qwen 3.6 35B locally, Claude via API for hard problems)
```

### Brigade endpoints Podcast-Ops calls (outbound)

- `POST {BRIGADE_BASE_URL}/agents/{agent_id}/chat` — runs the named Brigade agent with prompt + tools.
- `GET {BRIGADE_BASE_URL}/openai/v1/chat/completions` — OpenAI-compat surface when we just need raw LLM without Brigade persona/memory.

### Brigade endpoints Podcast-Ops exposes (inbound, v0.3)

For when Brigade orchestrates Podcast-Ops as part of a larger workflow (the BIP weekly recap case):

```
POST /api/v1/brigade/runs
  body: {
    show_slug: "bip-weekly",
    episode_slug: "ep23-2026-05-13",
    source: {
      type: "auto",
      forgejo_since: "2026-05-06",
      project_ops_workspace: "magic-unicorn"
    },
    cast: { default_voice_cast_id: "bip-default" },
    callback_url: "https://brigade.magicunicorn.dev/api/v1/runs/<id>/callback",
    auth: "Bearer <jwt>"
  }
  response: { run_id, status_url }

GET  /api/v1/brigade/runs/{run_id}     # poll status
POST /api/v1/brigade/runs/{run_id}/cancel
```

When the run completes, Podcast-Ops POSTs to the callback URL with the final asset path.

### Auth (Brigade ↔ Podcast-Ops)

- **Brigade → Podcast-Ops:** Bearer token issued by `auth.unicorncommander.ai`. Brigade has its own service account (Keycloak client `brigade-orchestrator`) with role `tenant:magic-unicorn:producer`.
- **Podcast-Ops → Brigade:** `BRIGADE_API_KEY` env var. Same pattern as Stable.

---

## 7. WebGUI Design (v0.2, sketched)

### Pages

| Path | Purpose |
|---|---|
| `/` | Dashboard — for the current tenant, list of shows, last activity per show |
| `/shows/[slug]` | Show overview — episode list with status pills, voice library link, brand kit |
| `/shows/[slug]/episodes/[ep]` | **Episode workspace** — three tabs (Outline / Script / Timeline) |
| `/shows/[slug]/episodes/[ep]/render/[job]` | Render job detail — per-scene WAVs, waveform, retry button |
| `/shows/[slug]/voices` | Voice library — list of personas, hear sample, drag-to-reassign |
| `/agents` | Agent runs (across all episodes for this tenant) |

### Episode workspace — the load-bearing screen

Three tabs:

1. **Outline tab.** Renders `outline.md` with a Monaco/CodeMirror editor. Save = writes to disk. Human-locks while editing.
2. **Script tab.** Same editor, scoped to `script.md`. Inline validation badges from `packages/script/validator`: red dot on banned phrases, yellow on uncited claims, green on clean scenes. Right rail: voice cast (drag a persona onto a line to reassign). Above the editor: per-scene WAV waveform with a "Render this scene" button.
3. **Timeline tab.** Visual playhead. Each scene = a block. Click to play. Below: agent run history (`run.jsonl` rendered as a vertical timeline). Each agent run is expandable, shows inputs/outputs, has a "Re-run with edits" button.

### Live collaboration model — final recommendation

**v0.1: skip. Use file-watching + a banner.**
- The script.md file is in a git repo. Aaron edits it in his editor. Claude (via Claude Code) edits it via the Edit tool. If both edit at once, git conflicts surface immediately.
- The WebGUI in v0.2 shows a banner: "Claude is currently in this file (last write 12s ago)" — read from `run.jsonl`.
- Last-write-wins is fine because both Aaron and Claude are deliberate.

**v0.2: Yjs CRDT.**
- Server: **Hocuspocus** (Yjs's reference Node server). Runs as a sidecar in `apps/api`'s compose stack.
- Client: **Monaco editor + y-monaco binding** in the Next.js GUI.
- Claude side: a small **y-py** (or `y-websocket-py`) client wrapped in an "edit tool" so Claude pushes Yjs deltas, including awareness updates with a cursor position (synthetic — Claude doesn't have a real cursor but emits cursor-after-last-insertion to give Aaron visual feedback).
- Persistence: Hocuspocus periodically materializes the Yjs document back to `script.md` on disk; conflicts go through Yjs, then the materialized file is committed.

**Why not LiveKit?** LiveKit is the right answer for voice/video (which Stable does). For text CRDT, Yjs is the right answer. Don't conflate.

### Voice preview UX

Drag a voice profile onto a line in the script editor. The frontend POSTs `/api/v1/render/preview` with `{voice_id, text}`. Backend dispatches to `tools/voice-render` with the **streaming-0.5B** model (real-time, single-speaker). WAV streams back via WebSocket, plays in the editor inline.

For multi-speaker scene previews, use the same render path with the 7B model on bigboy — these are slower (10–60s) but cached per `(scene_text, cast_hash)`.

---

## 8. Voice Rendering Pipeline

### Where rendering runs

| Workload | Host | Engine | Notes |
|---|---|---|---|
| **Full-episode multi-speaker render** | bigboy GPU (RTX 6000 / 3090) | VibeVoice-Large 7B | Primary path. Synchronous in v0.1 (5-15 min). |
| **Single-line voice preview** | bigboy GPU OR Mac Studio MLX | VibeVoice-Streaming-0.5B | Sub-second. Use during script editing. |
| **Spillover / hard voices** | ElevenLabs API | ElevenLabs Turbo v2.5 | When VibeVoice clone sounds wrong. Paid; only on owner approval. |
| **CPU fallback** | Anywhere | — | No. We refuse. Real-time TTS on CPU is unacceptable quality for podcasting. |

### Job lifecycle

```
1. CLI or API: `podcast-ops render <show> <ep>`
2. apps/api validates the script, writes a RenderJob record (Postgres or just a JSON file in v0.1).
3. Job pushed to Redis list `podcast-ops:render-jobs:bigboy`.
4. tools/voice-render worker on bigboy LPOPs the job.
5. Worker reads script.md, builds the VibeVoice input (Speaker N: format), assembles voice reference WAVs.
6. Worker invokes VibeVoice (subprocess: python -m vibevoice.demo.inference_from_file ...).
7. Per-scene WAVs land in shows/<show>/episodes/<ep>/render/per-scene/scene-NN.wav
8. Worker concatenates with cue insertion (ffmpeg) → episode.wav
9. Worker writes a JSON result, PUBs to Redis channel podcast-ops:render-events.
10. apps/api WebSocket pushes status to GUI; CLI's `--watch` mode prints progress.
```

### Job queue — `arq`

`arq` (Python, Redis-backed) is the right pick:
- Same Redis instance as the rest of the stack.
- Async-native.
- Simple. No worker DSL.

### Caching

`shows/<show>/episodes/<ep>/render/intermediates/scene-NN-<scripthash>-<casthash>.wav` — if you re-render a script where only scene 4 changed, scenes 1-3 and 5-N come from cache. Cuts iteration time hugely.

---

## 9. Federation / Multi-Show Story

### Kevin Holloway's tenant onboarding (v0.2 dry run)

1. **Keycloak group `kevin-holloway` created** in the `uchub` realm.
2. **Tenant row** `tenants/kevin-holloway.yaml`:
   ```yaml
   slug: kevin-holloway
   display_name: Kevin Holloway
   keycloak_group: kevin-holloway
   default_llm_routing:
     brigade_agent: kevin-content-producer
     litellm_model: opus-4-7
   default_voice_engine: vibevoice-7b
   brand:
     intro_music: assets/kevin-intro.wav
     color_primary: "#FF6B35"
   ```
3. **First show:** `shows/edtech-this-week/show.yaml` with `tenant: kevin-holloway`.
4. **Voice library:** Kevin uploads 3–5 reference WAVs through GUI; they land in `shows/edtech-this-week/voices/`. Marked `shared_with: []` so Aaron can't see them.
5. **Source connectors (when wired):** Kevin's tenant config points to his news sources / Forgejo / drive instead of Aaron's.

The platform code does not change. Kevin's onboarding is two YAML files and some WAVs.

### Per-tenant LLM model preferences

Resolved at agent-spawn time:
```python
def get_llm_for_agent(tenant_id: str, agent_kind: str) -> LLMConfig:
    tenant = load_tenant(tenant_id)
    if agent_kind in tenant.agent_overrides:
        return tenant.agent_overrides[agent_kind]
    return platform_defaults[agent_kind]
```

### Build-In-Public weekly recap (v0.3)

Brigade owns the cron. Brigade calls Podcast-Ops `POST /api/v1/brigade/runs` every Sunday night. Source connectors return Forgejo commits + project-ops activity for the past 7 days. Podcast-Ops produces a 5-minute episode. Brigade publishes.

---

## 10. Phased Plan

### v0.1 — "Claude + Aaron produce the Majiks pitch end-to-end with the CLI" (target: 1–2 weeks)

**Ships:**
- `packages/core`: pydantic types
- `packages/voice`: VibeVoice adapter only
- `packages/script`: parser + validator + VibeVoice emitter, script format spec
- `packages/research`: source-of-truth reader, claim/citation lookup
- `tools/cli`: `show`, `episode`, `outline`, `research`, `script`, `render`, `export`
- `tools/voice-render`: bigboy worker, arq + Redis
- 4 agents as CLI commands: Producer (orchestrator), Researcher, Scriptwriter (+ Voice Caster folded in), Renderer (+ Editor folded in)
- No DB. No GUI. No WebSocket. No Yjs.
- Auth: none locally; SSH/Tailscale to bigboy.
- Brigade: outbound only (we call Brigade for LLM).

**Acceptance:** `podcast-ops render majiks-pitch-investor-2026 ep01-the-window` produces a multi-voice WAV that Aaron approves.

### v0.2 — "Aaron + Kevin both use it with a GUI" (target: 4–6 weeks after v0.1)

**Adds:**
- `apps/api`: FastAPI, Postgres + Alembic, file-watcher syncing to DB
- `apps/web`: Next.js 15, NextAuth + Keycloak, episode workspace, voice preview
- Yjs/Hocuspocus for live script collaboration
- WebSocket for live agent run updates
- Director agent (script review pass)
- Editor agent (mastering pass with ffmpeg loudnorm)
- ElevenLabs adapter as fallback
- Kevin Holloway's tenant onboarded
- Multi-tenant RLS enforced

### v1.0 — "Brigade-orchestrated production runs" (target: ~3 months after v0.2)

**Adds:**
- Brigade inbound API + callback model
- BIP weekly recap as the first automated show
- Source connectors (Forgejo, project-ops, EdTech news for Kevin)
- Publication targets (Spotify, YouTube via Mux as in Majiks-Producer §3)
- Public review links (timed shareable episode URLs)
- Federation: Podcast-Ops can be a federated service in Unicorn Commander mesh; cross-tenant voice sharing via federated voice profiles.

---

## 11. Open Questions

- **Music generation:** Do we generate intro/outro music with ACE-Step (the Majiks engine itself!) or hand-curate? Recommend hand-curate for v0.1 and v0.2 (consistency > novelty for the pitch podcast); revisit for v1.0.
- **Auto-transcription on the output side:** Do we ship word-level alignment in v0.1? Recommend skip; Descript-style transcript editing is a v1.0 feature.
- **iOS/Mac native apps:** Out of scope. Podcast-Ops is creation-side only; distribution rides on existing rails.

---

## 12. References to Owner's Other Projects

| Pattern | Source |
|---|---|
| Multi-tenant via Postgres RLS, `tenant_id` everywhere | `/Volumes/Studio Storage/Development/Majiks-Producer/MAJIKS-PRODUCER-ARCHITECTURE.md` §6 |
| Tenant → Workspace → Show hierarchy | Majiks-Producer canonical data model §2 |
| FastAPI lifespan + structlog + Keycloak JWKS refresh | `/Volumes/Studio Storage/Development/Stable/server/app/main.py` |
| Brigade `execute_tool_loop` as the agent reasoning surface | `/Volumes/Studio Storage/Development/Unicorn-Brigade/CLAUDE.md` |
| Monorepo with `apps/api`, `apps/web`, `packages/`, `tools/`, `infra/` | `/Volumes/Studio Storage/Development/Listing-Ops/README.md` "Architecture" section |
| Per-task model routing config | Listing-Ops `infra/ai-tasks.yaml` |
| Bigboy as Tier 0 compute, midboy1 as P40 GPUs | Majiks-Producer §3, Listing-Ops architecture diagram |
| Hierarchical workflows (Orchestrator → Team Leads → Workers) inspiration for Producer → subagents | Unicorn-Brigade workflows/engine.py |
