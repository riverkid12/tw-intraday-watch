@echo off
chcp 65001 > nul
REM Nightly (21:40, Mon-Fri): rebuild watch_auto.json from tonight's setup scan, then push to GitHub
REM so the Actions job has tomorrow's watchlist. Pure script, no AI.
REM Git identity is passed per command (repo convention: never store user.name/email in the repo).
REM --autostash: cloud/*.py get CRLF-touched on Windows, which otherwise blocks the rebase.

setlocal
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set GITID=-c user.name=riverkid12 -c user.email=yihuang0903@gmail.com

echo === %date% %time% >> push_watch.out
python build_watch.py >> push_watch.out 2>&1
git add cloud watch_auto.json >> push_watch.out 2>&1
git %GITID% commit -m "watchlist update" >> push_watch.out 2>&1
git %GITID% pull --rebase --autostash >> push_watch.out 2>&1
git push >> push_watch.out 2>&1
echo done %date% %time% >> push_watch.out
