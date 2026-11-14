# -*- coding: utf-8 -*-
"""IWAO 画风 x 角色版本，3x3 总览"""
import os
from PIL import Image

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "ComfyUI_windows_portable-marduk191-v1.0", "ComfyUI", "output")

VERSIONS = ["ep09", "ep12", "ep15"]
SEEDS = [1001, 1002, 1003]
CW, CH = 300, 438
PAD = 5

W = len(SEEDS) * (CW + PAD) + PAD
H = len(VERSIONS) * (CH + PAD) + PAD
canvas = Image.new("RGB", (W, H), (24, 24, 28))

n = 0
for r, tag in enumerate(VERSIONS):
    for c, s in enumerate(SEEDS):
        p = os.path.join(OUT, "iwao_%s_%d_00001_.png" % (tag, s))
        if not os.path.exists(p):
            print("缺:", p)
            continue
        im = Image.open(p).convert("RGB").resize((CW, CH), Image.LANCZOS)
        canvas.paste(im, (PAD + c * (CW + PAD), PAD + r * (CH + PAD)))
        n += 1

dst = os.path.join(OUT, "IWAO总览.png")
canvas.save(dst)
print("拼了 %d 张 -> %s (%dx%d)" % (n, dst, W, H))
