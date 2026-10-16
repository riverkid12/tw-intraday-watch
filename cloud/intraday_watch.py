"""盤中監看(2026-10-16)—— 吃發車觀察的「蓄勢」名單,開盤到收盤每 N 秒看證交所快照,只在狀態改變時推 Discord。

事件:過線(第一次收在線上)/ 回到線下 / 跌破失效線(基底低)/ 13:20 準備過關(列過線且量推估夠的)/ 13:30 收盤確認(實際量)。
量的推估:台股典型 U 型量能曲線(DEFAULT_PROFILE,11:00 累積約五成)把「到目前的量」換算成全天量,再除以 20 日均量。
規則來源:投資政策 §4.1 —— 收盤過線、量 ≥ 1.35 倍就算;13:25 看到 ≥ 1.25 倍可以準備。

純邏輯(Monitor / evaluate / parse_mis)全部可用假快照測;網路只在 fetch_mis。
CLI 例(台股):
  python intraday_watch.py --setups C:/Projects/tw-stock-ai-agent/setups_history.jsonl --date 2026-10-19 \
      --extra C:/Projects/tw-stock-ai-agent/watchlist.json --env-dir C:/Projects/tw-stock-ai-agent --log C:/Projects/tw-stock-ai-agent/intraday_log.jsonl
  --dry-run 只印不發;--once 只看一次(收盤後拿來驗格式)。
"""
import sys, os, json, time, argparse, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

MIS = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
# 累積成交量占全天比例(時間 → 比例),節點之間線性內插。ponytail: 經驗曲線,之後用 intraday_log 校正
DEFAULT_PROFILE = [("09:00:00", 0.0), ("09:30:00", 0.20), ("10:00:00", 0.32), ("10:30:00", 0.42), ("11:00:00", 0.50),
                   ("11:30:00", 0.57), ("12:00:00", 0.64), ("12:30:00", 0.71), ("13:00:00", 0.80), ("13:25:00", 0.90), ("13:30:00", 1.0)]


def _sec(t):
    h, m, s = (t.split(":") + ["0", "0"])[:3]
    return int(h) * 3600 + int(m) * 60 + int(s)


def mis_url(symbols, otc=()):
    ch = "|".join(f"{'otc' if s in set(otc) else 'tse'}_{s}.tw" for s in symbols)
    return f"{MIS}?ex_ch={ch}&json=1&delay=0"


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def parse_mis(payload):
    """{symbol: {price, volume(張), open, high, low, prev_close, time, date, name}};沒成交的 price=None、volume=0。"""
    out = {}
    for m in payload.get("msgArray", []):
        sym = m.get("c")
        if not sym:
            continue
        v = _num(m.get("v"))
        out[sym] = {"symbol": sym, "name": m.get("n", ""), "price": _num(m.get("z")), "volume": int(v) if v else 0,
                    "open": _num(m.get("o")), "high": _num(m.get("h")), "low": _num(m.get("l")), "prev_close": _num(m.get("y")),
                    "time": m.get("t", ""), "date": m.get("d", "")}
    return out


def fetch_mis(symbols, otc=()):
    import requests
    r = requests.get(mis_url(symbols, otc), timeout=15, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    r.raise_for_status()
    return parse_mis(r.json())


def cum_fraction(t, profile=DEFAULT_PROFILE):
    s = _sec(t)
    pts = [(_sec(a), f) for a, f in profile]
    if s <= pts[0][0]:
        return 0.0
    if s >= pts[-1][0]:
        return 1.0
    for (a, fa), (b, fb) in zip(pts, pts[1:]):
        if a <= s <= b:
            return fa + (fb - fa) * (s - a) / (b - a)
    return 1.0


def projected_volume(cum_vol, t, profile=DEFAULT_PROFILE):
    f = cum_fraction(t, profile)
    if not cum_vol or f <= 0:
        return None
    return round(cum_vol / f)


def evaluate(item, snap, min_ratio=1.35):
    price, vol, t = snap.get("price"), snap.get("volume") or 0, snap.get("time") or "09:00:00"
    proj = projected_volume(vol, t)
    ratio = round(proj / item["avg_vol"], 2) if (proj and item.get("avg_vol")) else None
    return {"symbol": item["symbol"], "name": item.get("name", ""), "price": price, "level": item["level"],
            "above": bool(price is not None and price > item["level"]), "proj_vol": proj, "vol_ratio": ratio,
            "vol_ok": bool(ratio is not None and ratio >= min_ratio),
            "below_stop": bool(price is not None and item.get("stop") is not None and price <= item["stop"]), "time": t}


def _g(x):
    return f"{x:g}" if isinstance(x, (int, float)) else str(x)


class Monitor:
    def __init__(self, watchlist, poll, notify, log=None, pre_close="13:20:00", close="13:30:00", min_ratio=1.35, ready_ratio=1.25):
        self.items, self.poll, self.notify, self.log = list(watchlist), poll, notify, (log or (lambda r: None))
        self.pre_close, self.close, self.min_ratio, self.ready_ratio = pre_close, close, min_ratio, ready_ratio
        self.above = {}            # symbol -> 上一次是否在線上(None = 還沒看過)
        self.stopped = set()
        self.pre_sent = self.done = False
        self.last = {}

    def _emit(self, event, text, **rec):
        self.notify(text)
        self.log({"event": event, "text": text, **rec})

    def step(self, now):
        try:
            snaps = self.poll()
        except Exception as e:                                   # 網路壞了:記一筆、下一輪再試
            self.log({"event": "poll_error", "time": now, "error": repr(e)[:200]})
            return
        states = {}
        for it in self.items:
            s = snaps.get(it["symbol"])
            if s is None:
                continue
            s = dict(s, time=s.get("time") or now)
            e = evaluate(it, s, self.min_ratio); states[it["symbol"]] = e
            tag = f"{it['symbol']} {it.get('name', '')}".strip()
            prev = self.above.get(it["symbol"])
            if e["above"] and not prev:
                self._emit("cross", f"{tag} 過 {_g(it['level'])}:{_g(e['price'])},量推估 {e['vol_ratio'] if e['vol_ratio'] is not None else '?'}x",
                           symbol=it["symbol"], price=e["price"], vol_ratio=e["vol_ratio"], time=now)
            elif prev and not e["above"] and e["price"] is not None:
                self._emit("back_under", f"{tag} 回到線下 {_g(it['level'])}:{_g(e['price'])}", symbol=it["symbol"], price=e["price"], time=now)
            if e["price"] is not None:
                self.above[it["symbol"]] = e["above"]
            if e["below_stop"] and it["symbol"] not in self.stopped:
                self.stopped.add(it["symbol"])
                self._emit("stop", f"{tag} 跌破失效線 {_g(it['stop'])}:{_g(e['price'])}", symbol=it["symbol"], price=e["price"], time=now)
        self.last = states
        if not self.pre_sent and self.pre_close <= now < self.close:
            self.pre_sent = True
            ready = [e for e in states.values() if e["above"] and e["vol_ratio"] is not None and e["vol_ratio"] >= self.ready_ratio]
            short = [e for e in states.values() if e["above"] and e not in ready]
            txt = "13:20 準備過關:" + ("、".join(f"{e['symbol']} {e['name']} {_g(e['price'])} 量推估 {e['vol_ratio']}x" for e in ready) or "無")
            if short:
                txt += ";量不足:" + "、".join(f"{e['symbol']} {e['name']} {_g(e['price'])} {e['vol_ratio']}x" for e in short)
            self._emit("pre_close", txt, time=now)
        if not self.done and now >= self.close:
            self.done = True
            parts = []
            for e in states.values():
                if e["above"]:
                    parts.append(f"{e['symbol']} {e['name']} 過關 {_g(e['price'])}(量 {e['vol_ratio']}x{'' if e['vol_ok'] else ',量不足'})")
                else:
                    parts.append(f"{e['symbol']} {e['name']} 沒過 {_g(e['price'])}")
            self._emit("close", "13:30 收盤確認:" + ("; ".join(parts) or "無"), time=now)

    def run(self, clock, sleep, poll_seconds=30, stop_after="13:35:00"):
        while not self.done:
            now = clock()
            self.step(now)
            if self.done or now >= stop_after:
                break
            sleep(poll_seconds)


def load_watchlist(path, date, lot=1000, extra=()):
    """當天的 coil 列 → {symbol, name, level, stop, avg_vol(張)};extra 直接是同格式的 dict,重複的 symbol 不加。"""
    out, seen = [], set()
    if path and os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("date") == date and r.get("setup") == "coil" and r["symbol"] not in seen:
                vt = r.get("vol_trigger") or 0
                out.append({"symbol": r["symbol"], "name": r.get("name") or "", "level": r.get("setup_level"), "stop": r.get("base_low"),
                            "avg_vol": round(vt / 1.5 / lot) if vt else None})
                seen.add(r["symbol"])
    for x in extra:
        if x["symbol"] not in seen:
            out.append({k: x.get(k) for k in ("symbol", "name", "level", "stop", "avg_vol")}); seen.add(x["symbol"])
    return out


def load_extra(path):
    """手動名單檔:純 list,或 build_watch.py 產的 {"built_from":..., "items":[...]}。不存在 = []。"""
    if not path or not os.path.exists(path):
        return []
    d = json.load(open(path, encoding="utf-8"))
    return d.get("items", []) if isinstance(d, dict) else d


def _taipei_now():
    try:
        from zoneinfo import ZoneInfo
        return datetime.datetime.now(ZoneInfo("Asia/Taipei"))
    except Exception:
        return datetime.datetime.now()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="盤中監看:蓄勢名單過線 / 量推估 / 13:20 準備 / 13:30 確認 → Discord")
    ap.add_argument("--setups", default=None, help="setups_history.jsonl(取 --date 當天的 coil)")
    ap.add_argument("--date", default=None, help="名單日期(預設 = 前一個交易日,即今天之前最近一筆)")
    ap.add_argument("--extra", default=None, help="手動名單 json:[{symbol,name,level,stop,avg_vol,otc?}]")
    ap.add_argument("--otc", default="", help="逗號分隔,上櫃代號(快照前綴不同)")
    ap.add_argument("--env-dir", default=None, help="放 .env(DISCORD_WEBHOOK_URL)的資料夾;不給 = 只印")
    ap.add_argument("--log", default=None, help="事件 jsonl")
    ap.add_argument("--poll", type=int, default=30)
    ap.add_argument("--lot", type=int, default=1000)
    ap.add_argument("--dry-run", action="store_true", help="只印不發 Discord")
    ap.add_argument("--once", action="store_true", help="只輪一次就結束(驗格式用)")
    a = ap.parse_args()
    extra = load_extra(a.extra)
    otc = {s.strip() for s in a.otc.split(",") if s.strip()} | {x["symbol"] for x in extra if x.get("otc")}
    date = a.date
    if not date and a.setups and os.path.exists(a.setups):
        dates = sorted({json.loads(l)["date"] for l in open(a.setups, encoding="utf-8") if l.strip()})
        today = _taipei_now().date().isoformat()
        date = max([d for d in dates if d < today] or dates or [today])
    wl = load_watchlist(a.setups, date, a.lot, extra)
    if not wl:
        print(f"名單空(date={date}),結束"); sys.exit(0)
    print(f"監看 {len(wl)} 檔(名單日 {date}):", ", ".join(f"{w['symbol']} {w['name']}@{_g(w['level'])}" for w in wl))
    syms = [w["symbol"] for w in wl]

    def notify(text):
        print(_taipei_now().strftime("%H:%M:%S"), text, flush=True)
        if a.env_dir and not a.dry_run:
            try:
                from notify_discord import post
                post(text, [], env_dir=a.env_dir)
            except Exception as e:
                print("discord fail", repr(e)[:120])

    def log(rec):
        if a.log:
            rec = dict(rec, date=_taipei_now().date().isoformat())
            with open(a.log, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    m = Monitor(wl, poll=lambda: fetch_mis(syms, otc), notify=notify, log=log)
    if a.once:
        m.step(_taipei_now().strftime("%H:%M:%S")); print("last:", json.dumps(m.last, ensure_ascii=False)[:600])
    else:
        m.run(clock=lambda: _taipei_now().strftime("%H:%M:%S"), sleep=time.sleep, poll_seconds=a.poll)
