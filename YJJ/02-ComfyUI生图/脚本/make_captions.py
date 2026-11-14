# -*- coding: utf-8 -*-
"""
给训练集写 caption。
规则：每张只写角色特征 + 构图 + 服装，不写背景（训练图是白底，
写了背景 LoRA 会以为她总站在白墙前面）。

触发词统一用 ryou，放在最前面。
"""
import os

DIR = r"D:\HarnessAI\work\生图环境\dataset\img"

# 核心身份特征，所有图共用，放在最前（训练时用 --keep_tokens 保住这几句不被截断）
CORE = "ryou, 1girl, amber eyes, black choker"

LONG_HAIR = "long grey brown hair, ponytail, hair ornament"
SHORT_HAIR_DARK = "short black hair, orange hair tips"
SHORT_HAIR_GREY = "short grey brown hair, ahoge"

CAPTIONS = {
    # 立绘（长发马尾）
    "ryou_stand_face":  (LONG_HAIR, "close-up, face focus, looking at viewer, white camisole"),
    "ryou_stand_bust":  (LONG_HAIR, "upper body, white camisole, denim shorts"),
    "ryou_stand_body":  (LONG_HAIR, "full body, standing, white camisole, denim shorts, pink shoes"),

    # 私服（黑短发）
    "ryou_casual_face": (SHORT_HAIR_DARK, "close-up, face focus, looking at viewer"),
    "ryou_casual_bust": (SHORT_HAIR_DARK, "upper body, yellow t-shirt, white jacket, black shorts"),
    "ryou_casual_full": (SHORT_HAIR_DARK, "full body, standing, yellow t-shirt, black shorts, white jacket, sneakers"),

    # 水着
    "ryou_swim_face":   (SHORT_HAIR_DARK, "close-up, face focus, looking at viewer"),
    "ryou_swim_bust":   (SHORT_HAIR_DARK, "upper body, swimsuit"),
    "ryou_swim_full":   (SHORT_HAIR_DARK, "full body, standing, swimsuit"),

    # コスプレ
    "ryou_cos_face":    (SHORT_HAIR_DARK, "close-up, face focus, looking at viewer"),
    "ryou_cos_bust":    (SHORT_HAIR_DARK, "upper body, cosplay outfit"),
    "ryou_cos_full":    (SHORT_HAIR_DARK, "full body, standing, cosplay outfit"),

    # バニーガール
    "ryou_bunny_face":  (SHORT_HAIR_DARK, "close-up, face focus, looking at viewer"),
    "ryou_bunny_bust":  (SHORT_HAIR_DARK, "upper body, bunny girl suit, rabbit ears"),
    "ryou_bunny_full":  (SHORT_HAIR_DARK, "full body, standing, bunny girl suit, rabbit ears"),

    # 三套服装设计稿（灰棕短发）
    "ryou_design_a":    (SHORT_HAIR_GREY, "upper body, red tank top, ripped jeans, tan jacket, smirk"),
    "ryou_design_b":    (SHORT_HAIR_GREY, "upper body, black uniform, orange necktie, short hair"),
    "ryou_design_c":    (SHORT_HAIR_GREY, "upper body, white blouse, plaid long skirt"),

    # 其余角色图
    "ryou_char02":      (SHORT_HAIR_GREY, "upper body, looking at viewer"),
    "ryou_char03":      (SHORT_HAIR_GREY, "upper body, looking at viewer"),
}

def main():
    n = 0
    for name, (hair, rest) in CAPTIONS.items():
        png = os.path.join(DIR, name + ".png")
        if not os.path.exists(png):
            print("[缺图]", name)
            continue
        text = "%s, %s, %s" % (CORE, hair, rest)
        with open(os.path.join(DIR, name + ".txt"), "w", encoding="utf-8") as f:
            f.write(text)
        print("  %-24s %s" % (name, text))
        n += 1
    print("\n写好 %d 条 caption" % n)

    # 触发词字数：ryou, 1girl, amber eyes, black choker, <发型> —— 训练时 keep_tokens 设 6
    print("建议 --keep_tokens 6")


if __name__ == "__main__":
    main()
