#!/bin/bash
echo "=== processes ==="
pgrep -af "run.py" || echo "none (ok)"
echo "=== cron ==="
crontab -l | grep blogbot
echo "=== config ==="
grep -E '"publish"|posts_per_day' ~/blogbot/config.json
echo "=== today posts ==="
grep -c "2026-08-22" ~/blogbot/logs/published.jsonl
echo "=== disk/mem ==="
df -h / | tail -1
free -h | head -2
