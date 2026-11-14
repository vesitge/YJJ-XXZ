# -*- coding: utf-8 -*-
"""
素材预处理：归一化 → 静音切分 → ASR 转写 → 与台本对齐 → 产出训练清单

用法：
    python 预处理.py                      # 用默认路径，跑全流程
    python 预处理.py --skip-asr           # 只切分，不转写
    python 预处理.py --device cuda        # 有 CUDA 就快很多

设计要点：
  * 全局归一化，逐段不做 —— 保持说话人自己的动态，也避免把各段底噪抬起来
  * 切点吸附在静音处，段长控制在 3~10 秒
  * 文本优先用台本（100% 准确），用 ASR 结果做对齐和校验
"""
import os, sys, re, json, math, argparse, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEF_SRC = os.path.join(ROOT, "素材")
DEF_OUT = os.path.join(ROOT, "工作")

LOG = []
STATUS = None          # 由 main() 设定：进度看板读取的 json 路径

def log(msg=""):
    print(msg, flush=True)
    LOG.append(str(msg))
    _flush_status()

_STATUS = {"stage": "启动", "i": 0, "n": 0, "note": ""}

def set_status(stage, i=0, n=0, note=""):
    """更新进度，供 看进度.bat 实时读取。"""
    _STATUS.update({"stage": stage, "i": i, "n": n, "note": note})
    _flush_status()

def _flush_status():
    if not STATUS:
        return
    try:
        import time
        d = dict(_STATUS)
        d["updated"] = time.time()
        tmp = STATUS + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
        os.replace(tmp, STATUS)
    except Exception:
        pass

# ---------------------------------------------------------------- 工具

def read_text_any(path):
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "utf-8", "cp932", "shift_jis", "gbk", "utf-16"):
        try:
            return raw.decode(enc), enc
        except Exception:
            continue
    return raw.decode("utf-8", "replace"), "utf-8/replace"


BAD_CHARS = re.compile(r"[ｗwＷ]{2,}|//+|♪|☆|★|（笑）|\(笑\)")

def clean_script_line(s):
    s = s.replace("\u3000", " ")
    s = BAD_CHARS.sub("", s)
    s = re.sub(r"[ \t]+", " ", s).strip()
    return s

def load_script(path):
    txt, enc = read_text_any(path)
    lines = [clean_script_line(l) for l in txt.splitlines()]
    lines = [l for l in lines if l]
    log("台本 %s  (%s)  有效行 %d" % (os.path.basename(path), enc, len(lines)))
    return lines

def find_pairs(src):
    out = []
    for f in sorted(os.listdir(src)):
        if not f.lower().endswith((".wav", ".mp3", ".flac", ".m4a")):
            continue
        stem = os.path.splitext(f)[0]
        cand_txt = [x for x in os.listdir(src) if x.lower().endswith(".txt")
                    and (stem.startswith(os.path.splitext(x)[0]) or os.path.splitext(x)[0].startswith(stem.split(".")[0]))]
        out.append((os.path.join(src, f), os.path.join(src, cand_txt[0]) if cand_txt else None))
    return out

# ---------------------------------------------------------------- 音频

def load_audio(path):
    import soundfile as sf
    import numpy as np
    data, sr = sf.read(path, always_2d=True, dtype="float64")
    mono = data.mean(axis=1)
    log("载入 %s  %.2f s  %d Hz  %d ch" % (os.path.basename(path), len(mono)/sr, sr, data.shape[1]))
    return mono, sr

def normalize(mono, target_peak=0.89):
    import numpy as np
    peak = float(np.max(np.abs(mono))) if len(mono) else 0.0
    if peak <= 1e-9:
        return mono, 0.0, 0
    clip = int(np.sum(np.abs(mono) >= 0.999))
    gain = target_peak / peak
    return mono * gain, 20*math.log10(gain), clip

def frame_db(mono, sr, win=0.03, hop=0.01):
    """返回 (每帧 dBFS, 帧移采样数, 窗长采样数)。
    用累加和算滑窗均方，避免构建 n×w 的巨大索引矩阵。"""
    import numpy as np
    w, h = int(sr*win), int(sr*hop)
    n = max(1, (len(mono) - w)//h + 1)
    sq = mono.astype(np.float64) ** 2
    c = np.concatenate(([0.0], np.cumsum(sq)))
    starts = np.arange(n) * h
    ends = starts + w
    mean_sq = (c[ends] - c[starts]) / float(w)
    db = 10.0 * np.log10(np.maximum(mean_sq, 1e-20))
    return db, h, w

def speech_mask(db, smooth=7):
    import numpy as np
    floor = float(np.percentile(db, 10))
    loud = float(np.percentile(db, 90))
    thr = max(floor + 10.0, loud - 26.0)
    mask = db > thr
    if smooth > 1:
        k = np.ones(smooth)/smooth
        mask = np.convolve(mask.astype(float), k, mode="same") > 0.5
    return mask, thr, floor

def regions(mask, hop, max_gap=0.35):
    import numpy as np
    segs, start = [], None
    for i, v in enumerate(mask):
        if v and start is None:
            start = i
        elif not v and start is not None:
            segs.append([start*hop, i*hop]); start = None
    if start is not None:
        segs.append([start*hop, len(mask)*hop])
    merged = []
    for s in segs:
        if merged and s[0] - merged[-1][1] < max_gap:
            merged[-1][1] = s[1]
        else:
            merged.append(s)
    return merged

def split_long(segs, db, hop, win, max_len=9.0, min_len=2.0):
    """过长段在能量最低处切开；过短段丢掉（返回保留 + 丢弃统计）"""
    import numpy as np
    kept, dropped = [], 0
    for s, e in segs:
        dur = e - s
        if dur < min_len:
            dropped += 1
            continue
        if dur <= max_len:
            kept.append([s, e]); continue
        n = int(math.ceil(dur / max_len))
        bounds = [s]
        for k in range(1, n):
            center = s + dur*k/n
            lo = int(max(0, (center - 0.9 - win/2)/hop))
            hi = int(min(len(db), (center + 0.9 - win/2)/hop))
            if hi <= lo:
                bounds.append(center); continue
            local = db[lo:hi]
            cut = lo + int(np.argmin(local))
            bounds.append(cut*hop + win/2)
        bounds.append(e)
        for a, b in zip(bounds[:-1], bounds[1:]):
            if b - a >= min_len:
                kept.append([a, b])
            else:
                dropped += 1
    return kept, dropped

def slice_and_write(mono, sr, segs, outdir, pad=0.08, target_sr=44100):
    import soundfile as sf
    os.makedirs(outdir, exist_ok=True)
    meta = []
    for i, (s, e) in enumerate(segs, 1):
        a = max(0, int((s - pad)*sr)); b = min(len(mono), int((e + pad)*sr))
        clip = mono[a:b]
        name = "seg_%04d.wav" % i
        sf.write(os.path.join(outdir, name), clip.astype("float32"), sr, subtype="PCM_16")
        meta.append({"id": i, "file": name, "start": round(a/sr, 3), "dur": round(len(clip)/sr, 3)})
    log("写出片段 %d 个 → %s" % (len(meta), outdir))
    return meta

# ---------------------------------------------------------------- ASR

def transcribe(meta, outdir, model_name, device):
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    from faster_whisper import WhisperModel
    log("加载 ASR 模型 %s (%s) …" % (model_name, device))
    model = None
    for dev, ct in ((device, "int8" if device == "cpu" else "int8_float16"), ("cpu", "int8")):
        try:
            model = WhisperModel(model_name, device=dev, compute_type=ct)
            log("  实际使用: %s / %s" % (dev, ct))
            break
        except Exception as ex:
            log("  %s 加载失败（%s），换个组合重试" % (dev, str(ex)[:80]))
    if model is None:
        raise RuntimeError("ASR 模型加载失败")
    set_status("ASR 转写", 0, len(meta), "使用 %s" % dev)
    for i, m in enumerate(meta, 1):
        path = os.path.join(outdir, m["file"])
        try:
            segs, info = model.transcribe(path, language="ja", beam_size=5,
                                          vad_filter=False, condition_on_previous_text=False)
            text = "".join(s.text for s in segs).strip()
            prob = [s.avg_logprob for s in segs]
            m["asr"] = text
            m["asr_score"] = round(sum(prob)/len(prob), 3) if prob else -9
        except Exception as ex:
            m["asr"] = ""; m["asr_score"] = -9
            log("  ASR 失败 %s: %s" % (m["file"], ex))
        set_status("ASR 转写", i, len(meta), "使用 %s" % dev)
        if i % 10 == 0 or i == len(meta):
            log("  转写 %d/%d" % (i, len(meta)))
    return meta

# ---------------------------------------------------------------- 对齐

def norm_jp(s):
    import unicodedata
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"[\s、。,.!?！？…‥・「」『』（）()【】\-—ー~〜]", "", s)
    return s

def align(meta, script):
    """把 ASR 片段文本与台本行做全局对齐，返回每段对应的台本行（或 None）"""
    from difflib import SequenceMatcher
    A = [norm_jp(m.get("asr", "")) for m in meta]
    B = [norm_jp(s) for s in script]
    n, m = len(A), len(B)
    SKIP = -0.45
    NEG = -1e9
    dp = [[NEG]*(m+1) for _ in range(n+1)]
    bt = [[None]*(m+1) for _ in range(n+1)]
    dp[0][0] = 0.0
    for i in range(n+1):
        for j in range(m+1):
            cur = dp[i][j]
            if cur == NEG: continue
            if i < n and j < m and A[i] and B[j]:
                sim = SequenceMatcher(None, A[i], B[j]).ratio()
                sc = cur + (sim - 0.30)*2.0
                if sc > dp[i+1][j+1]:
                    dp[i+1][j+1] = sc; bt[i+1][j+1] = ("pair", sim)
            if i < n and cur + SKIP > dp[i+1][j]:
                dp[i+1][j] = cur + SKIP; bt[i+1][j] = ("skipSeg", None)
            if j < m and cur + SKIP > dp[i][j+1]:
                dp[i][j+1] = cur + SKIP; bt[i][j+1] = ("skipLine", None)
    i, j = n, m
    mapping = [None]*n
    while i > 0 or j > 0:
        op, info = bt[i][j]
        if op == "pair":
            mapping[i-1] = {"line": j-1, "sim": round(info, 3)}
            i -= 1; j -= 1
        elif op == "skipSeg":
            i -= 1
        else:
            j -= 1
    return mapping

# ---------------------------------------------------------------- 校对表

HTML = r"""<!doctype html><html lang="ja"><meta charset="utf-8">
<title>素材校对表</title>
<style>
:root{--bg:#0f1115;--fg:#e6e6e6;--dim:#8a8f98;--accent:#4da3ff;--warn:#ffb454;--bad:#ff6b6b;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.6 system-ui,"Microsoft YaHei",sans-serif}
header{position:sticky;top:0;z-index:9;background:#161a21;padding:12px 16px;border-bottom:1px solid #262b35;
  display:flex;gap:16px;align-items:center;flex-wrap:wrap}
header b{font-size:15px}
button{background:#232a35;color:var(--fg);border:1px solid #333c4a;border-radius:6px;padding:6px 12px;cursor:pointer}
button:hover{background:#2c3542}
button.primary{background:#1d4ed8;border-color:#2563eb}
table{width:100%;border-collapse:collapse}
td{padding:8px 10px;border-bottom:1px solid #1d222b;vertical-align:top}
tr:hover{background:#151a22}
.id{color:var(--dim);font-family:ui-monospace,monospace;white-space:nowrap}
.dur{color:var(--dim);white-space:nowrap;font-variant-numeric:tabular-nums}
textarea{width:100%;background:#11151c;color:var(--fg);border:1px solid #2b3442;border-radius:5px;
  padding:6px 8px;font:14px/1.5 inherit;resize:vertical;min-height:34px}
textarea:focus{outline:none;border-color:var(--accent)}
textarea.changed{border-color:var(--warn)}
textarea.lowconf{border-color:#7a4b00}
.tag{display:inline-block;font-size:11px;padding:1px 6px;border-radius:4px;margin-left:6px}
.tag.ok{background:#12351f;color:#4ade80}
.tag.warn{background:#3a2a10;color:var(--warn)}
.tag.bad{background:#3a1515;color:var(--bad)}
</style>
<header>
  <b>素材校对表</b>
  <span id="stat" style="color:var(--dim)"></span>
  <span style="flex:1"></span>
  <label style="color:var(--dim)"><input type="checkbox" id="only" onchange="render()"> 只看可疑的</label>
  <button onclick="playAll()">顺序试听</button>
  <button class="primary" onclick="exportJson()">导出标注</button>
</header>
<table><tbody id="tb"></tbody></table>
<script>
const DATA = __DATA__;
const edited = {};
let idx = 0, playing = false, audio = null;
function suspect(d){ return d.sim !== null && d.sim < 0.55; }
function render(){
  const only = document.getElementById('only').checked;
  const tb = document.getElementById('tb');
  tb.innerHTML = '';
  DATA.forEach((d, i) => {
    if (only && !suspect(d)) return;
    const tr = document.createElement('tr');
    const st = d.sim === null ? ['bad','未匹配']
             : d.sim >= 0.75 ? ['ok','好']
             : d.sim >= 0.55 ? ['warn','存疑'] : ['bad','可疑'];
    tr.innerHTML = `<td class="id">${String(d.id).padStart(4,'0')}</td>
      <td class="dur">${d.dur.toFixed(2)}s</td>
      <td style="width:60px"><button data-i="${i}">▶</button></td>
      <td><textarea data-i="${i}" rows="1">${escapeHtml(d.text)}</textarea>
      <span class="tag ${st[0]}">${st[1]} ${d.sim===null?'':'· '+(d.sim*100|0)+'%'}</span></td>`;
    tb.appendChild(tr);
  });
  tb.querySelectorAll('button[data-i]').forEach(b => b.onclick = () => play(+b.dataset.i));
  tb.querySelectorAll('textarea[data-i]').forEach(t => {
    t.oninput = () => {
      const i = +t.dataset.i;
      edited[i] = t.value;
      t.classList.add('changed');
      updateStat();
    };
  });
  updateStat();
}
function escapeHtml(s){ return (s||'').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
function play(i){
  if (audio) { audio.pause(); audio = null; }
  audio = new Audio('片段/' + DATA[i].file);
  audio.play();
}
function playAll(){
  if (playing) { playing = false; if (audio) audio.pause(); return; }
  playing = true;
  const step = () => {
    if (!playing || idx >= DATA.length) { playing = false; return; }
    const a = new Audio('片段/' + DATA[idx].file);
    audio = a;
    a.onended = () => { idx++; step(); };
    a.play();
  };
  step();
}
function updateStat(){
  const n = Object.keys(edited).length;
  const sus = DATA.filter(suspect).length;
  document.getElementById('stat').textContent =
    `共 ${DATA.length} 条 · 可疑 ${sus} 条 · 已改 ${n} 条`;
}
function exportJson(){
  const out = DATA.map((d,i) => ({...d, text: edited[i] !== undefined ? edited[i] : d.text}));
  const blob = new Blob([JSON.stringify(out, null, 1)], {type:'application/json'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = '校对结果.json';
  a.click();
}
render();
</script></html>"""

def write_html(meta, path, script=None):
    import json
    rows = []
    for m in meta:
        rows.append({
            "id": m["id"], "file": m["file"], "dur": m["dur"],
            "text": m.get("final", m.get("asr", "")),
            "sim": m.get("sim"),
            "asr": m.get("asr", ""),
        })
    html = HTML.replace("__DATA__", json.dumps(rows, ensure_ascii=False))
    open(path, "w", encoding="utf-8").write(html)
    log("校对表 → %s" % path)

# ---------------------------------------------------------------- 主流程

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=DEF_SRC)
    ap.add_argument("--out", default=DEF_OUT)
    ap.add_argument("--model", default="large-v3-turbo")
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--skip-asr", action="store_true")
    a = ap.parse_args()

    global STATUS
    os.makedirs(a.out, exist_ok=True)
    STATUS = os.path.join(a.out, "prep_status.json")
    set_status("启动", 0, 0, "扫描素材")

    segdir = os.path.join(a.out, "片段")
    os.makedirs(segdir, exist_ok=True)

    pairs = find_pairs(a.src)
    if not pairs:
        log("素材目录里没找到音频：%s" % a.src); return 1

    allmeta = []
    for audio_path, txt_path in pairs:
        log("")
        log("="*60)
        mono, sr = load_audio(audio_path)
        total = len(mono)/sr
        set_status("解码与归一化", 0, 0, os.path.basename(audio_path))
        mono, gain_db, clip = normalize(mono)
        log("归一化 +%.2f dB   原始削波样本 %d" % (gain_db, clip))
        set_status("切分", 0, 0, "VAD + 吸附静音")
        db, hop_n, win_n = frame_db(mono, sr)
        hop_s, win_s = hop_n / sr, win_n / sr          # ★ 统一用「秒」，别拿采样点当秒
        mask, thr, floor = speech_mask(db)
        segs = regions(mask, hop_s)
        kept, dropped = split_long(segs, db, hop_s, win_s)
        if len(kept) > 3000:
            raise RuntimeError("切出 %d 段，明显不对（正常应 <300 段）。停下，检查 VAD 参数。" % len(kept))
        log("静音门限 %.1f dBFS  底噪 %.1f dBFS" % (thr, floor))
        log("粗切 %d 段 → 保留 %d 段，丢弃 %d 段（过短）" % (len(segs), len(kept), dropped))
        meta = slice_and_write(mono, sr, kept, segdir)
        durs = sorted(x["dur"] for x in meta)
        if durs:
            log("段长 最短 %.2f / 中位 %.2f / 最长 %.2f 秒   有声总计 %.1f 分"
                % (durs[0], durs[len(durs)//2], durs[-1], sum(durs)/60))
        if txt_path:
            script = load_script(txt_path)
            meta_script = script
        else:
            script, meta_script = None, None
        for m in meta:
            m["_script"] = meta_script
        allmeta.extend(meta)

    if not a.skip_asr:
        transcribe(allmeta, segdir, a.model, a.device)

    # 对齐：每段音频独立对其台本
    for m in allmeta:
        m["final"] = m.get("asr", "")
        m["sim"] = None
    # 按源文件分组对齐（这里假设单文件，够用）
    script = None
    for m in allmeta:
        if m.get("_script"):
            script = m["_script"]; break
    if script and not a.skip_asr:
        mapping = align(allmeta, script)
        hit = 0
        for m, mp in zip(allmeta, mapping):
            if mp:
                m["final"] = script[mp["line"]]
                m["sim"] = mp["sim"]
                m["script_line"] = mp["line"] + 1
                hit += 1
        log("")
        log("台本对齐：命中 %d / %d 段" % (hit, len(allmeta)))
        used = set(m.get("script_line", -1) for m in allmeta)
        missing = [i+1 for i in range(len(script)) if i+1 not in used]
        if missing:
            log("没被用到的台本行 %d 行：%s%s" % (len(missing), missing[:30], " …" if len(missing) > 30 else ""))
    elif script:
        # 没有 ASR 时退而求其次：按顺序一一对应，标成「顺序推定」，靠人耳在核对表里验
        n, k = len(allmeta), len(script)
        log("")
        log("无 ASR，按顺序推定对齐：段 %d 条 / 台本 %d 行" % (n, k))
        for i, m in enumerate(allmeta):
            j = round(i * (k - 1) / max(n - 1, 1)) if n > 1 else 0
            m["final"] = script[j]
            m["script_line"] = j + 1
            m["seq_guess"] = True

    # 汇总
    lst = os.path.join(a.out, "train.list")
    with open(lst, "w", encoding="utf-8") as f:
        for m in allmeta:
            f.write("%s|speaker|ja|%s\n" % (os.path.join(segdir, m["file"]), m.get("final", "")))
    log("训练清单 → %s  (%d 行)" % (lst, len(allmeta)))

    write_html(allmeta, os.path.join(a.out, "校对表.html"))
    json.dump(allmeta, open(os.path.join(a.out, "meta.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    open(os.path.join(a.out, "处理日志.txt"), "w", encoding="utf-8").write("\n".join(LOG))
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
