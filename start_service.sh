#!/bin/bash
# SenseVoice 服务启动脚本

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

LOG_FILE="sensevoice.log"
PID_FILE="sensevoice.pid"

# 检查是否已经在运行
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if ps -p "$OLD_PID" > /dev/null 2>&1; then
        echo "❌ SenseVoice 服务已在运行 (PID: $OLD_PID)"
        echo "如需重启，请先运行: ./stop_service.sh"
        exit 1
    else
        echo "⚠️  发现旧的 PID 文件，清理中..."
        rm -f "$PID_FILE"
    fi
fi

# 设置环境变量
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export SENSEVOICE_DEVICE=auto

echo "=========================================="
echo "  启动 SenseVoice 服务"
echo "=========================================="
echo ""
echo "配置信息:"
echo "  日志文件: $LOG_FILE"
echo "  PID文件: $PID_FILE"
echo "  工作目录: $SCRIPT_DIR"
echo "  PYTORCH_CUDA_ALLOC_CONF: $PYTORCH_CUDA_ALLOC_CONF"
echo "  SENSEVOICE_DEVICE: $SENSEVOICE_DEVICE"
echo ""

# 启动服务
nohup python3 main.py > "$LOG_FILE" 2>&1 &
SERVICE_PID=$!

# 保存 PID
echo "$SERVICE_PID" > "$PID_FILE"

# 等待几秒检查服务是否正常启动
sleep 3

if ps -p "$SERVICE_PID" > /dev/null 2>&1; then
    echo "✅ SenseVoice 服务启动成功!"
    echo "  PID: $SERVICE_PID"
    echo "  端口: 50000"
    echo ""
    echo "常用命令:"
    echo "  查看日志: tail -f $LOG_FILE"
    echo "  停止服务: ./stop_service.sh"
    echo "  重启服务: ./restart_service.sh"
    echo "  查看状态: ./status_service.sh"
    echo ""
else
    echo "❌ 服务启动失败，请查看日志: $LOG_FILE"
    rm -f "$PID_FILE"
    exit 1
fi
