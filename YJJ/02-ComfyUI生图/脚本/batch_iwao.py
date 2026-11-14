# -*- coding: utf-8 -*-
"""
角色 LoRA（ep09 / ep12 / ep15） x 画风 LoRA（Iwao178），各 3 张。
参数照作者给的：CFG 5, Steps 30，触发词用 ryou + 1wa0 两个。
"""
import json
import os
import time
import urllib.request

HOST = "http://127.0.0.1:8188"
BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "ComfyUI_windows_portable-marduk191-v1.0", "ComfyUI", "output")
CKPT = "waiIllustriousSDXL_v170.safetensors"
IWAO = "Iwao178.safetensors"
IWAO_W = 0.6
RYOU_W = 0.9

PROMPT = ("ryou, 1wa0, 1girl, amber eyes, black choker, long grey brown hair, ponytail, "
          "white camisole, denim shorts, indoor, living room, warm lighting, "
          "looking at viewer, upper body, masterpiece, best quality, "
          "highly detailed, anime style")
NEG = ("low quality, worst quality, bad anatomy, extra digits, missing fingers, "
       "watermark, blurry, jpeg artifacts")

VERSIONS = [
    ("ryou_v2_1024-000009.safetensors", "ep09"),
    ("ryou_v2_1024-000012.safetensors", "ep12"),
    ("ryou_v2_1024.safetensors", "ep15"),
]
SEEDS = [1001, 1002, 1003]
W, H, STEPS, CFG = 832, 1216, 30, 5.0


def post(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def get(url, timeout=60):
    return json.loads(urllib.request.urlopen(url, timeout=timeout).read())


def build(ryou_lora, seed, prefix):
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": CKPT}},
        "2": {"class_type": "LoraLoader",
              "inputs": {"model": ["1", 0], "clip": ["1", 1], "lora_name": IWAO,
                         "strength_model": IWAO_W, "strength_clip": IWAO_W}},
        "3": {"class_type": "LoraLoader",
              "inputs": {"model": ["2", 0], "clip": ["2", 1], "lora_name": ryou_lora,
                         "strength_model": RYOU_W, "strength_clip": RYOU_W}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": PROMPT, "clip": ["3", 1]}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": NEG, "clip": ["3", 1]}},
        "6": {"class_type": "EmptyLatentImage",
              "inputs": {"width": W, "height": H, "batch_size": 1}},
        "7": {"class_type": "KSampler",
              "inputs": {"seed": seed, "steps": STEPS, "cfg": CFG,
                         "sampler_name": "euler_ancestral", "scheduler": "normal",
                         "denoise": 1.0, "model": ["3", 0],
                         "positive": ["4", 0], "negative": ["5", 0],
                         "latent_image": ["6", 0]}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["7", 0], "vae": ["1", 2]}},
        "9": {"class_type": "SaveImage",
              "inputs": {"filename_prefix": prefix, "images": ["8", 0]}},
    }


def main():
    t0 = time.time()
    jobs = []
    print("提交 %d 个任务（画风 %.2f / 角色 %.2f）..."
          % (len(VERSIONS) * len(SEEDS), IWAO_W, RYOU_W), flush=True)
    for lora, tag in VERSIONS:
        for s in SEEDS:
            prefix = "iwao_%s_%d" % (tag, s)
            pid = post(HOST + "/prompt", {"prompt": build(lora, s, prefix),
                                          "client_id": "iwao"})["prompt_id"]
            jobs.append((tag, s, pid))
        print("  %s 的 3 张已入队" % tag, flush=True)

    total = len(jobs)
    done = set()
    while len(done) < total and time.time() - t0 < 1800:
        time.sleep(5)
        try:
            hist = get(HOST + "/history")
        except Exception:
            continue
        for tag, s, pid in jobs:
            if pid in hist:
                done.add(pid)
        if len(done) == total:
            break
    print("完成 %d/%d，耗时 %.0f 秒" % (len(done), total, time.time() - t0), flush=True)

    rows = []
    for lora, tag in VERSIONS:
        cells = []
        for s in SEEDS:
            f = "iwao_%s_%d_00001_.png" % (tag, s)
            if os.path.exists(os.path.join(OUT, f)):
                cells.append('<td><img src="%s"><div>seed %d</div></td>' % (f, s))
            else:
                cells.append('<td class="miss">缺</td>')
        rows.append("<tr><th>%s</th>%s</tr>" % (tag, "".join(cells)))

    html = """<!doctype html><meta charset="utf-8"><title>IWAO 画风 x 角色版本</title>
<style>body{background:#1a1a1e;color:#ddd;font-family:system-ui;margin:16px}
table{border-collapse:collapse}th{padding:8px;color:#7fd;font-size:15px}
td{padding:3px;text-align:center;font-size:11px;color:#888}
img{width:260px;display:block;border:1px solid #333}</style>
<h2>画风 Iwao178 (0.6) x 角色版本 (0.9) · CFG 5 · 30 步</h2>
<table>%s</table>""" % ("".join(rows))
    p = os.path.join(OUT, "IWAO对比.html")
    with open(p, "w", encoding="utf-8") as f:
        f.write(html)
    print("对比页:", p, flush=True)


if __name__ == "__main__":
    main()
