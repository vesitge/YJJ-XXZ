# -*- coding: utf-8 -*-
"""冒烟测试：确认 GPT-SoVITS 的 TTS 管线能真正加载起来。"""
import sys, os
ROOT = r"D:\HarnessAI\work\GPT-SoVITS"
os.chdir(ROOT)
sys.path.append(ROOT)
sys.path.append(os.path.join(ROOT, "GPT_SoVITS"))

try:
    from GPT_SoVITS.TTS_infer_pack.TTS import TTS, TTS_Config
    print("TTS 模块导入 OK")
    cfg = TTS_Config("GPT_SoVITS/configs/tts_infer.yaml")
    print("配置加载 OK")
    pm = getattr(cfg, "pretrained_models", {}) or {}
    for k, v in pm.items():
        print("    %-14s %s  %s" % (k, "存在" if os.path.exists(str(v)) else "缺失", v))
    print("    device:", getattr(cfg, "device", "?"), " version:", getattr(cfg, "version", "?"))
    t = TTS(cfg)
    print("TTS 实例化 OK —— 管线可用")
    import pyopenjtalk
    print("日语 g2p:", pyopenjtalk.g2p("おはようございます"))
except Exception:
    import traceback
    traceback.print_exc()
