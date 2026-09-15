# Podcast-Ops — Multi-Tenant Build Prompt (follow-up to v1)

> This is the follow-up to `PODCAST-OPS-WEBGUI-CODEX-PROMPT.md`. The v1 studio (single-user, filesystem-as-state) is already shipped and running locally. This doc covers turning it into a multi-tenant, multi-user, collaborative platform — the real product.
>
> Paste this into Codex (or your coding agent of choice) when ready to expand. Stage 1 is the minimum to unlock multi-user collab; Stages 2-4 are the path to a real SaaS / white-label product.

---

## Mission

Take the existing single-user `apps/web` + `apps/api` Podcast-Ops studio at `/Volumes/Studio Storage/Development/Podcast-Ops/` and rebuild the backend to support:

1. **Multi-user collaboration** (Stage 1)
2. **Multi-tenant isolation** (Stage 2)
3. **White-label per-brand deployments** (Stage 3)
4. **Public SaaS billing + onboarding** (Stage 4)

Each stage is independently shippable. Don't build Stage 4 before Stage 1 lands.

Keep the existing render + mix pipeline (`tools/audio/render_episode.py`, `tools/audio/build_episode_mix.sh`). Don't rewrite those. Wrap them.

---

## What we already have in the Magic Unicorn stack (leverage, don't rebuild)

| Component | Where | What it does |
|---|---|---|
| **Keycloak SSO** | `auth.unicorncommander.ai` (uchub realm) | OIDC. `uc_uid` claim is the canonical user ID. Use Keycloak — don't build new auth. |
| **Brigade** | `https://brigade.magicunicorn.dev` | LLM orchestrator + agents. Already used by Stable, Crisis-Ops, Meeting-Ops. OpenAI-compatible at `/api/v1/openai/v1`. |
| **Stable LiveKit** | `/Volumes/Studio Storage/Development/Stable/` | Multi-tenant LiveKit rooms for humans + agents. The pattern for real-time conversational features. |
| **Project Ops** | `https://api.projectops.magicunicorn.dev/api/v1` | Project / task tracking. Link episodes → tasks for review workflow. |
| **Garage** | bigboy + cluster | Object storage standard. Don't add MinIO. |
| **Ops-Center white-label** | per-brand subdomains | Pattern for multi-brand deployment. Each domain is its own instance, themed via `BRANDING_*` env vars. |
| **Postmark** | smtp.postmarkapp.com:587 | Transactional email. Per-service Postmark server for clean analytics. |
| **Federation Trust Modes** | Unicorn-Ecosystem doc | Design intent for per-peer trust + service RBAC. |
| **GPU pool** | bigboy (3090 + Quadro), midboy1 (P40s), Strix Halo machines | Render compute. Currently single-instance VibeVoice + ACE-Step. |

---

## Stage 1 — Multi-user, single tenant

**Goal**: Multiple Magic Unicorn employees can collaborate on the same shows. One tenant ("Magic Unicorn"). No billing. No tenant isolation. Just auth + RBAC + collab.

### Backend changes

- **Switch from filesystem-as-state to Postgres-backed metadata**. Files (audio, scripts) still on disk or in Garage, but metadata in Postgres.
- **Schema** (minimum viable):
  - `users` (id, uc_uid, email, name, created_at)
  - `shows` (id, slug, title, brand_brief_md, created_by, created_at)
  - `seasons` (id, show_id, slug, title, season_number)
  - `episodes` (id, season_id, slug, title, target_minutes, status)
  - `script_versions` (id, episode_id, version_label, script_md, frontmatter_json, created_by, created_at)
  - `audio_versions` (id, episode_id, version_label, voice_only_path, mixed_path, mp3_path, render_params_json, mix_params_json, render_duration_s, created_at)
  - `render_jobs` (id, episode_id, status, ddpm_steps, cfg_scale, sections_requested_json, started_at, completed_at, error)
  - `annotations` (id, episode_id, audio_version_id, time_s, text, created_by, created_at)
  - `comments` (id, episode_id, script_line_anchor, body_md, parent_id, created_by, created_at)
  - `role_assignments` (user_id, scope_type ENUM('show','episode','season'), scope_id, role ENUM('OWNER','ADMIN','EDITOR','LISTENER','GUEST'))
  - `audit_log` (id, user_id, action, resource_type, resource_id, payload_json, created_at)

- **Auth**: Replace the `PODCAST_OPS_API_TOKEN` bearer with Keycloak OIDC. Use the `uc_uid` claim from JWTs as the user ID. Existing Keycloak SDK / lib: copy the pattern from `project-ops-backend` or `stable/server/app/auth/`.

- **RBAC enforcement**: Add a `@requires_role(min_role, scope_resolver)` decorator on every write endpoint. CLIENT/LISTENER roles get reads only.

- **Render queue**: Add Redis + a worker process. The API only enqueues; the worker (Python) pulls jobs and runs the existing `render_episode.py`. Multiple workers can run on different GPU hosts.
  - Job payload: `{ episode_id, script_version_id, ddpm_steps, cfg_scale, sections: 'all' | [section_indices], gpu_pool_hint: 'bigboy_3090' | 'midboy1_p40' | 'auto' }`
  - Worker writes back to `render_jobs` table with progress + result.
  - WebSocket to frontend streams progress.

- **Voice clone management**: Per-user, per-show, or per-workspace scoping. For Stage 1, keep it simple: any user can clone, but voices are tagged with `created_by`. Voice IDs still go into VibeVoice's flat namespace, just prefix them: `mu_<user_uid>_<name>.wav`.

### Frontend changes

- **Auth wrapper**: NextAuth.js with Keycloak provider, points at uchub realm.
- **User presence**: Yjs + Hocuspocus for real-time cursor presence in the script editor.
- **Comments + threads**: Side panel on the script editor. Click a line → start a thread. @-mentions trigger Postmark email.
- **Show roster page**: Who has access to which show, with what role. Owners can manage.
- **Audit log viewer**: Admin-only. Filterable by user, action, time range.

### Deployment

- Single Postgres instance (`tank/databases` on bigboy — per your existing infra).
- Single Redis (`tank/databases`).
- API + worker as separate Docker services.
- Web behind Traefik at `podcast-ops.magicunicorn.dev`.

### Acceptance criteria for Stage 1

1. Two different Magic Unicorn employees can both log in via Keycloak.
2. One creates a show; the other gets invited as Editor.
3. Both can edit the same script at the same time with visible cursors.
4. Both can leave comments on script lines; @mentioning the other sends an email.
5. Either can kick off a render; both see the progress; both can listen to the result.
6. Audit log shows every render and significant edit.

---

## Stage 2 — Multi-tenant

**Goal**: Multiple orgs can use the platform, each isolated from the others. Magic Unicorn is one tenant. Brightwater Labs is another. External clients are tenants.

### Schema additions

- `tenants` (id, slug, name, branding_json, plan_id, created_at, suspended_at)
- `workspaces` (id, tenant_id, slug, name) — optional nesting inside tenant
- `tenant_users` (tenant_id, user_id, role_in_tenant) — user can belong to multiple tenants

### Data isolation

- Add `tenant_id` column to every domain table (shows, episodes, etc.).
- Use Postgres row-level security (RLS) policies bound to a session variable `app.current_tenant_id`.
- API middleware extracts `tenant_id` from JWT or subdomain and sets the RLS session variable.

### Voice clone isolation

- Rename voice files to `<tenant_slug>_<voice_name>.wav` in the VibeVoice mount.
- API filters voices by tenant when serving `/voices`.

### Quotas

- `tenant_quotas` (tenant_id, render_minutes_used_this_month, render_minutes_quota, voice_clone_slots_used, voice_clone_slots_quota, storage_bytes_used, storage_bytes_quota)
- Enforced on render enqueue: if quota exceeded, return 429 with a friendly message.
- Reset monthly via a cron.

### Onboarding flow

- User logs in via Keycloak. If they have no tenant, redirect to "create or join a tenant" page.
- "Create tenant" prompts for org name + slug + plan (free default).
- "Join tenant" requires an invite link (one-shot token, emailed via Postmark).

### Acceptance criteria for Stage 2

1. Aaron and Shafen both log in. Aaron belongs to Magic Unicorn tenant. Shafen belongs to Brightwater Labs tenant.
2. They can't see each other's shows.
3. Aaron clones a voice — it's only available in Magic Unicorn's voice picker.
4. Quotas show in the UI ("3 / 60 render minutes used this month").
5. Render rate limiting kicks in if a tenant exceeds quota.

---

## Stage 3 — White-label + federation

**Goal**: `podcast-ops.magicunicorn.dev`, `podcast-ops.brightwaterlabs.example`, `podcast-ops.<client>.com` are all the same platform, but visually branded per domain.

### Approach

Follow the **Ops-Center multi-tenant white-label** pattern that already exists for `unicorncommander.ai` / `magicunicorn.dev` / `centerdeep.online`.

- Single deployment of `apps/web` + `apps/api` + workers.
- Traefik routes multiple domains to the same backend.
- Backend looks up the domain in a `domain_branding` table to determine:
  - Logo + favicon
  - Color theme (Tailwind tokens via CSS variables)
  - Default Keycloak realm to use (uchub for Magic Unicorn, gflrealm for GFL, etc.)
  - Default tenant to scope to
- All tenants federated — `Federation Trust Modes` doc covers per-peer trust + service RBAC.

### Acceptance criteria for Stage 3

1. Visit `podcast-ops.magicunicorn.dev` → see Magic Unicorn branding.
2. Visit `podcast-ops.brightwaterlabs.example` → see GFL branding.
3. Both connect to the same backend.
4. Federation: a Magic Unicorn user can listen to a GFL-published episode if the GFL show is set to public, but can't edit it.

---

## Stage 4 — Public SaaS billing + launch

**Goal**: External orgs can sign up, pay, and use the platform without Aaron in the loop.

### Components

- **Stripe Connect** integration (you already have the pattern from `majiks.online`).
- **Plans table**: `plans` (id, slug, name, monthly_price_cents, render_minutes_quota, voice_clone_slots, features_json).
- **Tiers**:
  - Free: 60 min/month, 1 voice clone slot, no white-label.
  - Pro ($29/mo): 300 min/month, 5 voice clone slots, custom show artwork.
  - Studio ($99/mo): 1000 min/month, 25 voice clone slots, branded RSS feed.
  - Enterprise (custom): unlimited + white-label + dedicated GPU pool.
- **Public marketing site** at `podcast-ops.com` or `podcastops.ai` (separate from the app at `app.podcastops.ai`).
- **Sign-up flow**: email + password (or Google/GitHub OAuth via Keycloak) → confirm email → create tenant → land in the studio.
- **Public RSS feeds**: each show can optionally publish an RSS feed for Spotify / Apple Podcasts ingestion.
- **Distribution publish**: this is also Project Ops PROJ-2026-000079 — Brigade Pipeline Buildout's last task. Wire it in here.

---

## Cross-cutting concerns

### Audit + compliance
- Every state-changing API call writes to `audit_log`.
- Per-tenant audit log export endpoint (CSV + JSON).
- Soft-delete with 90-day retention.

### Notifications
- Postmark for transactional email (invites, render-completed, comment mentions, weekly digest).
- In-app notifications (red dot on header) backed by `notifications` table.

### Observability
- Structured logs (JSON) → Loki.
- Metrics (Prometheus) on render queue depth, render duration, queue wait time.
- Per-tenant dashboards (Grafana) for usage analytics.

### Backups
- Postgres logical backups daily to Garage.
- Voice clone WAVs backed up daily.
- Render outputs aged out to cold storage after 30 days; deleted after 90 days unless tenant pins.

### Security
- API rate limiting per user (default 100 req/min, render-enqueue 10 req/min).
- CORS locked to the configured frontend domain(s).
- Signed URLs for audio downloads (5-minute TTL).
- All secrets in env vars (no hardcoded keys), pulled from a secrets manager (Vault or sops-encrypted files).

### Federation
- Per `Federation Trust Modes` doc: each peer Podcast-Ops instance can be configured as full-mesh, zero-trust, or partial.
- Authority promotion: a Magic Unicorn instance can mark itself as the authority for `magic-unicorn:*` show slugs.
- Discovery via the existing Unicorn-Ecosystem federation infrastructure.

---

## What NOT to do

- Don't switch to a JS backend. The existing Python FastAPI is fine. Stay on Python 3.13.
- Don't build your own auth system. Keycloak via OIDC.
- Don't pick MongoDB. Postgres is the standard across your ecosystem.
- Don't add MinIO. Garage is the standard.
- Don't build a new LLM endpoint. Brigade.
- Don't add per-tenant Postgres databases. Single DB with RLS.
- Don't migrate filesystem-as-state to S3 in one step. Postgres for metadata first, then move audio assets to Garage in a separate migration.

---

## First migration (Stage 1 starter)

Codex's first task should be the database migration plan:

1. Add Postgres + Redis to `docker-compose.yml`.
2. Create the Stage 1 schema (alembic / migrations folder).
3. Add SQLAlchemy / Tortoise ORM models matching the schema.
4. Write a one-shot **import script** that walks the existing `shows/` filesystem tree and creates Postgres rows for everything that exists today (shows, episodes, script versions, audio versions, annotations from any existing `episode.annotations.jsonl`).
5. Switch the API to read/write through the ORM, with the filesystem as a write-through cache (so existing tools still work).
6. Add the Keycloak OIDC middleware.
7. Add the RBAC decorator + initial role-assignment endpoints.
8. Verify all existing endpoints still work end-to-end via the studio UI.

After Stage 1 lands, Stages 2-4 can be built incrementally without rewrites.

---

## Where to look

- `/Volumes/Studio Storage/Development/Stable/server/app/auth/` — existing Keycloak auth pattern in Python FastAPI.
- `/Volumes/Studio Storage/Development/Project-Ops/backend/src/auth/` — same, but NestJS / TypeScript. Pattern is identical.
- `/Volumes/Studio Storage/Development/Meeting-Ops/` — another `*-Ops` project. Same shape.
- `/Volumes/Studio Storage/Development/Unicorn-Ecosystem/FEDERATION_TRUST_MODES.md` — federation spec.
- `/Volumes/Studio Storage/Development/Podcast-Ops/docs/SHOW-INTROS-HANDOFF.md` — the show-network architecture this is built for.
- `apps/api/app/main.py` (existing v1) — what's being upgraded.
- `apps/web/src/components/studio.tsx` (existing v1) — the frontend that stays mostly the same UX-wise.
