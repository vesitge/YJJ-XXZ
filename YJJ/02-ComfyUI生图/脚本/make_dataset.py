# -*- coding: utf-8 -*-
"""
从素材里裁训练集。
透明底统一压白底，输出 1024x1024。
裁错了没关系，重跑一次覆盖。
"""
import os
from PIL import Image

SRC = r"D:\HarnessAI\work\素材"
DST = r"D:\HarnessAI\work\生图环境\dataset\img"
os.makedirs(DST, exist_ok=True)

SIZE = 1024


def to_rgb(im):
    """透明底压白底"""
    if im.mode in ("RGBA", "LA"):
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[-1])
        return bg
    return im.convert("RGB")


def crop_box(im, box, out):
    """box 用相对坐标 (l, t, r, b)"""
    w, h = im.size
    l, t, r, b = box
    c = im.crop((int(l * w), int(t * h), int(r * w), int(b * h)))
    c = c.resize((SIZE, SIZE), Image.LANCZOS)
    c.save(os.path.join(DST, out), "PNG")
    print("  ->", out, c.size)


# 每张源图裁几刀，用相对坐标，方便调
JOBS = [
    # 全身立绘（长发马尾）1346x3086
    ("夏城涼.png", [
        ("ryou_stand_face.png",  (0.10, 0.02, 0.95, 0.30)),
        ("ryou_stand_bust.png",  (0.08, 0.12, 0.98, 0.48)),
        ("ryou_stand_body.png",  (0.05, 0.02, 1.00, 0.98)),
    ]),
    # 服装差分 3240x5760 —— 每套裁头肩 + 上半身
    ("1.私服.png", [
        ("ryou_casual_face.png", (0.30, 0.03, 0.72, 0.20)),
        ("ryou_casual_bust.png", (0.22, 0.08, 0.80, 0.42)),
        ("ryou_casual_full.png", (0.10, 0.02, 0.92, 0.98)),
    ]),
    ("2.水着.png", [
        ("ryou_swim_face.png",   (0.30, 0.03, 0.72, 0.20)),
        ("ryou_swim_bust.png",   (0.22, 0.08, 0.80, 0.42)),
        ("ryou_swim_full.png",   (0.10, 0.02, 0.92, 0.98)),
    ]),
    ("3.コスプレ.png", [
        ("ryou_cos_face.png",    (0.30, 0.03, 0.72, 0.20)),
        ("ryou_cos_bust.png",    (0.22, 0.08, 0.80, 0.42)),
        ("ryou_cos_full.png",    (0.10, 0.02, 0.92, 0.98)),
    ]),
    ("4.バニーガール.png", [
        ("ryou_bunny_face.png",  (0.30, 0.03, 0.72, 0.20)),
        ("ryou_bunny_bust.png",  (0.22, 0.08, 0.80, 0.42)),
        ("ryou_bunny_full.png",  (0.10, 0.02, 0.92, 0.98)),
    ]),
    # 三套服装设计稿 2479x1756，三个竖条各裁上半身
    ("07.キャラクターデザイン.png", [
        ("ryou_design_a.png",    (0.02, 0.02, 0.32, 0.62)),
        ("ryou_design_b.png",    (0.35, 0.02, 0.65, 0.62)),
        ("ryou_design_c.png",    (0.67, 0.02, 0.99, 0.62)),
    ]),
    # 其余角色图
    ("02.Character.png", [
        ("ryou_char02.png",      (0.0, 0.0, 1.0, 1.0)),
    ]),
    ("03.Character.png", [
        ("ryou_char03.png",      (0.0, 0.0, 1.0, 1.0)),
    ]),
]


def main():
    for fname, cuts in JOBS:
        path = os.path.join(SRC, fname)
        if not os.path.exists(path):
            print("[缺] " + fname)
            continue
        im = to_rgb(Image.open(path))
        print("[源] %s  %dx%d" % (fname, im.size[0], im.size[1]))
        for out, box in cuts:
            crop_box(im, box, out)
    n = len([f for f in os.listdir(DST) if f.endswith(".png")])
    print("\n共 %d 张训练图 -> %s" % (n, DST))


if __name__ == "__main__":
    main()
