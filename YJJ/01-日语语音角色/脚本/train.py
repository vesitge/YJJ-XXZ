# -*- coding: utf-8 -*-
"""一键训练驱动：预处理 → 训练 SoVITS → 训练 GPT。

复刻 WebUI 里那几步做的事，但用命令行，并且把进度写进 prep_status.json。
用法：python tools/train.py [--epochs-s2 8] [--epochs-s1 12] [--batch 2]
"""
import os, sys, json, time, argparse, subprocess, shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import prep
from prep import set_status, log, _flush_status

GS = os.path.join(ROOT, "GPT-SoVITS")
GSP = os.path.join(GS, "GPT_SoVITS")
PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
NV = os.path.join(ROOT, ".venv", "Lib", "site-packages", "nvidia")
EXP_ROOT = os.path.join(ROOT, "train_out")
TRAIN_LIST = os.path.join(ROOT, "train.list")
SEGDIR = os.path.join(ROOT, "seg")
PM = os.path.join(GSP, "pretrained_models")
V2 = os.path.join(PM, "gsv-v2final-pretrained")


def add_cuda_dlls():
    for sub in ("cublas", "cudnn", "cuda_nvrtc"):
        p = os.path.join(NV, sub, "bin")
        if os.path.isdir(p):
            os.environ["PATH"] = p + os.pathsep + os.environ["PATH"]


def run(cmd, env=None, cwd=None, tag=""):
    cwd = cwd or GSP                      # 必须在 GPT_SoVITS 下跑，否则 import text 失败
    e = os.environ.copy()
    e["PYTHONPATH"] = os.pathsep.join([GSP, GS, e.get("PYTHONPATH", "")])
    e["PATH"] = os.path.join(ROOT, "bin") + os.pathsep + e.get("PATH", "")   # ffmpeg 在这个目录
    # Windows 上 torch + numba 会各自带一份 OpenMP，重复加载会让进程直接崩（0xC0000409）
    e["KMP_DUPLICATE_LIB_OK"] = "TRUE"
    e["OMP_NUM_THREADS"] = "1"
    if env:
        e.update({k: str(v) for k, v in env.items()})
    log("$ %s" % (cmd if isinstance(cmd, str) else " ".join(cmd)))
    t0 = time.time()
    p = subprocess.run(cmd, shell=isinstance(cmd, str), env=e, cwd=cwd,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    dt = time.time() - t0
    out = (p.stdout or "") + (p.stderr or "")
    log("[%s] 退出码 %d，用时 %.0f 秒" % (tag, p.returncode, dt))
    tail = "\n".join(out.strip().splitlines()[-25:])
    if tail:
        log(tail)
    if p.returncode != 0:
        raise RuntimeError("%s 失败（退出码 %d）" % (tag, p.returncode))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", default="ryou")
    ap.add_argument("--epochs-s2", type=int, default=8)
    ap.add_argument("--epochs-s1", type=int, default=12)
    ap.add_argument("--batch", type=int, default=2)
    ap.add_argument("--skip-prepare", action="store_true")
    ap.add_argument("--no-fp16", dest="fp16", action="store_false")
    ap.set_defaults(fp16=True)
    a = ap.parse_args()

    # 训练不要注入 nvidia/*/bin：那套是给 ASR 用的，会盖住 torch 自带的 cuBLAS/cuDNN，
    # 反过来触发 cudaErrorUnknown。这里只用 torch 自己带的。
    prep.STATUS = os.path.join(ROOT, "工作", "prep_status.json")
    exp_dir = os.path.join(EXP_ROOT, a.exp)
    os.makedirs(exp_dir, exist_ok=True)

    n = sum(1 for _ in open(TRAIN_LIST, encoding="utf-8"))
    log("=" * 60)
    log("训练实验：%s" % a.exp)
    log("训练清单：%d 条" % n)
    log("工作目录：%s" % exp_dir)
    log("=" * 60)

    common_env = {
        "inp_text": TRAIN_LIST,
        "inp_wav_dir": SEGDIR,
        "exp_name": a.exp,
        "opt_dir": exp_dir,
        "i_part": 0,
        "all_parts": 1,
        "is_half": "True",
        "version": "v2",
        "bert_pretrained_dir": os.path.join(PM, "chinese-roberta-wwm-ext-large"),
        "cnhubert_base_dir": os.path.join(PM, "chinese-hubert-base"),
        "pretrained_s2G": os.path.join(V2, "s2G2333k.pth"),
        "s2config_path": os.path.join(GSP, "configs", "s2.json"),
    }

    if not a.skip_prepare:
        # ① 文本 → 音素
        set_status("训练 1/5 文本预处理", 0, 1, "日语文本转音素")
        run([PY, os.path.join(GSP, "prepare_datasets", "1-get-text.py")],
            common_env, tag="1-get-text")

        # ② hubert 特征 + 32k 重采样（3-get-semantic 依赖它的产物，必须先跑完）
        set_status("训练 2/5 抽取音频特征", 0, 1, "HuBERT + 重采样 32k")
        run([PY, os.path.join(GSP, "prepare_datasets", "2-get-hubert-wav32k.py")],
            common_env, tag="2-get-hubert")
        n_wav = len([f for f in os.listdir(os.path.join(exp_dir, "5-wav32k"))
                     if f.endswith(".wav")]) if os.path.isdir(os.path.join(exp_dir, "5-wav32k")) else 0
        log("  5-wav32k 产出 %d 个（应为 %d）" % (n_wav, n))
        if n_wav < n * 0.9:
            raise RuntimeError("特征提取只完成 %d/%d，先别训" % (n_wav, n))

        # ③ 语义 token
        set_status("训练 3/5 抽语义 token", 0, 1, "从音频抽 semantic")
        run([PY, os.path.join(GSP, "prepare_datasets", "3-get-semantic.py")],
            common_env, tag="3-get-semantic")

    # 分片文件改名：xxx-0.txt → xxx.txt（训练脚本只认不带后缀的）
    for base in ("2-name2text", "6-name2semantic"):
        for ext in (".txt", ".tsv"):
            src = os.path.join(exp_dir, "%s-0%s" % (base, ext))
            dst = os.path.join(exp_dir, "%s%s" % (base, ext))
            if os.path.exists(src):
                if os.path.exists(dst):
                    os.remove(dst)
                os.replace(src, dst)
                nline = sum(1 for _ in open(dst, encoding="utf-8", errors="replace"))
                log("  %s 共 %d 行" % (os.path.basename(dst), nline))
                if nline == 0:
                    raise RuntimeError("%s 是空的，预处理没成功" % dst)

    # ④ SoVITS
    cfg = json.load(open(os.path.join(GSP, "configs", "s2.json"), encoding="utf-8"))
    cfg["train"]["epochs"] = a.epochs_s2
    cfg["train"]["batch_size"] = a.batch
    cfg["train"]["text_low_lr_rate"] = 0.4
    cfg["train"]["pretrained_s2G"] = os.path.join(V2, "s2G2333k.pth")
    cfg["train"]["pretrained_s2D"] = os.path.join(V2, "s2D2333k.pth")
    cfg["train"]["if_save_latest"] = True
    cfg["train"]["if_save_every_weights"] = True
    cfg["train"]["save_every_epoch"] = max(1, a.epochs_s2 // 2)
    cfg["train"]["gpu_numbers"] = "0"
    cfg["train"]["fp16_run"] = bool(a.fp16)
    cfg["train"]["grad_ckpt"] = False
    cfg["train"]["lora_rank"] = 32
    cfg["model"]["version"] = "v2"
    cfg["data"]["exp_dir"] = cfg["s2_ckpt_dir"] = exp_dir
    cfg["save_weight_dir"] = os.path.join(GS, "SoVITS_weights_v2")
    cfg["name"] = a.exp
    cfg["version"] = "v2"
    os.makedirs(cfg["save_weight_dir"], exist_ok=True)
    tmp_s2 = os.path.join(exp_dir, "tmp_s2.json")
    json.dump(cfg, open(tmp_s2, "w", encoding="utf-8"), ensure_ascii=False)

    set_status("训练 4/5 SoVITS", 0, a.epochs_s2, "共 %d 轮" % a.epochs_s2)
    run([PY, os.path.join(GSP, "s2_train.py"), "-c", tmp_s2], tag="s2_train")

    # ⑤ GPT
    import yaml
    s1cfg_path = os.path.join(GSP, "configs", "s1longer-v2.yaml")
    data = yaml.safe_load(open(s1cfg_path, encoding="utf-8"))
    data["train"]["epochs"] = a.epochs_s1
    data["train"]["batch_size"] = a.batch
    data["train"]["num_workers"] = 0      # 沙箱禁止命名管道，多进程 DataLoader 会失败
    data["train_semantic_path"] = os.path.join(exp_dir, "6-name2semantic.tsv")
    data["train_phoneme_path"] = os.path.join(exp_dir, "2-name2text.txt")
    data["output_dir"] = os.path.join(exp_dir, "logs_s1")
    os.makedirs(data["output_dir"], exist_ok=True)
    tmp_s1 = os.path.join(exp_dir, "tmp_s1.yaml")
    yaml.safe_dump(data, open(tmp_s1, "w", encoding="utf-8"), allow_unicode=True, sort_keys=False)

    set_status("训练 5/5 GPT", 0, a.epochs_s1, "共 %d 轮" % a.epochs_s1)
    run([PY, os.path.join(GSP, "s1_train.py"), "-c", tmp_s1], tag="s1_train")

    set_status("训练完成", 1, 1, "看 训练/%s" % a.exp)
    log("")
    log("=" * 60)
    log("训练结束。产物：")
    for d, _, fs in os.walk(exp_dir):
        for f in fs:
            if f.endswith((".ckpt", ".pth")):
                log("  %s" % os.path.join(d, f))
    for d in (os.path.join(GS, "SoVITS_weights_v2"), os.path.join(GS, "GPT_weights_v2")):
        if os.path.isdir(d):
            for f in os.listdir(d):
                log("  %s" % os.path.join(d, f))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        import traceback
        traceback.print_exc()
        set_status("训练失败", 0, 1, "看 训练日志.txt")
        sys.exit(1)
