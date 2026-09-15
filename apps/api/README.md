# Podcast-Ops API

Local FastAPI wrapper around the existing Podcast-Ops filesystem and audio tools.

```bash
cd apps/api
./run.sh
```

Default API: `http://localhost:8011`

Useful env vars live in `.env.example`. The API keeps episode metadata in
`episode.state.json` and annotations in `episode.annotations.jsonl` beside each
episode `script.md`.
