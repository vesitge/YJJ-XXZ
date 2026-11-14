# -*- coding: utf-8 -*-
"""
带 LoRA 的出图客户端。
用法：
  python gen_lora.py "提示词" --lora ryou_v1.safetensors --strength 0.8 --seed 42 --prefix test
"""
import argparse
import json
import os
import random
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


def build(pos, neg, w, h, steps, cfg, seed, prefix, lora, strength):
    wf = {
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
    if lora:
        wf["8"] = {"class_type": "LoraLoader",
                   "inputs": {"model": ["1", 0], "clip": ["1", 1],
                              "lora_name": lora,
                              "strength_model": strength,
                              "strength_clip": strength}}
        wf["2"]["inputs"]["clip"] = ["8", 1]
        wf["3"]["inputs"]["clip"] = ["8", 1]
        wf["5"]["inputs"]["model"] = ["8", 0]
    return wf


def generate(pos, neg, w, h, steps, cfg, seed, prefix, lora, strength):
    t0 = time.time()
    wf = build(pos, neg, w, h, steps, cfg, seed, prefix, lora, strength)
    pid = post_json(HOST + "/prompt", {"prompt": wf, "client_id": "dsh"})["prompt_id"]
    while True:
        time.sleep(2)
        hist = get_json(HOST + "/history/" + pid)
        if pid in hist:
            if not hist[pid].get("status", {}).get("completed"):
                continue
            files = []
            for node in hist[pid].get("outputs", {}).values():
                for img in node.get("images", []):
                    files.append(os.path.join(OUTPUT_DIR,
                                              img.get("subfolder", ""),
                                              img["filename"]))
            return files, time.time() - t0
        if time.time() - t0 > 600:
            return [], time.time() - t0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("prompt")
    p.add_argument("-n", "--negative", default=DEFAULT_NEG)
    p.add_argument("--size", default="832x1216")
    p.add_argument("--steps", type=int, default=28)
    p.add_argument("--cfg", type=float, default=5.5)
    p.add_argument("--seed", type=int, default=-1)
    p.add_argument("--prefix", default="lora_test")
    p.add_argument("--lora", default=None)
    p.add_argument("--strength", type=float, default=0.8)
    a = p.parse_args()

    w, h = [int(x) for x in a.size.lower().split("x")]
    w, h = (w // 16) * 16, (h // 16) * 16
    seed = a.seed if a.seed >= 0 else random.randint(0, 2**31)

    files, sec = generate(a.prompt, a.negative, w, h, a.steps, a.cfg,
                          seed, a.prefix, a.lora, a.strength)
    print("LoRA=%s 强度=%.2f  用时 %.1f 秒" % (a.lora, a.strength, sec))
    for f in files:
        print("  ", f, "存在" if os.path.exists(f) else "缺失")


if __name__ == "__main__":
    main()
