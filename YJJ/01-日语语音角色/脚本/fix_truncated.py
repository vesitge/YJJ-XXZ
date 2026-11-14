# -*- coding: utf-8 -*-
"""修回被字数上限截断的标注文本。

之前 cap_text() 在没有标点可切时会硬截到字数上限，结果把词砍断
（「甘いものだと濃厚チョコミルクパ」这种）。
砍断的文本会教错误音素，比长度不匹配更伤——这里一律还原成台本原句。

用法：python tools/fix_truncated.py [剪辑结果.json]
"""
import os, sys, json, shutil, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, "工作")
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(WORK, "校对结果.json")


def load_script():
    cands = glob.glob(os.path.join(ROOT, "素材", "*.txt"))
    if not cands:
        raise SystemExit("找不到台本")
    raw = open(cands[-1], "rb").read()
    for enc in ("utf-8-sig", "cp932", "utf-8"):
        try:
            txt = raw.decode(enc)
            break
        except Exception:
            continue
    return [l.strip() for l in txt.splitlines() if l.strip()]


def main():
    data = json.load(open(SRC, encoding="utf-8"))
    lines = load_script()
    out = os.path.join(WORK, "校对结果-修正.json")

    fixed = 0
    for r in data:
        t = (r.get("text") or "").strip()
        if not t or r.get("keep") is False:
            continue
        for L in lines:
            if len(t) < len(L) and L.startswith(t) and len(t) >= 4:
                r["text"] = L
                r["was_truncated"] = True
                fixed += 1
                break

    json.dump(data, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("还原被截断的标注：%d 条" % fixed)
    print("已另存为：%s（原始导出文件不动）" % os.path.basename(out))
    print("接着跑 tools/apply_sheet.py，它会优先读这份修正版")
    return 0


if __name__ == "__main__":
    sys.exit(main())
