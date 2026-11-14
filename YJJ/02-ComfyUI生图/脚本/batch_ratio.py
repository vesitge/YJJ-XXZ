# -*- coding: utf-8 -*-
"""
画风 : 角色 = 1:9 → 9:1，九档，总和固定 1.0，同种子。
ep15 = ryou_v2_1024.safetensors
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
RYOU = "ryou_v2_1024.safetensors"

PROMPT = ("ryou, 1wa0, 1girl, amber eyes, black choker, long grey brown hair, ponytail, "
          "white camisole, denim shorts, indoor, living room, warm lighting, "
          "looking at viewer, upper body, masterpiece, best quality, "
          "highly detailed, anime style")
NEG = ("low quality, worst quality, bad anatomy, extra digits, missing fingers, "
       "watermark, blurry, jpeg artifacts")

# (画风, 角色)，总和都是 1.0
RATIOS = [
    (0.1, 0.9, "1to9"),
    (0.2, 0.8, "2to8"),
    (0.3, 0.7, "3to7"),
    (0.4, 0.6, "4to6"),
    (0.5, 0.5, "5to5"),
    (0.6, 0.4, "6to4"),
    (0.7, 0.3, "7to3"),
    (0.8, 0.2, "8to2"),
    (0.9, 0.1, "9to1"),
]
SEED = 1001
W, H, STEPS, CFG = 832, 1216, 30, 5.0


def post(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def get(url, timeout=60):
    return json.loads(urllib.request.urlopen(url, timeout=timeout).read())


def build(iw, ry, prefix):
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": CKPT}},
        "2": {"class_type": "LoraLoader",
              "inputs": {"model": ["1", 0], "clip": ["1", 1], "lora_name": IWAO,
                         "strength_model": iw, "strength_clip": iw}},
        "3": {"class_type": "LoraLoader",
              "inputs": {"model": ["2", 0], "clip": ["2", 1], "lora_name": RYOU,
                         "strength_model": ry, "strength_clip": ry}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": PROMPT, "clip": ["3", 1]}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": NEG, "clip": ["3", 1]}},
        "6": {"class_type": "EmptyLatentImage",
              "inputs": {"width": W, "height": H, "batch_size": 1}},
        "7": {"class_type": "KSampler",
              "inputs": {"seed": SEED, "steps": STEPS, "cfg": CFG,
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
    print("提交 %d 档比例..." % len(RATIOS), flush=True)
    for iw, ry, tag in RATIOS:
        prefix = "ratio_%s" % tag
        pid = post(HOST + "/prompt", {"prompt": build(iw, ry, prefix),
                                      "client_id": "ratio"})["prompt_id"]
        jobs.append((tag, pid))
        print("  画风 %.1f : 角色 %.1f  -> %s" % (iw, ry, tag), flush=True)

    done = set()
    while len(done) < len(jobs) and time.time() - t0 < 1800:
        time.sleep(4)
        try:
            hist = get(HOST + "/history")
        except Exception:
            continue
        for tag, pid in jobs:
            if pid in hist:
                done.add(pid)
        if len(done) == len(jobs):
            break
    print("完成 %d/%d，耗时 %.0f 秒" % (len(done), len(jobs), time.time() - t0), flush=True)

    # 拼 3x3
    from PIL import Image
    CW, CH, PAD = 300, 438, 5
    Wc = 3 * (CW + PAD) + PAD
    Hc = 3 * (CH + PAD) + PAD
    canvas = Image.new("RGB", (Wc, Hc), (24, 24, 28))
    n = 0
    for idx, (iw, ry, tag) in enumerate(RATIOS):
        p = os.path.join(OUT, "ratio_%s_00001_.png" % tag)
        if not os.path.exists(p):
            continue
        im = Image.open(p).convert("RGB").resize((CW, CH), Image.LANCZOS)
        r, c = idx // 3, idx % 3
        canvas.paste(im, (PAD + c * (CW + PAD), PAD + r * (CH + PAD)))
        n += 1
    dst = os.path.join(OUT, "比例实验总览.png")
    canvas.save(dst)
    print("拼图 %d 张 -> %s" % (n, dst), flush=True)
    print("顺序: 左上 1:9 → 中上 2:8 → 右上 3:7 → 左中 4:6 → 正中 5:5 → "
          "右中 6:4 → 左下 7:3 → 中下 8:2 → 右下 9:1", flush=True)


if __name__ == "__main__":
    main()
