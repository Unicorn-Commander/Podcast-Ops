# Contributing to Podcast-Ops

Podcast-Ops is licensed under the GNU AGPL v3.0 or later. Contributions are contributions under that license. See [LICENSE](LICENSE).

## What runs

The studio is two processes:

- [`apps/api`](apps/api) — FastAPI. Routes live in `apps/api/app/main.py`. Start it with `apps/api/run.sh` (Python 3.13 and [uv](https://docs.astral.sh/uv/)).
- [`apps/web`](apps/web) — Next.js. One page. `npm ci` then `npm run dev` from that directory.

Episode state is the `shows/` tree. Rendering speech needs a VibeVoice server (`VIBEVOICE_URL`). Chat and model script edits need Unicorn Brigade (`BRIGADE_BASE_URL` and `BRIGADE_API_KEY`). Both are optional for browsing and editing scripts. Leave `PODCAST_OPS_API_TOKEN` empty when you use the bundled web app. It does not send an `Authorization` header.

`docs/` contains earlier design notes. Several of those notes describe a CLI, database, and SSO layer that this tree does not implement. Change the code and [README.md](README.md) together when behavior changes.

## Checks

From the repository root:

```bash
uv run --project apps/api python -m unittest discover -s tests -v
```

That is the exporter contract suite (`tests/test_exporter.py`). It needs `git`, `ffmpeg`, and `ffprobe` on `PATH`.

Web lint, from `apps/web`:

```bash
npm ci
npm run lint
```

The API project has no separate lint target.

## Please leave out of commits

- `.env` files, tokens, and private keys
- `selection.yaml` and generated export manifests
- Audio and other media (the gitignore already excludes the common extensions)
- Machine-specific paths and internal host names

The exporter takes `PODCAST_EXPORT_TOKEN` from the environment, not from a command-line argument. Keep it that way.
