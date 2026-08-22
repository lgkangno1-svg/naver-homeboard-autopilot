@echo off
cd /d "C:\Users\tnfwo\Documents\Default Project"
".venv\Scripts\python.exe" -u run.py daily >> "%TEMP%\opencode\blog_daily.log" 2>&1
