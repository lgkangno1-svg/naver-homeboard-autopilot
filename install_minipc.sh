#!/bin/bash
set -euo pipefail
BASE="${BLOGBOT_HOME:-$HOME/blogbot}"
PYTHON="${PYTHON:-python3}"

cd "$BASE"
$PYTHON -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium
mkdir -p logs downloads images_pool

if [ ! -f .env ]; then
  cp .env.example .env
  chmod 600 .env
  echo ".env created. Fill API keys and Naver credentials before running login/cron."
fi

CRON_LINE="*/5 * * * * cd $BASE && HEADLESS=1 .venv/bin/python -u run.py cron >> $BASE/logs/cron.log 2>&1"
( crontab -l 2>/dev/null | grep -v "run.py cron" || true; echo "$CRON_LINE" ) | crontab -

echo "Installed. First verify: .venv/bin/python run.py check"
echo "For first interactive login, run on a machine with a visible browser: .venv/bin/python run.py login"
