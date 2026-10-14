# Sourced by demo_up.sh / demo_down.sh: find and stop OUR web app without touching any shell that merely quotes its name.
# The app runs as `uv run python -m src.web.app` (session leader, pid in data/logs/web.pid) plus its child
# `<repo>/.venv/bin/python3 -m src.web.app`; both share one process group.
WEB_PIDFILE="data/logs/web.pid"
WEB_RE='^(uv run )?([^ ]*/)?python3? -m src\.web\.app ?$'   # anchored: a shell running grep/tmux with this text cannot match

is_web_pid() {  # pid → 0 if alive and its command line is our app
  local cmd
  [[ -n "${1:-}" && -r /proc/$1/cmdline ]] || return 1
  cmd="$(tr '\0' ' ' </proc/"$1"/cmdline)"
  [[ "$cmd" =~ $WEB_RE ]]
}

web_pids() {  # our app's pids: from the pid file if valid, else the anchored pattern
  local p
  p="$(cat "$WEB_PIDFILE" 2>/dev/null)"
  if is_web_pid "$p"; then echo "$p"; pgrep -g "$(ps -o pgid= -p "$p" | tr -d ' ')" 2>/dev/null | grep -vx "$p"; return; fi
  for p in $(pgrep -f "$WEB_RE"); do is_web_pid "$p" && echo "$p"; done
}

stop_web() {  # → prints one status line; returns 0 if stopped or not running
  local pids pgids p
  pids="$(web_pids | sort -u)"
  if [[ -z "$pids" ]]; then echo "  OK    web app was not running"; rm -f "$WEB_PIDFILE"; return 0; fi
  pgids="$(for p in $pids; do ps -o pgid= -p "$p"; done | tr -d ' ' | sort -u)"
  for g in $pgids; do kill -TERM -- "-$g" 2>/dev/null; done
  for _ in 1 2 3 4 5 6 7 8 9 10; do [[ -z "$(web_pids)" ]] && break; sleep 0.5; done
  if [[ -n "$(web_pids)" ]]; then
    for g in $pgids; do kill -KILL -- "-$g" 2>/dev/null; done; sleep 1
    echo "  OK    web app killed (pids $(echo $pids); did not stop within 5 s)"
  else
    echo "  OK    web app stopped (pids $(echo $pids))"
  fi
  rm -f "$WEB_PIDFILE"
}
