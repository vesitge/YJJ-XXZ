# -*- coding: utf-8 -*-
"""把 50 张对比图拼成一张总览：5 行（版本）x 10 列（种子）"""
import os
from PIL import Image

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "ComfyUI_windows_portable-marduk191-v1.0", "ComfyUI", "output")

VERSIONS = ["ep03", "ep06", "ep09", "ep12", "ep15"]
SEEDS = [1001, 1002, 1003, 1004, 1005, 1006, 1007, 1008, 1009, 1010]
CW, CH = 160, 230
PAD = 4

W = len(SEEDS) * (CW + PAD) + PAD
H = len(VERSIONS) * (CH + PAD) + PAD

canvas = Image.new("RGB", (W, H), (24, 24, 28))
found = 0
for r, tag in enumerate(VERSIONS):
    for c, s in enumerate(SEEDS):
        p = os.path.join(OUT, "cmp_%s_%d_00001_.png" % (tag, s))
        if not os.path.exists(p):
            continue
        im = Image.open(p).convert("RGB")
        im = im.resize((CW, CH), Image.LANCZOS)
        canvas.paste(im, (PAD + c * (CW + PAD), PAD + r * (CH + PAD)))
        found += 1

dst = os.path.join(OUT, "对比总览.png")
canvas.save(dst)
print("拼了 %d 张 -> %s  (%dx%d)" % (found, dst, W, H))
