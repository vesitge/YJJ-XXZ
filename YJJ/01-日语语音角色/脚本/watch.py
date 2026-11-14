# -*- coding: utf-8 -*-
"""实时进度看板：每 2 秒刷新，显示当前阶段、百分比、已用时间和预计剩余。"""
import os, re, sys, time, json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, "工作")
STATUS = os.path.join(WORK, "prep_status.json")
PREPLOG = os.path.join(WORK, "asr.log")


def read(p):
    """按 BOM 猜编码。PowerShell 的 *> 重定向会写成 UTF-16LE，不能假定 UTF-8。"""
    try:
        b = open(p, "rb").read()
    except Exception:
        return ""
    if b[:2] in (b"\xff\xfe", b"\xfe\xff"):
        try:
            return b.decode("utf-16")
        except Exception:
            pass
    if b[:3] == b"\xef\xbb\xbf":
        return b[3:].decode("utf-8", "replace")
    try:
        return b.decode("utf-8")
    except Exception:
        return b.decode("utf-8", "replace")


def parse():
    """优先读 prep_status.json；没有就从日志里扒。返回 dict。"""
    st = {"stage": "等待中", "i": 0, "n": 0, "note": ""}
    if os.path.exists(STATUS):
        try:
            d = json.loads(read(STATUS))
            st.update({k: d.get(k, st[k]) for k in ("stage", "i", "n", "note")})
            st["updated"] = d.get("updated", 0)
        except Exception:
            pass
    # 日志兜底：抓「转写 12/69」
    log = read(PREPLOG)
    m = re.findall(r"转写 (\d+)/(\d+)", log)
    if m:
        st["stage"] = "ASR 转写"
        st["i"], st["n"] = int(m[-1][0]), int(m[-1][1])
    if "加载 ASR 模型" in log and not m:
        st["stage"] = "加载 ASR 模型"
    for kw, label in [("归一化", "归一化"), ("写出片段", "切分完成"), ("台本对齐", "台本对齐")]:
        if kw in log:
            st["note"] = label
    return st


def bar(pct, width=40):
    filled = int(round(width * pct / 100))
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def main():
    samples = []
    t0 = time.time()
    last_i = -1
    last_t = t0
    speed = 0.0
    while True:
        st = parse()
        now = time.time()
        i, n = st["i"], st["n"]
        if i != last_i and i > 0:
            dt = now - last_t
            if dt > 0:
                inst = (i - last_i) / dt
                speed = inst if speed == 0 else speed * 0.6 + inst * 0.4
            last_i, last_t = i, now

        os.system("cls")
        pct = (100.0 * i / n) if n else 0.0
        print("=" * 66)
        print("  GPT-SoVITS 素材处理 · 实时进度")
        print("=" * 66)
        print()
        print("  阶段:   %s" % st["stage"])
        if n:
            print("  进度:   %s %5.1f%%   (%d / %d)" % (bar(pct), pct, i, n))
        else:
            print("  进度:   %s" % bar(0))
        if speed > 0 and n > i:
            eta = (n - i) / speed
            print("  速度:   %.2f 条/秒    预计剩余 %d 分 %02d 秒" % (speed, eta // 60, eta % 60))
        print("  已用:   %d 分 %02d 秒" % ((now - t0) // 60, (now - t0) % 60))
        if st.get("note"):
            print("  备注:   %s" % st["note"])
        print()
        print("-" * 66)
        print("  这个窗口可以一直开着，它自己刷新。关掉不影响后台运行。")
        print("  Ctrl+C 退出。")
        print("-" * 66)
        time.sleep(2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
