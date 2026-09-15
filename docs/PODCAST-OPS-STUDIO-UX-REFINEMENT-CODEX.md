# Podcast-Ops Studio — UX Refinement + Brigade Chat Codex Prompt

> Paste into Codex (or Cursor / Claude Code agent / Zed) as a comprehensive **visual + interaction redesign** of the existing studio at `/Volumes/Studio Storage/Development/Podcast-Ops/apps/web/`. The backend (`apps/api/`) is functionally complete — this pass is almost entirely frontend, with one small Brigade-chat addition on the API side.
>
> The current v1 studio works mechanically but looks like a generic Tailwind admin panel. Aaron took a screenshot showing an empty sidebar (since-fixed CORS bug), generic chrome, sparse panels, and no brand presence. This is the pass that turns it from "functional foundation" into something he'd actually want to spend hours in.

---

## Mission

Take the existing Podcast-Ops studio at `apps/web/` and make it feel like a **professional creative studio**, not an internal admin panel. Add an embedded Brigade-powered chat panel so the producer can collaborate with AI agents from inside the studio without context-switching to another window.

The studio is the place where someone (today: Aaron) iterates on real investor-facing podcast episodes. It should feel like Linear meets Logic Pro meets a writer's tool. Not Stripe Dashboard. Not Grafana. Not WordPress.

---

## What exists today (read first)

| File | What it is |
|---|---|
| `apps/web/src/components/studio.tsx` | The main three-pane component |
| `apps/web/src/components/audio-player.tsx` | Wavesurfer-based player + `playFrom()` handle |
| `apps/web/src/lib/api.ts` | API client + types |
| `apps/web/src/app/globals.css` | Tailwind + Monaco speaker color classes |
| `apps/api/app/main.py` | FastAPI backend — all endpoints needed already exist |
| `apps/api/.env` | Connectivity config (VibeVoice via Tailscale IP, Brigade base URL, music catalog) |
| `shows/magic-unicorn/a-layer-below/show.yaml` | Per-show defaults — sample structure |
| `shows/magic-unicorn/a-layer-below/season-1-majiks/episodes/ep01-creative-ai-suite/script.md` | Canonical script.md with frontmatter |

Already-working endpoints (don't re-implement):
- `GET /shows`, `GET /episode/...`, `PUT /script`, `POST /render`, `GET /render-jobs/{id}`, `DELETE /render-jobs/{id}`, `POST /mix`, `POST /annotations`, `GET /annotations`, `POST /voices/clone`, `GET /voices`, `GET /voices/{id}/sample`, `GET /music-beds`, `GET /shows/{show}/seasons/{season}/source` (Brief), `PUT /shows/{show}/defaults`, `POST /shows/.../duplicate`, `POST /ai/script-edit`

**One new backend endpoint to add (see §6):** `POST /chat/brigade` for the chat panel.

---

## Brand + aesthetic direction

The studio's parent brands are **Magic Unicorn Unconventional Technology & Stuff Inc.** and **Magic's Studio**. Look at these for the actual brand voice:
- `https://majiks.studio` — *"Your music. Your machine. Your rules."*
- `https://majiks.online` — clean dark mode, deliberate typography, no SaaS bloat
- `https://majiks.io` — umbrella entry point

Aesthetic feel: **serious technical workspace with warm character.** Think:
- Linear (clean, dense, modern, dark-mode-first)
- Logic Pro X (audio-tool gravitas, panel-driven, contextual controls)
- Ulysses / iA Writer (the writing surface is the hero)
- A touch of unexpected warmth — Magic Unicorn whimsy in small details (e.g., one ✨ in the empty-state CTA, the literal unicorn glyph somewhere subtle), never in the core chrome.

Avoid:
- Generic Tailwind admin colors (slate-900 / gray-600 / blue-500 — feels like a template)
- Bento boxes everywhere (current UI is too box-grid)
- Bootstrap-style toolbars (chunky buttons in a row)
- Emoji-heavy interfaces (one or two ambient unicorn/sparkle accents max)

Concrete color direction:
- **Background**: rich deep navy `#0a0e1a` to `#0f1219` (not pure black, not slate-gray)
- **Surface**: subtle elevation `#141826` for panels, `#1a1f2e` for cards
- **Text**: primary `#e8ecf2`, secondary `#9ba5b5`, tertiary `#5a6478`
- **Accent (primary)**: a confident bright purple/violet — `#a36bff` or thereabouts. This is the Magic Unicorn signature color. Use for primary actions, active states, and important data.
- **Accent (secondary)**: warm gold `#ffc875` for highlights, status, "good" outcomes
- **Speaker colors** (preserved from current speaker color-coding):
  - Speaker 1 (typically host): teal `#5eead4`
  - Speaker 2: amber `#fbbf24`
  - Speaker 3+: rotate through magenta `#f472b6`, sky `#7dd3fc`, lime `#bef264`
- **Status colors** (semantic): success `#5eead4`, warning `#fbbf24`, danger `#f87171`, info `#7dd3fc`

Typography:
- **Sans-serif UI**: Inter or Geist Sans (the existing setup probably has one)
- **Monospace for code/markdown**: JetBrains Mono or Geist Mono
- **Display (sparingly)** — for the studio title and any hero text — consider a more characterful sans like Söhne, or stay on Inter at a tighter tracking. No Times New Roman or "creative" fonts.

---

## The three-pane redesign

The current layout (tree | editor | audio + annotations) is fundamentally correct. Refine it:

### Pane 1 — Episode tree (left, ~280px wide, collapsible to 56px)

- **Show as the unit**, not a flat list. Each show is an expandable section with seasons → episodes nested.
- **Episode rows show:** title + episode number + status badge (draft / rendering / ready) + last-render-time relative format ("2h ago"). Two lines, tight.
- **Status badge**: small filled pill with status color (orange for rendering, green for ready, gray for draft). Animate the rendering one with a subtle pulse.
- **Active episode**: distinct background + left border in accent purple.
- **Context menu** (right-click): Duplicate, Rename, Open audio folder, Delete (with confirm). Currently exists as a button — make it a real right-click menu.
- **Show settings gear** appears on hover next to the show name → opens the per-show defaults modal.
- **Bottom section** of the pane: a compact "Voices" library showing all VibeVoice voices with a small play icon (hover-to-preview).
- **Footer of the pane**: "+ New show" / "+ Voice clone" buttons, minimal.
- **Collapsed state**: just episode-status icons stacked vertically, full sidebar restored on click.

### Pane 2 — Script editor (center, takes remaining width)

This is the **hero** of the app. Everything else serves it.

- **Top bar**: Episode title (editable inline). Status. Word count + estimated audio duration + estimated render time — live, updating as you type. Last saved indicator. Save button (only highlighted if dirty).
- **Tabs (not chunky tabs — minimal underline-style)**: Script · Brief · Notes
  - **Script** tab: the Monaco editor with current syntax highlighting + speaker color rows
  - **Brief** tab: rendered source-of-truth markdown with command-K search
  - **Notes** tab: free-form per-episode notes (new — episodes have `notes.md` next to `script.md`). Backend endpoint can be added: `GET/PUT /episode/{ep}/notes`.
- **Inline § section markers in the gutter**: each `## § N` heading gets a clickable marker showing section number + a "▶ render" icon and a "🎧 play this section" icon. Inline contextual actions, not buried in a panel.
- **Selected text → floating mini-toolbar**: Edit with AI · Speak this · Add annotation. Like Notion's selection menu.
- **Bottom strip of the editor**: estimated section-render times for each section. Click a section to scroll to it.
- **Frontmatter editor**: collapsed YAML panel above the script body. Default collapsed showing just the title + cast + status. Expand to edit. Form-mode toggle: "View as form" lets you edit frontmatter via labeled fields instead of YAML.

### Pane 3 — Right rail (right, ~360px wide, tabbed)

Tabs at the top: Voices · Render · Mix · Jobs · Chat

- **Voices tab**: Voice cast mapping with each speaker → voice dropdown. Each voice has a 🔊 button that plays a 2-second sample. "Clone new voice" expands an inline upload (drag-drop area + name field) instead of a modal.
- **Render tab**: DDPM slider (10–100), CFG slider (1.0–2.0), Model dropdown. Selected section indicator. "Render section §3" button (primary). "Render full episode" button (secondary). Time estimate updates as parameters change.
- **Mix tab**: Music bed picker (dropdown with preview button per bed), Intro hot duration, Intro fade duration, Outro duration, Target LUFS, Music-off toggle. "Mix now" button. Preview waveform of the mix-in-progress.
- **Jobs tab**: List of active + recent render/mix jobs. Each row: episode name, status, progress bar, ETA, log preview (expandable), cancel button. Auto-refresh via existing WebSocket or 2s poll. Empty state: "No active jobs."
- **Chat tab**: NEW — see §6 below.

### Bottom panel — Audio + annotations (full width, ~280px tall, collapsible)

- **Audio versions list** on the left side of the bottom panel — clickable rows, each row plays in the player on the right.
- **Wavesurfer player** in the middle, with:
  - Section markers overlaid on the waveform (lines + section numbers)
  - Annotation markers (dots on the waveform — click to view annotation)
  - Click anywhere on waveform → add annotation at that timestamp (popover input)
  - Side-by-side compare mode: two players synced for A/B
- **Annotations list** on the right side — each annotation shows timestamp, text, version. Click an annotation → seeks player to that time.
- **Keyboard**: `space` plays/pauses, `j/k` skip backward/forward, `m` adds annotation at current playhead.

---

## 6. Brigade chat panel (NEW major feature)

### Why this matters

The script editor is great for direct editing, but most of the iteration value comes from conversation: *"make this section tighter," "what's the precise comp set for AI music?" "summarize today's audio feedback."* Currently that has to happen in another window. Embedding it inside the studio with full episode context unlocks the real workflow.

### Backend addition

Add **`POST /chat/brigade`** to `apps/api/app/main.py`:

```python
class ChatRequest(BaseModel):
    agent: str = "majik"  # which Brigade agent to talk to
    messages: list[dict[str, str]]  # OpenAI-style {role, content}
    episode_context: dict[str, Any] | None = None  # show/season/ep slugs + script excerpt + recent annotations
    stream: bool = True

@app.post("/chat/brigade")
async def chat_brigade(request: ChatRequest):
    # Forward to Brigade's OpenAI-compat endpoint at
    # f"{BRIGADE_BASE_URL}/openai/v1/chat/completions"
    # with the agent's system prompt + episode context injected.
    # Stream SSE back to the frontend.
    ...
```

**Agents to expose** (configurable list from env or `apps/api/agents.yaml`):
- `majik` — main producer agent, knows the whole ecosystem
- `the-general` — strategic/high-level
- `gunny` — pragmatic implementation
- `gflow` — operational/process

(These already exist on `https://brigade.magicunicorn.dev` per Aaron's existing setup — just need to wire them into the chat panel as agent options.)

### Frontend chat UI

In the right-rail **Chat** tab:

- **Agent picker** at the top: dropdown with the 4 agents above, default `majik`. Each has a one-line description (`majik — knows the whole ecosystem`, etc.).
- **Message thread** below: chat bubbles, user-right, agent-left. Agent name + small icon as the sender.
- **Markdown rendering** in agent responses (the agent will often return formatted text).
- **Input area** at the bottom: textarea + send button. `⌘↩` to send.
- **Context awareness**: a chip above the input showing what's being sent as context — e.g., `📎 Ep 1 §3 (currently selected) + last 3 annotations`. Click to expand/edit what's included.
- **Streaming**: agent responses stream in token-by-token, not after-the-fact.
- **Quick actions** on each agent message: 🔁 retry, 📋 copy, ✂️ insert into script at cursor, 💬 follow up (kept the thread open).
- **Slash commands** in the input:
  - `/tighten` — request edit on selection
  - `/punch-up` — make selection more energetic
  - `/research <topic>` — agent does external lookup
  - `/render` — agent triggers render with current params (asks confirmation)
  - `/mix` — agent triggers mix
- **Persist conversations per episode** — `apps/api/state` already stores per-episode JSON; add `chat.jsonl` next to `episode.state.json`.

### Behavioral expectations

- Chat is a **collaborator**, not a chatbot. It should know about the current episode, the current selection, recent annotations, recent renders, the show's brand brief.
- Responses should be terse by default but expand to detail if asked.
- When the agent suggests an edit, the studio offers a one-click "apply this edit" with a diff preview — same UX as the existing AI-edit feature, just initiated from the chat.

---

## Component-by-component refinement specs

### Buttons + controls
- **Primary action**: filled accent purple, white text, subtle shadow, hover darkens
- **Secondary**: outline with accent purple border, accent purple text
- **Tertiary**: ghost — no background, secondary text color, hover surface
- **Destructive**: same as primary but danger red `#f87171`
- **Toggle/switch**: pill-shape, accent purple when on
- **Slider**: thin track, accent purple fill + handle
- **All controls**: 32px min height for click targets, 6px corner radius (slightly soft, not pill-round)

### Inputs
- **Text input**: dark surface, secondary text border, accent purple focus ring (2px)
- **Textarea**: same, with min-height 80px
- **Select/dropdown**: similar to input, dropdown chevron on right
- **Slider**: as above
- **File upload**: drag-drop area with dashed border, accent on drag-over

### Cards + panels
- **Surface elevation** via background color shift, not heavy shadows or borders
- **Panel headers**: small caps, 12px, tertiary text color, letter-spacing slightly wide
- **Panel padding**: 16px sides, 12px vertical
- **Dividers**: subtle 1px in `#1f2433`

### Empty states
- Every empty state needs **art + copy + CTA**:
  - Subtle illustration (ASCII-art-style icon or a thin-line svg — keep it minimal)
  - One sentence of explanation
  - A primary action button
- Example for empty Voices tab: *"No voice cast yet."* + *"Add a voice"* button
- Example for empty Jobs tab: *"No active jobs. Try rendering a section."* + ▶ Render section §0 quick-action

### Animations
- **Fade in** for newly-loaded content (200ms)
- **Slide-in** for panels opening (250ms with ease-out)
- **Subtle pulse** for in-progress states (renders, chat thinking)
- **No bouncy spring physics**, no overdone microinteractions

### Keyboard shortcuts (build on existing)
- `⌘S` save
- `⌘R` render current section
- `⌘↩` play current section / send chat message (context-dependent)
- `⌘E` open AI edit on selection
- `⌘K` quick-find episode / fuzzy switcher
- `⌘1`–`⌘5` switch right-rail tab (Voices/Render/Mix/Jobs/Chat)
- `?` global keyboard-shortcut overlay (modal)
- `j/k` audio scrub (when player focused)
- `m` add annotation at current playhead
- `space` play/pause player

---

## Reference products to invoke

Codex (or whichever agent) should look at these for inspiration on **specific patterns**, not wholesale clone:

| For this part of the studio | Look at |
|---|---|
| Three-pane shell + density + dark mode | **Linear** (linear.app), **Zed**, **Cursor** |
| Markdown editor + writer's-tool ergonomics | **Ulysses**, **iA Writer**, **Notion** (selection menu) |
| Audio panel + waveform + section markers | **Logic Pro X**, **Descript** (this is the closest existing analogue to what we're building) |
| Right-rail panel that doesn't feel like an admin panel | **Stripe Dashboard**'s right-rail (subdued, contextual), **Linear**'s sidebar |
| Chat panel inside a creative tool | **Cursor**'s sidebar chat, **Replit Agent**, **Notion AI** sidebar |
| Empty-state design | **Linear**, **Vercel** dashboards |
| Job queue / status visibility | **Vercel** deployment list, **Linear** triage |

---

## Acceptance criteria

The build is "done" for this pass when:

1. **A producer opening the studio for the first time** sees a populated episode tree, a meaningful empty state in the script pane until they click an episode, and immediately understands what to do.
2. **Selecting an episode** loads script + voices + audio versions + annotations in under 1 second on the local network. No "0 playable files" when there are 25 of them.
3. **The script editor** has live word count + duration estimates + speaker colors + inline section markers with render buttons.
4. **Right-rail tabs** are all functional: Voices (with sample previews), Render (with sliders + section target), Mix (with bed preview), Jobs (with progress + cancel), Chat (with Brigade integration + episode context awareness + streaming responses).
5. **The bottom audio panel** has the wavesurfer player, section markers overlaid, annotation markers overlaid, side-by-side compare working with synced scrub.
6. **Dark mode is the default** and **the palette is custom** (not Tailwind defaults). The accent purple is present and consistent.
7. **Keyboard shortcuts** work for save, render, play-section, chat-send, fuzzy-switcher, shortcut-overlay.
8. **The chat panel** can hold a conversation with the `majik` Brigade agent that knows about the currently-loaded episode (script excerpt + last 3 annotations injected as context). The agent can suggest an edit that the user can apply with one click.
9. **Empty states** everywhere have copy + CTA. No bare "No data" messages.
10. **It feels like a studio.** When you open it, you want to spend time in it. The current v1 feels like a CRM form.

---

## What NOT to do in this pass

- **Don't break the existing API contract.** The backend works. Add only the `/chat/brigade` endpoint plus any small additions explicitly called out.
- **Don't rebuild the editor.** Monaco stays. Just style + extend it.
- **Don't add user accounts / auth.** That's the multi-tenant pass (see `PODCAST-OPS-MULTITENANT-CODEX-PROMPT.md`).
- **Don't migrate to a new framework.** Next.js 15 + React 19 + Tailwind + shadcn/ui stays. Add components, don't replace foundations.
- **Don't add dozens of new dependencies.** If a component can be built in 80 lines of React with what's already installed, do that. Reserve new deps for things that genuinely warrant them (wavesurfer is fine; an entire UI library to replace shadcn is not).
- **Don't try to be cute with motion.** Subtle is the bar. Bouncy spring transitions and microinteractions galore make it feel like a portfolio site, not a studio.
- **Don't expand scope into Majik's Producer.** That's a sibling project at `/Volumes/Studio Storage/Development/Majiks-Producer/` with its own design language. We're not unifying with it in this pass — that's a future federation concern.

---

## Stretch goals (only if time)

- **Command palette** (`⌘K`): fuzzy across episodes, voices, music beds, recent annotations. Linear-style.
- **Onboarding tour**: 4-step interactive walk-through the first time a user opens an episode (skippable, dismissible).
- **Diff view in the AI edit modal**: side-by-side script-before-vs-after with syntax-highlighted changes.
- **Auto-save** with version history (every 30s while typing, 10 most recent versions kept on disk).
- **Theme picker**: dark / "auto" / "studio-light" — keep dark as default but support light for daylight use.

---

## First commit suggestion

Codex's first commit should be:
1. The color palette as Tailwind theme tokens in `apps/web/tailwind.config.ts`
2. The new three-pane shell layout (no functional changes, just the visual structure)
3. The Voices, Render, Mix, Jobs, Chat tab scaffolding (placeholder content if needed, but the tabs themselves should switch)
4. The `/chat/brigade` endpoint stub on the backend (can return placeholder data initially)

That's the "skeleton with the right bones" commit. Then iterate per the pane-by-pane specs above.

---

## Final note

The episode you'll see referenced everywhere — *A Layer Below S1 Ep 1, "The story of Magic's Studio"* — is the canonical test bed. It has 30+ audio versions, 8 sections, 2 host voices (Aria + Beck), and one spliced-in clip. Use it as the worked example for every UI state. If the studio handles that episode beautifully, it'll handle anything.
