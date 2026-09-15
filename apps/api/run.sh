#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

# Source .env if present so config is picked up without python-dotenv.
if [[ -f .env ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

export PODCAST_OPS_ROOT="${PODCAST_OPS_ROOT:-$(cd ../.. && pwd)}"
export PORT="${PORT:-8011}"
export UV_PYTHON="${UV_PYTHON:-python3.13}"

exec uv run uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --reload
