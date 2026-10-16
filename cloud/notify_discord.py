"""發 Discord webhook:content(自動截 2000)+ 可選附件。
webhook / thread 從環境變數或 --env-dir/.env(預設 CWD)讀;UA 依 env-dir 資料夾名自動決定。
若該 repo .env 有 DISCORD_THREAD_ID(forum 貼文串),自動把訊息發到那串底下。
共用檔:us-stock-ai-agent 與 tw-stock-ai-agent 都指到這裡,只維護這一份。"""
import sys, os, argparse

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

def build_data(content):
    return {"content": content[:2000]} if content else {}

def ua(env_dir=None):
    name = os.path.basename(os.path.abspath(env_dir or os.getcwd())) or "stock-ai-agent"
    return f"{name}/1.0"

def post(content, files, env_dir=None, thread_id=None):
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
        r = requests.post(url, headers=headers, data=build_data(content),
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
    a = ap.parse_args()
    sys.exit(post(a.content, a.file, env_dir=a.env_dir, thread_id=a.thread_id))
