#!/bin/bash
set -u
BASE="${BLOGBOT_HOME:-$HOME/blogbot}"
TODAY="$(TZ=Asia/Seoul date +%F)"

echo "=== processes ==="
pgrep -af "run.py" || echo "none"
echo "=== cron ==="
crontab -l 2>/dev/null | grep -E "run.py (cron|audit)" || echo "cron/audit entry not found"
echo "=== config ==="
grep -E '"publish"|"posts_per_day"|"publish_times"|"min_editor_score"|"max_recent_title_similarity"' "$BASE/config.json" || true
echo "=== today slots ==="
if [ -f "$BASE/logs/published.jsonl" ]; then
  grep -c "$TODAY" "$BASE/logs/published.jsonl" || true
else
  echo "0 (no log yet)"
fi
echo "=== live feedback ==="
if [ -f "$BASE/logs/live_feedback.json" ]; then
  "$BASE/.venv/bin/python" - <<'PY'
import json, os
p=os.path.expanduser(os.environ.get('BLOGBOT_HOME','~/blogbot')) + '/logs/live_feedback.json'
try:
    d=json.load(open(p,encoding='utf-8'))
    print('generated_at:', d.get('generated_at'))
    print('aggregate_scores:', d.get('aggregate_scores',{}))
except Exception as e:
    print('feedback read failed:', e)
PY
else
  echo "not created yet (run.py audit)"
fi
echo "=== python syntax ==="
"$BASE/.venv/bin/python" -m py_compile \
  "$BASE"/run.py "$BASE"/writer_v2.py "$BASE"/publish_guard.py \
  "$BASE"/research.py "$BASE"/quality_feedback.py "$BASE"/llm.py && echo "OK"
echo "=== disk/mem ==="
df -h / | tail -1
free -h | head -2
