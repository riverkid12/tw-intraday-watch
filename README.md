# tw-intraday-watch

台股盤中監看的雲端執行殼。邏輯本體在本機 `C:\Projects\stock-ai-shared\intraday_watch.py`(有測試),`cloud/` 裡的是每晚自動複製的副本,**不要直接改 cloud/**。

- **名單** `watch_auto.json`:本機每晚 21:40 `push_watch.bat` 由當天發車觀察的「蓄勢」檔 + `tw-stock-ai-agent\watchlist.json`(手動)合成後 push。
- **執行** `.github/workflows/intraday-watch.yml`:週一到週五台北 08:37 觸發,輪詢證交所快照到 13:35,事件推 Discord(secrets:`DISCORD_WEBHOOK_URL`、`DISCORD_THREAD_ID`),收盤後把 `intraday_log.jsonl` commit 回來。
- **手動測試**:Actions 頁面 Run workflow(once=true)= 只輪一次、不發 Discord。

規則來源:`C:\Projects\finance-learning\投資政策.md` §4.1(收盤過線、量 ≥ 1.35 倍;13:25 看到 ≥ 1.25 倍可以準備)。
