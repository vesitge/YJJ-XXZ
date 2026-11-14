#!/bin/bash
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
