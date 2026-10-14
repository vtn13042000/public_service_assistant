#!/usr/bin/env bash
# Stop the demo web app (src.web.app on 127.0.0.1:8000). Ollama, LangFuse and SearxNG keep running
# unless --all is given (then LangFuse and SearxNG are stopped too; Ollama is a system service and is never touched).
# The app is found by data/logs/web.pid (written by demo_up.sh), else by an anchored command-line pattern that cannot
# match a shell or terminal that merely quotes the command (scripts/demo_web_pids.sh).
# Usage: scripts/demo_down.sh [--all]
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1
# shellcheck source=demo_web_pids.sh
source "$ROOT/scripts/demo_web_pids.sh"

stop_web

if [[ "${1:-}" == "--all" ]]; then
  infra/langfuse/up.sh down >/dev/null 2>&1 && echo "  OK    LangFuse stopped (data volumes kept)" || echo "  FAIL  LangFuse stop"
  infra/searxng/up.sh down >/dev/null 2>&1 && echo "  OK    SearxNG stopped" || echo "  FAIL  SearxNG stop"
  echo "  --    Ollama left running (system service)"
fi
