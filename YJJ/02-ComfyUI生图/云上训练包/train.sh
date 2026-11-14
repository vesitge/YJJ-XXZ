#!/bin/bash
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
