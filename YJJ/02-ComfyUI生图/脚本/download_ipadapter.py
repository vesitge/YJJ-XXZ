# -*- coding: utf-8 -*-
"""下载 IP-Adapter 需要的节点和模型"""
import os
import time
import urllib.request

MIRROR = "https://hf-mirror.com"
BASE = r"D:\HarnessAI\work\生图环境"
COMFY = os.path.join(BASE, "ComfyUI_windows_portable-marduk191-v1.0", "ComfyUI")
DL = os.path.join(BASE, "download")

os.makedirs(DL, exist_ok=True)
os.makedirs(os.path.join(COMFY, "models", "ipadapter"), exist_ok=True)
os.makedirs(os.path.join(COMFY, "models", "clip_vision"), exist_ok=True)

FILES = [
    ("ipadapter_node.zip",
     "https://codeload.github.com/cubiq/ComfyUI_IPAdapter_plus/zip/refs/heads/main"),
    ("ip-adapter-plus-face_sdxl_vit-h.safetensors",
     MIRROR + "/h94/IP-Adapter/resolve/main/sdxl_models/ip-adapter-plus-face_sdxl_vit-h.safetensors"),
    ("ip-adapter-plus_sdxl_vit-h.safetensors",
     MIRROR + "/h94/IP-Adapter/resolve/main/sdxl_models/ip-adapter-plus_sdxl_vit-h.safetensors"),
    ("image_encoder_sdxl.safetensors",
     MIRROR + "/h94/IP-Adapter/resolve/main/sdxl_models/image_encoder/model.safetensors"),
]


def fetch(name, url):
    path = os.path.join(DL, name)
    if os.path.exists(path) and os.path.getsize(path) > 1024 * 1024:
        print("[skip] %s already there (%.0f MB)" % (name, os.path.getsize(path) / 1e6), flush=True)
        return path

    print("[get ] %s" % name, flush=True)
    t0 = time.time()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as r, open(path, "wb") as f:
        total = int(r.headers.get("Content-Length", 0))
        got = 0
        last = 0.0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            now = time.time()
            if now - last > 5:
                last = now
                sp = got / max(now - t0, 1e-6) / 1e6
                pct = (got / total * 100) if total else 0
                print("       %5.1f%%  %6.0f / %.0f MB  %5.1f MB/s"
                      % (pct, got / 1e6, total / 1e6, sp), flush=True)
    print("[done] %s  %.0f MB  %.0f s" % (name, os.path.getsize(path) / 1e6, time.time() - t0), flush=True)
    return path


def main():
    for name, url in FILES:
        try:
            fetch(name, url)
        except Exception as e:
            print("[FAIL] %s : %s" % (name, e), flush=True)
    print("=== all done ===")


if __name__ == "__main__":
    main()
