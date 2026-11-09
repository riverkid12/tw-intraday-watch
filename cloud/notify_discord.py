"""發 Discord webhook:content(自動截 2000)+ 可選附件;給 --embed-title 就改發 embed(標題 + 色條 + 內文 ≤4096)。
webhook / thread 從環境變數或 --env-dir/.env(預設 CWD)讀;UA 依 env-dir 資料夾名自動決定。
若該 repo .env 有 DISCORD_THREAD_ID(forum 貼文串),自動把訊息發到那串底下。
共用檔:us-stock-ai-agent 與 tw-stock-ai-agent 都指到這裡,只維護這一份。"""
import sys, os, json, argparse

COLORS = {"green": 0x2ECC71, "yellow": 0xF1C40F, "red": 0xE74C3C}   # 市場姿態 攻擊 / 中性 / 防禦

def _from_env(key, env_dir=None):
    v = os.environ.get(key)
    if v:
        return v
    d = os.path.abspath(env_dir or os.getcwd())
    envp = os.path.join(d, ".env")
    if os.path.exists(envp):
        for line in open(envp, encoding="utf-8"):
            line = line.strip()
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip()
    return None

def load_webhook(env_dir=None):
    return _from_env("DISCORD_WEBHOOK_URL", env_dir)

def load_thread_id(env_dir=None):
    return _from_env("DISCORD_THREAD_ID", env_dir)

def color_value(c):
    """'green'/'yellow'/'red' 或 hex('e74c3c')→ int;None → None。"""
    if c is None or c == "":
        return None
    return COLORS[c] if c in COLORS else int(str(c).lstrip("#"), 16)

def build_data(content, title=None, color=None):
    if title:
        e = {"title": title[:256], "description": (content or "")[:4096]}
        cv = color_value(color)
        if cv is not None:
            e["color"] = cv
        return {"embeds": [e]}
    return {"content": content[:2000]} if content else {}

def form_fields(data):
    """multipart 表單欄位:embeds 必須走 payload_json;純 content 照舊。"""
    return {"payload_json": json.dumps(data, ensure_ascii=False)} if "embeds" in data else data

def ua(env_dir=None):
    name = os.path.basename(os.path.abspath(env_dir or os.getcwd())) or "stock-ai-agent"
    return f"{name}/1.0"

def post(content, files, env_dir=None, thread_id=None, title=None, color=None):
    url = load_webhook(env_dir)
    if not url:
        print("FATAL: no DISCORD_WEBHOOK_URL (env or .env)")
        return 2
    tid = thread_id or load_thread_id(env_dir)
    if tid:
        url = url + ("&" if "?" in url else "?") + "thread_id=" + tid
    import requests
    headers = {"User-Agent": ua(env_dir)}  # Discord 無 UA 會 403
    fobjs, multipart = [], []
    try:
        for i, fp in enumerate(files or []):
            fobjs.append(open(fp, "rb"))
            multipart.append((f"file{i}", (os.path.basename(fp), fobjs[-1])))
        r = requests.post(url, headers=headers, data=form_fields(build_data(content, title, color)),
                          files=multipart or None, timeout=30)
        print(f"discord status {r.status_code}")
        return 0 if r.status_code in (200, 204) else 1
    finally:
        for f in fobjs:
            f.close()

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Post to Discord webhook")
    ap.add_argument("--content", default="")
    ap.add_argument("--file", action="append", default=[])
    ap.add_argument("--env-dir", default=None, help="dir holding .env / naming the UA (default: CWD)")
    ap.add_argument("--thread-id", default=None, help="override DISCORD_THREAD_ID (forum thread)")
    ap.add_argument("--embed-title", default=None, help="給了就發 embed:這是標題,--content 變內文(≤4096)")
    ap.add_argument("--embed-color", default=None, help="green / yellow / red 或 hex(姿態色條)")
    a = ap.parse_args()
    sys.exit(post(a.content, a.file, env_dir=a.env_dir, thread_id=a.thread_id, title=a.embed_title, color=a.embed_color))
