# -*- coding: utf-8 -*-
"""
中文 → 英文 tag 转换

Illustrious 只认英文，中文写进提示词不报错但完全不起作用。
这个脚本把中文描述拆成词，按表换成 tag，再拼成能用的提示词。

用法：
  python cn2tag.py "她坐在沙发上，穿着一件红毛衣，逆光，微笑"
  python cn2tag.py "厨房，傍晚，碗面" --base      # 只输出转换结果，不接出图
"""
import argparse
import re
import sys

# 词表：长词排前面，避免「毛衣」先吃掉「红毛衣」
TABLE = {
    # ---- 服装 ----
    "红色高领毛衣": "red turtleneck sweater",
    "高领毛衣": "turtleneck sweater",
    "红色毛衣": "red sweater",
    "红毛衣": "red sweater",
    "白毛衣": "white sweater",
    "黑毛衣": "black sweater",
    "灰毛衣": "grey sweater",
    "毛衣": "sweater",
    "白吊带": "white camisole",
    "吊带": "camisole",
    "T恤": "t-shirt",
    "白衬衫": "white shirt",
    "衬衫": "shirt",
    "牛仔短裤": "denim shorts",
    "牛仔裤": "jeans",
    "百褶裙": "pleated skirt",
    "长裙": "long skirt",
    "短裙": "skirt",
    "连衣裙": "dress",
    "睡衣": "pajamas",
    "浴衣": "yukata",
    "水手服": "sailor uniform",
    "校服": "school uniform",
    "西装": "suit",
    "外套": "jacket",
    "大衣": "coat",
    "卫衣": "hoodie",
    "运动服": "tracksuit",
    "泳装": "swimsuit",
    "毛线帽": "knit hat",
    "帽子": "hat",
    "围巾": "scarf",
    "眼镜": "glasses",
    "项圈": "choker",
    "光脚": "barefoot",
    "赤脚": "barefoot",
    "袜子": "socks",
    "高跟鞋": "high heels",
    "运动鞋": "sneakers",

    # ---- 动作 ----
    "坐在沙发上": "sitting on sofa",
    "坐在床上": "sitting on bed",
    "坐在椅子上": "sitting on chair",
    "躺在沙发上": "lying on sofa",
    "躺在床上": "lying on bed",
    "趴在桌上": "lying on table",
    "站着": "standing",
    "靠在墙边": "leaning against wall",
    "抱着膝盖": "hugging own knees",
    "抱着枕头": "holding pillow",
    "回头看": "looking back",
    "回头": "looking back",
    "伸懒腰": "stretching",
    "打哈欠": "yawning",
    "看书": "reading book",
    "玩手机": "using phone",
    "喝咖啡": "drinking coffee",
    "做饭": "cooking",
    "洗碗": "washing dishes",
    "梳头发": "brushing hair",
    "撩头发": "hand in hair",
    "双手抱胸": "crossed arms",
    "招手": "waving hand",
    "指着": "pointing",
    "睡着了": "sleeping",
    "刚睡醒": "just woke up",
    "换衣服": "changing clothes",

    # ---- 场景 ----
    "客厅": "living room",
    "卧室": "bedroom",
    "厨房": "kitchen",
    "浴室": "bathroom",
    "玄关": "entrance hall",
    "阳台": "balcony",
    "走廊": "hallway",
    "餐厅": "dining room",
    "咖啡馆": "cafe",
    "教室": "classroom",
    "办公室": "office",
    "街道": "street",
    "公园": "park",
    "车站": "train station",
    "便利店": "convenience store",
    "床上": "on bed",
    "沙发上": "on sofa",
    "地毯上": "on rug",
    "窗边": "by window",
    "门口": "at doorway",
    "餐桌前": "at dining table",

    # ---- 表情 / 状态 ----
    "微笑": "smile",
    "大笑": "laughing",
    "坏笑": "smirk",
    "害羞": "blush",
    "脸红": "blushing",
    "生气": "angry",
    "皱眉": "frown",
    "难过": "sad",
    "哭": "crying",
    "惊讶": "surprised",
    "困": "sleepy",
    "无聊": "bored",
    "得意": "confident",
    "冷淡": "expressionless",
    "面无表情": "expressionless",
    "闭眼": "closed eyes",
    "看向观众": "looking at viewer",
    "看向别处": "looking away",

    # ---- 光线 ----
    "逆光": "backlight",
    "暖光": "warm lighting",
    "冷光": "cold lighting",
    "夕阳光": "sunset light",
    "晨光": "morning light",
    "月光": "moonlight",
    "阳光": "sunlight",
    "灯光": "lamplight",
    "昏暗": "dim lighting",
    "明亮": "bright lighting",

    # ---- 视角 / 构图 ----
    "侧面": "from side",
    "正面": "front view",
    "背面": "from behind",
    "俯视": "from above",
    "仰视": "from below",
    "特写": "close-up",
    "半身": "upper body",
    "全身": "full body",
    "远景": "wide shot",
    "倾斜构图": "dutch angle",

    # ---- 物件 ----
    "碗面": "bowl of noodles",
    "咖啡杯": "coffee cup",
    "马克杯": "mug",
    "书": "book",
    "手机": "phone",
    "枕头": "pillow",
    "被子": "blanket",
    "窗帘": "curtains",
    "台灯": "table lamp",
    "电视": "tv",
    "樱花": "cherry blossoms",
    "飘落的樱花": "falling cherry blossom petals",
    "花瓣": "petals",
    "花": "flowers",
    "猫": "cat",
    "雨": "rain",
    "雪": "snow",

    # ---- 时间 ----
    "清晨": "early morning",
    "早上": "morning",
    "中午": "noon",
    "下午": "afternoon",
    "傍晚": "evening",
    "晚上": "night",
    "深夜": "late night",
}

# 角色固定开头（触发词 + 特征），可以自己改
CHARACTER = "ryou, 1girl, amber eyes, black choker"
QUALITY = "masterpiece, best quality, highly detailed, anime style"

# 按长度倒序，长的先匹配
SORTED = sorted(TABLE.keys(), key=len, reverse=True)


def convert(text):
    """把中文描述切成 tag，返回 (匹配到的tag列表, 没认出来的片段)"""
    hits = []
    leftover = text
    for cn in SORTED:
        if cn in leftover:
            hits.append(TABLE[cn])
            leftover = leftover.replace(cn, " ")
    # 清掉标点和空白
    leftover = re.sub(r"[，,。.、；;！!？?\s]+", " ", leftover).strip()
    return hits, leftover


def main():
    p = argparse.ArgumentParser()
    p.add_argument("text", help="中文描述")
    p.add_argument("--base", action="store_true", help="只输出转换结果")
    p.add_argument("--no-character", action="store_true", help="不加角色触发词")
    p.add_argument("--no-quality", action="store_true", help="不加画质词")
    a = p.parse_args()

    hits, leftover = convert(a.text)

    parts = []
    if not a.no_character:
        parts.append(CHARACTER)
    parts.extend(hits)
    if not a.no_quality:
        parts.append(QUALITY)

    prompt = ", ".join(parts)

    print()
    print("  中文原文 ：", a.text)
    print("  认出来的 ：", ", ".join(hits) if hits else "（一个都没有）")
    if leftover:
        print("  没认出来 ：", leftover, " ← 这部分不会生效，需要手动换成英文")
    print()
    print("  最终提示词：")
    print("  " + prompt)
    print()

    if not a.base:
        print("  直接出图：")
        print('  python gen_lora.py "%s" --lora ryou_v2_1024-000009.safetensors --strength 1.0' % prompt)
        print()


if __name__ == "__main__":
    main()
