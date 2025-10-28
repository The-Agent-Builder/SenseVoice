#!/bin/bash
# SenseVoice 服务停止脚本

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PID_FILE="sensevoice.pid"

if [ ! -f "$PID_FILE" ]; then
    echo "❌ 服务未运行（未找到 PID 文件）"
    
    # 尝试查找并停止所有相关进程
    PIDS=$(pgrep -f "python3 main.py" || true)
    if [ -n "$PIDS" ]; then
        echo "⚠️  发现运行中的进程，尝试停止..."
        pkill -f "python3 main.py"
        sleep 2
        echo "✅ 已停止相关进程"
    fi
    exit 0
fi

PID=$(cat "$PID_FILE")

if ! ps -p "$PID" > /dev/null 2>&1; then
    echo "⚠️  进程已不存在 (PID: $PID)"
    rm -f "$PID_FILE"
    exit 0
fi

echo "正在停止 SenseVoice 服务 (PID: $PID)..."
kill "$PID"

# 等待进程结束
for i in {1..10}; do
    if ! ps -p "$PID" > /dev/null 2>&1; then
        echo "✅ 服务已停止"
        rm -f "$PID_FILE"
        exit 0
    fi
    sleep 1
done

# 如果还没停止，强制终止
echo "⚠️  正常停止失败，强制终止..."
kill -9 "$PID" 2>/dev/null || true
rm -f "$PID_FILE"
echo "✅ 服务已强制停止"

