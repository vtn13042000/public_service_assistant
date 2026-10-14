#!/usr/bin/env bash
# Bring the demo up: checks, warm models, LangFuse, SearxNG, web app, one smoke question, then the question list.
# Usage: scripts/demo_up.sh            (from anywhere; safe to re-run — reuses whatever is already up)
# Stop:  scripts/demo_down.sh          (web app only; --all also stops LangFuse and SearxNG)
# Runbook: docs/11_demo/DEMO-RUNBOOK.md
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1
# shellcheck source=demo_web_pids.sh
source "$ROOT/scripts/demo_web_pids.sh"
EVAL_RE='^(uv run )?([^ ]*/)?python3? .*-m eval\.'   # anchored on the interpreter, so a shell quoting it does not count

APP=http://127.0.0.1:8000
LANGFUSE=http://127.0.0.1:3000
SEARXNG=http://127.0.0.1:8080
OLLAMA="${OLLAMA_BASE_URL:-http://127.0.0.1:11434}"
NUM_CTX=16384          # src/llm.py NUM_CTX: warm with the app's settings, or Ollama reloads on the first question
LOG_DIR="$ROOT/data/logs"

ok()   { printf '  \033[32mOK\033[0m    %s\n' "$*"; }
warn() { printf '  \033[33mWARN\033[0m  %s\n' "$*"; }
fail() { printf '  \033[31mFAIL\033[0m  %s\n' "$*"; exit 1; }
step() { printf '\n[%s] %s\n' "$1" "$2"; }
up()   { curl -fsS -m 3 -o /dev/null "$1" 2>/dev/null; }
wait_for() {  # url seconds → 0 when the url answers within the time
  local url=$1 t=$2 i
  for ((i = 0; i < t; i += 2)); do up "$url" && return 0; sleep 2; done
  return 1
}
envval() { grep -E "^$1=" .env 2>/dev/null | tail -1 | cut -d= -f2- | sed 's/[[:space:]]*#.*$//'; }

mkdir -p "$LOG_DIR"

# ------------------------------------------------------------------ 1. preconditions
step 1 "Preconditions"
ok "repo root $ROOT"
command -v uv >/dev/null || fail "uv not found on PATH (install: https://docs.astral.sh/uv/)"
ok "uv $(uv --version 2>/dev/null | awk '{print $2}')"
[[ -f .env ]] || fail ".env missing in the repo root (copy .env.example, or run infra/langfuse/up.sh once to generate it)"
ok ".env present"
if [[ -e data/.RUNLOCK ]]; then
  fail "data/.RUNLOCK exists ($(cat data/.RUNLOCK)). An evaluation or build is running; wait for it or ask its owner to stop it. Do not delete the lock while its process runs."
fi
ok "no data/.RUNLOCK"
if pgrep -f "$EVAL_RE" >/dev/null; then
  pgrep -af "$EVAL_RE" | sed 's/^/        /'
  fail "an evaluation process is running (above); it shares the GPUs. Wait for it or stop it, then re-run."
fi
ok "no evaluation process"

# ------------------------------------------------------------------ 2. Ollama
step 2 "Ollama (local models)"
up "$OLLAMA/api/tags" || fail "Ollama does not answer at $OLLAMA (try: sudo systemctl start ollama)"
ok "server answers at $OLLAMA"
GEN="$(envval APP_GENERATOR_MODEL)"; GEN="${GEN:-$(envval APP_LLM_MODEL)}"; GEN="${GEN:-qwen3.5}"
JUDGE="$(envval APP_JUDGE_MODEL)"; JUDGE="${JUDGE:-qwen3.6}"
EMBED="$(envval APP_EMBED_MODEL)"; EMBED="${EMBED:-bge-m3}"
models="$(ollama list 2>/dev/null | awk 'NR>1{print $1}')"
for m in "$GEN" "$JUDGE" "$EMBED"; do
  grep -qxE "${m}(:latest)?" <<<"$models" || fail "model $m is not pulled (ollama pull $m); this script pulls nothing"
done
ok "models present: $GEN, $JUDGE, $EMBED"
warm() {  # name endpoint json
  local t
  t=$(curl -fsS -m 300 -o /dev/null -w '%{time_total}' "$OLLAMA/api/$2" -d "$3" 2>/dev/null) || fail "warm-up call to $1 failed"
  printf '  \033[32mOK\033[0m    %s warm in %.1f s\n' "$1" "$t"
}
gen_body() { printf '{"model":"%s","prompt":"Xin chào","stream":false,"think":false,"keep_alive":-1,"options":{"num_ctx":%d,"num_predict":1,"temperature":0}}' "$1" "$NUM_CTX"; }
warm "$GEN" generate "$(gen_body "$GEN")"
warm "$JUDGE" generate "$(gen_body "$JUDGE")"
warm "$EMBED" embed "$(printf '{"model":"%s","input":"Xin chào","keep_alive":-1}' "$EMBED")"

# ------------------------------------------------------------------ 3. LangFuse
step 3 "LangFuse (traces)"
if up "$LANGFUSE/api/public/health"; then
  ok "already up at $LANGFUSE"
else
  warn "not answering; starting infra/langfuse/up.sh"
  timeout 150 infra/langfuse/up.sh >"$ROOT/data/logs/.langfuse_up.out" 2>&1 || true
  wait_for "$LANGFUSE/api/public/health" 120 || fail "LangFuse not up after 120 s (docker compose -f infra/langfuse/docker-compose.yml logs langfuse-web)"
  ok "started; answers at $LANGFUSE"
fi

# ------------------------------------------------------------------ 4. SearxNG
step 4 "SearxNG (local web search)"
if up "$SEARXNG/healthz"; then
  ok "already up at $SEARXNG"
else
  warn "not answering; starting infra/searxng/up.sh"
  timeout 150 infra/searxng/up.sh >"$ROOT/data/logs/.searxng_up.out" 2>&1 || true
  wait_for "$SEARXNG/healthz" 120 || fail "SearxNG not up after 120 s (docker compose -f infra/searxng/docker-compose.yml logs)"
  ok "started; answers at $SEARXNG"
fi

# ------------------------------------------------------------------ 5. web app
step 5 "Web app (127.0.0.1:8000)"
want="$(uv run --quiet python -c 'from src.presets import DEFAULT_PRESET; print(DEFAULT_PRESET)' 2>/dev/null)"
[[ -n "$want" ]] || fail "could not read DEFAULT_PRESET from src/presets.py (uv run python -c ...)"
start_app() {
  local log="$LOG_DIR/web-$(date -u +%Y%m%dT%H%M%SZ).log"
  setsid nohup uv run python -m src.web.app >"$log" 2>&1 </dev/null &
  echo $! >"$ROOT/$WEB_PIDFILE"   # setsid execs (not a group leader here), so $! is the uv process = session/group leader
  ok "started (pid $(cat "$ROOT/$WEB_PIDFILE"), log ${log#$ROOT/})"
}
if ss -ltn 2>/dev/null | grep -q '127.0.0.1:8000 \|\*:8000 \|0.0.0.0:8000 '; then
  presets="$(curl -fsS -m 3 "$APP/presets" 2>/dev/null)"
  if [[ "$presets" != *guardrailed* ]]; then
    fail "port 8000 is used by something else ($(ss -ltnp 2>/dev/null | grep ':8000 ' | head -1)); free it and re-run"
  fi
  if [[ "$presets" == *"\"guardrailed\":\"$want\""* ]]; then
    ok "our web app is already running with the current configuration; reusing it"
  else
    warn "our web app runs an older configuration than src/presets.py; restarting"
    stop_web
    start_app
  fi
else
  start_app
fi
health=""
for ((i = 0; i < 90; i += 2)); do
  health="$(curl -fsS -m 3 "$APP/health" 2>/dev/null)" && [[ "$health" == *'"ok":true}'* ]] && break
  sleep 2
done
[[ "$health" == *'"ok":true}'* ]] || fail "web app /health not ok after 90 s: ${health:-no answer} (see the newest $LOG_DIR/web-*.log)"
for svc in ollama langfuse searxng db; do
  if [[ "$health" =~ \"$svc\":\{\"ok\":true ]]; then ok "/health $svc ok"; else warn "/health $svc NOT ok: $health"; fi
done

# ------------------------------------------------------------------ 6. smoke question
step 6 "Smoke question (professor's row 1)"
resp="$(curl -fsS -m 60 -H 'Content-Type: application/json' -X POST "$APP/ask" \
        -d '{"query":"Hồ sơ đăng ký khai sinh gồm những gì?"}' 2>/dev/null)" || fail "POST /ask did not answer within 60 s"
summary="$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["outcome"], d.get("preset"), d.get("procedure_id"), d["latency_s"], len(d["citations"]), d.get("trace_id") or "-")' <<<"$resp")" \
  || fail "unreadable /ask reply: ${resp:0:200}"
read -r outcome preset pid lat ncite tid <<<"$summary"
[[ "$outcome" == answer ]] || fail "expected outcome answer, got $outcome (procedure $pid); see docs/11_demo/DEMO-RUNBOOK.md §D"
[[ "$preset" == "$want" ]] || fail "the app answered with configuration '$preset', not the current one in src/presets.py"
ok "outcome $outcome · procedure $pid · $ncite citations · current configuration · ${lat} s · trace $tid"

# ------------------------------------------------------------------ 7. banner
cat <<EOF

======================================================================
 DEMO READY
   Web app   http://127.0.0.1:8000        (current configuration)
   LangFuse  $LANGFUSE    (login: LANGFUSE_INIT_USER_EMAIL / _PASSWORD in .env)
   Runbook   docs/11_demo/DEMO-RUNBOOK.md

 Demo questions (runbook section B, nine), in order:
   B1  Hồ sơ đăng ký khai sinh gồm những gì?
   B2  Lệ phí cấp lại CCCD là bao nhiêu?
   B3  Cấp lại thẻ căn cước cần giấy tờ gì?      (then click option 1)
   B4  Thủ tục nhập tịch cho người nước ngoài?
   B5  Xác nhận số CMND 9 số làm thế nào?
       fallback: Cấp xác nhận số chứng minh nhân dân 09 số cần hồ sơ gì?
   B6  Tôi có đủ điều kiện được đăng ký thường trú vào nhà bố mẹ vợ không?
   B7  Thủ tục đăng ký thường trú cần giấy tờ gì?
   B8  Hồ sơ đăng ký khai sinh gồm những gì?      (Chế độ = Bản so sánh không rào chắn)
   B9  đăng ký khai sinh để điền tên cha có cần phải có giấy kết hôn để chứng minh quan hệ không

 Run scripts/demo_down.sh to stop the web app.
======================================================================
EOF
