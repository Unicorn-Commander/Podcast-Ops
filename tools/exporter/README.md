# podcast-ops-export — read-only Producer handoff, v1

Runs beside the existing filesystem rail; does not call the Studio API, modify scripts, render, mix, or publish. `find_show_dir` in the Studio is slug-only; this exporter always uses `shows/<tenant>/<show>/<season>/episodes/<episode>` and does not reuse that lookup.

## Setup

Use Python 3.12+ with `pyyaml>=6.0.2` and `httpx>=0.27.0` (also API dependencies), plus `ffprobe` on PATH. Activate that environment and put `tools/exporter` on PATH, or run `python tools/exporter/exporter.py`. The `podcast-ops-export` executable is a wrapper for the same CLI. Tests generate tiny WAV fixtures in `/tmp` only:

```sh
python -m unittest discover -s tests -v
podcast-ops-export propose --root '/Volumes/Studio Storage/Development/Podcast-Ops' --output /tmp/proposed-selection.md
```

The report contains candidate paths, byte sizes and ffprobe durations. It does not select, rank, or approve anything; short test renders can appear. Producer's companion `docs/design/pr2-proposed-selection.md` records 15 candidates across the five The Layer Above season-1 episodes.

## Explicit operator selection

Copy `selection.example.yaml` to an ignored `selection.yaml`. Set the installation ID and tenant namespace, then list **one exact artifact path per episode** after reviewing the report. A filename containing FINAL or a recent modification time has no authority. The five episode keys are:

- `ep01-the-window`
- `ep02-make-music-that-lives-somewhere`
- `ep03-the-bank-is-not-the-bouncer`
- `ep04-eight-surfaces-one-rail`
- `ep05-the-bet`

An optional `annotations` path explicitly opts in to that episode's JSONL history. Script bodies are never sent: only their SHA-256 revision. Source state is reduced to observed render/mix status; no raw logs are sent. Missing authors are labeled `Podcast-Ops (source author unspecified)`, never mapped to a Producer person. Do not commit selection files, generated manifests containing history, media, private transcripts, or environment files.

```sh
podcast-ops-export manifest --root '/Volumes/Studio Storage/Development/Podcast-Ops' --selection selection.yaml --stable-seconds 3 --output /tmp/podcast-manifest.local.json
# Supply PODCAST_EXPORT_TOKEN through the operator's secret environment, never a CLI argument.
podcast-ops-export push --root '/Volumes/Studio Storage/Development/Podcast-Ops' --selection selection.yaml --stable-seconds 3 --endpoint https://producer.magicunicorn.dev/api/podcast
```

`--repo` identifies the Podcast-Ops source checkout for git HEAD; default is this checkout. The manifest includes git SHA plus source file mtimes (nanoseconds as strings), installation/tenant, tenant-qualified stable episode key, selected relative path, size, SHA-256, script revision, observed status and opted-in annotations. v1 rejects unknown keys. No arbitrary saved manifest can be passed to `push`: it rebuilds from selection and the filesystem each time.

## Transport and retry

1. POST `/manifest` reconciles explicit entries, returning server-owned upload IDs and part sizes.
2. POST `/parts` signs only numbered parts of those uploads; the CLI PUTs selected media to the returned HTTPS storage URLs. The bearer is sent only to Producer, never to storage. Redirects are refused.
3. POST `/complete` verifies storage size and SHA-256 through Producer's PR1 spine, appends an immutable AssetVersion, and queues CPU probe/proxy work. Originals remain in Producer storage for playback with the rail disconnected.

Retry the same command after interruption. Matching current hashes need no upload; pending matching uploads are reused (parts are safely re-sent); changed hashes produce a new version of the same asset. Explicitly selected missing files send `available: false`; omitted episodes are left alone. A later rescan supersedes a pending different artifact, so its old completion is refused. No source history is deleted or replayed as Producer approvals/comments.

All file reads resolve symlinks inside the allowlisted root and compare inode, size, mtime and ctime before/after a positive stability interval and hashing. Media is rechecked into a private temporary snapshot before transmission; its bytes must match the manifest. The temporary snapshot is removed on exit. Active writers must finish before retrying. This is a local operator tool, not a hardened multi-user filesystem service: restrict write access to its root and selection file.

Persephone provisions an enabled Producer `podcast` connector with one exact tenant/workspace, source installation ID, tenant namespace, and server-side credential reference to a SHA-256 bearer digest. The exporter receives only the bearer through its secret environment. Configuration details and actual verification receipts live in Producer `docs/design/pr2-verification.md`. No real media push is part of this implementation pass; operator selection and provisioning precede that separate run.

Rollback: disable the connector/exporter. Keep all rail files, Producer mappings, versions and imported history.
