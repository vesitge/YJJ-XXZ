# -*- coding: utf-8 -*-
"""
ComfyUI 生图环境 —— 批量下载器
支持断点续传，可重复运行（已下完的会跳过）。
用法：python download.py
"""
import os
import sys
import time
import urllib.request
import urllib.error

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "download")
os.makedirs(OUT, exist_ok=True)
LOG = os.path.join(BASE, "download.log")

MIRROR = "https://hf-mirror.com"

FILES = [
    ("ComfyUI_windows_portable-marduk191-v1.0.7z",
     MIRROR + "/marduk191/Comfyui_windows_portable_builds/resolve/main/ComfyUI_windows_portable-marduk191-v1.0.7z"),
    ("waiIllustriousSDXL_v170.safetensors",
     MIRROR + "/LyliaEngine/waiIllustriousSDXL_v170/resolve/main/waiIllustriousSDXL_v170.safetensors"),
    ("illustriousXLDepth_v20.safetensors",
     MIRROR + "/ERDude/Illustrious-XL-Depth-Midas/resolve/main/illustriousXLDepth_v20.safetensors"),
    ("openpose_s6000.safetensors",
     MIRROR + "/windsingai/Illustrious-XL-openpose-test/resolve/main/openpose_s6000.safetensors"),
]


def log(msg):
    line = time.strftime("%H:%M:%S ") + msg
    print(line, flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def head_size(url):
    req = urllib.request.Request(url, method="HEAD")
    req.add_header("User-Agent", "Mozilla/5.0")
    with urllib.request.urlopen(req, timeout=30) as r:
        return int(r.headers.get("Content-Length", 0))


def download(name, url, total, tries=4):
    path = os.path.join(OUT, name)
    for attempt in range(1, tries + 1):
        have = os.path.getsize(path) if os.path.exists(path) else 0
        if total and have >= total:
            log("[skip] %s already complete (%.0f MB)" % (name, have / 1e6))
            return True

        headers = {"User-Agent": "Mozilla/5.0"}
        if have:
            headers["Range"] = "bytes=%d-" % have

        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=90) as r:
                status = r.status
                if have and status != 206:
                    # 服务器不支持续传，只能从头来
                    log("[restart] %s (server returned %d, no partial support)" % (name, status))
                    have = 0
                clen = int(r.headers.get("Content-Length", 0))
                if not total:
                    total = clen + have
                mode = "ab" if have else "wb"
                log("[get ] %s  from %.0f MB / %.0f MB" % (name, have / 1e6, total / 1e6))

                with open(path, mode) as f:
                    got = have
                    t0 = time.time()
                    last = 0.0
                    speed = 0.0
                    while True:
                        chunk = r.read(1 << 20)
                        if not chunk:
                            break
                        f.write(chunk)
                        got += len(chunk)
                        now = time.time()
                        if now - last > 5:
                            last = now
                            speed = (got - have) / max(now - t0, 1e-6) / 1e6
                            pct = (got / total * 100) if total else 0
                            log("       %5.1f%%  %7.0f / %.0f MB   %5.2f MB/s"
                                % (pct, got / 1e6, total / 1e6, speed))

            size = os.path.getsize(path)
            if total and size >= total:
                log("[done] %s  %.0f MB" % (name, size / 1e6))
                return True
            log("[warn] %s incomplete %d / %d" % (name, size, total))
        except Exception as e:
            log("[fail] %s attempt %d/%d: %s" % (name, attempt, tries, e))
            if attempt < tries:
                time.sleep(5)
    return False


def main():
    log("=== download start ===")
    ok = 0
    for name, url in FILES:
        try:
            total = head_size(url)
        except Exception as e:
            log("[head-fail] %s: %s" % (name, e))
            total = 0
        log("[plan] %s  expect %.0f MB" % (name, total / 1e6))
        if download(name, url, total):
            ok += 1
    log("=== download finished: %d/%d ===" % (ok, len(FILES)))


if __name__ == "__main__":
    main()
