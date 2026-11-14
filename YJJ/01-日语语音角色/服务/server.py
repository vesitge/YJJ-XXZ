#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
本地打字对话（对话模型 + 日语语音输出）

流程：浏览器打字 -> 对话模型生成日语回复 -> 本地 GPT-SoVITS 合成 -> 播放

- 依赖：本机 9888 端口的 TTS API（GPT-SoVITS api_v2.py）
- 对话模型：任何 OpenAI 兼容接口（默认 DeepSeek），key 由用户在页面里自己填
- 只用标准库
"""

import base64
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")
TTS_API = "http://127.0.0.1:9888/tts"
TTS_PORT = 9888
PORT = 9890
ASR_MODEL_DIR = r"D:\HarnessAI\work\models\faster-whisper-large-v3-turbo"
ASR_MODELS = {
    "large": ASR_MODEL_DIR,
    "small": r"D:\HarnessAI\work\models\faster-whisper-small",
}

# 参考音频默认值（可在页面「设置」里改，改完写进 config.json）
REF_AUDIO = r"D:\HarnessAI\work\工作\参考音频\ref_seg_0028.wav"
REF_TEXT = "イチゴのアイス一つおまけしてやったんだぞ～？ 優しいだろ。"

DEFAULT_CONFIG = {
    "api_base": "https://api.deepseek.com/v1",
    "api_key": "",
    "model": "deepseek-chat",
    "ref_audio": REF_AUDIO,
    "ref_text": REF_TEXT,
    # 发声引擎：local = 本地 GPT-SoVITS；volc = 火山豆包语音合成（可用复刻音色）
    "tts_backend": "local",
    "volc_speaker": "S_JiTK35lk2",
    "volc_resource": "seed-icl-2.0",
    "volc_lang": "ja",
    "volc_api_key": "",
    # 火山发声的性格档位与情绪提示：expressive 更会演，context 是给它的情绪说明
    "volc_model": "seed-tts-2.0-expressive",
    "volc_context": "少しツンとした、でも面倒見のいい口調で。感情をしっかり乗せて、棒読みにしないで。",
    # 识别模型：large = large-v3-turbo（准），small = 快一倍但日语精度略降；改了要重启
    "asr_model": "large",
    "persona": (
        "あなたは「凉（リョウ）」という女性です。"
        "日本語で、短く、砕けた口調で返事をしてください。1〜2文まで。"
        "相手が中国語で話しかけても、返事は必ず日本語で返してください。"
        "説明口調や丁寧すぎる敬語は使わない。"
        "棒読みにならないよう、感情のこもった言い方で。「〜」「？」「！」「あ、」「もう、」"
        "みたいな自然な間投詞や語尾を入れて、話し言葉らしくしてください。"
    ),
}


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    return cfg


def save_config(patch):
    cfg = load_config()
    for k in ("api_base", "api_key", "model", "persona", "ref_audio", "ref_text",
              "tts_backend", "volc_speaker", "volc_resource", "volc_lang", "volc_api_key", "volc_model", "volc_context",
              "asr_model"):
        if k in patch and isinstance(patch[k], str) and patch[k].strip():
            cfg[k] = patch[k].strip()
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return cfg


def llm_reply(user_text, history):
    cfg = load_config()
    if not cfg.get("api_key"):
        raise RuntimeError("还没填 API key，点右上角「设置」填一下")
    msgs = [{"role": "system", "content": cfg["persona"]}]
    for h in (history or [])[-8:]:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            msgs.append({"role": h["role"], "content": h["content"]})
    msgs.append({"role": "user", "content": user_text})
    payload = {"model": cfg["model"], "messages": msgs, "temperature": 0.85, "max_tokens": 200}
    req = urllib.request.Request(
        cfg["api_base"].rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + cfg["api_key"]},
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:300]
        raise RuntimeError("接口返回 %s：%s" % (e.code, detail))
    except Exception as e:
        raise RuntimeError("连不上对话接口：%s" % e)
    try:
        return data["choices"][0]["message"]["content"].strip()
    except Exception:
        raise RuntimeError("返回格式看不懂：" + json.dumps(data, ensure_ascii=False)[:200])


def translate_zh(jp_text):
    """把日语回复翻成中文，只用于屏幕显示。失败返回空串，不挡主流程。"""
    cfg = load_config()
    if not cfg.get("api_key") or not (jp_text or "").strip():
        return ""
    msgs = [
        {"role": "system", "content": "你只做翻译。把用户给的日语译成自然口语的中文，只输出译文本身，不要解释、不要加引号、不要复述原文。"},
        {"role": "user", "content": jp_text},
    ]
    payload = {"model": cfg["model"], "messages": msgs, "temperature": 0.2, "max_tokens": 300}
    req = urllib.request.Request(
        cfg["api_base"].rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + cfg["api_key"]},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"].strip()


def translate_ja(zh_text):
    """把中文译成自然口语的日语，只给朗读用（插件里的「日」档）。"""
    cfg = load_config()
    if not cfg.get("api_key"):
        raise RuntimeError("还没填 API key：右上角「设置」里填一个")
    text = (zh_text or "").strip()
    if not text:
        raise RuntimeError("没有要翻译的文字")
    msgs = [
        {"role": "system", "content": "你只做翻译。把用户给的中文译成自然、口语化的日语，保持原意，不要敬语过头。只输出日语译文本身：不要解释、不要加引号、不要保留中文、不要写注音。"},
        {"role": "user", "content": text},
    ]
    payload = {"model": cfg["model"], "messages": msgs, "temperature": 0.2, "max_tokens": 1200}
    req = urllib.request.Request(
        cfg["api_base"].rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + cfg["api_key"]},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError("翻译接口返回 %s：%s" % (e.code, e.read()[:200].decode("utf-8", "ignore")))
    except Exception as e:
        raise RuntimeError("连不上翻译接口：%s" % e)
    try:
        return data["choices"][0]["message"]["content"].strip()
    except Exception:
        raise RuntimeError("翻译结果看不懂：" + json.dumps(data, ensure_ascii=False)[:200])


VOLC_TTS_URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
GAME_BUDDY_SETTINGS = r"D:\HarnessAI\home\dsh-game-buddy\settings.json"


def volc_key(cfg):
    """火山 API Key：先用本页配置，没有就复用游戏搭档里填的那把。"""
    key = (cfg.get("volc_api_key") or "").strip()
    if key:
        return key
    try:
        with open(GAME_BUDDY_SETTINGS, encoding="utf-8") as f:
            return (json.load(f).get("apiKey") or "").strip()
    except Exception:
        return ""


def synth_volc(text):
    """走火山豆包语音合成（单向 HTTP），返回一段 wav 字节。"""
    cfg = load_config()
    key = volc_key(cfg)
    if not key:
        raise RuntimeError("没有火山 API Key：在游戏搭档里填过就能复用，或者在这里填一把")
    sr = 24000
    additions = {"explicit_language": cfg.get("volc_lang") or "ja"}
    ctx = (cfg.get("volc_context") or "").strip()
    if ctx:
        additions["context_texts"] = [ctx]
    req_params = {
        "text": text,
        "speaker": cfg.get("volc_speaker") or "S_JiTK35lk2",
        "audio_params": {"format": "pcm", "sample_rate": sr},
        "additions": json.dumps(additions, ensure_ascii=False),
    }
    vmodel = (cfg.get("volc_model") or "").strip()
    if vmodel:
        req_params["model"] = vmodel
    body = {"user": {"uid": "dsh-local"}, "req_params": req_params}
    headers = {
        "X-Api-Key": key,
        "X-Api-Resource-Id": cfg.get("volc_resource") or "seed-icl-2.0",
        "X-Api-Request-Id": str(uuid.uuid4()),
        "Content-Type": "application/json",
    }
    def _once():
        req = urllib.request.Request(VOLC_TTS_URL, data=json.dumps(body).encode("utf-8"),
                                     headers=dict(headers, **{"X-Api-Request-Id": str(uuid.uuid4())}),
                                     method="POST")
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                raw = r.read().decode("utf-8", "ignore")
        except urllib.error.HTTPError as e:
            raise RuntimeError("火山返回 %s：%s" % (e.code, e.read()[:200].decode("utf-8", "ignore")))
        buf_pcm = b""
        chunks = 0
        bad = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                j = json.loads(line)
            except Exception:
                continue
            if j.get("code") not in (0, 20000000, None):   # 20000000 = 正常流结束
                bad.append(j.get("code"))
            if j.get("data"):
                buf_pcm += base64.b64decode(j["data"])
                chunks += 1
        return buf_pcm, chunks, bad

    # 一句话的正常长度：日语约 0.45 秒/字，留足余量
    expect = max(6.0, len(text) * 0.6)
    limit = max(8.0, expect * 1.6)
    pcm, chunks, bad = _once()
    secs = len(pcm) / 2 / sr
    if secs > limit:
        print("[volc] 异常：%.1f 秒，超过上限 %.1f（%d 字），重试一次" % (secs, limit, len(text)), flush=True)
        pcm, chunks, bad = _once()
        secs = len(pcm) / 2 / sr
        if secs > limit:
            raise RuntimeError("合成音频异常：%d 字却生成了 %.1f 秒，已丢弃" % (len(text), secs))
    if not pcm:
        raise RuntimeError("火山没返回音频")
    print("[volc] %d 字 -> %d 包 / %.2f 秒 / 异常码 %s" % (len(text), chunks, secs, bad[:3]), flush=True)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm)
    return buf.getvalue()


def synth(text):
    cfg = load_config()
    ref_audio = cfg.get("ref_audio") or REF_AUDIO
    ref_text = cfg.get("ref_text") or REF_TEXT
    if not os.path.exists(ref_audio):
        raise RuntimeError("参考音频不存在：" + ref_audio)
    params = {
        "text": text,
        "text_lang": "ja",
        "ref_audio_path": ref_audio,
        "prompt_lang": "ja",
        "prompt_text": ref_text,
        "text_split_method": "cut5",
        "media_type": "wav",
        "streaming_mode": "false",
        # 这台机器上 v5 的并行推理会吐全零，必须关掉
        "parallel_infer": "false",
    }
    url = TTS_API + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=300) as r:
        data = r.read()
    # 本地回包也要验：时长明显对不上就是出问题了，别把它播出去
    try:
        with wave.open(io.BytesIO(data)) as w:
            secs = w.getnframes() / w.getframerate()
            got_sr = w.getframerate()
        limit = max(10.0, max(6.0, len(text) * 0.6) * 1.8)
        print("[local tts] %d 字 -> %.2f 秒 @%dHz" % (len(text), secs, got_sr), flush=True)
        if secs > limit:
            raise RuntimeError("本地合成音频异常：%d 字生成 %.1f 秒" % (len(text), secs))
    except RuntimeError:
        raise
    except Exception:
        pass
    return data


def tts_alive():
    try:
        urllib.request.urlopen("http://127.0.0.1:9888/docs", timeout=3)
        return True
    except Exception:
        return False


# ---------------- 耳朵：faster-whisper 转文字 ----------------
_asr = None
_asr_lock = threading.Lock()
_asr_state = {"state": "cold", "device": ""}


def _prepare_cuda_dlls():
    """ctranslate2 要 cublas64_12.dll，让它在 torch 自带的目录里找到。"""
    work = os.path.dirname(os.path.dirname(HERE))          # ...\work
    runtime = os.path.join(work, "GPT-SoVITS-v5", "runtime")
    for p in (os.path.join(runtime, "Lib", "site-packages", "torch", "lib"),
              os.path.join(runtime, "Library", "bin")):
        if os.path.isdir(p):
            print("[asr] 加 DLL 目录:", p, flush=True)
            os.environ["PATH"] = p + os.pathsep + os.environ.get("PATH", "")
            try:
                os.add_dll_directory(p)
            except Exception:
                pass


def get_asr():
    """懒加载，第一次用的时候才占显存。CUDA 起不来就退回 CPU。"""
    global _asr
    with _asr_lock:
        if _asr is not None:
            return _asr
        _prepare_cuda_dlls()
        from faster_whisper import WhisperModel
        want = (load_config().get("asr_model") or "large").lower()
        model_dir = ASR_MODELS.get(want, ASR_MODELS["large"])
        if not os.path.isdir(model_dir):
            print("[asr] 找不到 %s，退回 large" % model_dir, flush=True)
            model_dir = ASR_MODELS["large"]
        print("[asr] 加载 %s" % model_dir, flush=True)
        for device, ctype in (("cuda", "float16"), ("cpu", "int8")):
            try:
                m = WhisperModel(model_dir, device=device, compute_type=ctype)
                _asr = m
                _asr_state["state"] = "ready"
                _asr_state["device"] = device
                print("[asr] 就绪，设备:", device, flush=True)
                return m
            except Exception as e:
                print("[asr] %s 起不来: %s" % (device, e), flush=True)
        _asr_state["state"] = "failed"
        raise RuntimeError("语音识别模型加载失败")


def transcribe(path, lang=None):
    """lang: "ja" / "zh" / None(自动)。短句自动检测很容易串语言，所以页面给了两个按钮。"""
    m = get_asr()
    force = lang if lang in ("ja", "zh", "en") else None
    segs, info = m.transcribe(path, language=force, vad_filter=True, beam_size=5)
    text = "".join(s.text for s in segs).strip()
    return text, (info.language or ""), (force is not None)


def warm_asr():
    def run():
        try:
            _asr_state["state"] = "loading"
            get_asr()
        except Exception:
            pass
    threading.Thread(target=run, daemon=True).start()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        # 让 DSH 页面（127.0.0.1:30808 等其它端口）能直接调用
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                self._send(200, f.read(), "text/html; charset=utf-8")
        elif self.path == "/api/ping":
            # 轻量存活探测：不读配置、不碰 9888，插件用它判断服务在不在
            self._json(200, {"ok": True})
        elif self.path == "/api/config":
            cfg = load_config()
            cfg["api_key"] = "***" if cfg.get("api_key") else ""
            cfg["tts_api"] = tts_alive()
            self._json(200, cfg)
        elif self.path == "/api/models":
            cfg = load_config()
            if not cfg.get("api_key"):
                self._json(400, {"error": "先填 key 再拉模型列表"})
                return
            try:
                req = urllib.request.Request(
                    cfg["api_base"].rstrip("/") + "/models",
                    headers={"Authorization": "Bearer " + cfg["api_key"]},
                )
                with urllib.request.urlopen(req, timeout=30) as r:
                    data = json.loads(r.read().decode("utf-8"))
                ids = [m.get("id") for m in data.get("data", []) if m.get("id")]
                self._json(200, {"models": ids})
            except Exception as e:
                self._json(500, {"error": "拉取失败：%s" % e})
        else:
            self._json(404, {"error": "not found"})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Max-Age", "600")
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw or b"{}")
        except Exception:
            payload = {}
        # 路由只看路径，查询串（?lang=ja）另外解析
        route = urllib.parse.urlparse(self.path).path

        if route == "/api/quit":
            self._json(200, {"ok": True})
            threading.Thread(target=shutdown_all, daemon=True).start()
            return
        if route == "/api/config":
            save_config(payload)
            self._json(200, {"ok": True})
        elif route == "/api/chat":
            text = (payload.get("text") or "").strip()
            if not text:
                self._json(400, {"error": "空消息"})
                return
            try:
                reply = llm_reply(text, payload.get("history") or [])
            except Exception as e:
                self._json(500, {"error": "%s" % e})
                return
            # 中文只作翻译显示，不发声；翻译失败不影响日语主体
            zh = ""
            try:
                zh = translate_zh(reply)
            except Exception as e:
                print("[zh] 翻译失败:", e, flush=True)
            self._json(200, {"reply": reply, "zh": zh})
        elif route == "/api/warm":
            warm_asr()
            self._json(200, {"ok": True})
        elif route == "/api/translate":
            text = (payload.get("text") or "").strip()
            if not text:
                self._json(400, {"error": "empty text"})
                return
            try:
                ja = translate_ja(text)
            except Exception as e:
                self._json(500, {"error": "%s" % e})
                return
            self._json(200, {"text": ja})
        elif route == "/api/say":
            text = (payload.get("text") or "").strip()
            if not text:
                self._json(400, {"error": "empty text"})
                return
            try:
                backend = (load_config().get("tts_backend") or "local").lower()
                wav = synth_volc(text) if backend == "volc" else synth(text)
            except Exception as e:
                self._json(500, {"error": "%s: %s" % (type(e).__name__, e)})
                return
            self._send(200, wav, "audio/wav")
        elif route == "/api/hear":
            if not raw:
                self._json(400, {"error": "没收到声音"})
                return
            ctype = (self.headers.get("Content-Type") or "").lower()
            ext = ".webm"
            if "wav" in ctype:
                ext = ".wav"
            elif "ogg" in ctype:
                ext = ".ogg"
            elif "mp4" in ctype or "m4a" in ctype:
                ext = ".m4a"
            fd, tmp = tempfile.mkstemp(suffix=ext, prefix="hear_", dir=HERE)
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(raw)
                t0 = time.time()
                q = urllib.parse.urlparse(self.path).query
                want = (urllib.parse.parse_qs(q).get("lang") or [""])[0]
                text, lang, forced = transcribe(tmp, want)
                print("[asr] %.1fs %s%s -> %r" % (time.time() - t0, lang,
                                                  "(指定)" if forced else "(自动)", text), flush=True)
                try:
                    with open(os.path.join(HERE, "hear.log"), "a", encoding="utf-8") as lf:
                        lf.write("%s\t%s\t%s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), lang, text))
                except Exception:
                    pass
            except Exception as e:
                self._json(500, {"error": "%s: %s" % (type(e).__name__, e)})
                return
            finally:
                try:
                    os.remove(tmp)
                except Exception:
                    pass
            self._json(200, {"text": text, "lang": lang, "forced": forced})
        else:
            self._json(404, {"error": "not found"})


def _kill_port(port):
    """把占着某个端口的进程干掉（只用于退出时清场）。"""
    try:
        out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, timeout=10).stdout
        for line in out.splitlines():
            if ":%d" % port in line and "LISTENING" in line:
                pid = line.split()[-1]
                if pid.isdigit():
                    subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True, timeout=10)
    except Exception as e:
        print("[quit] 清端口失败:", e, flush=True)


def shutdown_all():
    time.sleep(0.3)
    _kill_port(TTS_PORT)
    os._exit(0)


def port_busy():
    """端口只要有人绑着就算占用 —— 不看 HTTP 有没有应答。

    Windows 允许重复绑定，光靠“能不能请求到”会漏判：对方在加载模型时
    还没开始收请求，新进程就也跟着绑上去，最后两个实例抢一个端口。
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        return s.connect_ex(("127.0.0.1", PORT)) == 0
    finally:
        try:
            s.close()
        except Exception:
            pass


def main():
    if port_busy():
        print("[跳过] 端口 %d 上已经有实例在跑，这次不启动。" % PORT)
        print("       要重启就先关掉托盘图标（右键退出），或结束 python 进程。")
        sys.exit(0)
    if not os.path.exists(REF_AUDIO):
        print("参考音频不存在:", REF_AUDIO)
        sys.exit(1)
    if not os.path.exists(CONFIG_PATH):
        save_config({})
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print("对话服务已启动: http://127.0.0.1:%d" % PORT)
    print("TTS API:", TTS_API, "| 就绪:", tts_alive())
    print("识别模型:", (load_config().get("asr_model") or "large"))
    if os.environ.get("VOICECHAT_LAZY_ASR") == "1":
        print("[asr] 懒加载模式：识别模型等真正要用时再加载", flush=True)
    else:
        warm_asr()
    srv.serve_forever()


if __name__ == "__main__":
    main()
