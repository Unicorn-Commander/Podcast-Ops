<div align="center">

# Podcast-Ops

A local studio for multi-voice podcast episodes: markdown scripts, speech rendering, a music mix, and AI edits that land only after you approve them.

[![Licence](https://img.shields.io/badge/licence-AGPL--3.0--or--later-blue)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.1.0-blue)](apps/api/pyproject.toml)
[![Python](https://img.shields.io/badge/python-3.13-3776AB?logo=python&logoColor=white)](apps/api/pyproject.toml)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.136.1-009688?logo=fastapi&logoColor=white)](apps/api/uv.lock)
[![Next.js](https://img.shields.io/badge/Next.js-15.5.18-black?logo=nextdotjs&logoColor=white)](apps/web/package-lock.json)
[![Self-hosted](https://img.shields.io/badge/self--hosted-yes-3DDC84)](#quick-start)

[Quick start](#quick-start) · [Features](#feature-tour) · [Agents](#built-for-agents) · [Architecture](#architecture) · [Suite](#part-of-unicorn-commander)

</div>

<p align="center">
  <img src="docs/screenshots/episodes.webp" width="880" alt="Episodes view in the Podcast-Ops studio, with the show tree and the open script">
  <br>
  <em>Episodes view. The show tree and the script for the episode you have open.</em>
</p>

## What is Podcast-Ops?

Podcast-Ops is the production desk for scripted, multi-voice shows. A producer keeps each episode as markdown on disk, renders the spoken sections through a VibeVoice HTTP server, and mixes a music bed into a loudness-normalized WAV and MP3.

It is for people who want the episode files in git and a studio UI on top of them. Chat and script suggestions can go through [Unicorn Brigade](https://github.com/Unicorn-Commander/Unicorn-Brigade). The studio inserts an AI edit into the editor only after you approve it, and saving the file is a separate step. You run the API and the web app yourself. This repository does not share a database with the rest of the suite.

## Highlights

- **The episode is a folder.** Under `shows/`, each episode holds `script.md`, `notes.md`, `episode.state.json`, `episode.annotations.jsonl`, and `episode.chat.jsonl`. The checkout contains 2 shows, 3 seasons, 8 episode directories, and 7 scripts, so the studio is not empty on first launch.
- **One studio page.** The Next.js app is a single page: show tree, Monaco script editor, waveform player, and an A/B compare view. It talks to the FastAPI app on port 8011.
- **Section rendering.** A render job calls `tools/audio/render_episode.py`, which sends each `## §` section to VibeVoice and concatenates the WAVs with 0.6 seconds of silence. You can re-render selected sections. One job runs at a time. The queue lives in the API process and is gone when that process exits.
- **A finished mix.** `tools/audio/build_episode_mix.sh` plays an intro, ducks the bed under the voice, swells an outro, and loudness-normalizes to −16 LUFS integrated, −1.5 dBTP true peak, loudness range 11. The API then writes a 256 kbps MP3 next to the WAV.
- **Approval before the script changes.** `POST /ai/script-edit` returns a diff. The studio writes that text into the editor after you press Approve. Chat history is appended to `episode.chat.jsonl` and does not modify `script.md`.
- **A bearer when you want one.** If `PODCAST_OPS_API_TOKEN` is set, every HTTP route except `GET /health` requires `Authorization: Bearer <token>`. The bundled studio does not send that header, so leave the token unset while you use the UI. The render-log WebSocket is not covered by that HTTP check.
- **Export only the file you named.** [`podcast-ops-export`](tools/exporter/README.md) inventories media, then uploads the exact artifact in your selection file. Script bodies stay on disk. The manifest carries a SHA-256 of the script. The bearer is sent to the ingest host, not to object storage.

## Feature tour

The production path is the script, then speech, then a mix.

```mermaid
flowchart LR
  script["script.md"] --> split["Split on section headings"]
  split --> vv["VibeVoice POST /podcast"]
  vv --> parts["Section WAVs"]
  parts --> concat["ffmpeg concat, 0.6s gaps"]
  concat --> voice["Voice-only WAV"]
  voice --> mix["build_episode_mix.sh"]
  bed["Music bed"] --> mix
  mix --> master["WAV at -16 LUFS"]
  master --> mp3["MP3 at 256 kbps"]
```

### Episode library

`GET /shows` walks `shows/`. A directory is a show when one of its children contains `episodes/`. A parent directory above that show is reported as the tenant. The tree in this repository sits at `shows/magic-unicorn/`.

Each episode row shows the title and `status` from the script frontmatter, how many audio files are present, and the newest audio mtime. The studio can duplicate an episode (`POST .../duplicate`): the new folder gets merged frontmatter, `status: draft`, an empty `audio/` directory, and either the old body or a single cold-open heading. Show settings write `defaults` into `<show>/show.yaml`. Adding a show is a new directory on disk. The “New show” button in the sidebar has no handler.

The season brief panel reads `source/source-of-truth.md` beside the season, beside the show, or from a sibling show in the same tenant that has the same season name.

### Script editor

The editor is Monaco. Scripts are markdown with YAML frontmatter. The renderer and the studio both understand this shape:

```markdown
---
show: Example Show
title: Cold open
target_minutes: 9
cast:
  aria: host       # voice: alice
  beck: host       # voice: carter
status: draft
---

## § 0 · Cold open

**ARIA:**
The line the listener hears.

**BECK:**
The reply.
```

`# voice:` on a cast line is the VibeVoice voice id. Speaker labels in the body are `**NAME:**` on their own line. Section headings are `## § N · Title`. Bracketed stage directions are stripped before synthesis. The editor status bar counts words and estimates spoken length at 165 words per minute, which is the same ratio `script_metrics` uses in the API.

`PUT .../script` replaces `script.md` and appends a row to `episode.state.json` under `script_saves`. Per-episode production notes are `notes.md`.

### Speech render

`POST /shows/{show}/seasons/{season}/episodes/{episode}/render` queues a job. The worker runs `tools/audio/render_episode.py` with `--host` set to `VIBEVOICE_URL`. A full render writes `<prefix>-voice-only.wav` and a sibling `.sections` directory of per-section WAVs. A partial render rebuilds the requested sections into that directory and concatenates them.

`GET /render-jobs` and `GET /render-jobs/{job_id}` read the in-memory job list. `DELETE /render-jobs/{job_id}` marks the job cancelled and terminates the child process. `WS /render-jobs/{job_id}/stream` pushes log lines. Completed and failed renders are also appended to `episode.state.json`.

The request body accepts `version`, `ddpm_steps`, `cfg_scale`, and `sections`. The API stores those fields and exports the step and scale values as environment variables for the child. `render_episode.py` does not read them. It posts `{"script", "voices", "format": "wav"}` to `{VIBEVOICE_URL}/podcast`. Speech quality is whatever that server does with that payload.

### Music mix

`POST .../mix` runs `tools/audio/build_episode_mix.sh` on a voice WAV that already exists in the episode `audio/` directory. `mode: music_under_voice` needs a music bed resolved from `assets/music-beds/`, a show-level bed directory, or the episode `audio/` folder. `mode: music_off` masters the voice alone. The shell script reads `INTRO_HOT_S`, `INTRO_FADE_S`, and `OUTRO_S` from the environment; the API sets them from the request. The request field `master_lufs` is stored on the mix row and is not passed into the shell script. The script always normalizes to −16 LUFS.

The API then encodes `<stem>.mp3` with `libmp3lame` at 256 kbps. Both outputs are listed on the episode.

`POST /music-beds/extract` cuts a WAV out of a file under `MUSIC_CATALOG_PATH` with ffmpeg (`-ss`, `-t`, stereo, 48 kHz PCM) and stores it in `assets/music-beds/`.

### Player, compare, and annotations

The player is wavesurfer.js. It can seek, and it can drop an annotation at the playhead. Annotations append to `episode.annotations.jsonl` with an id, timestamp, version label, time in seconds, text, and optional line or section.

The compare view plays two episode files from the same playhead. On macOS, the studio can ask the API to reveal a file in Finder (`POST .../open` runs `open -R`). That call is local to the machine running the API.

### Voices and music beds

`GET /voices` calls `{VIBEVOICE_URL}/voices`. If that call fails, the API returns a fixed fallback list of ten voice ids and marks them `source: fallback`. `GET /voices/{voice_id}/sample` returns a cached WAV, generating one with a short `POST /podcast` line the first time. `POST /voices/clone` converts an upload to 24 kHz mono PCM with ffmpeg and `scp`s it to `VIBEVOICE_VOICE_MOUNT_REMOTE`.

`GET /music-beds` lists audio files under `assets/music-beds/` and any `shows/**/assets/music-beds/` directory. This checkout does not include those audio files. WAV, MP3, and the other media extensions are gitignored.

Fourteen voice-profile markdown files live under `shows/magic-unicorn/the-layer-above/season-1-majiks/voices/`. They are show notes. `GET /voices` does not read them.

### Chat and script edits

The studio chat rail calls `POST /chat/brigade` and streams server-sent events. The agent id is one of `majik`, `the-general`, `gunny`, or `gflow`. Any other id is treated as `majik`. The system prompt includes a JSON snippet of the episode context, truncated at 12,000 characters. Turns are appended to `episode.chat.jsonl`.

When `BRIGADE_BASE_URL` and `BRIGADE_API_KEY` are both set, chat streams from `{BRIGADE_BASE_URL}/openai/v1/chat/completions`. When they are not set, the API streams a local notice that Brigade is unconfigured.

`POST /ai/script-edit` asks Brigade for a revised markdown document and returns a unified diff. The web client shows that diff and waits for Approve. If Brigade is unset or errors, and the instruction contains “tight” or “short”, a local fallback deletes a fixed list of filler words. Any other instruction is returned unchanged. `POST /ai/generate-script` is API-only. The web client does not call it. Its local fallback is a two-speaker skeleton with frontmatter and two sections.

### Selected export

The exporter is a separate CLI. It does not call the studio API, and it does not render or mix. Full operator notes are in [`tools/exporter/README.md`](tools/exporter/README.md). Use your own `--root` and `--endpoint`. The sample values in that file are not a public server. The contract, short version:

1. `propose` writes a metadata report (path, size, ffprobe duration) for media under one tenant, show, and season. It does not choose a take.
2. You copy [`tools/exporter/selection.example.yaml`](tools/exporter/selection.example.yaml) to `selection.yaml` (gitignored) and name one artifact path per episode. Paths must stay inside `shows/<tenant>/<show>/<season>/episodes/<episode>/` and use a wav, mp3, m4a, or flac suffix. An optional annotations path must be that episode’s `episode.annotations.jsonl`.
3. `manifest` hashes the selected files after a stability wait. It records git HEAD, sizes, script SHA-256, and observed status. It refuses paths that move while being read, symlinks that leave the root, and empty files.
4. `push` rebuilds the manifest from the selection, `POST`s `/manifest`, `POST`s `/parts`, uploads bytes to the returned HTTPS URLs, and `POST`s `/complete`. Redirects are refused. A changed hash is a new version. A missing selected file is reported `available: false`.

Set `PODCAST_EXPORT_TOKEN` in the environment. The CLI will not take the token as an argument. Twelve tests in [`tests/test_exporter.py`](tests/test_exporter.py) cover this contract.

### Audio checks and the other CLIs

These tools are not buttons in the studio. They are scripts next to the API:

| Tool | What it does |
|---|---|
| [`tools/audio/audio_qa.py`](tools/audio/audio_qa.py) | Writes `qa-report.md`: transcription, long silences, loudness, and a word diff against `script.md` when you pass `--script`. |
| [`tools/audio/render_suite_dramabox.py`](tools/audio/render_suite_dramabox.py) | Renders a two-host script one turn at a time through DramaBox, then splices and normalizes. |
| [`tools/audio/splice_dramabox.py`](tools/audio/splice_dramabox.py) | Splices an existing DramaBox `manifest.json` directory into one WAV. |
| [`tools/audio/generate_stings.py`](tools/audio/generate_stings.py) | Asks an ACE-Step HTTP server for short stings described by a JSON spec. |
| [`tools/audio/build_announcer_intro.sh`](tools/audio/build_announcer_intro.sh) | Mixes announcer voice, a music bed, and an applause file with ffmpeg. |
| [`tools/audio/start_acestep_sft.sh`](tools/audio/start_acestep_sft.sh) | Starts an ACE-Step API process for sting generation. |

`audio_qa.py` reads `WHISPER_URL` and `WHISPER_MODEL`, and it uses SSH for the silence and loudness pass. Set those for your own machines. The defaults in the script are not a public service.

## Built for agents

This repository has no MCP server and no A2A endpoint. The agent surface is HTTP on the studio API.

`GET /chat/agents` returns four ids:

| Id | Role stored in the API |
|---|---|
| `majik` | Main producer agent for the studio ecosystem |
| `the-general` | Strategic direction |
| `gunny` | Implementation and execution |
| `gflow` | Process and workflow |

Script routes call Brigade’s OpenAI-compatible chat completions first (`{BRIGADE_BASE_URL}/openai/v1/chat/completions`) with the model name you send. A timeout, connection failure, or other `httpx.RequestError` stops there. An HTTP error status, or a body that is not a chat message, is tried once more at `{BRIGADE_BASE_URL}/agents/{BRIGADE_SCRIPT_AGENT}/chat`. If that second call fails, the route uses the local fallback. `BRIGADE_SCRIPT_AGENT` defaults to `podcast-scriptwriter`. A missing base URL or key skips the network and uses the local fallback described above. `GET /health` reports `brigade_configured`.

The studio does not send a Podcast-Ops bearer. Send one yourself when `PODCAST_OPS_API_TOKEN` is set. Replace the placeholders. Do not commit a real token.

```bash
curl -sS "http://localhost:8011/chat/agents"

curl -N -sS "http://localhost:8011/chat/brigade" \
  -H "Authorization: Bearer <podcast-ops-api-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "agent": "majik",
    "stream": true,
    "episode_context": {
      "show": "<show>",
      "season": "<season>",
      "episode": "<episode>"
    },
    "messages": [
      {"role": "user", "content": "What is the cold open doing?"}
    ]
  }'

curl -sS "http://localhost:8011/ai/script-edit" \
  -H "Authorization: Bearer <podcast-ops-api-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "current_script": "<markdown script>",
    "instruction": "Tighten the cold open.",
    "model": "podcast-scriptwriter"
  }'
```

Omit the `Authorization` header when `PODCAST_OPS_API_TOKEN` is empty. When the token is set, a missing or wrong header receives HTTP 401.

## Quick start

This repository has no Docker Compose file and no image. Run the API and the studio as two processes. Browsing and editing the checked-in scripts need no other service. Rendering speech needs a VibeVoice server. Live model replies need Unicorn Brigade. With it unset, chat streams a notice that Brigade is not configured, and script edit uses the local fallback.

You need:

- Python 3.13 and [uv](https://docs.astral.sh/uv/)
- Node.js and npm (the web app ships `package-lock.json`)
- `ffmpeg` and `ffprobe` on `PATH` for mix, MP3 encode, durations, voice upload, and export reports

```bash
git clone https://github.com/Unicorn-Commander/Podcast-Ops.git
cd Podcast-Ops
```

Terminal A, the API:

```bash
cd apps/api
./run.sh
```

`apps/api/run.sh` loads `apps/api/.env` when that file exists, defaults `PODCAST_OPS_ROOT` to the repository root, and listens on `0.0.0.0` port `8011` (`PORT` overrides the port). Leave `.env` absent for a first run. `.env.example` contains machine-specific paths. Copy it only after you replace those paths, and leave `PODCAST_OPS_API_TOKEN` empty while you use the bundled studio.

Terminal B, the studio:

```bash
cd apps/web
npm ci
npm run dev
```

Open <http://localhost:3000>. The API health check is <http://localhost:8011/health>.

The API’s CORS regex allows `http://localhost` and `http://127.0.0.1` on ports 3000–3004. `npm run dev` uses port 3000 when that port is free. Pin it with:

```bash
npm run dev -- --port 3000
```

`NEXT_PUBLIC_API_BASE_URL` selects the API origin. It does not change which browser origins the API accepts. A page on any other origin needs a change to the CORS regex in `apps/api/app/main.py`.

Before the first render, set `VIBEVOICE_URL` to the base URL of a server that implements `GET /voices` and `POST /podcast`. The code default is not a public server. Voice clone also needs `VIBEVOICE_VOICE_MOUNT_REMOTE`.

## Run from source

The two processes above are the source path. There is no separate install step for the API beyond `uv`, which `run.sh` invokes (`uv run uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --reload`).

Render one checked-in script without the UI. This calls VibeVoice and writes a WAV. It does not mix.

```bash
python tools/audio/render_episode.py \
  shows/magic-unicorn/a-layer-below/season-1-majiks/episodes/ep01-creative-ai-suite/script.md \
  /tmp/episode-voice-only.wav \
  --host "$VIBEVOICE_URL"
```

Mix that WAV under a bed you supply:

```bash
tools/audio/build_episode_mix.sh \
  /tmp/episode-voice-only.wav \
  path/to/bed.wav \
  /tmp/episode-final.wav
```

`MUSIC_OFF=1` on that command masters the voice and skips the bed.

Inventory media for the sample show (the report is metadata only; this clone has no audio files checked in):

```bash
python tools/exporter/exporter.py propose \
  --root . \
  --output /tmp/proposed-selection.md
```

The defaults for `--tenant`, `--show`, and `--season` match `shows/magic-unicorn/the-layer-above/season-1-majiks`. Pass the flags when you point `--root` at another tree. Push only after you have written a selection file and set `PODCAST_EXPORT_TOKEN` and `--endpoint` to your ingest base URL:

```bash
python tools/exporter/exporter.py push \
  --root . \
  --selection selection.yaml \
  --endpoint "https://<producer-host>/api/podcast"
```

## Configuration

Names only. Do not commit filled-in `.env` files, selection files, or tokens. `apps/api/.env` is gitignored. `selection.yaml` is gitignored.

| Variable | Read by | Meaning |
|---|---|---|
| `PODCAST_OPS_ROOT` | API | Directory whose `shows/` tree is the catalog. `run.sh` defaults it to the repository root when unset. |
| `VIBEVOICE_URL` | API | Base URL of the VibeVoice server. Render, the voice list, and voice samples call it. |
| `BRIGADE_BASE_URL` | API | Unicorn Brigade origin, with no trailing path. Chat and script routes append `/openai/v1/chat/completions`. |
| `BRIGADE_API_KEY` | API | Bearer sent only to Brigade. Both this and `BRIGADE_BASE_URL` must be set or the API stays on the local fallback. |
| `BRIGADE_SCRIPT_AGENT` | API | Agent id used on the script-route fallback. The code default is `podcast-scriptwriter`. |
| `MUSIC_CATALOG_PATH` | API | Directory searched by `POST /music-beds/extract` for a source filename. |
| `VIBEVOICE_VOICE_MOUNT_REMOTE` | API | `scp` destination for `POST /voices/clone`. |
| `PODCAST_OPS_API_TOKEN` | API | Shared bearer for HTTP routes other than `GET /health`. Empty means those routes are open. |

Also read by code, not listed in `apps/api/.env.example`:

| Variable | Read by | Meaning |
|---|---|---|
| `PORT` | `apps/api/run.sh` | API port. Default `8011`. |
| `UV_PYTHON` | `apps/api/run.sh` | Interpreter uv should use. Default `python3.13`. |
| `NEXT_PUBLIC_API_BASE_URL` | `apps/web` | Origin the studio calls. The client default is `http://localhost:8011`. |
| `PODCAST_EXPORT_TOKEN` | `tools/exporter/exporter.py` | Bearer for `push`. Required together with `--endpoint`. |
| `WHISPER_URL` | `tools/audio/audio_qa.py` | Transcription service base URL. |
| `WHISPER_MODEL` | `tools/audio/audio_qa.py` | Model name sent to that service. |

`audio_qa.py` also reads an SSH destination for the remote loudness pass. Override it. Do not rely on the script default.

## Architecture

```mermaid
flowchart TB
  subgraph repo [This repository]
    Web["Studio<br/>apps/web"]
    API["Studio API<br/>apps/api"]
    Shows["shows/ tree"]
    Render["render_episode.py"]
    Mix["build_episode_mix.sh"]
    Export["podcast-ops-export"]
    QA["audio_qa.py"]
  end
  Web -->|"HTTP, port 8011"| API
  API --> Shows
  API --> Render
  API --> Mix
  Render --> Shows
  Mix --> Shows
  Export --> Shows
  QA --> Shows
  Render -->|"POST /podcast"| VV["VibeVoice server"]
  API -->|"optional chat and script calls"| Brigade["Unicorn Brigade"]
  Export -->|"/manifest, /parts, /complete"| Ingest["Ingest URL from --endpoint"]
  QA --> Whisper["Transcription HTTP service"]
  Render --> FF["ffmpeg and ffprobe"]
  Mix --> FF
```

| Piece | Role |
|---|---|
| [`apps/web`](apps/web) | Next.js 15.5.18 and React 19.2.6. One route, `src/app/page.tsx`, renders the studio. Tailwind CSS 4. |
| [`apps/api`](apps/api) | `podcast-ops-api` 0.1.0. FastAPI 0.136.1 locked in `apps/api/uv.lock` (`pyproject.toml` allows `>=0.115.0`). All routes are in [`apps/api/app/main.py`](apps/api/app/main.py). |
| `shows/` | Authoritative episode state. The API is an index and a job runner over these files. |
| [`tools/audio`](tools/audio) | Render, mix, QA, DramaBox, stings, and the announcer-intro script. |
| [`tools/exporter`](tools/exporter) | Read-only, selection-locked upload. |
| [`tests/test_exporter.py`](tests/test_exporter.py) | Twelve contract tests. No API or web test suite is in the tree. |
| [`docs/`](docs) | Earlier design notes. See [Development](#development). |

### HTTP API

Thirty HTTP routes and one WebSocket, all declared on the FastAPI app:

| Method | Path |
|---|---|
| GET | `/health` |
| GET | `/shows` |
| GET | `/shows/{show}` |
| PUT | `/shows/{show}/defaults` |
| GET | `/shows/{show}/seasons/{season}/source` |
| GET | `/shows/{show}/seasons/{season}/episodes/{ep}/script` |
| PUT | `/shows/{show}/seasons/{season}/episodes/{ep}/script` |
| GET | `/shows/{show}/seasons/{season}/episodes/{ep}/notes` |
| PUT | `/shows/{show}/seasons/{season}/episodes/{ep}/notes` |
| GET | `/shows/{show}/seasons/{season}/episodes/{ep}/chat` |
| GET | `/shows/{show}/seasons/{season}/episodes/{ep}` |
| POST | `/shows/{show}/seasons/{season}/episodes/{ep}/duplicate` |
| GET | `/shows/{show}/seasons/{season}/episodes/{ep}/audio/{filename}` |
| POST | `/shows/{show}/seasons/{season}/episodes/{ep}/render` |
| GET | `/render-jobs` |
| GET | `/render-jobs/{job_id}` |
| DELETE | `/render-jobs/{job_id}` |
| WebSocket | `/render-jobs/{job_id}/stream` |
| POST | `/shows/{show}/seasons/{season}/episodes/{ep}/mix` |
| GET | `/shows/{show}/seasons/{season}/episodes/{ep}/annotations` |
| POST | `/shows/{show}/seasons/{season}/episodes/{ep}/annotations` |
| POST | `/shows/{show}/seasons/{season}/episodes/{ep}/open` |
| GET | `/voices` |
| GET | `/voices/{voice_id}/sample` |
| POST | `/voices/clone` |
| GET | `/music-beds` |
| POST | `/music-beds/extract` |
| GET | `/chat/agents` |
| POST | `/chat/brigade` |
| POST | `/ai/script-edit` |
| POST | `/ai/generate-script` |

```
Podcast-Ops/
├── apps/api/          FastAPI studio API
├── apps/web/          Next.js studio
├── shows/             Tenants, shows, seasons, episodes
├── tools/audio/       Render, mix, QA, and related CLIs
├── tools/exporter/    Selected-media export
├── tests/             Exporter contract tests
└── docs/              Design notes
```

## Part of Unicorn Commander

| App | What it does |
|---|---|
| [Ops-Center](https://github.com/Unicorn-Commander/Ops-Center) | The control plane: tenants, billing, federation, API keys, model routing |
| [Unicorn-Brigade](https://github.com/Unicorn-Commander/Unicorn-Brigade) | The agent layer: agents, tools, memory, orchestration |
| [Unicorn-Stable](https://github.com/Unicorn-Commander/Unicorn-Stable) | Humans and agents in the same room: chat, voice, video |
| [Accounting-Ops](https://github.com/Unicorn-Commander/Accounting-Ops) | Agent-native accounting and books |
| [Contact-Ops](https://github.com/Unicorn-Commander/Contact-Ops) | The shared contact and identity graph |
| [Customer-Ops](https://github.com/Unicorn-Commander/Customer-Ops) | Customers, pipeline, quotes and outreach |
| [Email-Ops](https://github.com/Unicorn-Commander/Email-Ops) | Agent-drafted email with a human approval inbox |
| [Project-Ops](https://github.com/Unicorn-Commander/Project-Ops) | Projects, tasks, time and invoices |
| [Meeting-Ops](https://github.com/Unicorn-Commander/Meeting-Ops) | Recordings, transcripts, summaries and action items |
| [Knowledge-Ops](https://github.com/Unicorn-Commander/Knowledge-Ops) | The wiki and memory your agents ground on |
| [Security-Ops](https://github.com/Unicorn-Commander/Security-Ops) | Authorized security scanning with engagement and attestation gates |
| [Tax-Planning-Ops](https://github.com/Unicorn-Commander/Tax-Planning-Ops) | Tax plans, scenarios and statutory deadlines |
| [Brand-Ops](https://github.com/Unicorn-Commander/Brand-Ops) | Brand kits, marks, voices and rules |
| **[Podcast-Ops](https://github.com/Unicorn-Commander/Podcast-Ops)** | **Episodes, audio QA and publishing** |
| [UUDA](https://github.com/Unicorn-Commander/UUDA) | The device agent for your fleet |
| [fleet-map](https://github.com/Unicorn-Commander/fleet-map) | Fleet inventory and topology map |

Podcast-Ops calls Unicorn Brigade for studio chat, script edit, and script generation when `BRIGADE_BASE_URL` and `BRIGADE_API_KEY` are set. Episode files stay in this checkout. The exporter can upload selected audio to an ingest URL you pass on the command line. No code in this repository reads or writes the other apps.

## Development

```bash
uv run --project apps/api python -m unittest discover -s tests -v
```

That runs the twelve exporter tests with the API project’s environment (Python 3.13, plus `pyyaml` and `httpx`). `ffmpeg` / `ffprobe` and `git` need to be on `PATH`. The tests build tiny WAV fixtures under `/tmp`.

The web lint script is ESLint:

```bash
cd apps/web
npm ci
npm run lint
```

`npm run build` is the production Next.js build. The API project has no lint or test extra in `pyproject.toml`.

[`docs/`](docs) holds earlier design notes: an architecture sketch, agent personas, voice-model research, and studio punch lists. Those notes describe a `podcast-ops` CLI, Postgres, Redis, package layout, and SSO middleware that are not in this tree, and they name internal hosts. Use this README and the code for what runs. The exporter’s current procedure is [`tools/exporter/README.md`](tools/exporter/README.md). [`apps/api/README.md`](apps/api/README.md) is the short API note: state file, annotations file, and port 8011.

## Security

Report a vulnerability through private GitHub Security Advisories on [Unicorn-Commander/Podcast-Ops](https://github.com/Unicorn-Commander/Podcast-Ops). Details are in [SECURITY.md](SECURITY.md). Please do not file a public issue that includes an unfixed exploit.

`run.sh` binds the API to all interfaces. The optional bearer is one shared secret for every HTTP caller, and it does not cover the render WebSocket. There is no per-user login in this code.

## Licence

Podcast-Ops is licensed under the GNU Affero General Public License v3.0 or later. The full text is [LICENSE](LICENSE).

If you modify this program and run it as a service for other people over a network, the AGPL requires you to offer those users the source of the version they use.

<div align="center">

Built by [Magic Unicorn](https://magicunicorn.tech) · part of [Unicorn Commander](https://unicorncommander.ai)

</div>
