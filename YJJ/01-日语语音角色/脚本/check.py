# -*- coding: utf-8 -*-
"""环境自检：逐项报告组件状态。任何一个 FAIL 都会在末尾汇总。"""
import os, sys, subprocess, importlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GS = os.path.join(ROOT, "GPT-SoVITS")
results = []

def add(name, ok, detail):
    results.append((name, ok, detail))
    flag = "OK  " if ok else "FAIL"
    print("  [%s] %-22s %s" % (flag, name, detail))

print("=" * 68)
print("  GPT-SoVITS 环境自检")
print("=" * 68)
print()

# 1 python
add("Python", True, "%d.%d.%d  %s" % (sys.version_info[:3] + (sys.executable,)))

# 2 torch
try:
    import torch
    ok = torch.cuda.is_available()
    dev = torch.cuda.get_device_name(0) if ok else "无可用设备"
    add("PyTorch + CUDA", ok, "torch %s / CUDA %s / %s" % (torch.__version__, torch.version.cuda, dev))
except Exception as e:
    add("PyTorch + CUDA", False, "导入失败: %s" % e)

# 3 ffmpeg
ff = os.path.join(ROOT, "bin", "ffmpeg.exe")
if os.path.exists(ff):
    try:
        out = subprocess.run([ff, "-version"], capture_output=True, text=True, timeout=15).stdout
        add("ffmpeg", True, out.splitlines()[0][:60])
    except Exception as e:
        add("ffmpeg", False, str(e))
else:
    add("ffmpeg", False, "找不到 %s" % ff)

# 4 GPT-SoVITS 关键文件
need = [
    ("GPT_SoVITS/pretrained_models", "预训练目录"),
    ("GPT_SoVITS/text/G2PWModel", "多音字模型"),
]
for rel, label in need:
    p = os.path.join(GS, rel)
    add(label, os.path.isdir(p), p if os.path.isdir(p) else "缺失：" + p)

# 5 关键底模文件
s2 = [f for f in os.listdir(os.path.join(GS, "GPT_SoVITS", "pretrained_models"))
      if f.startswith("s2") and f.endswith(".pth")] if os.path.isdir(os.path.join(GS, "GPT_SoVITS", "pretrained_models")) else []
s1 = [f for f in os.listdir(os.path.join(GS, "GPT_SoVITS", "pretrained_models"))
      if f.startswith("s1") and f.endswith(".ckpt")] if os.path.isdir(os.path.join(GS, "GPT_SoVITS", "pretrained_models")) else []
add("底模 s2*.pth", bool(s2), ", ".join(s2) if s2 else "缺失")
add("底模 s1*.ckpt", bool(s1), ", ".join(s1) if s1 else "缺失")

# 6 日语支持
try:
    import pyopenjtalk
    d = os.path.join(os.path.dirname(pyopenjtalk.__file__), "open_jtalk_dic_utf_8-1.11")
    add("pyopenjtalk + 词典", os.path.isdir(d), "日语分词 %s" % ("已就位" if os.path.isdir(d) else "缺 open_jtalk 词典"))
except Exception as e:
    add("pyopenjtalk + 词典", False, "导入失败: %s" % e)

# 7 其它关键依赖
for mod in ["faster_whisper", "soundfile", "numpy", "transformers", "librosa", "gradio", "pytorch_lightning"]:
    try:
        m = importlib.import_module(mod)
        add(mod, True, getattr(m, "__version__", "?"))
    except Exception as e:
        add(mod, False, "导入失败: %s" % str(e)[:50])

print()
bad = [r for r in results if not r[1]]
print("-" * 68)
if bad:
    print("  %d 项未通过：" % len(bad))
    for n, _, d in bad:
        print("    · %s —— %s" % (n, d))
    print()
    print("  把这些行发回去，我来处理。")
else:
    print("  全部通过。可以开工了。")
print("-" * 68)
