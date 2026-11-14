# -*- coding: utf-8 -*-
"""从 ModelScope 拉 faster-whisper 模型到本地（CTranslate2 格式，可直接给 WhisperModel 用）。"""
import os, sys, json, time, urllib.request

REPO = sys.argv[1] if len(sys.argv) > 1 else "pengzhendong/faster-whisper-large-v3-turbo"
NAME = REPO.split("/")[-1]
DST = os.path.join(r"D:\HarnessAI\work\models", NAME)
os.makedirs(DST, exist_ok=True)

def api(path):
    url = "https://www.modelscope.cn/api/v1/models/%s/repo/files" % REPO
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read().decode("utf-8"))

files = [f.get("Path") for f in (api(REPO).get("Data", {}).get("Files") or []) if f.get("Path")]
need = [f for f in files if "/" not in f and f.endswith((".bin", ".json", ".txt", ".model", ".vocab"))]
print("需要下载 %d 个文件 -> %s" % (len(need), DST), flush=True)

for i, fn in enumerate(need, 1):
    out = os.path.join(DST, fn)
    url = "https://www.modelscope.cn/models/%s/resolve/master/%s" % (REPO, fn)
    if os.path.exists(out) and os.path.getsize(out) > 0:
        print("  [%d/%d] %-28s 已存在，跳过" % (i, len(need), fn), flush=True)
        continue
    t0 = time.time()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r, open(out, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        got = 0
        while True:
            c = r.read(1 << 20)
            if not c:
                break
            f.write(c); got += len(c)
            if total and got % (50 << 20) < (1 << 20):
                print("    %5.1f/%.1f MB" % (got / 2**20, total / 2**20), end="\r", flush=True)
    dt = time.time() - t0
    print("  [%d/%d] %-28s %7.1f MB  %5.1f MB/s" % (i, len(need), fn, os.path.getsize(out) / 2**20, os.path.getsize(out) / 2**20 / max(dt, 0.01)), flush=True)

print("完成 ->", DST)
