"""每晚(本機 21:40)跑:① 把共用模組最新版複製進 cloud/;② 把 tw 帳本最近一天的蓄勢檔 + watchlist.json 合成 watch_auto.json。
純標準庫;push 由 push_watch.bat 做。"""
import json, os, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SHARED = r"C:\Projects\stock-ai-shared"
TW = r"C:\Projects\tw-stock-ai-agent"
CLOUD = os.path.join(HERE, "cloud")
os.makedirs(CLOUD, exist_ok=True)
for f in ("intraday_watch.py", "notify_discord.py"):
    shutil.copy(os.path.join(SHARED, f), os.path.join(CLOUD, f))

sys.path.insert(0, SHARED)
from intraday_watch import load_watchlist, drop_stopped  # noqa: E402

setups = os.path.join(TW, "setups_history.jsonl")
dates = sorted({json.loads(l)["date"] for l in open(setups, encoding="utf-8") if l.strip()}) if os.path.exists(setups) else []
date = dates[-1] if dates else None
extra_path = os.path.join(TW, "watchlist.json")
extra = json.load(open(extra_path, encoding="utf-8")) if os.path.exists(extra_path) else []
extra, dropped = drop_stopped(extra, os.path.join(HERE, "intraday_log.jsonl"), today=__import__("datetime").date.today().isoformat())
for sym, name, d, px in dropped:
    print(f"watchlist.json 略過 {sym} {name}:{d} 已跌破失效線({px:g}),要重新監看請把 stop 改到 {px:g} 以下")
wl = load_watchlist(setups, date, lot=1000, extra=extra)
otc = {x["symbol"] for x in extra if x.get("otc")}
for w in wl:
    w["otc"] = w["symbol"] in otc
out = {"built_from": date, "items": wl}
json.dump(out, open(os.path.join(HERE, "watch_auto.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"watch_auto.json: {len(wl)} 檔(名單日 {date})", ", ".join(f"{w['symbol']} {w['name']}" for w in wl))
