# -*- coding: utf-8 -*-
"""
ComfyUI 出图客户端
用法：
  python gen.py "正向提示词" [-n "负向提示词"] [--size 832x1216] [--steps 25] [--cfg 6] [--seed 42] [--count 1] [--prefix test]
"""
import argparse
import json
import os
import random
import sys
import time
import urllib.request

HOST = "http://127.0.0.1:8188"
OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "ComfyUI_windows_portable-marduk191-v1.0",
    "ComfyUI", "output",
)

CKPT = "waiIllustriousSDXL_v170.safetensors"

DEFAULT_NEG = ("low quality, worst quality, bad anatomy, extra digits, "
               "missing fingers, watermark, blurry, jpeg artifacts")


def post_json(url, payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def get_json(url, timeout=30):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read())


def build_workflow(pos, neg, w, h, steps, cfg, seed, prefix):
    return {
        "1": {"class_type": "CheckpointLoaderSimple",
              "inputs": {"ckpt_name": CKPT}},
        "2": {"class_type": "CLIPTextEncode",
              "inputs": {"text": pos, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode",
              "inputs": {"text": neg, "clip": ["1", 1]}},
        "4": {"class_type": "EmptyLatentImage",
              "inputs": {"width": w, "height": h, "batch_size": 1}},
        "5": {"class_type": "KSampler",
              "inputs": {"seed": seed, "steps": steps, "cfg": cfg,
                         "sampler_name": "euler_ancestral",
                         "scheduler": "normal", "denoise": 1.0,
                         "model": ["1", 0], "positive": ["2", 0],
                         "negative": ["3", 0], "latent_image": ["4", 0]}},
        "6": {"class_type": "VAEDecode",
              "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage",
              "inputs": {"filename_prefix": prefix, "images": ["6", 0]}},
    }


def generate(pos, neg, w, h, steps, cfg, seed, prefix):
    t0 = time.time()
    wf = build_workflow(pos, neg, w, h, steps, cfg, seed, prefix)
    res = post_json(HOST + "/prompt", {"prompt": wf, "client_id": "dsh"})
    pid = res["prompt_id"]
    print("  提交 prompt_id=%s" % pid, flush=True)

    while True:
        time.sleep(2)
        hist = get_json(HOST + "/history/" + pid)
        if pid in hist:
            st = hist[pid].get("status", {})
            if not st.get("completed"):
                continue
            outs = hist[pid].get("outputs", {})
            files = []
            for node in outs.values():
                for img in node.get("images", []):
                    p = os.path.join(OUTPUT_DIR, img.get("subfolder", ""),
                                     img["filename"])
                    files.append(p)
            print("  完成 %.1f 秒" % (time.time() - t0), flush=True)
            return files
        if time.time() - t0 > 900:
            print("  超时", flush=True)
            return []


def main():
    p = argparse.ArgumentParser()
    p.add_argument("prompt")
    p.add_argument("-n", "--negative", default=DEFAULT_NEG)
    p.add_argument("--size", default="832x1216")
    p.add_argument("--steps", type=int, default=25)
    p.add_argument("--cfg", type=float, default=6.0)
    p.add_argument("--seed", type=int, default=-1)
    p.add_argument("--count", type=int, default=1)
    p.add_argument("--prefix", default="test")
    a = p.parse_args()

    w, h = [int(x) for x in a.size.lower().split("x")]
    w, h = (w // 16) * 16, (h // 16) * 16
    seed = a.seed if a.seed >= 0 else random.randint(0, 2**31)

    print("尺寸 %dx%d  步数 %d  cfg %.1f  种子 %d" % (w, h, a.steps, a.cfg, seed))
    all_files = []
    for i in range(a.count):
        files = generate(a.prompt, a.negative, w, h, a.steps, a.cfg,
                         seed + i, "%s_%d" % (a.prefix, seed + i))
        for f in files:
            print("  图片:", f)
            if os.path.exists(f):
                print("  大小 %.0f KB" % (os.path.getsize(f) / 1024))
        all_files.extend(files)
    print("共 %d 张" % len(all_files))


if __name__ == "__main__":
    main()
