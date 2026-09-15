# Podcast-Ops Studio — Punch List for Codex

> Paste this into Codex as a self-contained brief. The v1 studio is already shipped and running locally. This is the **focused enhancement pass** to make it usable for the operator to produce real podcast episodes without needing to drop back to a chat agent for help.
>
> Scope is intentionally narrow. Don't expand it. Don't refactor what works. Don't start the multi-tenant / Unicorn Commander integration yet (that's `PODCAST-OPS-MULTITENANT-CODEX-PROMPT.md` and comes later).

---

## Working environment

| Thing | Path / URL |
|---|---|
| **Project root** | `/Volumes/Studio Storage/Development/Podcast-Ops/` |
| **Frontend** | `apps/web/` (Next.js 15 + React 19 + TypeScript + Tailwind + Monaco editor + shadcn/ui + Wavesurfer.js) |
| **Backend** | `apps/api/` (FastAPI + Python 3.13, uvicorn, httpx) |
| **Studio React component** | `apps/web/src/components/studio.tsx` |
| **API entrypoint** | `apps/api/app/main.py` |
| **Run script** | `apps/api/run.sh` (sources `.env`, launches uvicorn on 8011) |
| **Env file** | `apps/api/.env` (VibeVoice URL via Tailscale IP, Brigade URL, music catalog path) |
| **Existing render tool** | `tools/audio/render_episode.py` (wraps VibeVoice, chunks by section) |
| **Existing mix tool** | `tools/audio/build_episode_mix.sh` (ffmpeg, music intro+fade+outro) |
| **Sample show + episode** | `shows/magic-unicorn/a-layer-below/season-1-majiks/episodes/ep01-creative-ai-suite/` |
| **Source of truth** | `shows/magic-unicorn/the-layer-above/season-1-majiks/source/source-of-truth.md` (currently lives under `the-layer-above`; A Layer Below references the same content) |
| **Music beds** | `shows/magic-unicorn/the-layer-above/assets/music-beds/*.wav` |
| **Voice clone tests** | `tests/voice-clones/aaron-clone-test-*.mp3` |

VibeVoice runs on bigboy at `http://100.126.207.157:8885` (Tailscale IP — the `magicunicorn` hostname resolves to Cloudflare and won't work). The API already speaks to it. Don't change the URL.

To restart the API after backend changes: `pkill -f "uvicorn.*app.main"; bash apps/api/run.sh > /tmp/api.log 2>&1 &`

Web is at `http://localhost:3000`. Run `npm run dev` from `apps/web/` if it's down.

---

## What's working today (don't break)

Validated end-to-end in smoke testing:
- `GET /health`, `/shows`, episode detail with script + 25 audio versions
- `PUT /script` saves with full roundtrip
- `GET /voices` returns 20 real voices including the cloned `aaron`
- `GET /voices/{id}/sample` renders a WAV preview from VibeVoice
- `GET /music-beds` returns 4 catalog beds
- `POST /render` enqueues, `GET /render-jobs/{id}` returns status + streaming log
- `POST /mix` synchronously produces WAV + MP3 (~27s for 11-min episode)
- `POST /annotations` saves; `GET /annotations` lists
- `POST /voices/clone` accepts multipart, transcodes, installs on bigboy
- Side-by-side audio compare with synced scrub
- Section-level render

---

## The punch list (5 backend items + 2 UI items)

Implement these in order. Each item lists the **why**, the **acceptance criteria**, and the **files to touch**.

### 1. New episode from template

**Why**: When the operator drafts Ep 2 of A Layer Below, they want to inherit Ep 1's cast (aria/beck), target minutes, DDPM steps, music bed, pronunciation notes, and brand voice. Currently they'd have to hand-copy frontmatter and risk forgetting fields.

**Backend** (`apps/api/app/main.py`):
- New endpoint `POST /shows/{show}/seasons/{season}/episodes/{ep}/duplicate`
- Body: `{ "new_slug": "ep02-product-loop", "new_title": "Episode 2 title", "carry_body": false }`
- Behavior: copies the source episode's `script.md` frontmatter (everything between the `---` delimiters), drops the body, writes a new `script.md` at the new episode path with a single placeholder `## § 0 · Cold open` section.
- Returns the new episode's metadata payload (same shape as `GET /episodes/{ep}`).

**Frontend** (`apps/web/src/components/studio.tsx`):
- Episode tree: each episode gets a "Duplicate" context-menu item.
- Click → modal asks for new slug + title → POST → tree re-fetches → opens the new episode.

**Acceptance**:
- Right-click Ep 1 → Duplicate → "ep02-product-loop" + "Make music that lives somewhere" → new episode appears in tree under same season.
- Open it. Frontmatter has cast (aria=host, beck=host), target_minutes 9, DDPM 50, pronunciation_notes, music bed reference. Body is blank except a `§ 0 Cold open` placeholder.

---

### 2. Per-show defaults

**Why**: Cast, music bed, DDPM steps, target length — these are show-level, not episode-level. Right now each new episode could drift. The "show" itself should hold defaults that new episodes inherit.

**Backend**:
- Add an optional `show.yaml` (or `show.md` with frontmatter) at `shows/{show}/show.yaml`. Schema:
  ```yaml
  slug: a-layer-below
  title: A Layer Below
  defaults:
    cast: { aria: alice, beck: carter }
    music_bed: og_unicorn__echoes_in_code_part_ii_.wav
    ddpm_steps: 50
    cfg_scale: 1.3
    target_minutes: 9
    intro_hot_s: 3.5
    intro_fade_s: 4.0
    outro_s: 7.0
    pronunciation_notes: |
      Majik's * → Magic's *
      Shafen → Shahfin
      majiks.io → magic's dot i o
  ```
- `GET /shows/{show}` returns the show's defaults.
- `PUT /shows/{show}/defaults` saves the file.
- The duplicate-episode endpoint from #1 reads show defaults first, falls back to source episode's frontmatter.

**Frontend**:
- New "Show settings" gear icon next to the show name in the tree.
- Opens a form for the defaults (cast picker, music picker, sliders for DDPM/CFG/target_minutes).
- "Save" writes back via `PUT /shows/{show}/defaults`.

**Acceptance**:
- Open A Layer Below show settings. See current defaults.
- Change DDPM to 75 → save → duplicate Ep 1 → new episode has DDPM 75 in its frontmatter.

---

### 3. Source-of-truth doc surface

**Why**: While writing a new episode, the operator needs to reference verified facts (registry numbers, dates, partnership status, etc.). That lives in `source-of-truth.md`. Currently the studio doesn't surface it. Open in another window = friction.

**Backend**:
- `GET /shows/{show}/seasons/{season}/source` — returns the contents of `shows/{show}/{season}/source/source-of-truth.md` (or `null` if not present). Read-only for v1.
- Look in: `shows/{show}/{season}/source/source-of-truth.md`, then `shows/{show}/source/source-of-truth.md` (show-wide fallback).

**Frontend**:
- Add a "Brief" tab next to the script editor (the editor pane becomes tabbed: "Script" | "Brief").
- "Brief" tab renders the source-of-truth markdown read-only.
- Searchable (⌘F in the brief).

**Acceptance**:
- Open Ep 1. Click "Brief" tab. See the source-of-truth content rendered with Markdown.
- Type "ISRC" in search → highlights all matches.

---

### 4. Brigade fast-fail + UI error

**Why**: Validated as broken in smoke test. `POST /ai/script-edit` hangs because the httpx client uses a 120-second timeout. Without `BRIGADE_API_KEY` set, the request fails after 120s with no signal to the user.

**Backend** (`apps/api/app/main.py:641` — `call_brigade`):
- If `BRIGADE_API_KEY` is empty, immediately return `None` (don't even attempt the HTTP call). The local fallback already runs in that case.
- For actual Brigade calls, lower the httpx timeout to 10s. Catch timeout/connection errors and surface them as `{ "ok": false, "error": "brigade_timeout" }` in the response.
- The `/ai/script-edit` endpoint should always return within 15s, never 120s.

**Frontend**:
- When `/ai/script-edit` returns `{ ok: false, error: ... }`, show a toast: *"AI edit unavailable — set BRIGADE_API_KEY in apps/api/.env to enable. Using local fallback for now."*
- When `source: "local-fallback"` comes back, badge the diff as "local fallback" so the operator knows it wasn't Brigade.

**Acceptance**:
- Without `BRIGADE_API_KEY` set in `.env`: AI edit completes in <2s with local fallback + visible badge.
- With a valid key: AI edit calls Brigade, returns within 10s, no badge.

---

### 5. Render queue visibility

**Why**: When the operator kicks off 2 or 3 section renders back-to-back, they currently can't see queue depth or ETAs. They have to remember what they queued.

**Backend**:
- `GET /render-jobs?status=active` — returns all jobs with status `queued` or `running`.
- `GET /render-jobs?episode={episode_id}&limit=10` — recent jobs for an episode.
- Include per-job: `eta_s` (best-effort — based on script length and DDPM steps).

**Frontend**:
- Sidebar panel on the right edge of the studio. Collapsed by default. Header shows count: "Jobs: 2 running, 1 queued."
- Expand to see job list with: episode, version label, status, progress %, ETA, cancel button.
- Auto-refreshes every 2s (or via existing WebSocket if Codex wired it).
- Cancel button → `DELETE /render-jobs/{id}` (add this endpoint too — sends SIGTERM to the subprocess).

**Acceptance**:
- Kick a section render → sidebar shows "Jobs: 1 running" with progress.
- Kick a second → "Jobs: 1 running, 1 queued."
- Cancel the queued one → job disappears from queued.

---

### 6. UX polish: keyboard shortcuts

**Why**: Mouse-only iteration is slow. The operator should be able to save + render + play with the keyboard.

**Frontend** (`apps/web/src/components/studio.tsx` — Monaco editor + global hotkeys):
- `⌘S` / `Ctrl+S` — save script (calls existing `PUT /script`).
- `⌘R` / `Ctrl+R` — render section under cursor (find the closest `## §` heading above the cursor, kick a section render).
- `⌘↩` / `Ctrl+Enter` — play current section in the most-recent audio version (seek waveform to that section's start, play).
- `⌘E` / `Ctrl+E` — open AI edit prompt for selected text.
- `⌘P` / `Ctrl+P` — quick episode switcher (fuzzy-find across all shows/episodes).
- Hover tooltips on every button show the shortcut.

**Acceptance**:
- All shortcuts work. Visual hint shown on first use (e.g., a one-line "Try ⌘S to save" tip on first edit).

---

### 7. UX polish: speaker color-coding in editor

**Why**: When scanning a script, `**ARIA:**` and `**BECK:**` and `**MARGOT:**` all blend together. Color-coding makes the editor 3x more scannable.

**Frontend** (Monaco editor language definition):
- Detect speaker tags `\*\*([A-Z][A-Z0-9]*):\*\*`.
- Assign each unique speaker a distinct color from a fixed palette (e.g., teal for first speaker, amber for second, magenta for third).
- Color persists per speaker name within a session (so ARIA is always teal in this session).
- Apply the color to the speaker tag AND the entire line of dialogue that follows it.

**Acceptance**:
- Open Ep 1. ARIA lines are one color, BECK lines another. Distinct, not garish.
- Add a third speaker on a test script → they get a third distinct color.

---

## What NOT to do in this pass

- **Don't** add multi-tenant, auth, or RBAC. That's the next pass (separate Codex prompt: `PODCAST-OPS-MULTITENANT-CODEX-PROMPT.md`).
- **Don't** refactor `render_episode.py` or `build_episode_mix.sh`. They work. Wrap them.
- **Don't** add a producer-chat / wizard interface. That's a separate end-user product layer that comes after this enhancement pass.
- **Don't** touch the `.env` file beyond what's documented in #4 (Brigade fast-fail).
- **Don't** migrate filesystem-as-state to a database. Filesystem is the design.
- **Don't** rebuild the React tree. Add to it.
- **Don't** add new dependencies unless absolutely necessary. Stay with the existing stack.

---

## How to verify everything

After the punch list is done, run through this end-to-end as the user:

1. Open `http://localhost:3000`.
2. Right-click "Ep 1" → Duplicate → name it `ep02-product-loop` → "Make music that lives somewhere".
3. New episode opens. Frontmatter is inherited.
4. Click "Brief" tab. See the source-of-truth content rendered.
5. Type `⌘E` on a selected paragraph → AI edit modal opens → instruction: "make this punchier" → returns suggestion in <2s with "local fallback" badge (no Brigade key set).
6. Approve the edit.
7. `⌘S` saves.
8. Position cursor in `## § 0`. Press `⌘R`. Section renders. Right-sidebar shows "Jobs: 1 running."
9. When done, `⌘↩` plays the new section's audio.
10. Click waveform at 0:42 → add annotation "test" → reload page → annotation persists.
11. Open Show Settings → change DDPM to 75 → save.
12. Duplicate again → new episode has DDPM 75 in its frontmatter.

If all 12 steps work, ship it.

---

## Where to look for context

- `apps/api/app/main.py` — the existing FastAPI service. Read end-to-end before editing.
- `apps/web/src/components/studio.tsx` — the main React component. The three-pane layout, all the existing UI.
- `tools/audio/render_episode.py` — wrapped by the render endpoint.
- `tools/audio/build_episode_mix.sh` — wrapped by the mix endpoint.
- `docs/PODCAST-OPS-WEBGUI-CODEX-PROMPT.md` — the original v1 prompt that produced what's there today. Useful for understanding what was intentional vs. what was implementation choice.
- `shows/magic-unicorn/a-layer-below/season-1-majiks/episodes/ep01-creative-ai-suite/script.md` — the canonical script format Codex needs to preserve in templating.

---

## First commit

The minimal viable first commit is **#4 (Brigade fast-fail)** — it's the smallest change, all backend, and fixes a known broken state. Do that first, push, verify the API still works, then continue with #1 (duplicate endpoint), then #2-#7 in any order.

After this pass lands, the studio is good enough to use for real episode production. Then we can talk about multi-tenant.
