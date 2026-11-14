# -*- coding: utf-8 -*-
"""
把云上训练要用的东西一次准备好：
  1. dataset.zip    —— 22 张图 + caption，解压即是 sd-scripts 要的结构
  2. setup.sh       —— 云上装环境
  3. train.sh       —— 云上开训
  4. 云上说明.txt    —— 贴在机器上照着看
注意：.sh 必须用 LF 换行，Windows 的 CRLF 会让 bash 报 $'\\r' 错误。
"""
import os
import zipfile

BASE = r"D:\HarnessAI\work\生图环境"
OUT = os.path.join(BASE, "云上训练包")
os.makedirs(OUT, exist_ok=True)

# ---------------------------------------------------------------- 1. 打包数据集
zip_path = os.path.join(OUT, "dataset.zip")
src = os.path.join(BASE, "dataset", "1_ryou")
# 只打包图和 caption；.npz 是本地 --cache_latents 留下的潜变量缓存，
# 云上的 sd-scripts 版本不一定认，带过去反而会报格式错
packed = [f for f in sorted(os.listdir(src)) if f.lower().endswith((".png", ".txt"))]
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
    for f in packed:
        z.write(os.path.join(src, f), "dataset/1_ryou/" + f)
print("[1] dataset.zip 打好：%d 个文件（%d 张图 + %d 条 caption），%.1f MB"
      % (len(packed), len([f for f in packed if f.endswith('.png')]),
         len([f for f in packed if f.endswith('.txt')]),
         os.path.getsize(zip_path) / 1e6))

# ---------------------------------------------------------------- 2. setup.sh
SETUP = r"""#!/bin/bash
# ---- 一键装环境（约 8-15 分钟，看网速）----
set -e

cd /root

echo "==============================================="
echo " 第1步：下 sd-scripts 训练代码"
echo "==============================================="
if [ ! -d /root/sd-scripts ]; then
  git clone https://github.com/kohya-ss/sd-scripts.git
else
  echo "sd-scripts 已存在，跳过"
fi

echo "==============================================="
echo " 第2步：装 Python 依赖"
echo "==============================================="
cd /root/sd-scripts
pip install -r requirements.txt
pip install torchvision --no-deps
pip install -e . --no-deps
cd /root

echo "==============================================="
echo " 第3步：下底模 waiIllustrious（6.5 GB）"
echo "==============================================="
mkdir -p /root/autodl-tmp/models
if [ ! -f /root/autodl-tmp/models/waiIllustrious.safetensors ]; then
  wget -c -O /root/autodl-tmp/models/waiIllustrious.safetensors \
    https://hf-mirror.com/LyliaEngine/waiIllustriousSDXL_v170/resolve/main/waiIllustriousSDXL_v170.safetensors
else
  echo "底模已存在，跳过"
fi

echo "==============================================="
echo " 检查"
echo "==============================================="
ls -lh /root/autodl-tmp/models/
python -c "import torch; print('torch', torch.__version__, '| cuda', torch.cuda.is_available())"
python -c "import diffusers, transformers; print('diffusers', diffusers.__version__)"

echo ""
echo ">>> 环境好了，接着跑 bash /root/train.sh"
"""

# ---------------------------------------------------------------- 3. train.sh
TRAIN = r"""#!/bin/bash
# ---- 开训（4090 上约 8-12 分钟）----
set -e
cd /root/sd-scripts

if [ ! -d /root/autodl-tmp/dataset/1_ryou ]; then
  echo "!!! 找不到 /root/autodl-tmp/dataset/1_ryou"
  echo "!!! 先解压训练集：cd /root/autodl-tmp && unzip -o dataset.zip"
  exit 1
fi

mkdir -p /root/autodl-tmp/output

accelerate launch --num_cpu_threads_per_process 1 sdxl_train_network.py \
  --pretrained_model_name_or_path /root/autodl-tmp/models/waiIllustrious.safetensors \
  --train_data_dir /root/autodl-tmp/dataset \
  --output_dir /root/autodl-tmp/output \
  --output_name ryou_v2_1024 \
  --resolution 1024,1024 \
  --network_module networks.lora \
  --network_dim 32 \
  --network_alpha 16 \
  --network_train_unet_only \
  --learning_rate 1e-4 \
  --unet_lr 1e-4 \
  --optimizer_type AdamW \
  --gradient_checkpointing \
  --sdpa \
  --mixed_precision fp16 \
  --save_precision fp16 \
  --cache_latents \
  --cache_text_encoder_outputs \
  --max_train_epochs 15 \
  --save_every_n_epochs 3 \
  --train_batch_size 1 \
  --keep_tokens 6 \
  --min_snr_gamma 5 \
  --noise_offset 0.0357 \
  --max_data_loader_n_workers 2 \
  --seed 42

echo ""
echo "==============================================="
echo " 训完了，权重在 /root/output/"
echo "==============================================="
ls -lh /root/output/
echo ""
echo ">>> 下一步：把 /root/output 里的 safetensors 下载回本地"
"""

# ---------------------------------------------------------------- 4. 云上说明
README = """云上训练 · 操作顺序
==================================================

1) 解压训练集
   cd /root && unzip -o dataset.zip

2) 装环境（等它跑完，约 8-15 分钟）
   bash /root/setup.sh

3) 开训（约 8-12 分钟）
   bash /root/train.sh

4) 下结果
   /root/output/ 里的 ryou_v2_1024.safetensors 就是成品
   还有 -000003 / -000006 / -000009 / -000012 几个中间版本

5) 释放机器（不是关机！）

--------------------------------------------------
出问题了看这里
--------------------------------------------------
* git clone 卡住      -> 关掉，用平台自带的学术加速，或改用 gitee 镜像
* wget 太慢          -> 下到一半的别删，重跑同一条命令会接着下
* CUDA out of memory -> 把 train.sh 里 --train_batch_size 1 保持不变，
                         再确认没别的程序占显存
* 找不到 dataset      -> 先做第 1 步
"""

def w(name, text):
    p = os.path.join(OUT, name)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print("[2] %s  %.1f KB" % (name, os.path.getsize(p) / 1024))

w("setup.sh", SETUP)
w("train.sh", TRAIN)
w("云上说明.txt", README)

print("\n全部在：", OUT)
for f in os.listdir(OUT):
    print("  ", f, "%.1f MB" % (os.path.getsize(os.path.join(OUT, f)) / 1e6))
