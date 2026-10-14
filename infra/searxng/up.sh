#!/usr/bin/env bash
# Start the self-hosted SearxNG and wait until its JSON API answers.
# Usage: infra/searxng/up.sh            (from anywhere)
#        infra/searxng/up.sh down       (stop)
# Adds SEARXNG_SECRET (random) and SEARXNG_URL to the repo-root .env if missing.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV="$ROOT/.env"
DC=(docker compose --env-file "$ENV" -f "$ROOT/infra/searxng/docker-compose.yml")

if [[ "${1:-}" == "down" ]]; then "${DC[@]}" down; exit 0; fi

touch "$ENV"; chmod 600 "$ENV"
grep -q '^SEARXNG_SECRET=' "$ENV" || echo "SEARXNG_SECRET=$(openssl rand -hex 32)" >> "$ENV"
grep -q '^SEARXNG_URL=' "$ENV" || echo "SEARXNG_URL=http://127.0.0.1:8080" >> "$ENV"

"${DC[@]}" up -d
url="$(grep -E '^SEARXNG_URL=' "$ENV" | cut -d= -f2-)"
for i in $(seq 1 30); do
  if curl -fsS "$url/healthz" >/dev/null 2>&1 && curl -fsS "$url/search?q=test&format=json" >/dev/null 2>&1; then
    echo "SearxNG up after ~$((i*2))s at $url (JSON API ok)"; exit 0
  fi
  sleep 2
done
echo "SearxNG not ready after 60s; see: ${DC[*]} logs searxng" >&2; exit 1
