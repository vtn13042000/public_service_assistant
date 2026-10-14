#!/usr/bin/env bash
# Start the self-hosted LangFuse stack and wait until it is healthy.
# Usage: infra/langfuse/up.sh            (from anywhere)
#        infra/langfuse/up.sh down       (stop; data volumes are kept)
# Creates the repo-root .env with fresh random secrets and fixed init ids if it does not exist.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV="$ROOT/.env"
DC=(docker compose --env-file "$ENV" -f "$ROOT/infra/langfuse/docker-compose.yml")

if [[ "${1:-}" == "down" ]]; then "${DC[@]}" down; exit 0; fi

if [[ ! -f "$ENV" ]]; then
  r() { openssl rand -hex "$1"; }
  pk="pk-lf-$(r 16)"; sk="sk-lf-$(r 16)"
  sed -e "s/^LANGFUSE_PUBLIC_KEY=.*/LANGFUSE_PUBLIC_KEY=$pk/" \
      -e "s/^LANGFUSE_SECRET_KEY=.*/LANGFUSE_SECRET_KEY=$sk/" \
      -e "s/^LANGFUSE_INIT_PROJECT_PUBLIC_KEY=.*/LANGFUSE_INIT_PROJECT_PUBLIC_KEY=$pk/" \
      -e "s/^LANGFUSE_INIT_PROJECT_SECRET_KEY=.*/LANGFUSE_INIT_PROJECT_SECRET_KEY=$sk/" \
      -e "s/^LANGFUSE_INIT_USER_PASSWORD=.*/LANGFUSE_INIT_USER_PASSWORD=$(r 12)/" \
      -e "s/^NEXTAUTH_SECRET=.*/NEXTAUTH_SECRET=$(r 32)/" \
      -e "s/^SALT=.*/SALT=$(r 16)/" \
      -e "s/^ENCRYPTION_KEY=.*/ENCRYPTION_KEY=$(r 32)/" \
      -e "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(r 16)/" \
      -e "s/^CLICKHOUSE_PASSWORD=.*/CLICKHOUSE_PASSWORD=$(r 16)/" \
      -e "s/^MINIO_ROOT_PASSWORD=.*/MINIO_ROOT_PASSWORD=$(r 16)/" \
      -e "s/^REDIS_AUTH=.*/REDIS_AUTH=$(r 16)/" \
      "$ROOT/.env.example" | sed -e 's/[[:space:]]*#.*$//' -e '/^$/d' > "$ENV"
  chmod 600 "$ENV"
  echo "wrote $ENV"
fi

"${DC[@]}" up -d
host="$(grep -E '^LANGFUSE_HOST=' "$ENV" | cut -d= -f2-)"; host="${host:-http://127.0.0.1:3000}"
for i in $(seq 1 90); do
  if out="$(curl -fsS "$host/api/public/health" 2>/dev/null)"; then echo "healthy after ~$((i*5))s: $out"; exit 0; fi
  sleep 5
done
echo "LangFuse not healthy after 450s; see: ${DC[*]} logs langfuse-web" >&2; exit 1
