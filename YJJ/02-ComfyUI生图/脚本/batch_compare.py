# -*- coding: utf-8 -*-
"""
5 个 LoRA 版本 x 10 个种子，一次性提交到 ComfyUI 队列，跑完生成对比页。
"""
import json
import os
import time
import urllib.request

HOST = "http://127.0.0.1:8188"
BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "ComfyUI_windows_portable-marduk191-v1.0", "ComfyUI", "output")
CKPT = "waiIllustriousSDXL_v170.safetensors"

PROMPT = ("ryou, 1girl, amber eyes, black choker, long grey brown hair, ponytail, "
          "white camisole, denim shorts, indoor, living room, warm lighting, "
          "looking at viewer, upper body, masterpiece, best quality, "
          "highly detailed, anime style")
NEG = ("low quality, worst quality, bad anatomy, extra digits, missing fingers, "
       "watermark, blurry, jpeg artifacts")

VERSIONS = [
    ("ryou_v2_1024-000003.safetensors", "ep03"),
    ("ryou_v2_1024-000006.safetensors", "ep06"),
    ("ryou_v2_1024-000009.safetensors", "ep09"),
    ("ryou_v2_1024-000012.safetensors", "ep12"),
    ("ryou_v2_1024.safetensors", "ep15"),
]
SEEDS = [1001, 1002, 1003, 1004, 1005, 1006, 1007, 1008, 1009, 1010]
W, H, STEPS, CFG = 800, 1152, 24, 6.0


def post(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def get(url, timeout=60):
    return json.loads(urllib.request.urlopen(url, timeout=timeout).read())


def build(lora, seed, prefix):
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": CKPT}},
        "2": {"class_type": "LoraLoader",
              "inputs": {"model": ["1", 0], "clip": ["1", 1], "lora_name": lora,
                         "strength_model": 1.0, "strength_clip": 1.0}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": PROMPT, "clip": ["2", 1]}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": NEG, "clip": ["2", 1]}},
        "5": {"class_type": "EmptyLatentImage",
              "inputs": {"width": W, "height": H, "batch_size": 1}},
        "6": {"class_type": "KSampler",
              "inputs": {"seed": seed, "steps": STEPS, "cfg": CFG,
                         "sampler_name": "euler_ancestral", "scheduler": "normal",
                         "denoise": 1.0, "model": ["2", 0],
                         "positive": ["3", 0], "negative": ["4", 0],
                         "latent_image": ["5", 0]}},
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}},
        "8": {"class_type": "SaveImage",
              "inputs": {"filename_prefix": prefix, "images": ["7", 0]}},
    }


def main():
    t0 = time.time()
    jobs = []
    print("提交 %d 个任务..." % (len(VERSIONS) * len(SEEDS)), flush=True)
    for lora, tag in VERSIONS:
        for s in SEEDS:
            prefix = "cmp_%s_%d" % (tag, s)
            pid = post(HOST + "/prompt", {"prompt": build(lora, s, prefix),
                                          "client_id": "batch"})["prompt_id"]
            jobs.append((tag, s, pid, prefix))
        print("  %s 的 10 张已入队" % tag, flush=True)

    total = len(jobs)
    done = set()
    while len(done) < total and time.time() - t0 < 2400:
        time.sleep(5)
        try:
            hist = get(HOST + "/history")
        except Exception:
            continue
        for tag, s, pid, prefix in jobs:
            if pid in hist and pid not in done:
                done.add(pid)
        if len(done) % 10 == 0 and len(done):
            print("  完成 %d/%d  用时 %.0f 秒" % (len(done), total, time.time() - t0), flush=True)
        if len(done) == total:
            break

    print("全部完成 %d/%d，总耗时 %.0f 秒" % (len(done), total, time.time() - t0), flush=True)

    # 生成对比页
    rows = []
    for lora, tag in VERSIONS:
        cells = []
        for s in SEEDS:
            prefix = "cmp_%s_%d" % (tag, s)
            fname = prefix + "_00001_.png"
            if os.path.exists(os.path.join(OUT, fname)):
                cells.append('<td><img src="%s" title="seed %d"><div>%d</div></td>' % (fname, s, s))
            else:
                cells.append('<td class="miss">缺</td>')
        rows.append('<tr><th>%s</th>%s</tr>' % (tag, "".join(cells)))

    html = """<!doctype html><meta charset="utf-8">
<title>v2 LoRA 版本对比</title>
<style>
body{background:#1a1a1e;color:#ddd;font-family:system-ui,sans-serif;margin:16px}
table{border-collapse:collapse}
th{writing-mode:vertical-rl;transform:rotate(180deg);padding:6px;font-size:14px;color:#7fd}
td{padding:2px;text-align:center;font-size:10px;color:#888}
img{width:150px;display:block;border:1px solid #333}
.miss{color:#a44;padding:20px}
</style>
<h2>凉 · v2 各轮次对比（同提示词，种子 1001–1010）</h2>
<table>%s</table>
<p>横看同一行 = 同一版本不同种子；竖看同一列 = 同一种子不同版本。</p>
""" % ("".join(rows))

    p = os.path.join(OUT, "对比页.html")
    with open(p, "w", encoding="utf-8") as f:
        f.write(html)
    print("对比页:", p, flush=True)


if __name__ == "__main__":
    main()
