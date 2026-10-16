@echo off
chcp 65001 > nul
REM Nightly (21:40, Mon-Fri): rebuild watch_auto.json from tonight's setup scan, then push to GitHub
REM so the Actions job has tomorrow's watchlist. Pure script, no AI.

setlocal
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

python build_watch.py >> push_watch.out 2>&1
git add cloud watch_auto.json >> push_watch.out 2>&1
git commit -m "watchlist %date%" >> push_watch.out 2>&1
git pull --rebase >> push_watch.out 2>&1
git push >> push_watch.out 2>&1
echo done %date% %time% >> push_watch.out
