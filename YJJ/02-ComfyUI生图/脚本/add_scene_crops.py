# -*- coding: utf-8 -*-
"""
补两张「她在场景里」的训练图。
前一版训练集全是白底立绘，模型不知道她在房间里怎么站，生成时只能退回通用脸。
"""
import os
from PIL import Image

SRC = r"D:\HarnessAI\work\素材"
DST = r"D:\HarnessAI\work\生图环境\dataset\1_ryou"
os.makedirs(DST, exist_ok=True)
SIZE = 1024

JOBS = [
    # 2400x1800 横图，人物在中偏右
    ("07.だらパコルームカノジョ イラスト.png", [
        ("ryou_room_bust.png", (0.33, 0.00, 0.80, 0.62)),   # 半身，带沙发窗户
        ("ryou_room_face.png", (0.40, 0.00, 0.70, 0.40)),   # 脸
    ]),
]

CAPTIONS = {
    "ryou_room_bust": "ryou, 1girl, amber eyes, black choker, short black hair, orange hair tips, yellow off-shoulder shirt, white jacket, black shorts, upper body, standing, relaxed",
    "ryou_room_face": "ryou, 1girl, amber eyes, black choker, short black hair, orange hair tips, smiling, close-up, face focus, looking at viewer",
}


def to_rgb(im):
    if im.mode in ("RGBA", "LA"):
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[-1])
        return bg
    return im.convert("RGB")


def main():
    for fname, cuts in JOBS:
        p = os.path.join(SRC, fname)
        if not os.path.exists(p):
            print("[缺]", fname)
            continue
        im = to_rgb(Image.open(p))
        w, h = im.size
        print("[源] %s %dx%d" % (fname, w, h))
        for out, box in cuts:
            l, t, r, b = box
            c = im.crop((int(l * w), int(t * h), int(r * w), int(b * h)))
            c = c.resize((SIZE, SIZE), Image.LANCZOS)
            c.save(os.path.join(DST, out), "PNG")
            cap = CAPTIONS.get(out.split(".")[0])
            if cap:
                with open(os.path.join(DST, out.replace(".png", ".txt")), "w", encoding="utf-8") as f:
                    f.write(cap)
            print("  ->", out, "| caption:", cap)

    n = len([f for f in os.listdir(DST) if f.endswith(".png")])
    print("\n训练集现在 %d 张" % n)


if __name__ == "__main__":
    main()
