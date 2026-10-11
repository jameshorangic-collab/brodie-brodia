#!/usr/bin/env bash
# Load .env.local and run the coach or mint a phone link.
#   bash scripts/run.sh coach [gemini|openai|off] [worker flags...]   # voice defaults to VOICE in .env.local
#   bash scripts/run.sh link [room]                                   # room defaults to try-<time>
# The coach joins your own rooms (empty agent name); set LINE=1 to use AGENT_NAME from .env.local for the call line.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source .env.local; set +a
PY=.venv/bin/python

case "${1:-}" in
    coach)
        shift
        case "${1:-}" in gemini|openai|off) VOICE=$1; shift ;; esac
        agent=(); [ "${LINE:-}" = 1 ] || agent=(--agent-name "")
        exec "$PY" -m facetime.worker --voice "${VOICE:-gemini}" "${agent[@]}" "$@" dev ;;
    link)
        exec "$PY" -m facetime.mint_token --room "${2:-try-$(date +%H%M%S)}" --url ;;
    *)
        sed -n '2,5p' "$0"; exit 1 ;;
esac
