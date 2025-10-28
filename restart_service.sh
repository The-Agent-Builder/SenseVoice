#!/bin/bash
# SenseVoice 服务重启脚本

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "  重启 SenseVoice 服务"
echo "=========================================="
echo ""

# 停止服务
if [ -f "stop_service.sh" ]; then
    ./stop_service.sh
else
    echo "停止旧服务..."
    pkill -f "python3 main.py" || true
    sleep 2
fi

echo ""

# 启动服务
if [ -f "start_service.sh" ]; then
    ./start_service.sh
else
    echo "启动新服务..."
    export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
    export SENSEVOICE_DEVICE=auto
    nohup python3 main.py > sensevoice.log 2>&1 &
    echo "✅ 服务已启动"
fi

