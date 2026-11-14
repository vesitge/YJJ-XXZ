# -*- coding: utf-8 -*-
"""按 LRC 时间戳 + 日文台本切分（取代纯声学 VAD 切分）。

流程：
  1. 解码 → 单声道 → 全局归一化
  2. 解析 LRC 得到每个字幕行的起始时间，相邻两个起始时间之间就是一个窗口
  3. 整段跑一次 ASR，拿到带时间戳的识别结果
  4. 用动态规划把 ASR 结果与日文台本逐行对齐
  5. 每个 LRC 窗口内：收集落在里面的台本行，拼成该段的标注文本
  6. 窗口边界吸附到附近的能量最低点（静音），不硬砍在词中间
  7. 过短的窗口并到邻居，过长的在内部最低点切开
  8. 输出片段 + train.list + meta.json

用法：
    python tools/cut_by_lrc.py
"""
import os, sys, re, json, glob, subprocess, math

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import numpy as np
import soundfile as sf

import prep
from prep import (normalize, frame_db, read_text_any, clean_script_line,
                  norm_jp, align, set_status, log, _flush_status)

SRC = os.path.join(ROOT, "素材")
WORK = os.path.join(ROOT, "工作")
SEGDIR = os.path.join(WORK, "片段")
FFMPEG = os.path.join(ROOT, "bin", "ffmpeg.exe")
MODEL = os.path.join(ROOT, "models", "faster-whisper-large-v3-turbo")
NV = os.path.join(ROOT, ".venv", "Lib", "site-packages", "nvidia")


def add_cuda_dlls():
    for sub in ("cublas", "cudnn", "cuda_nvrtc"):
        p = os.path.join(NV, sub, "bin")
        if os.path.isdir(p):
            os.environ["PATH"] = p + os.pathsep + os.environ["PATH"]


def decode(path):
    """统一解码成 44.1k 单声道 float。mp3 走 ffmpeg 转 wav 再读。"""
    tmp = os.path.join(WORK, "_decode_tmp.wav")
    os.makedirs(WORK, exist_ok=True)
    cmd = [FFMPEG, "-y", "-v", "error", "-i", path, "-ac", "1", "-ar", "44100",
           "-c:a", "pcm_s16le", tmp]
    subprocess.run(cmd, check=True)
    x, sr = sf.read(tmp, dtype="float64")
    os.remove(tmp)
    return x, sr


def parse_lrc(path):
    txt, enc = read_text_any(path)
    out = []
    for line in txt.splitlines():
        m = re.match(r"\[(\d+):(\d+(?:\.\d+)?)\](.*)", line)
        if m:
            out.append((int(m.group(1)) * 60 + float(m.group(2)), m.group(3).strip()))
    return out, enc


def asr_whole(path):
    """整段识别，返回 [(start, end, text), ...]"""
    add_cuda_dlls()
    from faster_whisper import WhisperModel
    set_status("整段 ASR 识别", 0, 1, "加载模型")
    m = None
    for dev, ct in (("cuda", "int8_float16"), ("cpu", "int8")):
        try:
            m = WhisperModel(MODEL, device=dev, compute_type=ct)
            log("  ASR 使用 %s / %s" % (dev, ct))
            break
        except Exception as ex:
            log("  %s 不可用（%s）" % (dev, str(ex)[:70]))
    if m is None:
        raise RuntimeError("ASR 模型加载失败")

    set_status("整段 ASR 识别", 0, 1, "识别中（15 分钟音频，请稍候）")
    segs, info = m.transcribe(path, language="ja", beam_size=5,
                              vad_filter=True, vad_parameters={"min_silence_duration_ms": 300},
                              condition_on_previous_text=False)
    out = []
    total = info.duration or 1
    for s in segs:
        out.append((float(s.start), float(s.end), s.text.strip()))
        set_status("整段 ASR 识别", int(100 * s.end / total), 100, "识别到 %.1f / %.1f 秒" % (s.end, total))
    log("  识别出 %d 句，覆盖 %.1f 秒" % (len(out), out[-1][1] if out else 0))
    return out


def snap_to_silence(t, db, hop, win, radius=0.30):
    """把切点吸到附近能量最低处。"""
    lo = int(max(0, (t - radius - win / 2) / hop))
    hi = int(min(len(db), (t + radius - win / 2) / hop))
    if hi <= lo:
        return t
    return (lo + int(np.argmin(db[lo:hi]))) * hop + win / 2


def main():
    os.makedirs(SEGDIR, exist_ok=True)
    prep.STATUS = os.path.join(WORK, "prep_status.json")   # 让进度看板能读到
    set_status("启动", 0, 0, "扫描素材")
    # 清掉旧片段
    for f in glob.glob(os.path.join(SEGDIR, "seg_*.wav")):
        os.remove(f)

    audios = [p for p in glob.glob(os.path.join(SRC, "*")) if os.path.splitext(p)[1].lower() in (".mp3", ".wav", ".flac", ".m4a")]
    if not audios:
        print("素材目录没有音频"); return 1
    audio = sorted(audios)[-1]
    stem = os.path.splitext(audio)[0]
    lrcs = glob.glob(stem + ".lrc") or glob.glob(os.path.join(SRC, "*05*.lrc"))
    txts = glob.glob(stem + ".txt") or glob.glob(os.path.join(SRC, "*05*.txt"))
    if not lrcs or not txts:
        print("缺 lrc 或台本"); return 1
    lrc, txt = lrcs[0], txts[0]
    print("音频: %s" % os.path.basename(audio))
    print("字幕: %s" % os.path.basename(lrc))
    print("台本: %s" % os.path.basename(txt))

    set_status("解码", 0, 0, os.path.basename(audio))
    x, sr = decode(audio)
    dur = len(x) / sr
    log("解码完成 %.2f 分  %d Hz" % (dur / 60, sr))
    x, gain, clip = normalize(x)
    log("归一化 +%.2f dB  削波 %d" % (gain, clip))

    db, hop_n, win_n = frame_db(x, sr)
    hop_s, win_s = hop_n / sr, win_n / sr

    cues, enc = parse_lrc(lrc)
    cues = [c for c in cues if c[1]]
    log("LRC %d 行（%s），末行 %.1f 秒 / 音频 %.1f 秒" % (len(cues), enc, cues[-1][0], dur))
    # 去掉开头的标题行（时间 0 且内容像标题）
    if cues and cues[0][0] < 0.5:
        cues = cues[1:]
        log("  去掉标题行")

    script, senc = read_text_any(txt)
    script_lines = [clean_script_line(l) for l in script.splitlines()]
    script_lines = [l for l in script_lines if l]
    log("台本 %d 行（%s）" % (len(script_lines), senc))

    # 整段 ASR
    asr = asr_whole(audio)
    meta_tmp = [{"id": i + 1, "asr": t, "start": a, "dur": max(0.1, b - a)} for i, (a, b, t) in enumerate(asr)]
    mapping = align(meta_tmp, script_lines)
    hits = sum(1 for m in mapping if m)
    log("ASR→台本 对齐命中 %d / %d 句" % (hits, len(meta_tmp)))

    # ---- 每句台本行定位到时间（用 ASR 段的中点）
    line_time = {}
    for m, mp in zip(meta_tmp, mapping):
        if mp:
            line_time[mp["line"]] = (m["start"] + m["dur"] / 2)
    log("台本已定位 %d / %d 行" % (len(line_time), len(script_lines)))

    # ---- 切点 = 字幕起始时间 ∪ ASR 句边界，都是「句级」信号
    #      光靠字幕切太粗（一行盖好几句话），光靠 ASR 切会漏掉字幕的分行
    raw = [c[0] for c in cues]
    for (s, e, _t) in asr:
        raw.append(s); raw.append(e)
    raw = sorted(t for t in raw if 0.0 < t < dur)
    bounds = [0.0]
    for t in raw:
        if t - bounds[-1] >= 1.2:      # 太近的点不要，否则切出一堆碎片
            bounds.append(t)
    if dur - bounds[-1] > 0.8:
        bounds.append(dur)
    bounds = [snap_to_silence(b, db, hop_s, win_s, 0.25) for b in bounds]
    bounds[0] = 0.0
    log("切点 %d 个（字幕 %d + ASR %d）" % (len(bounds), len(cues), len(asr)))

    nwin = len(bounds) - 1

    def which_window(t):
        import bisect
        k = bisect.bisect_right(bounds, t) - 1
        return max(0, min(k, nwin - 1))

    # ---- 每一行都必须有归属：定位到的按时间进窗口，没定位到的跟在前一行后面
    from collections import defaultdict
    win_lines = defaultdict(list)
    last_w = 0
    for j in range(len(script_lines)):
        if j in line_time:
            w = which_window(line_time[j])
            last_w = w
        else:
            w = last_w
        win_lines[w].append(j)

    def chunk(seq, n):
        n = max(1, min(n, len(seq)))
        out, step = [], len(seq) / float(n)
        for i in range(n):
            a, b = int(round(i * step)), int(round((i + 1) * step))
            out.append(seq[a:b])
        return [c for c in out if c]

    # ---- 逐窗口生成片段
    set_status("按时间戳切分", 0, nwin, "")
    segs = []          # [start, end, text]
    for k in range(nwin):
        a, b = bounds[k], bounds[k + 1]
        if b - a < 0.2:
            continue
        lines = sorted(win_lines.get(k, []))
        asr_txt = "".join(t for (s, e, t) in asr if a <= (s + e) / 2 < b)
        d = b - a

        if not lines:
            # 没有台本行：纯环境音就丢掉，有识别文本才保留
            if asr_txt.strip():
                segs.append([a, b, asr_txt.strip()])
            continue

        # 窗口太长时按行数切块，块与块之间吸附到静音
        n_parts = int(min(max(1, math.ceil(d / 9.0)), len(lines))) if d > 12.0 else 1
        if n_parts <= 1:
            segs.append([a, b, "".join(script_lines[j] for j in lines)])
            continue

        cuts = [a]
        for i in range(1, n_parts):
            cuts.append(snap_to_silence(a + d * i / n_parts, db, hop_s, win_s, radius=1.2))
        cuts.append(b)
        for i, part in enumerate(chunk(lines, n_parts)):
            if i + 1 < len(cuts):
                segs.append([cuts[i], cuts[i + 1],
                             "".join(script_lines[j] for j in part)])
        if k % 20 == 0:
            set_status("按时间戳切分", k, len(cues), "")
    log("初切 %d 段" % len(segs))

    # ---- 合并过短的：只有短于 2 秒、且并完不超过 8 秒才并
    merged = []
    for a, b, t in segs:
        if merged and (b - a) < 2.0 and (b - merged[-1][0]) <= 8.0:
            merged[-1][1] = b
            merged[-1][2] += t
        else:
            merged.append([a, b, t])

    # ---- 过长的按字数比例切开，切点吸附静音
    def split_text(t, n):
        import re as _re
        if n <= 1 or not t:
            return [t] + [""] * (n - 1)
        parts = _re.split(r"(?<=[。．！？!?、])", t)
        parts = [p for p in parts if p]
        if len(parts) < n:
            k = max(1, len(t) // n)
            parts = [t[i:i + k] for i in range(0, len(t), k)]
        out, step = [], len(parts) / float(n)
        for i in range(n):
            a2, b2 = int(round(i * step)), int(round((i + 1) * step))
            out.append("".join(parts[a2:b2]))
        return out

    final = []
    for a, b, t in merged:
        d = b - a
        if d <= 10.0:
            final.append([a, b, t]); continue
        n = int(math.ceil(d / 8.0))
        cuts = [a]
        for i in range(1, n):
            cuts.append(snap_to_silence(a + d * i / n, db, hop_s, win_s, radius=1.0))
        cuts.append(b)
        for i, piece in enumerate(split_text(t, n)):
            if i + 1 < len(cuts) and cuts[i + 1] - cuts[i] >= 1.0:
                final.append([cuts[i], cuts[i + 1], piece])

    # ---- 裁掉每段头尾的静音，只留说话部分
    def trim(a, b, pad=0.06):
        i0 = max(0, int(a / hop_s))
        i1 = min(len(db), int(b / hop_s))
        if i1 - i0 < 3:
            return a, b
        local = db[i0:i1]
        thr = max(float(np.percentile(local, 15)) + 8.0, float(np.max(local)) - 26.0)
        idx = np.where(local > thr)[0]
        if len(idx) == 0:
            return a, b
        na = i0 * hop_s + idx[0] * hop_s - pad
        nb = i0 * hop_s + idx[-1] * hop_s + win_s + pad
        na = max(a, na); nb = min(b, nb)
        return (na, nb) if nb - na >= 0.6 else (a, b)

    trimmed = []
    for a, b, t in final:
        na, nb = trim(a, b)
        trimmed.append([na, nb, t])
    final = trimmed

    # ---- 给每段设文本字数上限：每秒最多 7.5 个字
    def cap_text(t, d):
        lim = max(4, int(d * 7.5))
        core = re.sub(r"\s", "", t or "")
        if len(core) <= lim:
            return t
        cut = 0
        for m2 in re.finditer(r"[。．！？!?、…]", t):
            if m2.end() <= lim:
                cut = m2.end()
            else:
                break
        return t[:cut] if cut >= 4 else t[:lim]

    final = [[a, b, cap_text(t, max(0.8, b - a))] for a, b, t in final]

    # ---- 丢掉「没有可训练文本」的段：核心字不足 3 个，或每秒字数低得不正常
    def core_len(t):
        return len(re.sub(r"[\s、。,.!?！？…‥・「」『』（）()【】\-—ー~〜ｗ]", "", t or ""))

    dropped_tiny = dropped_slow = 0
    keep = []
    for a, b, t in final:
        c = core_len(t)
        d = b - a
        if c < 3:
            dropped_tiny += 1
            continue
        if d > 0 and c / d < 1.2:
            dropped_slow += 1
            continue
        keep.append([a, b, t])
    final = keep
    log("剔除无文本段 %d 个、字数过稀段 %d 个" % (dropped_tiny, dropped_slow))

    # 吸附边界并落盘
    meta = []
    for i, (a, b, t) in enumerate(final, 1):
        a2 = snap_to_silence(a, db, hop_s, win_s)
        b2 = snap_to_silence(b, db, hop_s, win_s)
        if b2 - a2 < 1.2:
            a2, b2 = a, b
        a2 = max(0.0, a2 - 0.05)
        b2 = min(dur, b2 + 0.05)
        clip = x[int(a2 * sr):int(b2 * sr)]
        if len(clip) < int(0.5 * sr):
            continue
        name = "seg_%04d.wav" % len(meta)
        sf.write(os.path.join(SEGDIR, name), clip.astype("float32"), sr, subtype="PCM_16")
        meta.append({"id": len(meta) + 1, "file": name, "start": round(a2, 2),
                     "dur": round(len(clip) / sr, 2), "text": t, "_script": script_lines})

    durs = sorted(m["dur"] for m in meta)
    log("最终 %d 段，段长 最短 %.2f / 中位 %.2f / 最长 %.2f 秒，有声 %.1f 分"
        % (len(meta), durs[0], durs[len(durs) // 2], durs[-1], sum(durs) / 60))
    empty = sum(1 for m in meta if not m["text"])
    log("无文本段 %d 个（多半是环境音/喘息，校对时剔除）" % empty)

    json.dump(meta, open(os.path.join(WORK, "meta.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    with open(os.path.join(WORK, "train.list"), "w", encoding="utf-8") as f:
        for m in meta:
            f.write("%s|speaker|ja|%s\n" % (os.path.join(SEGDIR, m["file"]), m["text"]))
    log("meta.json / train.list 已写入")
    set_status("切分完成", 1, 1, "%d 段" % len(meta))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        import traceback; traceback.print_exc(); sys.exit(1)
