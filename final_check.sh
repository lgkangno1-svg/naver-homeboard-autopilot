#!/bin/bash
set -u
BASE="${BLOGBOT_HOME:-$HOME/blogbot}"
TODAY="$(TZ=Asia/Seoul date +%F)"

echo "=== processes ==="
pgrep -af "run.py" || echo "none"
echo "=== cron ==="
crontab -l 2>/dev/null | grep -E "blogbot|run.py cron" || echo "cron entry not found"
echo "=== config ==="
grep -E '"publish"|"posts_per_day"|"publish_times"' "$BASE/config.json" || true
echo "=== today slots ==="
if [ -f "$BASE/logs/published.jsonl" ]; then
  grep -c "$TODAY" "$BASE/logs/published.jsonl" || true
else
  echo "0 (no log yet)"
fi
echo "=== python syntax ==="
"$BASE/.venv/bin/python" -m py_compile "$BASE"/run.py "$BASE"/writer_v2.py "$BASE"/publish_guard.py "$BASE"/research.py "$BASE"/llm.py && echo "OK"
echo "=== disk/mem ==="
df -h / | tail -1
free -h | head -2
