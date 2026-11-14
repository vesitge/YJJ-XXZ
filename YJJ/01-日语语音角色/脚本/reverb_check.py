# -*- coding: utf-8 -*-
"""环境筛选：给每个片段算「混响指数」，找出浴室、空房间、远距离拾音这类不适合作素材的段。

原理：
  干声（贴麦近讲）说完就断，能量掉得极快；
  浴室、瓷砖房、大厅会加一层拖尾，能量掉得慢。
  在同一批素材里比较「掉 20 dB 需要多久」，离群的就是有问题的。

  不需要绝对 RT60，只做相对比较——同一批素材同一个麦，可比性很好。

输出：环境筛选.json（每段的混响指数与排名）+ 控制台排行榜
"""
import os, sys, json, glob

import numpy as np
import soundfile as sf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEGDIR = os.path.join(ROOT, "工作", "片段")
OUT = os.path.join(ROOT, "工作", "环境筛选.json")


def decay_time(x, sr, drop_db=20.0, win=0.02, hop=0.01):
    """返回该片段「每 20dB 落尾需要多少毫秒」的中位数，以及样本数。"""
    w, h = int(sr * win), int(sr * hop)
    n = max(1, (len(x) - w) // h + 1)
    sq = x.astype(np.float64) ** 2
    c = np.concatenate(([0.0], np.cumsum(sq)))
    starts = np.arange(n) * h
    db = 10 * np.log10(np.maximum((c[starts + w] - c[starts]) / w, 1e-20))

    # 平滑，去掉单帧毛刺
    if len(db) > 5:
        k = np.ones(5) / 5
        db = np.convolve(db, k, mode="same")

    peak = float(np.percentile(db, 95))
    floor = float(np.percentile(db, 10))
    if peak - floor < 15:
        return None, 0                      # 没有可测的动态范围

    drops = []
    i = 0
    while i < len(db) - 1:
        # 找一个局部高点（说话的音节峰）
        if db[i] >= peak - 6 and db[i] >= db[i + 1]:
            target = db[i] - drop_db
            j = i
            while j + 1 < len(db) and db[j + 1] > target:
                j += 1
            if j > i and db[j + 1] <= target if j + 1 < len(db) else False:
                drops.append((j - i) * hop * 1000.0)   # 毫秒
            i = j + 1
        else:
            i += 1
    if not drops:
        return None, 0
    return float(np.median(drops)), len(drops)


def main():
    files = sorted(glob.glob(os.path.join(SEGDIR, "seg_*.wav")))
    if not files:
        print("没找到片段：%s" % SEGDIR)
        return 1

    rows = []
    for p in files:
        x, sr = sf.read(p, dtype="float32", always_2d=True)
        x = x.mean(axis=1)
        t, k = decay_time(x, sr)
        rows.append({"file": os.path.basename(p), "decay_ms": t, "n": k,
                     "dur": round(len(x) / sr, 2)})

    valid = [r for r in rows if r["decay_ms"] is not None]
    if not valid:
        print("所有片段都测不出衰减，检查素材电平。")
        return 1

    med = float(np.median([r["decay_ms"] for r in valid]))
    mad = float(np.median([abs(r["decay_ms"] - med) for r in valid])) or 1.0
    for r in rows:
        if r["decay_ms"] is None:
            r["score"] = None
            r["flag"] = "无法测量"
        else:
            z = (r["decay_ms"] - med) / (1.4826 * mad)
            r["score"] = round(z, 2)
            r["flag"] = "可疑" if z > 2.5 else ("偏湿" if z > 1.5 else "干声")

    rows.sort(key=lambda r: (r["score"] is None, -(r["score"] or 0)))

    print("=" * 74)
    print("  环境筛选 · 中位落尾时间 %.0f ms（同一批素材的相对比较）" % med)
    print("=" * 74)
    print("  %-14s %8s %8s %6s  %s" % ("片段", "落尾ms", "偏离", "时长", "判断"))
    print("  " + "-" * 70)
    for r in rows:
        s = "%+7.2f" % r["score"] if r["score"] is not None else "     ---"
        d = "%6.2f" % r["decay_ms"] if r["decay_ms"] else "   ---"
        print("  %-14s %8s %8s %5.1fs  %s" % (r["file"], d, s, r["dur"], r["flag"]))

    suspicious = [r for r in rows if r["flag"] == "可疑"]
    print()
    print("  可疑 %d 段 / 共 %d 段" % (len(suspicious), len(rows)))
    if suspicious:
        print("  这些建议先听一遍再决定，多半是浴室、空房间或远距离拾音。")

    json.dump({"median_ms": med, "rows": rows}, open(OUT, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n  明细 → %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
