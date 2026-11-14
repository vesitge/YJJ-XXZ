# -*- coding: utf-8 -*-
"""
中文提示词 → 英文 tag（调用 DeepSeek / 任何 OpenAI 兼容接口）

为什么不用现成的翻译插件：
  普通翻译输出的是句子（"She is sitting on the sofa"），
  SDXL 要的是逗号分隔的关键词（"sitting on sofa"）。
  这里用一个 system prompt 强制它输出 tag 格式。

两个节点：
  CNPromptTranslator  只出 tag 字符串（预览用，STRING 输出，要接线得把文本框转成输入）
  CNPromptEncode      直接出 CONDITIONING（推荐，clip 是真正的插口，不用转 widget）

安装：放到 ComfyUI/custom_nodes/ 下，重启 ComfyUI
"""
import json
import urllib.request
import urllib.error

SYSTEM_PROMPT = """你是 Stable Diffusion 提示词工程师。把用户的中文场景描述转换成 SDXL 用的英文 tag。

严格遵守：
1. 只输出逗号分隔的英文 tag，不要完整的句子，不要任何解释、不要编号、不要 markdown、不要加引号。
2. 全部小写，用 danbooru 常见的 tag 写法。
3. 顺序：动作/姿势 → 服装 → 场景 → 光线 → 视角/构图。
4. 不要加画质词（masterpiece, best quality, highres, absurdres 等）。
5. 不要加角色触发词，也不要加 1girl / 1boy / solo —— 用户的模板里已经有了，重复会让权重失衡。
6. 动作短语要连成完整的一个 tag，不要拆开。写 sitting on sofa，不要写成 sitting, on sofa。
7. 只写中文里明确提到的内容，不要自己加细节。
8. tag 数量控制在 10 个以内，宁可少而准。

示例：
输入：她坐在沙发上，穿着红毛衣，逆光，侧面
输出：sitting on sofa, red sweater, backlight, from side

只输出 tag 本身。"""

# 角色模板：放在前面，中文翻出来的 tag 接在后面
DEFAULT_PREFIX = (
    "ryou, 1wa0, 1girl, amber eyes, black choker, long grey brown hair, ponytail, "
    "masterpiece, best quality, highly detailed, anime style"
)


def translate(text, api_key, base_url="https://api.deepseek.com",
              model="deepseek-chat", extra_rules="", temperature=0.3):
    """中文 → tag 字符串。空输入返回空串，不花 token。"""
    text = (text or "").strip()
    if not text:
        return ""

    key = (api_key or "").strip()
    if not key:
        raise RuntimeError(
            "没填 API key。到 platform.deepseek.com 建一个（sk- 开头），"
            "粘到本节点的 api_key 框里。"
        )

    user_msg = "中文描述：" + text
    if (extra_rules or "").strip():
        user_msg += "\n\n补充要求：" + extra_rules.strip()

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "temperature": temperature,
        "stream": False,
    }

    url = base_url.rstrip("/") + "/chat/completions"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + key,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        raise RuntimeError("API 返回 %s：%s" % (e.code, body))
    except Exception as e:
        raise RuntimeError("请求失败：%s" % e)

    try:
        out = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        raise RuntimeError("响应格式不对：%s" % str(data)[:300])

    out = out.strip().strip("。.").replace("\n", " ")
    while "  " in out:
        out = out.replace("  ", " ")
    if out.endswith(","):
        out = out[:-1]

    print("[中文提示词] %s  →  %s" % (text[:30], out))
    return out


def join_tags(prefix, tags):
    """英文模板 + 翻出来的 tag，去重、补逗号。"""
    parts = []
    seen = set()
    for chunk in (prefix or "").split(","):
        t = chunk.strip()
        if t and t.lower() not in seen:
            seen.add(t.lower())
            parts.append(t)
    for chunk in (tags or "").split(","):
        t = chunk.strip()
        if t and t.lower() not in seen:
            seen.add(t.lower())
            parts.append(t)
    return ", ".join(parts)


class CNPromptTranslator:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "chinese_text": ("STRING", {
                    "multiline": True,
                    "default": "她坐在沙发上，穿着红毛衣，逆光，侧面",
                }),
                "api_key": ("STRING", {
                    "default": "",
                }),
            },
            "optional": {
                "base_url": ("STRING", {
                    "default": "https://api.deepseek.com",
                }),
                "model": ("STRING", {
                    "default": "deepseek-chat",
                }),
                "extra_rules": ("STRING", {
                    "multiline": True,
                    "default": "",
                }),
                "temperature": ("FLOAT", {
                    "default": 0.3, "min": 0.0, "max": 1.5, "step": 0.05,
                }),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("english_tags",)
    FUNCTION = "run"
    CATEGORY = "提示词/中文"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        # 每次都重新请求，不吃缓存
        return float("nan")

    def run(self, chinese_text, api_key, extra_rules="", base_url="https://api.deepseek.com",
            model="deepseek-chat", temperature=0.3):
        return (translate(chinese_text, api_key, base_url, model, extra_rules, temperature),)


class CNPromptEncode:
    """中文 → CONDITIONING。clip 是真插口，接上去就能用，不用把文本框转成输入。"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "clip": ("CLIP",),
                "chinese_text": ("STRING", {
                    "multiline": True,
                    "default": "她坐在沙发上，穿着红毛衣，逆光，侧面",
                }),
                "api_key": ("STRING", {
                    "default": "",
                }),
            },
            "optional": {
                "prefix": ("STRING", {
                    "multiline": True,
                    "default": DEFAULT_PREFIX,
                }),
                "base_url": ("STRING", {
                    "default": "https://api.deepseek.com",
                }),
                "model": ("STRING", {
                    "default": "deepseek-chat",
                }),
                "extra_rules": ("STRING", {
                    "multiline": True,
                    "default": "",
                }),
                "temperature": ("FLOAT", {
                    "default": 0.3, "min": 0.0, "max": 1.5, "step": 0.05,
                }),
            },
        }

    RETURN_TYPES = ("CONDITIONING", "STRING")
    RETURN_NAMES = ("conditioning", "used_prompt")
    FUNCTION = "encode"
    CATEGORY = "提示词/中文"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def encode(self, clip, chinese_text, api_key, prefix=DEFAULT_PREFIX,
               base_url="https://api.deepseek.com", model="deepseek-chat",
               extra_rules="", temperature=0.3):
        tags = translate(chinese_text, api_key, base_url, model, extra_rules, temperature)
        full = join_tags(prefix, tags)
        print("[实际提示词] %s" % full)

        tokens = clip.tokenize(full)
        cond, pooled = clip.encode_from_tokens(tokens, return_pooled=True)
        return ([[cond, {"pooled_output": pooled}]], full)


NODE_CLASS_MAPPINGS = {
    "CNPromptTranslator": CNPromptTranslator,
    "CNPromptEncode": CNPromptEncode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "CNPromptTranslator": "中文提示词转 tag（DeepSeek）",
    "CNPromptEncode": "中文提示词→条件（DeepSeek）",
}
