# -*- coding: utf-8 -*-
"""
带 LoRA + IP-Adapter 的出图客户端
IP-Adapter 拿一张参考图锁住脸，比纯 LoRA 更贴原图。
"""
import argparse
import json
import os
import random
import time
import urllib.request

HOST = "http://127.0.0.1:8188"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "ComfyUI_windows_portable-marduk191-v1.0", "ComfyUI", "output")
CKPT = "waiIllustriousSDXL_v170.safetensors"
NEG = ("low quality, worst quality, bad anatomy, extra digits, "
       "missing fingers, watermark, blurry, jpeg artifacts")


def post(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def get(url, timeout=60):
    return json.loads(urllib.request.urlopen(url, timeout=timeout).read())


def build(a):
    wf = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": CKPT}},
        "2": {"class_type": "LoraLoader",
              "inputs": {"model": ["1", 0], "clip": ["1", 1],
                         "lora_name": a.lora, "strength_model": a.lora_strength,
                         "strength_clip": a.lora_strength}},
        "3": {"class_type": "IPAdapterUnifiedLoader",
              "inputs": {"model": ["2", 0], "preset": a.preset}},
        "4": {"class_type": "IPAdapterAdvanced",
              "inputs": {"model": ["3", 0], "ipadapter": ["3", 1],
                         "image": ["7", 0], "weight": a.ipa_weight,
                         "weight_type": "linear", "combine_embeds": "concat",
                         "start_at": 0.0, "end_at": 1.0,
                         "embeds_scaling": "V only"}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": a.prompt, "clip": ["2", 1]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": NEG, "clip": ["2", 1]}},
        "7": {"class_type": "LoadImage", "inputs": {"image": a.ref}},
        "8": {"class_type": "EmptyLatentImage",
              "inputs": {"width": a.w, "height": a.h, "batch_size": 1}},
        "9": {"class_type": "KSampler",
              "inputs": {"seed": a.seed, "steps": a.steps, "cfg": a.cfg,
                         "sampler_name": "euler_ancestral", "scheduler": "normal",
                         "denoise": 1.0, "model": ["4", 0],
                         "positive": ["5", 0], "negative": ["6", 0],
                         "latent_image": ["8", 0]}},
        "10": {"class_type": "VAEDecode",
               "inputs": {"samples": ["9", 0], "vae": ["1", 2]}},
        "11": {"class_type": "SaveImage",
               "inputs": {"filename_prefix": a.prefix, "images": ["10", 0]}},
    }
    return wf


def main():
    p = argparse.ArgumentParser()
    p.add_argument("prompt")
    p.add_argument("--ref", default="ryou_ref.png")
    p.add_argument("--lora", default="ryou_v1.safetensors")
    p.add_argument("--lora-strength", type=float, default=0.85)
    p.add_argument("--ipa-weight", type=float, default=0.7)
    p.add_argument("--preset", default="PLUS (high strength)")
    p.add_argument("--size", default="832x1216")
    p.add_argument("--steps", type=int, default=28)
    p.add_argument("--cfg", type=float, default=6.0)
    p.add_argument("--seed", type=int, default=-1)
    p.add_argument("--prefix", default="ipa_test")
    a = p.parse_args()

    a.w, a.h = [int(x) for x in a.size.lower().split("x")]
    a.w, a.h = (a.w // 16) * 16, (a.h // 16) * 16
    a.seed = a.seed if a.seed >= 0 else random.randint(0, 2**31)

    t0 = time.time()
    pid = post(HOST + "/prompt", {"prompt": build(a), "client_id": "dsh"})["prompt_id"]
    print("提交 %s | 参考图 %s | IPA权重 %.2f | LoRA %.2f"
          % (pid[:8], a.ref, a.ipa_weight, a.lora_strength), flush=True)

    while True:
        time.sleep(2)
        h = get(HOST + "/history/" + pid)
        if pid in h:
            if not h[pid].get("status", {}).get("completed"):
                continue
            for node in h[pid].get("outputs", {}).values():
                for img in node.get("images", []):
                    print("完成 %.0f 秒 -> %s" % (time.time() - t0,
                          os.path.join(OUT, img.get("subfolder", ""), img["filename"])))
            return
        if time.time() - t0 > 900:
            print("超时")
            return


if __name__ == "__main__":
    main()
