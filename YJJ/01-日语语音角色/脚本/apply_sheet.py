# -*- coding: utf-8 -*-
"""把校对表导出的结果落地成最终训练清单。

用法：
    python tools/apply_sheet.py
输入：工作/校对结果.json
输出：工作/train.list（最终版）、工作/训练集统计.txt
"""
import os, sys, json, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, "工作")
SRC = os.path.join(WORK, "校对结果.json")
SRC_FIXED = os.path.join(WORK, "校对结果-修正.json")
TRAIN = os.path.join(WORK, "train.list")
STAT = os.path.join(WORK, "训练集统计.txt")
SEGDIR = os.path.join(WORK, "片段")


def main():
    src = SRC_FIXED if os.path.exists(SRC_FIXED) else SRC
    if not os.path.exists(src):
        print("找不到 %s" % src)
        print("请先在校对表里点「导出结果」，把 json 放到 工作 目录下。")
        return 1
    print("读取：%s" % os.path.basename(src))

    data = json.load(open(src, encoding="utf-8"))
    kept, missing, empty = [], [], []
    for r in data:
        if r.get("keep") is False:
            continue
        text = (r.get("text") or "").strip()
        if not text:
            empty.append(r["id"])
            continue
        path = os.path.join(SEGDIR, r["file"])
        if not os.path.exists(path):
            missing.append(r["file"])
            continue
        kept.append({"id": r["id"], "file": r["file"], "dur": r["dur"], "text": text})

    kept.sort(key=lambda x: x["id"])
    with open(TRAIN, "w", encoding="utf-8") as f:
        for r in kept:
            f.write("%s|speaker|ja|%s\n" % (os.path.join(SEGDIR, r["file"]), r["text"]))

    total = sum(r["dur"] for r in kept)
    chars = sum(len(r["text"]) for r in kept)
    durs = sorted(r["dur"] for r in kept)
    lines = []
    lines.append("训练集统计")
    lines.append("=" * 44)
    lines.append("条目数        %d" % len(kept))
    lines.append("总时长        %.1f 秒（%.1f 分钟）" % (total, total / 60))
    lines.append("总字数        %d" % chars)
    if durs:
        lines.append("段长 最短     %.2f 秒" % durs[0])
        lines.append("段长 中位     %.2f 秒" % durs[len(durs) // 2])
        lines.append("段长 最长     %.2f 秒" % durs[-1])
        lines.append("平均段长      %.2f 秒" % (total / len(durs)))
    lines.append("")
    lines.append("排除：未勾保留 %d 条" % sum(1 for r in data if r.get("keep") is False))
    if empty:
        lines.append("排除：空文本   %d 条 %s" % (len(empty), empty[:10]))
    if missing:
        lines.append("排除：文件缺失 %d 条 %s" % (len(missing), missing[:10]))
    txt = "\n".join(lines)
    open(STAT, "w", encoding="utf-8").write(txt + "\n")
    print(txt)
    print()
    print("训练清单 → %s" % TRAIN)
    return 0


if __name__ == "__main__":
    sys.exit(main())
