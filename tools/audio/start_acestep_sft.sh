#!/usr/bin/env bash
# Start the ACE-Step API server with the production-quality SFT DiT
# on bigboy's RTX 3090 (GPU 0). Skip the 5Hz LM since we pass explicit
# prompts. Use expandable_segments to keep VRAM from fragmenting during
# the warm-up cycles.
#
# Usage (locally):
#   ssh magicunicorn 'bash -s' < tools/audio/start_acestep_sft.sh
# Or copy to bigboy and: bash start_acestep_sft.sh
#
# Restart cleanly: pkill -9 -f acestep-api  then re-run this.

set -euo pipefail

ACESTEP_DIR="/home/muut/models/ACE-Step-1.5"
LOG_FILE="/tmp/acestep-sft.log"

if pgrep -f acestep-api > /dev/null; then
    echo "[start-acestep] another acestep-api is already running, exiting." >&2
    pgrep -af acestep-api >&2
    exit 1
fi

cd "$ACESTEP_DIR"

# Bypass start_api_server.sh — it exports ACESTEP_INIT_LLM=auto which
# overrides our request to skip the LM. Call the venv binary directly.
ACESTEP_BIN="$ACESTEP_DIR/.venv/bin/acestep-api"

env \
    CUDA_VISIBLE_DEVICES=0 \
    ACESTEP_CONFIG_PATH=acestep-v15-sft \
    ACESTEP_INIT_LLM=false \
    PYTORCH_ALLOC_CONF=expandable_segments:True \
    nohup "$ACESTEP_BIN" --host 127.0.0.1 --port 8001 \
        > "$LOG_FILE" 2>&1 < /dev/null &

disown
echo "[start-acestep] launched. log: $LOG_FILE"
