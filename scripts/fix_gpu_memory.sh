#!/bin/bash
# GPU显存碎片化问题快速修复脚本

set -e

echo "=========================================="
echo "  SenseVoice GPU 显存碎片化修复工具"
echo "=========================================="
echo ""

# 检查是否在正确的目录
if [ ! -f "main.py" ]; then
    echo "错误: 请在 SenseVoice 项目根目录下运行此脚本"
    exit 1
fi

# 显示当前GPU状态
echo "1. 检查 GPU 状态..."
if command -v nvidia-smi &> /dev/null; then
    nvidia-smi --query-gpu=index,name,memory.total,memory.used,memory.free --format=csv,noheader,nounits | \
    awk -F', ' '{printf "  GPU %s (%s): 总显存 %.2fGB, 已用 %.2fGB, 空闲 %.2fGB\n", $1, $2, $3/1024, $4/1024, $5/1024}'
    echo ""
else
    echo "  警告: nvidia-smi 未找到，跳过GPU检查"
    echo ""
fi

# 设置环境变量
echo "2. 设置环境变量..."
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
echo "  ✓ PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True"
echo ""

# 可选：选择特定GPU
echo "3. GPU 设备选择"
read -p "是否要指定特定GPU？(y/N): " use_specific_gpu
if [[ "$use_specific_gpu" =~ ^[Yy]$ ]]; then
    read -p "请输入GPU编号 (例如: 4): " gpu_id
    export SENSEVOICE_DEVICE=cuda:${gpu_id}
    echo "  ✓ 将使用 GPU ${gpu_id}"
else
    export SENSEVOICE_DEVICE=auto
    echo "  ✓ 将自动选择显存最充足的GPU"
fi
echo ""

# 清理Python缓存
echo "4. 清理缓存..."
if command -v python3 &> /dev/null; then
    python3 << EOF
import gc
try:
    import torch
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        print("  ✓ GPU缓存已清理")
    else:
        print("  ⚠ CUDA不可用，跳过GPU缓存清理")
except Exception as e:
    print(f"  ⚠ 清理缓存时出错: {e}")
gc.collect()
EOF
else
    echo "  ⚠ Python3 未找到，跳过缓存清理"
fi
echo ""

# 显示将要使用的配置
echo "5. 当前配置:"
echo "  PYTORCH_CUDA_ALLOC_CONF: ${PYTORCH_CUDA_ALLOC_CONF}"
echo "  SENSEVOICE_DEVICE: ${SENSEVOICE_DEVICE}"
echo ""

# 询问是否启动服务
read -p "是否现在启动 SenseVoice 服务？(Y/n): " start_service
if [[ ! "$start_service" =~ ^[Nn]$ ]]; then
    echo ""
    echo "=========================================="
    echo "  正在启动 SenseVoice 服务..."
    echo "=========================================="
    echo ""
    
    # 检查是否有旧进程
    old_pid=$(pgrep -f "python.*main.py" || true)
    if [ -n "$old_pid" ]; then
        echo "发现旧的服务进程 (PID: $old_pid)"
        read -p "是否停止旧进程？(Y/n): " kill_old
        if [[ ! "$kill_old" =~ ^[Nn]$ ]]; then
            kill $old_pid
            sleep 2
            echo "  ✓ 旧进程已停止"
        fi
    fi
    
    # 启动服务
    python3 main.py
else
    echo ""
    echo "=========================================="
    echo "  配置完成！"
    echo "=========================================="
    echo ""
    echo "要启动服务，请运行:"
    echo "  export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True"
    echo "  export SENSEVOICE_DEVICE=${SENSEVOICE_DEVICE}"
    echo "  python3 main.py"
    echo ""
fi

